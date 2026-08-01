"""Intent analysis for the first node of the flow.

Two intents are supported (see flow.PNG):

* ``network``  - a *user specific* connectivity problem, which starts the
  OTP -> location -> package -> coverage -> site availability journey.
* ``faq``      - a general question answered from the knowledge base.
"""

from __future__ import annotations

import re

SUBJECT_WORDS = (
    "internet", "connection", "connectivity", "network", "signal", "data",
    "wifi", "wi-fi", "line", "lte", "5g", "4g", "3g", "2g", "coverage",
    "reception", "adsl", "dsl", "fibre", "fiber", "broadband", "router",
    "modem", "sim", "service", "speed", "bandwidth", "tower", "mobile",
)

ISSUE_WORDS = (
    "bad", "slow", "poor", "weak", "down", "drop", "dropping", "drops",
    "unstable", "terrible", "awful", "horrible", "useless", "lag", "lagging",
    "buffer", "buffering", "offline", "outage", "dead", "worst", "issue",
    "issues", "problem", "problems", "trouble", "fault", "faulty", "broken",
    "intermittent", "disconnect", "disconnects", "disconnecting", "cutting",
    "cuts", "freezing", "no signal", "not working", "doesn't work",
    "does not work", "dont work", "don't work", "not connecting",
    "can't connect", "cannot connect", "cant connect", "keeps dropping",
    "no internet", "no connection", "no service", "not connect",
    "stopped working", "won't connect", "not able to connect",
)

PERSONAL_WORDS = (
    "my", "mine", "i ", "i'm", "im ", "we ", "our", "me ", "at home",
    "at my", "here", "in my area",
)

TIME_WORDS = (
    "today", "yesterday", "tonight", "this morning", "this week", "last week",
    "since", "days ago", "day ago", "hours ago", "hour ago", "right now",
    "currently", "all day", "for a while", "past few",
)

FAQ_OPENERS = ("what", "which", "who", "when", "where", "how much", "how many",
               "does telkom", "do you", "can i", "is it true", "compare")

TROUBLESHOOT_TRIGGERS = (
    "network troubleshooting", "troubleshoot", "troubleshooting",
    "technical support", "user specific", "user-specific", "report a problem",
    "report an issue", "fix my", "help me with my",
)

FAQ_TRIGGERS = ("faq", "frequently asked", "general question", "general info")

YES_WORDS = (
    "yes", "yeah", "yep", "yup", "ye", "sure", "correct", "ok", "okay", "okey",
    "it worked", "worked", "working now", "it is fixed", "fixed", "resolved",
    "solved", "sorted", "better now", "all good", "thanks", "thank you",
    "helpful", "that helped", "it helped", "good", "great", "perfect", "y",
)

NO_WORDS = (
    "no", "nope", "nah", "not", "negative", "still", "didn't", "didnt",
    "did not", "doesn't", "doesnt", "does not", "not fixed", "not resolved",
    "not solved", "no change", "same", "unchanged", "already", "not helpful",
    "no help", "didn't help", "unresolved", "worse", "n",
)


def _contains(text: str, words) -> bool:
    return any(w in text for w in words)


def _normalize(text: str) -> str:
    return " " + re.sub(r"\s+", " ", (text or "").lower().strip()) + " "


def classify_intent(text: str) -> str:
    """Return ``"network"`` or ``"faq"`` for a free-text message."""
    t = _normalize(text)

    if _contains(t, TROUBLESHOOT_TRIGGERS):
        return "network"
    if _contains(t, FAQ_TRIGGERS):
        return "faq"

    has_subject = _contains(t, tuple(f" {w}" for w in SUBJECT_WORDS))
    has_issue = _contains(t, ISSUE_WORDS)
    if not (has_subject and has_issue):
        return "faq"

    # "Why is Telkom's LTE so slow compared to MTN?" is a knowledge-base
    # question, not a personal fault report - it lacks a personal/time marker
    # and reads like an open question about the company.
    personal = _contains(t, PERSONAL_WORDS) or _contains(t, TIME_WORDS)
    mentions_company = "telkom" in t and not _contains(t, PERSONAL_WORDS)
    asks_general = t.strip().startswith(FAQ_OPENERS) or "compared" in t or "compare" in t

    if personal and not mentions_company:
        return "network"
    if personal and mentions_company and not asks_general:
        return "network"
    return "faq"


_COVERAGE_PATTERNS = (
    re.compile(r"\bcoverage\b.*?\b(?:in|at|for|around|near)\s+(?P<place>.+)", re.I),
    re.compile(r"\b(?:5g|4g|lte|3g|2g)\b.*?\b(?:in|at|for|around|near)\s+(?P<place>.+)", re.I),
    re.compile(r"\bdo (?:you|we) (?:have|offer|provide) .*?\b(?:in|at|for|around|near)\s+(?P<place>.+)", re.I),
    re.compile(r"\bis\s+(?P<place>.+?)\s+covered\b", re.I),
    re.compile(r"\b(?:do you )?cover\s+(?P<place>.+)", re.I),
)

_TRAILING_PUNCT = re.compile(r"[?!.,]+$")
# Only strictly non-place filler is stripped here - words like "area" or
# "town" are deliberately excluded since they're legitimate parts of real
# place names ("Cape Town", "Broadacres Area" etc).
_TRAILING_FILLER = re.compile(
    r"\s+(please|yet|already|right now|now|currently|today)$", re.I)
_GENERIC_PLACES = {
    "my area", "my location", "my region", "my suburb", "my town",
    "here", "this area", "this location", "your network", "your area",
    "that area", "my home", "my house", "my street",
}


def extract_coverage_place(text: str) -> str | None:
    """Pull a place name out of an ad-hoc "do you have coverage in X?"
    style question, wherever it comes up in the conversation.

    Returns ``None`` when the message doesn't look like a coverage lookup,
    or when the "place" extracted is a generic phrase like "my area"
    rather than an actual town/suburb.
    """
    t = (text or "").strip()
    if not t:
        return None

    for pattern in _COVERAGE_PATTERNS:
        match = pattern.search(t)
        if not match:
            continue
        place = match.group("place").strip()
        place = _TRAILING_PUNCT.sub("", place).strip()
        if place.lower() in _GENERIC_PLACES:
            continue
        place = _TRAILING_FILLER.sub("", place).strip()
        place = _TRAILING_PUNCT.sub("", place).strip()
        if not place or len(place) > 60 or place.lower() in _GENERIC_PLACES:
            continue
        return place
    return None


def yes_no(text: str) -> str | None:
    """Classify a confirmation answer as ``"yes"``, ``"no"`` or ``None``."""
    t = _normalize(text)
    stripped = t.strip()

    # Explicit button payloads.
    if stripped in ("yes", "no"):
        return stripped

    negative_hit = _contains(t, tuple(f" {w}" for w in NO_WORDS))
    positive_hit = _contains(t, tuple(f" {w}" for w in YES_WORDS))

    # "no" beats "yes" - "yes it is still broken" is a negative answer.
    if negative_hit and not (positive_hit and not negative_hit):
        # "yes, that's better now" style answers should stay positive.
        if positive_hit and _contains(t, (" fixed", " resolved", " solved",
                                          " worked", " better", " helped")):
            if not _contains(t, (" not ", " didn't", " didnt", " no ", " nope",
                                 " still", " isn't", " isnt")):
                return "yes"
        return "no"
    if positive_hit:
        return "yes"
    return None
