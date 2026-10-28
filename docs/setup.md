# Setup - Talent Alpha (n8n)

About 15 minutes, no coding. Every step here also has a matching sticky note on
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

Only want WARN layoffs, not funding news? Delete **Fetch Funding-Distress Signals**
and **Normalize Funding-Distress Items** and skip the Perplexity credential.

## 3. Create one Data Table

n8n -> **Data Tables** -> **New**: name it **`talent_alpha_events_seen`** with a single text
column **`event_id`**. This is the dedupe memory, so you're never pinged about the
same event twice. Then open **Skip Already-Scanned Events** and **Record Scanned
Events** and pick that table from the dropdown (they can't come pre-linked; every
workspace has different internal table IDs).

## 4. Tell it who you're hiring - the **Config** node

Open **Config** and edit three things:

- **targetSectors** - the industries whose funding trouble you want to hear about,
  as one comma-separated line (for example `semiconductor, precision-manufacturing`).
  The funding-distress search reads it on every run; the WARN feed is not filtered
  by sector.
- **companyProfile** - one paragraph: your company plus the *concrete* leverage
  the judges will cite in each "edge" line (equity band, comp stance, relocation
  support, benefits, ownership scope). Be specific; vague profiles produce vague
  edges.
- **openRole** - the role you're filling: `title`, `functions` (the adjacent
  titles that still count as a match), and `location`.

**Already run `talent-alpha-setup` in Claude Code or Cowork?** It reads your
shared `onepromptman-profile.md` and writes `talent-alpha-n8n-config.json` in
your working folder in exactly this shape. Open it, copy the JSON, and paste
it as the **Config** node's Value (Execute Mode: raw) instead of typing this
by hand.

## 5. Set your email + error workflow

- Open **Email Overnight Digest** and set the recipient to your address (same on
  **Email Error Alert**).
- After you save the workflow once: **Settings -> Error Workflow -> this workflow**,
  so a failed run emails you instead of failing silently.

## 6. Test, then schedule

Click **Execute Workflow** to run once now. The card is the output of the
**Render Scanner Report** node (open its output to view the HTML) and it's emailed
to you. First run: everything is new, so you get a full card; later runs only
surface events you haven't seen. When you're happy, change the hour on **Nightly
06:00 Scan** if you like, and toggle the workflow **Active**.

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
3. **Judge** - an **Advocate** and a **Skeptic** (both Sonnet) independently argue
   each candidate on six axes and assign a tier.
4. **Reconcile** - the two judges' tiers are blended, fresher signals sort first
   when tiers tie, and the top 4-10 are kept. One model never grades its own work.
5. **Render + email** - the survivors become a one-page card, emailed to you.

## Tuning

- **How many make the card / how strict** - the **Reconcile Judges** node
  (`MIN_SHOWN`, `MAX_SHOWN`, and how tiers blend).
- **The scoring itself** - the **Signal Scanner Agent** and the two judge nodes
  hold the prompts; reference copies live in [`../n8n/prompts/`](../n8n/prompts/).
- **Cadence** - the **Nightly 06:00 Scan** trigger. Native scheduling on the
  Claude Code / Cowork side is unconfirmed for this build; n8n's own scheduler
  is the reliable place to run this unattended today.
