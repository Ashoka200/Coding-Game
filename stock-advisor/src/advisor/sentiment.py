"""AI news sentiment: what the words actually mean.

The keyword classifier in `news.py` is fast and free, but it is blind to the
things that decide a headline's meaning:

    "Profit falls 30%, but far less than the street feared"   → keywords: bad
    "Company denies allegations of accounting irregularities" → keywords: bad
    "Record profit driven by a one-off land sale"             → keywords: good

Every one of those is misread by pattern matching. A language model reads them
correctly, which is the honest use of an LLM here: it interprets TEXT, and never
supplies a number about a price.

The contract is strict. The model receives headlines and returns structure —
event type, direction, materiality, whether the item is rumour or confirmed
fact. It is explicitly forbidden from estimating prices, targets or valuations,
because those must come from the engines. If no API key is configured, this
falls back to the keyword classifier and says so, rather than pretending.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You classify financial news headlines about Indian listed companies.

Return ONLY a JSON array, one object per headline, in the same order:
{"direction": -3..3,        // effect on the company's value: -3 severe, +3 strongly positive
 "materiality": 0.0..1.0,   // would a professional investor change a decision on this alone?
 "event": "results|order_win|regulatory|litigation|management|ownership|policy|
           rating|expansion|payout|rumour|routine",
 "confirmed": true|false,   // reported fact vs speculation, "sources say", "may", "plans to"
 "about_company": true|false, // genuinely about THIS company, not a sector piece that names it
 "why": "at most 12 words"}

Rules that matter:
- Read the sentence, not the keywords. "Profit falls less than feared" is positive.
  "Denies allegations" is negative — the allegation is the news.
- A one-off gain (land sale, tax writeback) is NOT operating strength: mark it low
  materiality and say so.
- Analyst opinion is weaker evidence than company action. A broker upgrade is not
  the same as an order win.
- Anything hedged with "may", "plans", "in talks", "sources" is confirmed:false.
- NEVER estimate a price, target, valuation or return. You classify text only.
- If a headline is a listicle, an advertisement, or about a different company,
  set about_company:false and materiality:0."""


@dataclass
class Scored:
    title: str
    direction: int
    materiality: float
    event: str
    confirmed: bool
    about_company: bool
    why: str
    age_days: float | None = None
    source: str | None = None
    link: str | None = None


@dataclass
class SentimentRead:
    symbol: str
    method: str                       # "llm" | "keywords"
    items: list[Scored] = field(default_factory=list)
    score: float | None = None        # -1..+1, recency and materiality weighted
    confidence: float | None = None   # 0..1, from agreement and evidence quality
    material_count: int = 0
    disagreement: float | None = None
    summary: str | None = None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["items"] = [asdict(i) if not isinstance(i, dict) else i for i in self.items]
        return d


def _weight(item: Scored) -> float:
    """Recent, material, confirmed, company-specific news counts most."""
    if not item.about_company:
        return 0.0
    recency = 1.0 if item.age_days is None else max(0.15, 1 - item.age_days / 14)
    evidence = 1.0 if item.confirmed else 0.45      # rumour is discounted, not ignored
    return recency * evidence * max(0.0, min(1.0, item.materiality))


def aggregate(symbol: str, scored: list[Scored], method: str) -> SentimentRead:
    read = SentimentRead(symbol=symbol, method=method, items=scored)
    usable = [(s, _weight(s)) for s in scored]
    usable = [(s, w) for s, w in usable if w > 0]
    if not usable:
        read.score = None
        read.summary = ("Nothing company-specific and material in the window. Absence "
                        "of news is not evidence that nothing is happening.")
        return read

    total_w = sum(w for _, w in usable)
    read.score = round(sum((s.direction / 3.0) * w for s, w in usable) / total_w, 3)
    read.material_count = sum(1 for s in scored
                              if s.about_company and s.materiality >= 0.6)

    # Disagreement: are the stories pulling in opposite directions?
    pos = sum(w for s, w in usable if s.direction > 0)
    neg = sum(w for s, w in usable if s.direction < 0)
    read.disagreement = round(min(pos, neg) / (pos + neg), 3) if (pos + neg) else 0.0

    confirmed_share = (sum(w for s, w in usable if s.confirmed) / total_w)
    read.confidence = round(max(0.0, min(1.0,
        0.35 + 0.4 * confirmed_share + 0.25 * min(1.0, total_w / 3)
        - 0.3 * read.disagreement)), 2)

    strongest = max(usable, key=lambda x: abs(x[0].direction) * x[1])[0]
    tone = ("clearly positive" if read.score > 0.35 else "clearly negative"
            if read.score < -0.35 else "mixed")
    read.summary = (f"News reads {tone}. The item carrying most weight: "
                    f"“{strongest.title[:110]}” ({strongest.why}).")
    if read.disagreement > 0.35:
        read.caveats.append(
            f"The coverage disagrees with itself ({read.disagreement:.0%} of the weight "
            "points the other way). A split narrative usually means the market has not "
            "settled on an interpretation either.")
    if confirmed_share < 0.5:
        read.caveats.append(
            "Most of this is unconfirmed reporting rather than company disclosure. "
            "Speculation moves prices and then reverses.")
    return read


def _fallback(symbol: str, items: list[dict]) -> SentimentRead:
    """Keyword classification, clearly labelled as the weaker method."""
    from .news import classify

    scored = []
    for it in items:
        key, weight, label = classify(it.get("title", ""))
        scored.append(Scored(
            title=it.get("title", ""), direction=int(max(-3, min(3, weight))),
            materiality=0.7 if abs(weight) >= 2 else 0.3 if weight else 0.1,
            event=key, confirmed=True, about_company=True,
            why=f"keyword match: {label.lower()}",
            age_days=it.get("age_days"), source=it.get("source"),
            link=it.get("link")))
    read = aggregate(symbol, scored, method="keywords")
    read.caveats.insert(0,
        "Scored by keyword matching, not by reading. This misreads negation "
        "(“falls less than feared”), denials, and one-off gains. Set ANTHROPIC_API_KEY "
        "for the language-model reading, which handles those correctly.")
    return read


def analyse(symbol: str, items: list[dict], company_name: str | None = None,
            model: str = DEFAULT_MODEL) -> SentimentRead:
    """Score headlines with a language model, falling back to keywords."""
    if not items:
        return SentimentRead(symbol=symbol, method="none",
                             summary="No headlines in the window.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback(symbol, items)

    try:
        import anthropic
        client = anthropic.Anthropic()
        titles = [it.get("title", "") for it in items][:25]
        listing = "\n".join(f"{n + 1}. {t}" for n, t in enumerate(titles))
        msg = client.messages.create(
            model=model, max_tokens=2000, system=SYSTEM,
            messages=[{"role": "user",
                       "content": f"Company: {company_name or symbol} (NSE: {symbol})\n\n"
                                  f"Headlines:\n{listing}"}])
        text = msg.content[0].text.strip()
        start, end = text.find("["), text.rfind("]")
        parsed = json.loads(text[start:end + 1]) if start >= 0 else []
        scored = []
        for it, p in zip(items, parsed):
            scored.append(Scored(
                title=it.get("title", ""),
                direction=int(max(-3, min(3, p.get("direction", 0)))),
                materiality=float(max(0.0, min(1.0, p.get("materiality", 0)))),
                event=str(p.get("event", "routine")),
                confirmed=bool(p.get("confirmed", False)),
                about_company=bool(p.get("about_company", True)),
                why=str(p.get("why", ""))[:80],
                age_days=it.get("age_days"), source=it.get("source"),
                link=it.get("link")))
        if not scored:
            raise ValueError("model returned no usable classifications")
        read = aggregate(symbol, scored, method="llm")
        read.caveats.append(
            "Headlines were read and classified by a language model. It interprets "
            "text only — every price and ratio in this system comes from the engines, "
            "never from the model.")
        return read
    except Exception as exc:
        read = _fallback(symbol, items)
        read.caveats.insert(0, f"The language-model reading failed ({type(exc).__name__}), "
                               "so keyword scoring was used instead.")
        return read
