"""Separate provider-tagged editorial notes from the exact translation body.

Never infer footnotes from plain-text digits. The original provider HTML and
returned note text remain available for provenance and source review.
"""
import hashlib
import re
from bs4 import BeautifulSoup


def parse_translation(record: dict) -> dict:
    raw = record.get("text")
    if not isinstance(raw, str) or not raw.strip() or not record.get("resource_id"):
        raise ValueError("The provider translation is incomplete")
    soup = BeautifulSoup(raw, "html.parser")
    if soup.find(["script", "style", "iframe"]):
        raise ValueError("Unexpected markup in the provider translation")
    notes = []
    returned = record.get("foot_notes") or {}
    for marker in soup.find_all("sup"):
        note_id = str(marker.get("foot_note") or "")
        if not note_id.isdigit():
            raise ValueError("Unidentified superscript in the provider translation; source review is required")
        raw_note = returned.get(note_id)
        if raw_note is not None and not isinstance(raw_note, str):
            raise ValueError("Unexpected provider footnote format")
        note = BeautifulSoup(raw_note or "", "html.parser")
        notes.append({"id": note_id, "marker": marker.get_text(),
                      "text": note.get_text("\n", strip=True) or None,
                      "raw_html": raw_note, "status": "returned" if raw_note else "unavailable"})
        marker.decompose()
    body = soup.get_text().strip()
    if not body:
        raise ValueError("The provider translation has no body text")
    return {"version": 1, "resource_id": str(record["resource_id"]),
            "resource_name": record.get("resource_name"), "raw_html": raw,
            "body": body, "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "footnotes": notes}


def verified_translation_repair(item: dict, translation: dict, arabic: str, attribution: dict) -> dict:
    """Prepare a conservative update; refuse changes to source words or Arabic.

    Legacy imports stripped tags and mislabeled resource 20 as 131. Exact text
    and verse identity checks establish the actual resource, without substituting
    another translation. Saved posts are outside this repair's scope.
    """
    meta = item.get("meta") or {}
    verse_key = meta.get("verse_key")
    if not verse_key or translation.get("verse_key") != verse_key:
        raise ValueError("Provider and library verse identities do not match")
    chapter, verse = verse_key.split(":")
    if item.get("title") != f"Surah {int(chapter)}, Verse {int(verse)}":
        raise ValueError("Library title and verse identity do not match")
    if not arabic or arabic != item.get("arabic_text"):
        raise ValueError("Provider and library Arabic do not match")
    parsed = parse_translation(translation)
    legacy = re.sub(r"<[^>]+>", "", parsed["raw_html"]).strip()
    if item.get("text") not in (legacy, parsed["raw_html"], parsed["body"]):
        raise ValueError("Provider and library translation words do not match")
    name = translation.get("resource_name") or attribution.get("translation_name")
    parsed["resource_name"] = name
    correction = meta.get("translation_correction") or {
        "previous_translation_id": meta.get("translation_id"),
        "method": "exact_provider_text_and_arabic_match",
    }
    return {"text": parsed["body"], "translation": name,
            "meta": {**meta, "translation_id": parsed["resource_id"],
                     "translator": attribution.get("author_name"), "translation_name": name,
                     "quran_translation": parsed, "translation_correction": correction}}
