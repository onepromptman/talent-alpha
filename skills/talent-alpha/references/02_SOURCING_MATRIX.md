# SOURCING MATRIX: TALENT ALPHA

What each category pulls, how, and what it is allowed to claim. Add a new
category by duplicating a row and its fetch/normalize step; every category
must emit the same normalized shape (`references/EVENT_PIPELINE_SCHEMA.md` §1)
so it merges into the same scanner and judge panel unmodified.

## Category 1 of N: WARN Act layoffs and closures

**Retrieval, n8n.** `HTTP Request` (header auth) against
`https://warnfirehose.com/api/records` with `date_from` set to 3 days back and
`limit=100`. Requires a free API key (header `X-API-Key`; get one at
warnfirehose.com/account, 25 calls/day).

**Retrieval, in-session.** Claude Code / Cowork has no tool that can attach a
custom auth header to an outbound request (`WebFetch` takes a URL and a prompt
only), so calling an authenticated API like WARN Firehose is not reliably
available in-session. This plugin uses `WebSearch` instead: search for recent
WARN Act notices in the target industries and states, e.g. "WARN Act notice
filed layoff <industry> <state>" over roughly the last 3 days. This is a real
tradeoff, not a silent downgrade: state it plainly to the user during setup
(see `talent-alpha-setup`'s tools step) and note it again in the README.

**Provenance tier, per path.** The n8n path (official API, header-authenticated)
is **Filed**: highest confidence, an official state filing, always dated,
always employer-attributed. The in-session WebSearch path defaults to
**Reported**: news coverage of a filing is not the filing itself. Upgrade a
WebSearch result to Filed only when the result page IS the government notice
or the state labor department's own filing list, never from news coverage
alone, and never upgrade retroactively just because a story cites a filing
number.

**Normalize.** Company name, city/state, layoff vs. closure classification, and
employees-affected count come straight off the record (n8n) or the search
result (in-session, extracted by the scanner agent from title/snippet). Drop
any row missing a company name, and drop obvious PDF-artifact rows (a company
field that is actually a filename). Assign `event_id = "warn-" + <record id>`
(n8n) or `event_id = "warn-" + hash(url)` (in-session, same full-string hash
as the funding-distress category) so re-runs recognize the same event.

## Category 2 of N: funding distress

**Retrieval, in-session.** `WebSearch` for companies (scope the query to your
target industries; the default profile targets hard-tech/hardware, not general
SaaS) facing layoffs tied to a down round, missed earnings, or restructuring,
reported in roughly the last 7 days. Prefer named single-company stories over
industry roundups or tracker pages.

**Retrieval, n8n.** The bundled workflow uses a Perplexity Search node with a
domain filter (cnbc.com, bloomberg.com, reuters.com, techcrunch.com,
crunchbase.com) and a 7-day recency filter. This costs a paid Perplexity key.
**In-session, WebSearch covers the same need with no paid key.** See
`references/EVENT_PIPELINE_SCHEMA.md` §4 for the exact query shape. This is a
real cost reduction versus the n8n path, not a degraded substitute; note it to
the user during setup.

**Normalize.** Title, URL, and a snippet come off the search result. Compute
`event_id = "fund-" + hash(url)` (a full deterministic hash of the whole URL
string, never a truncated prefix, so two articles sharing a domain never
collide). Drop any result missing a title, URL, or a snippet under 40
characters (too thin to score).

**Provenance tier.** Reported. Single-source until a second search corroborates
it. Never let a Reported item's `why` read as confidently as a Filed one.

## Trust boundary (enforced in `scripts/render.py`, not by the agents)

An agent's output is only ever a shortlist or a verdict; it is never treated as
a source of truth for company facts. Every id the scanner or a judge returns is
checked against the trusted batch it was handed, and any id not present there
is silently dropped before it can reach the card. This is a mechanical check,
not something an agent self-polices, precisely because a model can and does
occasionally invent a plausible-looking id.

## Freshness

There is no hard cutoff that drops an old event outright; freshness is a
**sort tiebreak and a display label**, not a tier penalty, matching the
Advocate/Skeptic scoring below. An event's `event_age_label` (`today`, `1d
ago`, `Nd ago`) is computed from `published_at` at reconcile time. A Skeptic
may still cite genuine staleness as a reason to drop a tier; that is a
judgment call on the specific candidate, not an automatic rule.

## Adding a third category

Duplicate the fetch and normalize steps for the new category (M&A, RTO
mandates, exec departures, security breaches are natural next candidates).
Every new source must emit `company` and `location` so the card never shows a
nameless row, and must declare its provenance tier in this file before the
scanner or judges see it.
