"""Smart Handoff: high-confidence, language-aware requests to speak to a person.

Pure logic only: no network calls, customer-text storage, or AI quota usage.
Return None for uncertain messages rather than creating unwanted handoffs.
"""

from __future__ import annotations

import re

HUMAN_REQUESTED = "human_requested"

_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "\u0060": "'", "´": "'"})

_HUMAN_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    # Uzbek
    r"\b(?:akkaunt\s+egasi|egasi|operator|menejer|xodim|odam|inson|admin)\s+bilan\s+(?:gaplash\w*|suhbatlash\w*|bog'lan\w*|aloqa\s+qil\w*)",
    r"\b(?:meni\s+|menga\s+)?(?:operatorga|menejerga|egasiga|xodimga|odamga|insonga)\s+(?:ul\w*|bog'la\w*|o'tkaz\w*|chaqir\w*)",
    r"\b(?:operator|menejer|egasi|xodim|odam|inson)\w*\s+(?:ulab|bog'lab|chaqirib)\s+ber\w*",
    r"\b(?:egasi|operator|menejer|xodim)\s+(?:o'zi\s+)?(?:yoz\w*|javob\s+ber\w*|aloqaga\s+chiq\w*)",
    r"\b(?:tirik|haqiqiy)\s+odam\b.{0,40}\b(?:javob\s+ber\w*|gaplash\w*|kerak)\b",
    # English
    r"\b(?:speak|talk|chat)\s+(?:to|with)\s+(?:(?:an?|the)\s+)?(?:real\s+)?(?:human|person|operator|agent|owner|manager)\b",
    r"\b(?:connect|transfer|put)\s+me\s+(?:through\s+)?(?:to|with)\s+(?:(?:an?|the)\s+)?(?:real\s+)?(?:human|person|operator|agent|owner|manager)\b",
    r"\b(?:i\s+(?:want|need)\s+(?:to\s+reach\s+)?|get\s+me\s+)(?:(?:an?|the)\s+)?(?:real\s+)?(?:human|person|operator|agent|owner|manager)\b",
    # Russian
    r"\b(?:поговорить|связаться|пообщаться)\s+с\s+(?:живым\s+)?(?:человеком|оператором|сотрудником|менеджером|владельцем)\b",
    r"\b(?:соедините|свяжите|переключите)\s+(?:меня\s+)?с\s+(?:оператором|человеком|менеджером|владельцем)\b",
    r"\b(?:мне\s+(?:нужен|нужна)|позовите)\s+(?:живой\s+)?(?:оператор|человек|сотрудник|менеджер|владелец|оператора|менеджера|владельца)\b",
))

# A clear refusal is not a request. A false negative is safer than a false handoff.
_NEGATIONS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:operator|menejer|egasi|xodim|odam|inson)\s+bilan\s+(?:gaplashishni|suhbatlashishni)\s+xohlamayman\b",
    r"\b(?:i\s+do\s+not|i\s+don't)\s+(?:want|need)\s+to\s+(?:speak|talk|chat)\s+(?:to|with)\b",
    r"\bне\s+хочу\s+(?:говорить|поговорить|общаться)\s+с\b",
))


def detect_handoff_reason(text: str | None) -> str | None:
    """Recognize an explicit request for a human; return None for everything else.

    This intentionally does NOT infer unsolved AI questions or dissatisfaction:
    those require a separately tested, structured AI decision path.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = " ".join(text[:4000].translate(_APOSTROPHES).casefold().split())
    if any(pattern.search(normalized) for pattern in _NEGATIONS):
        return None
    if any(pattern.search(normalized) for pattern in _HUMAN_PATTERNS):
        return HUMAN_REQUESTED
    return None
