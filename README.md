<div align="center">

# Talent Alpha

**A scanner and two independent judges turn layoffs and funding-distress news into one ranked card.** Every run: who just became reachable, why now, your outreach hook, and your concrete edge.

[![Version](https://img.shields.io/badge/version-1.3.0-black)](CHANGELOG.md)
[![Runs in](https://img.shields.io/badge/runs%20in-Claude%20Code%20%7C%20Cowork%20%7C%20n8n-orange)](#where-it-runs)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

by [OnePromptMan](https://github.com/onepromptman) · © 2026

</div>

> **Built from source.** This repository is generated from the `talent-alpha` module of
> talentai, the OnePromptMan recruiting system (onepromptman/talentai), by its publish
> script `tools/publish/talent-alpha.sh` (readable once talentai is public). This copy is
> module version 1.3.0, module tree `183619c894537539da9ccea3d819fc78161fa5f3`. Changes are made in the module and
> published here, so a change made only here is replaced by the next publish. Once this
> repository is public, issues and pull requests here are welcome and are carried back
> to the module.
>
> **Upgrading from the earlier talent-alpha workflow?** The n8n dedupe Data Table is
> now `talent_alpha_events_seen` (it was `r04_events_seen`): rename yours, keeping its
> rows, before the next scheduled run. The steps are in
> [docs/setup.md](docs/setup.md#upgrading-an-existing-install). The four public forks
> of the earlier repository are detached copies of its single first commit and do
> not receive these updates.


---

> ### ⚠️ Where it runs
>
> Talent Alpha ships two ways, both from this one repository: a **standalone
> n8n workflow** (the original, scheduled, emails you a card overnight) and
> **this Cowork / Claude Code plugin** (the identical pull-scan-judge-render
> pipeline, run on demand inside a conversation).
>
> The plugin runs in **Claude Code** and **Cowork**. It does **not** run in
> the regular Claude chat window, which cannot spawn the scanner and judge
> subagents; `run talent alpha` will do nothing there.
>
> Native scheduled tasks on the Claude Code / Cowork side are **unconfirmed**
> for this build. If you want an unattended nightly run today, use the n8n
> workflow; see [State and scheduling](#state-and-scheduling-read-this-before-you-rely-on-it).

---

## Install (Cowork / Claude Code plugin)

**Option A: marketplace (recommended, two lines):**

```
/plugin marketplace add onepromptman/talent-alpha
/plugin install talent-alpha@talent-alpha
```

**Option B: manual.** Clone or download this repository and add the plugin's
folder (the one that holds `.claude-plugin/plugin.json`) as a plugin in Claude
Code or Cowork.

See [`docs/INSTALL.md`](docs/INSTALL.md) for the full walkthrough, including
what `talent-alpha-setup` writes on first run and how this path relates to
the n8n one below.

Want the standalone n8n workflow instead (or as well)? See
[`docs/setup.md`](docs/setup.md); importing
[`n8n/talent-alpha.workflow.json`](n8n/talent-alpha.workflow.json) is the
short version, and `talent-alpha-setup` writes a ready-to-paste `Config`
node value for it either way.

## First run

You have never used this plugin before. Here is exactly what happens.

**Type this once:**

```
set up talent alpha
```

**It will ask you**, one plain question at a time, never a form: your
company name (and optionally your website, just to look up things like
where you're based); a short paragraph on what makes your company worth
someone moving for, in concrete terms (pay, equity, remote policy, anything
real); the job you're trying to fill and which industries to watch for
layoffs and funding trouble; and how many people to show on each card
(a sensible default is already picked, so you can just say "default").
Every question can be skipped, and answering "not sure" is always fine.

**If you have already set up another kit from this marketplace** in the
same folder, it already knows your company name and a few other basics, so
it skips straight to Talent Alpha's own questions. That run is closer to a
minute.

**What you get back**: a short confirmation message, and two small files
saved quietly in your working folder: `onepromptman-profile.md` (the shared
profile every kit in this marketplace reads, plain text, safe to open, never
something you need to edit by hand) and `talent-alpha-n8n-config.json` (only
useful if you later want the scheduled n8n version; ignore it otherwise).
Nothing is sent anywhere, and no card is produced yet.

**Total time**: about 5 minutes for a first, full setup.

Once that is done, run an actual scan whenever you want one:

```
run talent alpha
```

See "You say / you get" below for what that produces and roughly how long
it takes.

## What this will not do

Talent Alpha drafts a card. It never acts on it. This plugin will not:

- message, email, or contact anyone on your behalf
- publish or post the card anywhere automatically
- change, revoke, or touch any account, access, or system permission (it
  has no such access to begin with, and nothing here asks you for any)
- decide who you should reach out to; it ranks and explains, you choose

A person reads every card and decides what happens next. See "Is it safe to
install?" below for what the plugin can and cannot touch on your machine.

## You say / you get

| You say | You get |
| --- | --- |
| `run talent alpha` | A pull of both feeds, a scanner shortlist, an Advocate/Skeptic judge pass, and one rendered card, a few minutes |
| `talent alpha setup` | The guided profile conversation, about 5 minutes |
| `run talent alpha` (a second time, later) | Only new-since-last-run events; the state file remembers what it already scanned |

## What it makes

| # | Output | Produced by | Sample |
| --- | --- | --- | --- |
| 01 | Overnight signal card (self-contained HTML) | `advocate` + `skeptic`, reconciled and rendered deterministically | [view](samples/01_Overnight_Card_SAMPLE.html) |

**`scanner`** (the broad-recall shortlist) runs automatically before the
judges. You never invoke it, `advocate`, or `skeptic` directly; they are
subagents the `talent-alpha` skill spawns for you.

Every event on the card traces to one of three named tiers: **Filed** (an
official WARN Act filing), **Reported** (dated news coverage), or
**Company-stated** (a leverage detail from your own saved profile). Nothing
is invented: an id a judge could not verify against the trusted event batch
is silently dropped before it can reach the card, and a candidate with no
applicable leverage gets an honestly empty `edge` line, never filler prose.

### Sample

<p align="center">
See [`samples/01_Overnight_Card_SAMPLE.html`](samples/01_Overnight_Card_SAMPLE.html) for a full rendered card. Open it in any browser.
</p>

> The linked file is the real rendered output on fictional companies; open it
> in a browser for the live interactive version (the hex fit-diagrams draw
> themselves). GitHub shows `.html` as source, so use the raw/download view
> or clone the repo.

## How it works

```
two feeds (WARN + funding-distress) ──▶ dedupe against local state
                                              │
                                              ▼
                                       scanner (sonnet)
                                              │
                                trust-boundary join (deterministic)
                                              │
                        ┌─────────────────────┴─────────────────────┐
                        ▼                                           ▼
                    advocate (sonnet)                          skeptic (sonnet)
                    argues FOR                                 argues AGAINST
                        └─────────────────────┬─────────────────────┘
                                              ▼
                        critic (opus) ──▶ repair patch, ≤2 laps
                                              ▼
                          reconcile (tier blend, deterministic)
                                              │
                                              ▼
                        render + verify (deterministic) ──▶ one HTML card
                                              │
                                              ▼
                                  record state (mark seen)
```

This plugin's in-session path runs `scanner` on the executor (Sonnet) tier,
same as `advocate` and `skeptic`, with `critic` (Opus) judging all three on
the verifier tier before reconcile (the model that made a verdict never
checks it). The standalone n8n workflow is a separate deployment and may
still route its scanner step to a cheaper model where its own cost profile
calls for it; that choice is n8n-side and does not change this plugin's tiers.

The Advocate and Skeptic never see each other's verdict before both return;
a deterministic script blends the two tiers by rank, never either judge.
Freshness is a sort tiebreak and a display label, not a tier penalty: an
hours-old signal simply sorts ahead of a stale one at the same tier.

**Timing:** a cold run (nothing in the state file yet) is a few minutes,
dominated by the two WebSearch pulls and the parallel judge pass. A warm
run (most events already seen) is faster in proportion to how few new events
there are to judge.

## Data and connectors

Works with **zero paid keys** in-session: both feeds run on `WebSearch`.
That is a real cost reduction versus the n8n workflow, not a degraded
substitute, for the funding-distress category. For WARN layoffs specifically,
it is a genuine tradeoff: see [CONNECTORS.md](CONNECTORS.md) for exactly
what is traded away.

The n8n workflow can use a free WARN Firehose key (25 calls/day) and an
optional paid Perplexity key for the authoritative feed versions; see
[`docs/setup.md`](docs/setup.md).

Full connector-by-connector detail -- what each tier requires, the eval
path's zero-web-calls guarantee, and the WARN Filed-versus-Reported tradeoff
stated plainly -- is in [CONNECTORS.md](CONNECTORS.md).

## State and scheduling (read this before you rely on it)

The n8n workflow dedupes against a Data Table (`talent_alpha_events_seen`) that n8n
persists for you. This plugin's in-session equivalent is a flat JSON file,
`talent-alpha-state.json` by default, written next to your shared
`onepromptman-profile.md` and read again at the start of every run
(`scripts/state.py`; full design in its docstring). Its exact path is
recorded in the profile, so it can be relocated without touching any skill.

**This has been tested across separate on-demand invocations in the same
working folder, and works as designed: a second run correctly skips events
the first run already saw.** What is **not yet verified** is whether the
working folder, and therefore this file, actually survives between two
separate firings of a native SCHEDULED task on this platform, since that
capability itself is unconfirmed for this build. If you attach `talent alpha`
to a schedule, test it: run it twice on different days and confirm the
second card omits the first run's events before trusting it unattended. The
n8n workflow's Data Table has no such open question.

## Is it safe to install?

The plugin is plain text: skills, agent prompts, and three small Python
scripts that only run inside Claude's own sandbox. No executables, nothing
installs on your computer beyond what the sandbox already provides, nothing
reports back to anyone. The whole source is in this repository; read it.

This product surfaces signals about real layoffs and companies in real
distress. Keep the framing respectful: the card names companies and
functions, never individuals. See "What this will not do" above for exactly
where this plugin's involvement stops.

## Repository layout

```
.claude-plugin/     plugin.json + marketplace.json
agents/             scanner, advocate, skeptic, critic
skills/             talent-alpha (orchestrator) + talent-alpha-setup
n8n/                the standalone workflow, its demo variant, and reference prompt copies
samples/            one worked-example card
docs/               plugin install guide + n8n click-by-click setup
```

## Docs

- [Install guide](docs/INSTALL.md): the Cowork / Claude Code plugin path
- [n8n setup guide](docs/setup.md): click-by-click, no coding
- [Connectors](CONNECTORS.md)
- [Changelog](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).

Every card is a draft for human review. Nothing this plugin produces should
be sent to anyone automatically; the decision to reach out, and the words
used, remain the recruiter's.

---

Questions or bugs? Open an [Issue](../../issues).
