#!/usr/bin/env python3
"""Talent Alpha dedupe state file: read-then-write, once per run.

DESIGN NOTE (read this before changing the shape below).

The n8n version of this workflow dedupes against a Data Table
(`talent_alpha_events_seen`, one row per seen `event_id`) that n8n persists for you
between scheduled runs. Running the same pipeline on demand, in a Claude
Code / Cowork session, has no equivalent managed store: the working folder is
the only thing that can plausibly survive between invocations. This script is
that equivalent, as a single flat JSON file:

    talent-alpha-state.json          (working-folder root, next to the
                                       shared onepromptman-profile.md)

The default filename above is the default only: the actual path this run
should use is recorded in the profile's `## Kit: talent-alpha` block as
`state_file`, so the talent-alpha skill passes it explicitly on every call
below rather than hardcoding it here.

Shape:

    {
      "schema_version": 1,
      "seen_events": {
        "<event_id>": {"first_seen_at": "<ISO timestamp>", "company": "<debug label>"}
      },
      "last_run_at": "<ISO timestamp>"
    }

`company` on each entry is a human-debugging aid only (so a person can skim
the file and recognize what it is remembering); nothing in the pipeline reads
it back. Entries older than --max-age-days (default 30) are dropped on every
`record` call, so the file does not grow without bound across months of
nightly runs; 30 days is comfortably past both source windows (3 days for
WARN, 7 for funding-distress), so nothing currently reachable by a fresh pull
can still be sitting just past the prune line.

CONTRACT WITH THE SKILL: call `dedupe` once, near the top of every run, before
spending any model call on an event. Call `record` once, near the end of
every run, over every reconciled candidate (shown AND held; a held item was
still scanned and judged, so it must not be re-scanned next run). Never call
`record` before the run has actually produced reconciled candidates: a
crashed run should not mark events as seen that were never actually judged.

UNVERIFIED: whether the working folder (and therefore this file) actually
persists between two separate invocations of a native scheduled task is not
something this plugin has been able to confirm on this platform. Test it
before relying on it: run the pipeline twice on different days and confirm
the second run's card omits the first run's events. See the README's
"State and scheduling" section.
"""
import argparse
import datetime
import json
import os
import sys
import tempfile

SCHEMA_VERSION = 1


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path):
    if not os.path.exists(path):
        return {"schema_version": SCHEMA_VERSION, "seen_events": {}, "last_run_at": None}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("seen_events", {})
    data.setdefault("last_run_at", None)
    return data


def write_state_atomic(path, data):
    """Write via a temp file + rename so a crash mid-write cannot corrupt the
    existing state file (the read-then-write cycle this script implements is
    the whole dedupe memory; a half-written file is worse than a stale one)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".talent-alpha-state-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def cmd_dedupe(args):
    with open(args.events, "r", encoding="utf-8") as f:
        events = json.load(f)
    state = load_state(args.state)
    seen = state["seen_events"]
    fresh = [e for e in events if e.get("event_id") not in seen]
    skipped = len(events) - len(fresh)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(fresh, f, indent=2)
        f.write("\n")
    print(f"dedupe: {len(events)} pulled, {skipped} already seen, {len(fresh)} new -> {args.out}")


def cmd_record(args):
    with open(args.candidates, "r", encoding="utf-8") as f:
        content = json.load(f)
    candidates = content["candidates"] if isinstance(content, dict) else content

    state = load_state(args.state)
    seen = state["seen_events"]
    stamp = now_iso()

    for c in candidates:
        event_id = c.get("id") or c.get("event_id")
        if not event_id:
            continue
        if event_id not in seen:
            seen[event_id] = {"first_seen_at": stamp, "company": c.get("company", "")}

    # Prune anything older than max_age_days so the file does not grow
    # without bound across months of nightly runs.
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.max_age_days)
    pruned = 0
    for event_id in list(seen.keys()):
        try:
            first_seen = datetime.datetime.strptime(
                seen[event_id]["first_seen_at"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
        except (KeyError, ValueError):
            continue
        if first_seen < cutoff:
            del seen[event_id]
            pruned += 1

    state["last_run_at"] = stamp
    write_state_atomic(args.state, state)
    print(f"record: {len(candidates)} candidates marked seen, {pruned} pruned "
          f"(older than {args.max_age_days}d), {len(seen)} total in state -> {args.state}")


def cmd_show(args):
    state = load_state(args.state)
    seen = state["seen_events"]
    print(f"state file: {args.state}")
    print(f"schema_version: {state['schema_version']}")
    print(f"last_run_at: {state['last_run_at']}")
    print(f"seen_events: {len(seen)}")
    if args.verbose:
        for event_id, entry in sorted(seen.items(), key=lambda kv: kv[1].get("first_seen_at", "")):
            print(f"  {entry.get('first_seen_at', '?')}  {event_id}  {entry.get('company', '')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dedupe", help="Filter raw pulled events against the state file.")
    d.add_argument("--events", required=True, help="Path to raw_events.json (array of normalized events).")
    d.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    d.add_argument("--out", required=True, help="Where to write the filtered (new-only) events array.")
    d.set_defaults(func=cmd_dedupe)

    r = sub.add_parser("record", help="Mark this run's reconciled candidates as seen; prune old entries.")
    r.add_argument("--candidates", required=True, help="Path to reconciled content JSON (or a bare array of candidates).")
    r.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    r.add_argument("--max-age-days", type=int, default=30, help="Prune entries older than this many days (default 30).")
    r.set_defaults(func=cmd_record)

    s = sub.add_parser("show", help="Print a summary of the current state file.")
    s.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    s.add_argument("--verbose", action="store_true", help="List every seen event id.")
    s.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
