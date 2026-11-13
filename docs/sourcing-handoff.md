# Take Talent Alpha signals into Noon or Juicebox

Talent Alpha finds companies where good people may be open to a move. Noon and
Juicebox source the people. This handoff passes the companies over and leaves
the hiring bar to a role or search you already trust.

> Run Talent Alpha for my saved role, export the sourcing handoff, and push it
> to Noon using my existing role as the template.

The build writes `sourcing-handoff.json` beside the checked card. It lists one
entry per shown S or A event, the shared `targets`, and the same targets shaped
for each tool in `noon` and `juicebox`. Null `targets` means nothing qualified
this run.

## What maps to what

Talent Alpha only fills the fields it has evidence for. The rest comes from the
template you choose.

| Target | Noon | Juicebox | Comes from |
|---|---|---|---|
| Name | Role name | Agent name | Talent Alpha: role, your company, signal companies |
| Companies | Target companies (Noon treats them as "Must work at") | Current companies | Talent Alpha, S and A rows only |
| Locations | Location | Locations | Your role's location plus each event's city. A state-only location is left out. |
| Titles | Titles | Job titles | Template, plus any title a source named |
| Exclude | Excluded companies, set in Noon after create | Excluded companies | Talent Alpha: your own company |
| Evidence | Job description | Kept in the agent description | Talent Alpha: event, date, expiry, source link |
| Expiry | No field | No field | Talent Alpha: `use_through` |
| Years of experience | Experience range | Experience | Template |
| Must-haves and nice-to-haves | Must-haves and nice-to-haves | Requirements | Template |
| Seniority | Noon default, IC to Senior IC | Template | Template or tool default |
| Outreach | Sequence copied from the template | Not touched | Template. It never mentions the event. |

Juicebox searches in plain language first, so the `juicebox` block also carries
a ready query, for example "Data Engineer currently at ServiceNow, near San
Francisco Bay Area, CA". The push step maps the filters onto the field names
Juicebox's connector reports at push time. A filter it cannot take stays in
the query.

A template is an existing role or search in the tool, or a brief such as a
Talent One sourcing strategy and outreach playbook for the same job.

## Set up event-driven campaigns once

The handoff works best when each kind of news already has a campaign waiting.
Make one template per event type you care about, in Noon or Juicebox:

- **Talent Alpha template: layoff**
- **Talent Alpha template: shutdown**
- **Talent Alpha template: funding distress**

Each template holds your hiring bar (titles, years, must-haves) and outreach
written for that moment. Outreach never names the event: "if you are weighing
a next step" reads well; "sorry about your layoff" does not. Claude matches
each signal to its template by name and creates one new role or agent per
event type. Without templates, Claude asks which role to copy every time.

## Push it

Connect the tool first: [Noon's MCP setup](https://www.noon.ai/docs/mcp) or
[Juicebox's MCP setup](https://docs.juicebox.ai/juicebox-mcp). Then ask Claude
to push. Claude creates a new Noon role or Juicebox agent from the matching
template and reads it back.

- **Noon:** sourcing starts as soon as the role exists. Every push is a new
  role, because the connector cannot edit an existing role's companies.
  Auto-contact stays off.
- **Juicebox:** the agent is created. It starts sourcing right away only when
  your request or saved schedule says "auto-source"; otherwise it waits for
  your go.

**Auto-source or review first?** Sourcing (finding people) can run on its own.
Contact cannot, unless you choose it: Claude never turns on outreach. If you
want hands-off campaigns, turn on auto-contact yourself on each new role once
the tuning below looks right, with a daily limit. If you want to review every
person first, leave it off and accept or reject in the tool.

## Tune it

You do need to tune. A new role starts from your template and a news signal,
and the first results show how the tool read them. Plan on a few minutes the
first time per template; later pushes from the same template need much less.
Do these in the tool, in order. Change one thing, then look at the results
again.

1. **Check the setup.** Confirm the companies, locations, titles, seniority and
   must-haves. In Noon, add your own company under excluded companies.
2. **Judge the first ten.** Mark the good ones and pass on the rest with a
   reason. Your judgments teach the search faster than anything else.
3. **Steer the whole list.** Describe patterns, not people ("too many
   consultants", "needs dbt in production"). In Noon each note becomes a hard
   rule, so send only the change.
4. **Too few people?** Loosen one thing at a time: a wider location radius, a
   higher seniority cap, more companies, or past employees as well as current
   ones.
5. **Too many?** Tighten the must-haves that matter. In Noon, lock them so the
   search never relaxes them on its own.
6. **Before any outreach.** Read every message, recheck company facts that may
   have changed, then start contact with a daily limit you are comfortable with.
7. **On the `use_through` date.** The signal is stale. Archive the role or
   agent, or swap in the next run's companies.

Each company event is a reason to look at a pool, not evidence that any person
is available.
