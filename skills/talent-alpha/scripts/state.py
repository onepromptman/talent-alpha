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
nightly runs.

SOURCE WINDOWS. `dedupe` is also where the scan window is enforced: an event
whose `published_at` is more than WINDOW_DAYS old on the run date (--as-of,
default today in UTC) is dropped and counted, never handed to a model. Ages
are whole calendar days from the event's UTC date to the run date. The
window is what keeps the 30-day prune safe: an id pruned from this file
belongs to an event long outside its window, so a later pull that returns
the same old article cannot bring it back as new. A web search can return
old articles; the n8n feeds are windowed by their own queries.

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
the second run's card omits the first run's events. See "State and scheduling" in
docs/how-it-works.md.
"""

import argparse
import datetime
import json
import os
import tempfile

import runlog

log = runlog.get_logger("talent-alpha.state")

SCHEMA_VERSION = 1

# Days an event stays reachable after publication, by event_type. The card's
# window note and the dedupe drop both read this one table.
WINDOW_DAYS = {"layoff": 3, "shutdown": 3, "funding_distress": 7}
# Seen events older than this are pruned from state on record.
MAX_AGE_DAYS = 30


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def parse_as_of(value):
    """argparse type for --as-of: the run date as YYYY-MM-DD."""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--as-of must be a date as YYYY-MM-DD, got {value!r}"
        ) from None


def parse_timestamp(value):
    """Use UTC consistently, including dates and timestamps without an offset."""
    if not isinstance(value, str):
        raise TypeError("published_at must be an ISO date or timestamp")
    dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def age_in_days(published_at, as_of):
    """Whole calendar days from the event's UTC date to the run date.

    Negative for an event dated after the run date; None if the date cannot be
    parsed (the trust-boundary join reports that event, so dedupe passes it on)."""
    try:
        published = parse_timestamp(published_at)
    except (ValueError, TypeError):
        return None
    return (as_of - published.date()).days


def load_state(path):
    if not os.path.exists(path):
        return {
            "schema_version": SCHEMA_VERSION,
            "seen_events": {},
            "last_run_at": None,
        }
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
    as_of = args.as_of or utc_today()
    fresh = []
    already = 0
    outside = []
    batch_ids = set()
    for e in events:
        event_id = e.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("every raw event needs a nonempty event_id")
        window = WINDOW_DAYS.get(e.get("event_type"))
        age = age_in_days(e.get("published_at"), as_of)
        if event_id in seen or event_id in batch_ids:
            already += 1
        elif window is not None and age is not None and age > window:
            outside.append(
                f"{event_id} ({age}d old, {e['event_type']} window {window}d)"
            )
        else:
            fresh.append(e)
        batch_ids.add(event_id)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(fresh, f, indent=2)
        f.write("\n")
    print(
        f"dedupe: {len(events)} pulled, {already} already seen, {len(outside)} outside "
        f"the source window as of {as_of.isoformat()}, {len(fresh)} new -> {args.out}"
        + "".join(f"\n  outside window: {item}" for item in outside)
    )
    log.info(
        "dedupe: %d pulled, %d already seen, %d outside window, %d new",
        len(events),
        already,
        len(outside),
        len(fresh),
    )


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
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=args.max_age_days
    )
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
    log.info(
        "record: %d marked seen, %d pruned, %d in state",
        len(candidates),
        pruned,
        len(seen),
    )
    print(
        f"record: {len(candidates)} candidates marked seen, {pruned} pruned "
        f"(older than {args.max_age_days}d), {len(seen)} total in state -> {args.state}"
    )


def cmd_show(args):
    state = load_state(args.state)
    seen = state["seen_events"]
    print(f"state file: {args.state}")
    print(f"schema_version: {state['schema_version']}")
    print(f"last_run_at: {state['last_run_at']}")
    print(f"seen_events: {len(seen)}")
    if args.verbose:
        for event_id, entry in sorted(
            seen.items(), key=lambda kv: kv[1].get("first_seen_at", "")
        ):
            print(
                f"  {entry.get('first_seen_at', '?')}  {event_id}  {entry.get('company', '')}"
            )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser(
        "dedupe", help="Filter raw pulled events against the state file."
    )
    d.add_argument(
        "--events",
        required=True,
        help="Path to raw_events.json (array of normalized events).",
    )
    d.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    d.add_argument(
        "--out",
        required=True,
        help="Where to write the filtered (new-only) events array.",
    )
    d.add_argument(
        "--as-of",
        type=parse_as_of,
        default=None,
        help="Run date (YYYY-MM-DD) that event ages count to; default today (UTC). "
        "Events older than their source window on this date are dropped.",
    )
    d.set_defaults(func=cmd_dedupe)

    r = sub.add_parser(
        "record",
        help="Mark this run's reconciled candidates as seen; prune old entries.",
    )
    r.add_argument(
        "--candidates",
        required=True,
        help="Path to reconciled content JSON (or a bare array of candidates).",
    )
    r.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    r.add_argument(
        "--max-age-days",
        type=int,
        default=MAX_AGE_DAYS,
        help=f"Prune entries older than this many days (default {MAX_AGE_DAYS}).",
    )
    r.set_defaults(func=cmd_record)

    s = sub.add_parser("show", help="Print a summary of the current state file.")
    s.add_argument("--state", required=True, help="Path to talent-alpha-state.json.")
    s.add_argument("--verbose", action="store_true", help="List every seen event id.")
    s.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    runlog.setup()
    log.debug("state.py %s", args.cmd)
    args.func(args)
    return 0


if __name__ == "__main__":
    runlog.run(main)
