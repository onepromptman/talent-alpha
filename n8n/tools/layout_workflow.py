"""Arrange the public canvas and explain its stages without changing execution."""

import copy
import uuid

POSITIONS = {
    "Nightly 06:00 Scan": [0, 440],
    "Config": [240, 440],
    "Validate Config": [240, 680],
    "Funding Enabled": [560, 840],
    "Funding Disabled": [800, 840],
    "Fetch WARN Notices": [560, 280],
    "Normalize WARN Items": [800, 280],
    "Fetch Funding-Distress Signals": [560, 600],
    "Normalize Funding-Distress Items": [800, 600],
    "Merge Category Feeds": [1080, 440],
    "Skip Already-Scanned Events": [1400, 440],
    "Batch For Scanner Agent": [1640, 440],
    "Signal Scanner Agent": [1960, 440],
    "Haiku Scanner Model": [1900, 700],
    "Scanner Output Parser": [2140, 700],
    "Trust-Boundary Join": [2240, 440],
    "Batch For Judges": [2460, 440],
    "Judge Advocate": [2700, 260],
    "Judge Skeptic": [2700, 600],
    "Sonnet Judge Model": [2660, 830],
    "Advocate Output Parser": [2940, 260],
    "Skeptic Output Parser": [2940, 700],
    "Collect Judge Outputs": [3200, 440],
    "Reconcile Judges": [3500, 440],
    "Render Scanner Report": [4060, 440],
    "Email Overnight Digest": [4620, 440],
    "Confirm Digest Delivery": [4860, 440],
    "Record Scanned Events": [5100, 440],
    "On Workflow Error": [4080, 1180],
    "Email Error Alert": [4380, 1180],
}

# name, position, size, n8n color, plain-language explanation
NOTES = [
    (
        "Talent Alpha overview",
        [-80, -420],
        [5440, 240],
        4,
        (
            "# Talent Alpha\n## A daily head start for your sourcing research\n"
            "Read the main flow from left to right. It finds company changes, checks them against one open role, "
            "and sends you a short card with the evidence and a possible approach. You review the card and choose whether to act. "
            "The workflow never contacts candidates."
        ),
    ),
    (
        "Stage 1 - Set the target",
        [-80, -100],
        [520, 950],
        4,
        (
            "## 1. Set your target\n\nTell **Config** which role you are filling, which industries to watch, "
            "and what your company can actually offer. Save skills, eligible locations and priority triggers in sourcingCriteria.\n\n"
            "A timely event, plausible role overlap and compatible geography make a lead worth investigating today. "
            "Use a separate Config and stateNamespace for each role. Validation runs before sources."
        ),
    ),
    (
        "Stage 2 - Find company changes",
        [480, -100],
        [800, 950],
        5,
        (
            "## 2. Find recent company changes\n\nLook for two kinds of signal: official layoff notices and news about funding trouble or restructuring.\n\n"
            "The paths keep dates and source links. Set includeFundingDistress=false to bypass Perplexity without editing the graph. "
            "WARN needs its source account; the funding account is needed only when enabled."
        ),
    ),
    (
        "Stage 3 - Skip repeats",
        [1320, -100],
        [520, 950],
        7,
        (
            "## 3. Skip what you already received\n\nCheck the saved memory before spending time on a story. "
            "Only new source IDs continue.\n\nDifferent articles about the same company event can still appear separately."
        ),
    ),
    (
        "Stage 4 - Make a shortlist",
        [1880, -100],
        [700, 950],
        1,
        (
            "## 4. Make a useful shortlist\n\nA quick first pass picks stories that could matter for your role. "
            "The next check ties each suggestion back to the original evidence.\n\nCompany names must trace back to the collected story."
        ),
    ),
    (
        "Stage 5 - Check both sides",
        [2620, -100],
        [760, 1050],
        2,
        (
            "## 5. Check the opportunity from both sides\n\nOne reviewer makes the case for acting. Another challenges weak evidence, "
            "poor fit or an overconfident pitch.\n\nBoth must finish a review of every shortlisted story. A missing review stops the run."
        ),
    ),
    (
        "Stage 6 - Rank with care",
        [3420, -100],
        [520, 950],
        4,
        (
            "## 6. Decide what deserves attention\n\nCombine both reviews and put stronger opportunities first. "
            "Fresher news breaks a tie.\n\nSharp disagreement is held for your review. The card is never padded just to reach a target count."
        ),
    ),
    (
        "Stage 7 - Build the card",
        [3980, -100],
        [520, 950],
        6,
        (
            "## 7. Build your research card\n\nFor each company, show why now, a possible opening line, "
            "and an advantage your company can honestly offer.\n\nKeep the source links so you can check the story. Verify the finished card before sending it."
        ),
    ),
    (
        "Stage 8 - Deliver then remember",
        [4540, -100],
        [820, 950],
        5,
        (
            "## 8. Deliver the card, then remember it\n\nEmail one digest to you. When Gmail confirms the send, save the event IDs in memory.\n\n"
            "A failed send leaves the stories available for retry. If delivery is uncertain or saving memory fails, a retry may repeat a card."
        ),
    ),
    (
        "Before the first run",
        [-80, 960],
        [1920, 440],
        7,
        (
            "## Before the first run\n\n"
            "1. Describe your company, open role and target industries in **Config**.\n"
            "2. Connect WARN, the AI and email accounts, plus Perplexity if funding news is enabled.\n"
            "3. Select the saved-memory table on both memory steps and set your own email address.\n"
            "4. Check the timezone, run a test card, and review its sources before turning on the daily schedule.\n\n"
            "The demo uses sample stories and has email and memory writes switched off."
        ),
    ),
    (
        "When a step needs attention",
        [3980, 960],
        [1380, 440],
        3,
        (
            "## When something needs attention\n\nA source, review or delivery failure stops the run. A failed source is never treated as a quiet news day.\n\n"
            "Open **Executions** to see which step needs help. A working email account and a published error handler can also send you an alert. "
            "The workflow stays off until you activate it."
        ),
    ),
]


def layout_workflow(source):
    workflow = copy.deepcopy(source)
    nodes = [n for n in workflow["nodes"] if n["type"] != "n8n-nodes-base.stickyNote"]
    names = {n["name"] for n in nodes}
    if set(POSITIONS) - names:
        raise ValueError(f"missing canvas nodes: {sorted(set(POSITIONS) - names)}")
    for node in nodes:
        if node["name"] in POSITIONS:
            node["position"] = POSITIONS[node["name"]].copy()
    for name, position, size, color, text in NOTES:
        nodes.append(
            {
                "id": str(
                    uuid.uuid5(uuid.NAMESPACE_URL, "talent-alpha/canvas/" + name)
                ),
                "name": name,
                "type": "n8n-nodes-base.stickyNote",
                "typeVersion": 1,
                "position": position,
                "parameters": {
                    "content": text,
                    "width": size[0],
                    "height": size[1],
                    "color": color,
                },
            }
        )
    workflow["nodes"] = nodes
    return workflow
