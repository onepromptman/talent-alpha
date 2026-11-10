# What makes a sourcing target worth today's attention

Use this during setup to propose a search plan, and during scanning and judging
to apply the recruiter's confirmed criteria. It describes company-level leads,
not proof that a particular person is available or wants contact.

## Explain before asking

"Talent Alpha looks for a recent change at an employer that could make relevant
people more open to a move. It checks the affected work against your role,
location and hiring terms, then gives you a ranked research list with sources.
You get the reason to investigate today and a draft opener. You decide whom to
research and contact."

Ask which roles or role families they want to target first, including seniority,
essential skills, location and on-site/hybrid/remote terms. For remote roles,
ask where they can actually hire; remote does not mean worldwide. For on-site
roles, ask about commuting areas and relocation. Leave unknown terms unknown.

## Propose relevant triggers

| Target work | Useful events to investigate | Why they could matter |
| --- | --- | --- |
| Software, data, security | Product or engineering-team cuts, platform shutdowns, funding-related restructuring | Similar systems, skills or customers may transfer |
| Manufacturing, hardware, quality | Plant closure, production reduction, site consolidation | Process, equipment and quality experience may transfer locally |
| Sales, customer success, recruiting | Go-to-market reductions, territory consolidation, hiring retrenchment tied to distress | Customer segment and operating experience may transfer |
| Finance, operations, leadership | Restructuring, site or business-unit closure, consolidation with reported job impact | Comparable scope and operating problems may transfer |

These are starting hypotheses, not a fixed industry filter. Suggest adjacent
industries when skills transfer and explain the bridge. Let the recruiter edit
the suggested sectors, triggers and exclusions. Never assume their own industry
is the only talent source.

The current feeds support `layoff`, `shutdown` and `funding_distress`. Product
cuts, consolidation and restructuring qualify only when evidence connects them
to those events. A successful funding round, acquisition announcement, executive
departure, expansion or generic hiring headline alone is not evidence of talent
availability. Do not promise separate monitoring for those categories.

## Apply the criteria every run

`SOURCING_CRITERIA` carries `seniority`, `skills`, `workArrangement`,
`eligibleLocations`, `eventTypes`, `priorityTriggers` and `excludeCompanies`.
Empty optional fields mean unknown, never permission to invent a preference.
Missing criteria on an older profile retain broad scanning against OPEN_ROLE.

- **Freshness and evidence:** use a dated, checkable, company-specific source.
  WARN layoffs and closures have a 3-day window; funding news has 7 days.
  An old story republished today is not a new event without new facts.
- **Role and skills:** compare the affected work with the title, seniority and
  essential skills. A broad company layoff does not establish that the desired
  team was affected. Label that overlap as inference and a research step.
- **Location:** compare the affected site with eligible locations and the work
  arrangement. Unknown location is an unresolved question. Relocation only
  helps when the recruiter's offer actually includes it.
- **Priority triggers:** favor the confirmed triggers when the evidence supports
  them. A keyword match or distress alone is not enough for an urgent card.
- **Exclusions:** exclude a named company or disabled event type even when it
  would otherwise score well. Do not infer protected personal characteristics.
- **Offer:** use only stated leverage. Size and stage remain neutral unless both
  sides have evidence. An absent pitch never becomes invented compensation.

The scanner may keep uncertain matches for review, but excludes clear conflicts
with the recruiter's explicit requirements. Judges independently apply the same
criteria. S/A means investigate today: a timely trigger, credible role overlap
and compatible geography, with remaining uncertainty stated. B means watch or
verify a missing link; C means poor fit. Do not award S/A on distress alone or
when a hard location/skill constraint is known to fail. Priority is a reason to
research, not a claim about an individual's circumstances.

At setup's end, show a short plan per role: target work and geography, proposed
sectors, enabled signals, priority triggers, exclusions and what remains unknown.
Give one hypothetical qualifying example and one non-qualifying example. Label
them hypothetical. Confirm the plan once, then save it for daily reuse.
