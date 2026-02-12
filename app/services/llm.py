from typing import Any

def generate_draft(source_text: str, media_hint: str | None = None) -> dict[str, Any]:
    text = (source_text or "").strip()

    caption = (
        f"{text}\n\n"
        "May Allah bless you and increase you in خير.\n"
        "—\n"
        "Follow for updates."
    ).strip()

    hashtags = ["Islam", "Dawah", "Community", "Reminder", "Barakah"]
    alt_text = media_hint or "An image related to the post content."

    return {"caption": caption, "hashtags": hashtags, "alt_text": alt_text}