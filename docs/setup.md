# Setup - Talent Alpha (n8n)

This integration preview needs an n8n workspace and the accounts below. Complete
[the platform acceptance cases](ACCEPTANCE.md) before scheduling it. Every step here also has a matching sticky note on
the n8n canvas once you import the workflow; this page is the full picture if
you'd rather read it up front.

> **Just want to see it work first?** Import
> `n8n/talent-alpha-demo.workflow.json`, connect an Anthropic credential
> (step 2), and hit **Execute Workflow**. It has sample signals pinned in, so it
> produces a full card with nothing else set up. Come back here when you're ready
> to run it for real.

> **Don't want to run n8n at all?** The same pipeline runs on demand inside
> Claude Code or Cowork: install this plugin and say "run talent alpha." See
> the repository README for that path; this page is only for the standalone
> n8n workflow.

## 1. Import the workflow

n8n -> **Workflows** -> **Import from File** -> `n8n/talent-alpha.workflow.json`.

## 2. Connect your accounts (credentials)

n8n -> **Credentials** -> **New**, then attach each on the matching node(s):

| Credential | Where to get it | Attach to |
|---|---|---|
| **Anthropic** (required) | [console.anthropic.com](https://console.anthropic.com) | **Haiku Scanner Model**, **Sonnet Judge Model** |
| **WARN Firehose** - Header Auth, header name `X-API-Key` | free key at [warnfirehose.com/account](https://warnfirehose.com/account) (25/day) | **Fetch WARN Notices** |
| **Perplexity** (optional) | [perplexity.ai](https://www.perplexity.ai) API settings | **Fetch Funding-Distress Signals** |
| **Gmail** | connect your Google account in n8n | **Email Overnight Digest**, **Email Error Alert** |

Only want WARN layoffs? Set `includeFundingDistress` to `false` in Config. The
funding branch is bypassed without calling Perplexity; no graph editing or
Perplexity credential is needed. Only want funding-distress news? Set
`sourcingCriteria.eventTypes` to `["funding_distress"]` and keep
`includeFundingDistress` true. The WARN branch is bypassed without calling its
API or requiring its credential. At least one event type must remain enabled;
repeated entries do not enable an otherwise disabled source.

## 3. Create one Data Table

n8n -> **Data Tables** -> **New**: name it **`talent_alpha_events_seen`** with a single text
column **`event_id`**. This is the dedupe memory, so you're never pinged about the
same event twice. Then open **Skip Already-Scanned Events** and **Record Scanned
Events** and pick that table from the dropdown (they can't come pre-linked; every
workspace has different internal table IDs).

## 4. Tell it who you're hiring - the **Config** node

Talent Alpha starts from the role, then proposes relevant triggers. A useful
signal is fresh and checkable, overlaps the work you need, and fits where you can
hire. A company in distress alone is not enough. Read the
[targeting playbook](../skills/talent-alpha/references/03_TARGETING_PLAYBOOK.md)
for examples and the difference between "investigate today" and "watch".

Open **Config** and set these fields:

- **targetSectors** - the industries whose funding trouble you want to hear about,
  as one comma-separated line (for example `semiconductor, precision-manufacturing`).
  The funding-distress search reads it on every run; the WARN feed is not filtered
  by sector.
- **companyProfile** - one paragraph: your company plus the *concrete* leverage
  the judges will cite in each "edge" line (equity band, comp stance, relocation
  support, benefits, ownership scope). Be specific; vague profiles produce vague
  edges.
- **openRole** - the role you're filling: `title`, `functions` (the adjacent
  titles that still count as a match), `location`, and a stable `id`.
- **sourcingCriteria** - optional seniority, skills, workArrangement
  (`onsite`, `hybrid`, `remote`), eligibleLocations, eventTypes (`layoff`,
  `shutdown`, `funding_distress`), priorityTriggers and excludeCompanies.
  These guide both the scanner and the judges; known company exclusions and
  disabled types are also filtered in code. Unknown location or affected work
  stays a question to verify. Do not interpret remote as worldwide.
- **companyName**, **companyFacts** - the hiring company and its explicitly stated
  `size`/`stage`. Empty facts keep those scores neutral. The pitch stays in
  companyProfile; do not put the company name in place of a real offer.
- **maxShown** and **includeFundingDistress** - default 10 (1-12) and true.
- **stateNamespace** - a stable role ID for separate memory per role. Use an
  empty string when retaining an existing single-role install's unprefixed IDs.

**Already run `talent-alpha-setup` in Claude Code or Cowork?** It reads your
shared `onepromptman-profile.md` and writes `talent-alpha-n8n-config.json` in
your working folder in exactly this shape. Open it, copy the JSON, and paste
it as the **Config** node's Value (Execute Mode: raw) instead of typing this
by hand.

For several roles, import one workflow per role and paste that role's
`talent-alpha-n8n-config-<id>.json`. They can share a Data Table when each has a
different stateNamespace. Changing a namespace resets what that role considers
seen; preserve it on upgrades. A Config validation error stops before feed calls.

## 5. Set your email + error workflow

- Open **Email Overnight Digest** and set the recipient to your address (same on
  **Email Error Alert**).
- For automatic error alerts, select a published error-handler workflow under
  **Settings -> Error Workflow**. n8n may reject a reference to this workflow
  while it has no published version. Leave the inactive draft unlinked, then
  configure the handler when publishing. If you use this workflow itself, its
  **On Workflow Error** branch supplies the handler,
  so an automatic failed run can email you. Fetch, scoring and digest-delivery
  errors stop the workflow; they are not counted as a quiet day. If Gmail itself
  is unavailable, the email alert may fail too; inspect Executions for the error.

## 6. Test, then schedule

Click **Execute Workflow** to run once now. The card is the output of the
**Render Scanner Report** node (open its output to view the HTML) and it's emailed
to you when eligible events reach the card. A first live run can legitimately
have no matches; the fictional demo is the route for a guaranteed sample batch.
Inspect the execution to distinguish empty feeds, stale/disabled events and an
empty shortlist from a failed node. Later runs only surface unseen events for
that role. When you're happy, set the workflow timezone and hour on **Nightly 06:00 Scan**, then publish it
when the sources and delivery have passed your test. An imported copy stays inactive
until you publish it (older n8n versions call this Activate).

## Upgrading an existing install

Imported an earlier copy of this workflow? Three things changed; they are listed
below.

The four public forks of the earlier talent-alpha repository are detached copies of
its single old commit and get no updates. If your copy came from one of them, take
the new workflow from this repository.

1. **The dedupe Data Table has a new name.** Earlier copies used a table named
   `r04_events_seen`; this one uses `talent_alpha_events_seen`. In n8n -> **Data
   Tables**, rename your existing table to `talent_alpha_events_seen` and keep its
   rows (they are the events you have already been sent). Then open **Skip
   Already-Scanned Events** and **Record Scanned Events** and pick it from the
   dropdown. A new, empty table works too, but the first run after the switch
   re-sends every event still inside the pull window (3 days of WARN notices, a
   week of funding news).
2. **Config gains `targetSectors`** (step 4). Earlier copies searched a fixed list
   of hardware sectors whatever Config said.
3. **Re-import rather than patch.** Import `n8n/talent-alpha.workflow.json` as a
   new workflow, carry over your Config value, credentials and email recipients,
   run it once by hand, then deactivate the old one. The new copy also escapes
   every value it puts on the emailed card, so a company name or a judge's line
   from a feed can never add markup or links to the email.

## How it works

1. **Pull** - two feeds: WARN layoff/closure notices and funding-distress news.
2. **Shortlist** - a fast model (Haiku) does a broad-recall scan against your role.
   An event older than its source window (3 days for WARN, 7 for funding
   news) is dropped before model calls and checked again at **Trust-Boundary Join**. The demo workflow skips this,
   because its sample signals carry fixed dates.
   Rows with missing, unparseable or more-than-a-day-future dates are also dropped
   before scanning, so one malformed row does not discard the rest of a feed.
   A failed source request or malformed response envelope still fails the run.
3. **Judge** - an **Advocate** and a **Skeptic** (both Sonnet) independently argue
   each candidate on six axes and assign a tier.
   Size and stage use only the explicit `companyFacts` fields, not the pitch.
   If a field is missing or empty, reconciliation sets that axis to neutral M
   for both judges instead of stopping the digest. The plugin retains its
   reject-and-repair behavior.
4. **Reconcile** - both judges must cover every trusted event exactly once. Their
   tiers are blended; freshness breaks ties. Sharp S/C disagreement is always held,
   and unsupported numeric claims fail the run. These checks do not prove news true.
5. **Render + email** - the card retains source links. Rendering is checked before
   email. Only a confirmed Gmail message ID allows **Confirm Digest Delivery** to
   pass event IDs to **Record Scanned Events**. A failed send leaves them unseen.
   If Gmail sends but the response or later state write is lost, a retry can resend;
   delivery is not guaranteed exactly once.

A valid empty feed is distinct from a failed response. When neither source has
new events, scoring stops without model calls. Different URLs about the same
real-world layoff are still distinct source IDs. The n8n path uses two judges
and deterministic checks; the plugin's additional critic is a separate feature.

## Tuning

- **How many make the card** - `maxShown` in Config. No minimum overrides a
  disagreement hold. Held items do not consume the available shown slots.
- **The scoring itself** - edit the maintained prompts in
  [`../n8n/prompts/`](../n8n/prompts/). Code nodes are maintained in `n8n/code/`;
  run `python n8n/tools/build_workflows.py` after editing either. `--check`
  verifies both exports match those sources and the
  shared HTML template. Keep credential IDs and private profiles out of public exports.
- **Cadence** - the **Nightly 06:00 Scan** trigger. Native scheduling on the
  Claude Code / Cowork side is unconfirmed for this build; n8n's own scheduler
  provides the scheduling route after the live acceptance cases pass.
