"""
News Integration Protocol

Injection fragments that weave current events into existing engine outputs.
Each engine gets a tailored injection that fits its methodology.

These fragments are appended to the engine's system prompt when news integration is enabled.
"""

THRESHOLD_NEWS_INJECTION = """

## NEWS INTEGRATION — CURRENT EVENTS THRESHOLD

A current news event has been provided alongside the biblical text. You MUST integrate this event into your analysis as follows:

**CURRENT EVENT ({news_date}):**
{news_context}

### Integration Instructions for Threshold Engine:

Add a **FIFTH MOVEMENT** after the Tech Touchpoint called **"NEWS THRESHOLD: Reading the Signs"**

In this movement (400-600 words):
1. Name the news event clearly and what is at stake
2. Show how the core insight from the four thresholds speaks directly to this moment
3. Identify where the gospel comforts AND confronts in this situation
4. Provide 2-3 specific connections between the biblical text and the news event
5. End with a practical "threshold crossing" — how does this text change how we engage with this news?

Additionally, weave at least ONE reference to the news event naturally into Threshold Three (Present Friction). The news should feel like a natural example of the friction between text and world, not a forced insertion.
"""

PALIMPSEST_NEWS_INJECTION = """

## NEWS INTEGRATION — CURRENT EVENTS LAYER

A current news event has been provided alongside the biblical text. You MUST integrate this event across your five layers.

**CURRENT EVENT ({news_date}):**
{news_context}

### Integration Instructions for Palimpsest Engine:

For EACH of the five PaRDeS layers, include at least one substantive connection to the news event:

1. **Peshat (Surface)**: Note how the literal reading of the text maps onto the literal facts of the news event
2. **Remez (Hint)**: What allegorical connections emerge between the text's hints and the deeper dynamics at work in this event?
3. **Derash (Seek)**: How do rabbinic/homiletical interpretive traditions illuminate this contemporary moment?
4. **Sod (Secret)**: What mystical or hidden dimensions of the text speak to what is unseen in this news story?
5. **Synthesis**: In the final synthesis, the news event should serve as a contemporary case study — how do all five layers, read together, transform our understanding of this moment?

The news integration should feel organic within each layer, not appended. The Palimpsest methodology reveals that ancient texts have ALWAYS been speaking to moments like this — the layers prove it.
"""

COLLISION_NEWS_INJECTION = """

## NEWS INTEGRATION — CURRENT EVENTS COLLISION

A current news event has been provided alongside the biblical text. This event becomes a PRIMARY COLLISION POLE — it must be as central as the biblical text itself.

**CURRENT EVENT ({news_date}):**
{news_context}

### Integration Instructions for Collision Engine:

The news event is not background context — it is an ACTIVE COLLISION PARTNER with the biblical text. Treat it with the same intensity as the scripture.

1. **Anchor in Antiquity**: Proceed as normal, but in the final paragraph, name the specific tension between the ancient context and today's event
2. **Collide with Now**: The news event should be woven into AT LEAST 3 of the 5 collision vectors. Force the connections — this is where unexpected meaning erupts
3. **Navigate the Rupture**: At least 2 of the minimum 4 rupture points MUST directly address the news event. These should be the most intense rupture points — where ancient text and breaking news tear open new meaning
4. **Crystallize the Insight**: The refrain/poetry section should hold BOTH the biblical text and the news event in creative tension. The one-sentence wisdom must speak to this specific moment
5. **Release into Future**: The practical lens must address how to live in light of BOTH the text and this news. Be specific — name actions, postures, prayers that respond to this moment

The collision between ancient scripture and today's headlines is where the most dangerous, generative meaning lives. Do not domesticate it.
"""


def get_news_injection(engine_name: str, news_context: str, news_date: str) -> str:
    """
    Get the news injection fragment for a specific engine.

    Args:
        engine_name: 'threshold', 'palimpsest', or 'collision'
        news_context: The news story/event text
        news_date: Date string for the news event

    Returns:
        Formatted injection fragment to append to engine system prompt
    """
    templates = {
        "threshold": THRESHOLD_NEWS_INJECTION,
        "palimpsest": PALIMPSEST_NEWS_INJECTION,
        "collision": COLLISION_NEWS_INJECTION,
    }

    template = templates.get(engine_name)
    if not template:
        raise ValueError(f"Unknown engine: {engine_name}. Choose from: {', '.join(templates.keys())}")

    return template.format(
        news_context=news_context,
        news_date=news_date,
    )
