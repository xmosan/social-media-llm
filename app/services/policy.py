import re

POLITICS_KEYWORDS = [
    "election","vote","voting","campaign","senate","congress","president",
    "democrat","republican","parliament","prime minister","governor","mayor",
    "trump","biden","obama","clinton",
]

MUSIC_KEYWORDS = [
    "music","song","album","lyrics","spotify","apple music","soundcloud",
    "rapper","rap","singer","concert","playlist","beat","instrumental",
]

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())

def keyword_flags(text: str) -> dict:
    t = _normalize(text)
    reasons = []
    politics = any(k in t for k in POLITICS_KEYWORDS)
    music = any(k in t for k in MUSIC_KEYWORDS)

    if politics:
        reasons.append("politics_keyword_match")
    if music:
        reasons.append("music_keyword_match")

    needs_review = politics or music
    return {"politics": politics, "music": music, "needs_review": needs_review, "reasons": reasons}