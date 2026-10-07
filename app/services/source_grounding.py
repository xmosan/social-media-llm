"""Resolve selected source identity against the database/provider, not client text."""

from app.security.ownership import require_content_item, resource_id
from app.services.quran_serialization import normalize_quran_verse


def resolve_selected_source(db, org_id: int, source_type: str, payload: dict, user_id=None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Select a valid source record")
    if source_type == "quran":
        from app.services.quran_service import get_verse_by_reference, parse_quran_reference
        item_id = payload.get("id") or payload.get("item_id")
        if item_id is None:
            reference = payload.get("reference") or payload.get("verse_key")
            if not reference:
                raise ValueError("Select a Quran verse from the library")
            item = get_verse_by_reference(db, reference)
            if item is None:
                raise ValueError("The selected Quran verse is unavailable")
            item_id = item.id
        item = require_content_item(db, org_id, item_id, user_id=user_id)
        if item.item_type != "quran":
            raise ValueError("The selected source is not a Quran verse")
        canonical = normalize_quran_verse(item)
        supplied_reference = payload.get("reference") or payload.get("verse_key")
        if supplied_reference and parse_quran_reference(supplied_reference) != (canonical["surah_number"], canonical["ayah_number"]):
            raise ValueError("Selected verse identity and reference do not match. Select the verse again.")
    elif source_type == "hadith":
        from app.services.hadith_service import get_hadith_by_reference
        collection = payload.get("collection_key")
        number = payload.get("hadith_number")
        if not collection or number is None:
            raise ValueError("Select a Hadith with a collection and narration number")
        page_hint = {"provider_page": payload["provider_page"]} if payload.get("provider_page") is not None else {}
        canonical = get_hadith_by_reference(collection, resource_id(number), **page_hint)
        if not canonical:
            raise ValueError("The selected Hadith is unavailable from the configured provider")
        if canonical.get("collection_key") != collection or str(canonical.get("hadith_number")) != str(number):
            raise ValueError("The Hadith provider returned a different source record")
        if payload.get("reference") and payload["reference"] != canonical.get("reference"):
            raise ValueError("Selected Hadith identity and reference do not match. Select it again.")
    else:
        return payload

    if not canonical.get("reference") or not canonical.get("translation_text"):
        raise ValueError("The selected source is incomplete")
    # Detect stale/modified client data instead of silently changing the selection.
    for field in ("arabic_text", "translation_text", "narrator", "grade"):
        supplied = payload.get(field)
        if supplied in (None, "") and canonical.get(field) in (None, ""):
            continue
        if supplied is not None and supplied != canonical.get(field):
            raise ValueError("Selected source data changed. Select the source again before continuing.")
    return canonical


def validate_source_card(card, canonical: dict, source_type: str):
    if card is None:
        return
    headline = (canonical.get("card_text") if source_type == "hadith" and not (isinstance(card, dict) and card.get("source_complete")) else None) or canonical.get("translation_text")
    if (not isinstance(card, dict) or card.get("headline") != headline
            or card.get("eyebrow") != canonical.get("reference")
            or (card.get("arabic_text") or "") != (canonical.get("arabic_text") or "")):
        raise ValueError("Card text does not match the selected source. Rebuild the card before saving.")
    for card_field, source_field in (("hadith_narrator", "narrator"), ("hadith_grade", "grade"), ("hadith_collection", "collection")):
        if card_field in card and card[card_field] != canonical.get(source_field):
            raise ValueError("Card metadata does not match the selected source")


def saved_source_type(post):
    return post.source_type if post.source_type in {"quran", "hadith"} else post.source_foundation


def validate_saved_source_snapshot(post):
    """Check that publishing still uses the source snapshot saved by Studio/automation."""
    source_type = saved_source_type(post)
    if source_type not in {"quran", "hadith"}:
        return
    metadata = post.source_metadata or {}
    canonical = {**(metadata.get("metadata") or {}), **metadata}
    if not canonical.get("reference") or not canonical.get("translation_text"):
        raise ValueError("This legacy post has no complete source record. Select its source again in Studio.")
    if post.source_reference != canonical["reference"] or post.source_text != canonical["translation_text"]:
        raise ValueError("Saved source text or reference does not match its source record. Rebuild the post in Studio.")
    validate_source_card(post.card_message, canonical, source_type)


def resolve_saved_source(db, post, user_id=None):
    source_type = saved_source_type(post)
    payload = dict(post.source_metadata or {})
    if source_type not in {"quran", "hadith"}:
        return None
    nested = payload.get("metadata") or {}
    payload = {**nested, **payload}
    if source_type == "quran" and payload.get("original_id"):
        payload.setdefault("id", payload["original_id"])
    payload.setdefault("reference", post.source_reference)
    return resolve_selected_source(db, post.org_id, source_type, payload, user_id)


def validate_source_edit(post, changes: dict):
    """Editing social copy must not detach a saved post from its source record."""
    source_type = saved_source_type(post)
    protected = {"source_text", "source_reference", "source_foundation", "library_item_id"}
    if source_type not in {"quran", "hadith"}:
        if changes.get("source_foundation") in {"quran", "hadith"}:
            raise ValueError("Select a verified source in Studio before creating a scripture post")
        return
    for field in protected.intersection(changes):
        if changes[field] != getattr(post, field):
            raise ValueError("This post's source is fixed. Select a new source in Studio to create another post.")
    if "card_message" in changes:
        canonical = {**((post.source_metadata or {}).get("metadata") or {}), **(post.source_metadata or {})}
        if not canonical.get("reference") or not canonical.get("translation_text"):
            raise ValueError("This legacy post has no verified source record. Select the source again in Studio.")
        validate_source_card(changes["card_message"], canonical, source_type)
