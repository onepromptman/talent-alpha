# Connectors

## How talent-alpha sources signals

Talent Alpha reads two categories of signal and one category of user-stated
fact, and every event on the card carries one of three named tiers:

| Tier | What backs it | Source in this module |
| --- | --- | --- |
| **Filed** | A government WARN Act filing: highest confidence, dated, official, employer-attributed | The n8n path's `WARN Firehose` API call only |
| **Reported** | A dated news or search result about a layoff or funding distress; single-source until corroborated | `WebSearch` (in-session) for both WARN and funding-distress events; `Perplexity Search` (n8n) for funding-distress only -- n8n's WARN category is Filed-only, never Reported |
| **Company-stated** | A fact from your own saved profile (`COMPANY_PROFILE`, the leverage paragraph) | Never independently verified, by design |

`MODULE.yaml` declares these three tiers, but its `Reported` line describes
the funding-distress category only. Placing in-session WARN events at
Reported too is a sourcing-matrix decision, not something `MODULE.yaml`
itself states -- see the tradeoff below and
`skills/talent-alpha/references/02_SOURCING_MATRIX.md` for where that rule
actually lives.

## The known one-way tradeoff: in-session WARN degrades to Reported

The n8n workflow's WARN category calls `https://warnfirehose.com/api/records`
with a header-auth API key (`X-API-Key`) and gets back **Filed**-tier data:
an official state filing, always dated, always employer-attributed.

The in-session plugin path cannot make that same call. Claude Code and
Cowork have no tool that attaches a custom auth header to an outbound
request -- `WebFetch` takes a URL and a prompt only, nothing else -- so an
authenticated call to WARN Firehose is not reliably available in-session.
Talent Alpha's in-session WARN category runs on `WebSearch` instead, and the
result defaults to **Reported**, not Filed: news coverage of a filing is not
the filing itself.

This is a real, one-way tradeoff, not a silent downgrade -- it is named
plainly in the plugin's own setup step (`skills/talent-alpha-setup/SKILL.md`)
and documented in full here. A WebSearch result
is only ever upgraded to Filed when the result page IS the government notice
or the state labor department's own filing list, never from news coverage
alone, and never retroactively just because a later story cites a filing
number. (Full sourcing rules, including the funding-distress category and
freshness handling, are documented at the code level in
`skills/talent-alpha/references/02_SOURCING_MATRIX.md`.)

The funding-distress category has no such gap: both paths (WebSearch
in-session, Perplexity Search in n8n) land at Reported, so there is nothing
in that category to trade away.

## What each path requires

**Plugin (Claude Code / Cowork, in-session):**

- No paid keys and no credentials of any kind. Both categories run on the
  built-in `WebSearch` tool.
- The tradeoff above -- Reported instead of Filed for WARN events -- is the
  cost of that zero-key path.

**n8n (standalone workflow):**

| Credential | Required? | Attach to | What it buys |
| --- | --- | --- | --- |
| Anthropic | required | Haiku Scanner Model, Sonnet Judge Model | the model calls themselves |
| WARN Firehose (header auth, free, 25 calls/day) | required -- the WARN category has no fallback in n8n the way it does in-session | Fetch WARN Notices | Filed-tier WARN data |
| Perplexity | optional | Fetch Funding-Distress Signals | a domain-filtered (cnbc.com, bloomberg.com, reuters.com, techcrunch.com, crunchbase.com), recency-filtered funding-distress feed. Skipping it means deleting the Fetch/Normalize Funding-Distress nodes and running WARN-only -- n8n has no WebSearch-style fallback for this category |
| Gmail | required to receive the emailed card | Email Overnight Digest, Email Error Alert | the nightly delivery itself |
| a Data Table (`talent_alpha_events_seen`) | required | Skip Already-Scanned Events, Record Scanned Events | dedupe memory across runs |

See `docs/setup.md` for the click-by-click credential setup.

## Eval path: no web calls at all

The `card-accuracy` eval (`evals/card-accuracy/prompt.md`) runs against a
frozen, pre-pulled fixture batch -- there is no pull step in an eval run.
Its frontmatter's `allowed_tools` is `[Write, Edit, Bash]`: neither
`WebFetch` nor `WebSearch` is granted. Two graders enforce the same fact
mechanically: `graders/no-webfetch.md` and `graders/no-websearch.md` each
pin their tool's call count at `min: 0, max: 0`. The eval path makes no web
calls, full stop; it cannot exercise either sourcing path above, only the
scan/judge/reconcile/render pipeline downstream of the pull.

## Rule that always holds regardless of connections

Never upgrade a Reported event to Filed except from the primary filing
document itself. A news story that cites a filing number is still Reported.
