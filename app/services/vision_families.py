"""Versioned Sabeel Vision catalog shared by Studio and automations.

Recipes describe backgrounds only. Source text never enters an image prompt.
Legacy IDs remain stable; saved posts and their media are never rewritten.
"""
import hashlib
import json
import secrets

RECIPE_VERSION = 1
SCENE_FAMILIES = {
    "luxury_editorial": {
        "label": "Material Editorial", "description": "Soft plaster, linen and natural light.",
        "brief": "A believable interior photograph of a smooth warm ivory plaster wall. Fine subtle texture, soft diffuse overcast light and consistently light tones throughout the reading area. A low pale wooden ledge with a small fold of natural linen only below the reading area. No plants, vases, branches, dramatic shadows, coarse stone, dark edges or decorative objects. Material detail should feel photographic, softly imperfect and ordinary rather than glossy or computer-rendered.",
        "variations": ("Warm chalk and ivory linen.", "Pale limestone and unbleached cotton.", "Warm grey plaster and pale oak."),
    },
    "desert_glow": {
        "label": "Desert Light", "description": "Low dunes and quiet morning skies.",
        "brief": "Quiet low dunes photographed just before sunrise, a large pale dust-blue and warm cream sky. Restrained natural colour, fine realistic sand and subdued shadows. Documentary landscape photography, not a fantasy desert or a movie poster. Keep every ridge and shadow below the reading area.",
        "variations": ("Soft early daylight and a low wind-shaped dune at the right.", "Diffuse dawn light and a distant low ridge at the left.", "Overcast morning and a flat sandy plain."),
    },
    "midnight_oasis": {
        "label": "Quiet Night", "description": "Deep blue dusk and simple stone.",
        "brief": "A believable outdoor architectural photograph at late blue hour. An uninterrupted evenly dark navy sky above a low plain stone courtyard wall. No trees, plants, lights, lanterns, stars, doorways, bright stone edges or objects extending into the reading area. Subtle realistic atmosphere, quiet true photographic exposure. The low wall and a small amount of terrace floor below the reading area provide credible depth.",
        "variations": ("Muted navy and weathered limestone.", "Dark slate blue and ordinary grey stone.", "Deep dusk blue and subdued warm stone."),
    },
    "emerald_forest": {
        "label": "Quiet Nature", "description": "Still water and soft skies. Roomy layouts only.",
        "brief": "A real-looking still lake on an overcast morning with a low distant tree line and muted sage-grey atmosphere. The reading area is open pale sky and softly reflected water with no contrasting branches, objects or hard horizon crossing it. A narrow band of realistic reeds and a distant soft tree line remain below the reading area. Believable nature photography, diffuse light, restrained color, no supernatural mist, dramatic rays or fantasy.",
        "variations": ("Muted sage, distant trees and a few low reeds.", "Pale grey sky and a quiet low grassy shore.", "Soft blue-grey water and a distant low wooded bank."),
    },
}
DESIGNED_FAMILIES = {"editorial", "quiet_photography", "minimal_paper"}
DESIGN_FAMILIES = DESIGNED_FAMILIES | SCENE_FAMILIES.keys()
REUSABLE_FAMILIES = {"quiet_photography"} | SCENE_FAMILIES.keys()

# Preserve legacy renderer behavior while removing the previously conflicting
# preview/run mappings. The four revised families use their canonical IDs.
LEGACY_FAMILIES = {"sacred_black", "celestial_night", "parchment_manuscript", "luxury_marble",
                   "sacred_desert", "royal_velvet", "midnight_ink", "dawn_horizon",
                   "obsidian_stone", "ocean_depth", "warm_copper"}
FAMILY_TO_SCENE_KEY = {key: key for key in DESIGN_FAMILIES | LEGACY_FAMILIES}
FAMILY_TO_RENDER_STYLE = {
    "sacred_black": "quran", "celestial_night": "laylulqadr", "parchment_manuscript": "scholar",
    "luxury_marble": "kaaba", "sacred_desert": "madinah", "royal_velvet": "midnight",
    "midnight_ink": "kaaba", "dawn_horizon": "madinah", "obsidian_stone": "quran",
    "ocean_depth": "fajr", "warm_copper": "desert", **{key: key for key in DESIGN_FAMILIES},
}


def recipe_binding(family, post_format):
    if family not in SCENE_FAMILIES:
        return None
    return {"family": family, "recipe": RECIPE_VERSION,
            "format": "story_9_16" if post_format == "story_9_16" else "feed_4_5"}


def scene_prompt(family, size, bounds, direction=None, history=None):
    """Use measured bounds from EVERY page sharing this photograph."""
    spec = SCENE_FAMILIES[family]
    width, height = size
    zones = sorted(set(tuple(round(v / (width if i % 2 == 0 else height)*100, 1)
                                   for i, v in enumerate(box)) for box in bounds))
    candidates = []
    for index, variation in enumerate(spec["variations"]):
        signature = hashlib.sha256(json.dumps([family, RECIPE_VERSION, index, direction or ""]).encode()).hexdigest()
        candidates.append((signature, variation))
    history = history or {}
    unused = [item for item in candidates if item[0] not in history]
    signature, variation = secrets.choice(unused) if unused else min(candidates, key=lambda item: history[item[0]])
    bottom = min(97, max(box[3] for box in zones)+3)
    prompt = (spec["brief"] + " " + variation +
        (" Creator direction (subject to the reading-area and realism requirements): " + direction + "." if direction else "") +
        f" Portrait {'9:16 Story' if height == 1920 else '4:5 feed'} composition. "
        f"The complete reading area runs from 5% down to {bottom}% of the image height, across the middle 86% of its width. "
        "It must have a single consistent lightness: " + ("evenly dark" if family == "midnight_oasis" else "evenly pale") + ". "
        f"Confine the foreground scene to below {bottom}% height. Do not place any object in the reading area. "
        "This is a background for exact typography added separately. Maintain a continuous natural scene, "
        "with low-detail evenly lit areas under these text rectangles (left, top, right, bottom, percentages): " + str(zones) +
        ". Keep major objects and strong edges away from these areas, including the small reference. "
        "Do not draw rectangles, panels, borders or empty label boxes. No lettering, pseudo-script, Arabic, symbols, logos, "
        "people, sacred-site reconstructions, supernatural imagery, glow, gold decoration, excessive blur or glossy CGI. "
        "Preserve photographic depth and realistic materials. No text anywhere.")
    return prompt, {"family": family, "recipe_version": RECIPE_VERSION, "prompt_signature": signature,
                    "reading_bottom_percent": bottom, "text_zones": zones}
