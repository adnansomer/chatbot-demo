"""FAQ knowledge base: parsing + lightweight TF-IDF style retrieval.

The knowledge base lives in ``data/faq.txt`` in the ``QuestionN:`` /
``AnswerN:`` format supplied by the business.  Retrieval is dependency-free
so the app runs anywhere with just Flask installed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FAQ_FILE = DATA_DIR / "faq.txt"

_QUESTION_RE = re.compile(r"^Question(\d+)\s*:\s*(.*)$", re.I)
_ANSWER_RE = re.compile(r"^Answer(\d+)\s*:\s*(.*)$", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9']+")

STOPWORDS = {
    "a", "about", "after", "again", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "being", "but", "by", "can", "could",
    "did", "do", "does", "doing", "for", "from", "get", "give", "had", "has",
    "have", "he", "her", "here", "him", "his", "how", "i", "if", "in", "into",
    "is", "it", "its", "just", "know", "let", "like", "may", "me", "more",
    "most", "much", "must", "my", "need", "no", "not", "of", "on", "one",
    "or", "other", "our", "out", "over", "please", "should", "so", "some",
    "still", "such", "tell", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "those", "to", "too", "up", "us",
    "use", "very", "want", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "why", "will", "with", "would", "you", "your",
    "yours", "many", "give", "got", "kindly", "hi", "hello", "hey", "thanks",
    "thank", "many", "also", "really", "actually", "okay", "ok", "am",
}

# Light stemming: enough to match "charges"/"charge", "bundles"/"bundle".
def _stem(word: str) -> str:
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            if suffix == "ies":
                return word[:-3] + "y"
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    # Stopwords are removed *before* stemming as well, otherwise words like
    # "does" would be stemmed to "doe" and survive the filter.
    raw = [t for t in _TOKEN_RE.findall((text or "").lower())
           if t not in STOPWORDS]
    tokens = [_stem(t) for t in raw]
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


# Query-side synonym expansion, so "who runs telkom" still finds the CEO entry.
# Keys and values are stored already stemmed.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "ceo": ("chief", "executive", "management", "leadership", "team"),
    "boss": ("ceo", "chief", "executive", "management"),
    "run": ("ceo", "chief", "executive", "management"),
    "head": ("ceo", "chief", "executive", "management"),
    "lead": ("ceo", "management", "executive"),
    "director": ("management", "executive"),
    "cost": ("price", "charge", "rate", "fee"),
    "price": ("cost", "charge", "rate", "pricing"),
    "cheap": ("price", "cost", "cheapest"),
    "expensive": ("price", "cost", "charge"),
    "fee": ("charge", "cost", "price"),
    "bill": ("billing", "invoice", "account", "payment"),
    "invoice": ("bill", "billing"),
    "pay": ("payment", "bill", "debit"),
    "abroad": ("international", "roaming"),
    "overseas": ("international", "roaming"),
    "travel": ("roaming", "international"),
    "sms": ("message", "text"),
    "cellphone": ("mobile", "phone"),
    "wifi": ("router", "connection", "wireless"),
    "vas": ("value", "add", "service"),
    "cancel": ("cancellation", "contract"),
    "goal": ("mission", "vision"),
    "purpose": ("mission",),
    "difference": ("differ", "compare", "vs"),
    "support": ("help", "assist", "contact"),
    "reach": ("contact", "talk"),
    "call": ("contact", "talk", "phone"),
}


@dataclass
class FaqEntry:
    number: int
    question: str
    answer: str
    q_tokens: set[str] = field(default_factory=set)
    a_tokens: set[str] = field(default_factory=set)


class FaqIndex:
    """Tiny bag-of-words retriever over the FAQ entries."""

    #: below this score we treat the match as "not confident enough"
    THRESHOLD = 0.28

    def __init__(self, entries: list[FaqEntry]):
        self.entries = entries
        self.idf: dict[str, float] = {}
        total = max(len(entries), 1)
        df: dict[str, int] = {}
        for entry in entries:
            for token in entry.q_tokens | entry.a_tokens:
                df[token] = df.get(token, 0) + 1
        for token, count in df.items():
            self.idf[token] = math.log((total + 1) / (count + 0.5)) + 1.0

    def _weight(self, token: str) -> float:
        return self.idf.get(token, math.log(len(self.entries) + 1) + 1.0)

    #: how much a synonym-expanded term counts relative to a typed one
    SYNONYM_FACTOR = 0.3
    #: bonus for a typed term that appears in the entry's *question*
    QUESTION_BOOST = 1.25

    def _query_terms(self, query: str) -> dict[str, tuple[float, bool]]:
        """Map term -> (weight, was_typed_by_the_user)."""
        terms: dict[str, tuple[float, bool]] = {}
        for token in set(tokenize(query)):
            terms[token] = (self._weight(token), True)
        for token in [t for t, (_, typed) in terms.items() if typed]:
            for synonym in SYNONYMS.get(token, ()):
                syn = _stem(synonym)
                if syn not in terms:
                    terms[syn] = (self._weight(syn) * self.SYNONYM_FACTOR, False)
        return terms

    def rank(self, query: str) -> list[tuple[float, FaqEntry]]:
        terms = self._query_terms(query)
        if not terms:
            return []
        norm = sum(weight for weight, typed in terms.values() if typed) or 1.0
        norm *= self.QUESTION_BOOST
        scored: list[tuple[float, FaqEntry]] = []
        for entry in self.entries:
            score = 0.0
            for token, (weight, typed) in terms.items():
                if token in entry.q_tokens:
                    score += weight * (self.QUESTION_BOOST if typed else 1.0)
                elif token in entry.a_tokens:
                    score += weight * 0.35
            scored.append((score / norm, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored

    def search(self, query: str, limit: int = 3) -> list[tuple[float, FaqEntry]]:
        return self.rank(query)[:limit]

    def best(self, query: str) -> tuple[FaqEntry | None, float, list[FaqEntry]]:
        """Return (entry_or_None, score, suggestions)."""
        ranked = self.rank(query)
        if not ranked:
            return None, 0.0, []
        top_score, top_entry = ranked[0]
        suggestions = [entry for score, entry in ranked[:3] if score > 0.05]
        if top_score < self.THRESHOLD:
            return None, top_score, suggestions
        return top_entry, top_score, suggestions


# Extra phrasings folded into an entry's *question* index, for questions
# customers commonly ask with completely different wording.
ALIASES: dict[int, str] = {
    3: "reconnect reconnection restore my line was cut off disconnected arrears",
    8: "roaming rates abroad overseas travelling data prices per country",
    11: "reach support customer care call centre agent help desk contact us "
        "speak to someone phone number live agent",
    18: "adsl speed measured mbps how fast is my line",
    19: "download rate slow dsl speed factors affecting",
    22: "cancel cancellation terminate end my contract",
    43: "ceo group chief executive officer who leads telkom",
    45: "management team executives leadership board members",
}


def _parse(raw: str) -> list[FaqEntry]:
    questions: dict[int, str] = {}
    answers: dict[int, list[str]] = {}
    current: int | None = None
    mode: str | None = None

    for line in raw.replace("\r\n", "\n").split("\n"):
        q_match = _QUESTION_RE.match(line.strip())
        a_match = _ANSWER_RE.match(line.strip())
        if q_match:
            current = int(q_match.group(1))
            mode = "q"
            questions[current] = q_match.group(2).strip()
            continue
        if a_match:
            current = int(a_match.group(1))
            mode = "a"
            answers.setdefault(current, [])
            first = a_match.group(2).strip()
            if first:
                answers[current].append(first)
            continue
        if current is None:
            continue
        if mode == "a":
            answers.setdefault(current, []).append(line)
        elif mode == "q" and line.strip():
            questions[current] = (questions[current] + " " + line.strip()).strip()

    entries: list[FaqEntry] = []
    for number in sorted(questions):
        answer = "\n".join(answers.get(number, [])).strip("\n")
        entry = FaqEntry(number=number, question=questions[number], answer=answer)
        entry.q_tokens = set(tokenize(entry.question))
        entry.q_tokens |= set(tokenize(ALIASES.get(number, "")))
        entry.a_tokens = set(tokenize(entry.answer))
        entries.append(entry)
    return entries


def load_index(path: Path | None = None) -> FaqIndex:
    path = path or FAQ_FILE
    raw = path.read_text(encoding="utf-8")
    return FaqIndex(_parse(raw))
