"""Explicitly opt-in, bounded live image comparison. Never imports the application.

python scripts/compare_image_models.py --env-file /private/.env --output /private/evaluation --live
Without --live, prints only the planned model/brief pairs. No secrets or provider
response bodies are written. The output directory must be outside the repository.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from app.services.image_provider import generate_openai_image, generate_google_image, ImageGenerationError

MODELS = {
    "sunburst": ("openai", "gpt-image-2.5-sunburst"),
    "flare": ("openai", "gpt-image-2.5-flare"),
    "banana21": ("google", "gemini-nano-banana-2.1"),
    "banana_pro": ("google", "gemini-3-pro-image"),
}
BRIEFS = {
    "architecture": "A believable limestone courtyard at dawn, a single pointed arch at the far left, finely weathered stone and soft reflected warm light. Architectural editorial photograph, understated and serene.",
    "desert": "A natural desert landscape before sunrise, low rolling sand dunes across the bottom fifth, subtle distant mountains, muted indigo and warm sand palette, realistic atmospheric depth and fine windblown sand detail. Premium landscape photograph.",
    "editorial": "A premium editorial still life: ivory linen draped near the bottom edge, a small unmarked aged brass bowl in the lower right corner, matte warm plaster wall, soft daylight from the left, tactile believable materials, restrained and elegant.",
}
CONSTRAINTS = (" Square 1:1 background for a Sabeel Studio reminder card. Keep the central 60 percent calm, "
               "low contrast and uncluttered for typography added later. No text, letters, calligraphy, "
               "symbols, logos, borders, people, supernatural effects or glowing ornaments. "
               "Use natural lighting and credible geometry; no rectangular panel behind the future text.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--briefs", nargs="+", choices=BRIEFS, default=list(BRIEFS))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Evaluation outputs must be outside the repository")
    planned = [(name, brief) for name in dict.fromkeys(args.models) for brief in dict.fromkeys(args.briefs)]
    if not args.live:
        print(json.dumps({"planned_requests": planned, "count": len(planned)}))
        return
    values = dotenv_values(args.env_file) if args.env_file else os.environ
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    results = []
    for name, brief in planned:
        provider, model = MODELS[name]
        filename = f"{name}_{brief}.png"
        record_path = output / f"{name}_{brief}.json"
        if record_path.exists():
            print(json.dumps({"model": model, "brief": brief, "skipped": "already_attempted"}), flush=True)
            continue
        prompt = BRIEFS[brief] + CONSTRAINTS
        record = {"model": model, "provider": provider, "brief": brief, "prompt": prompt,
                  "quality": "medium" if provider == "openai" else "1K", "started_at": time.time()}
        # Save intent before the paid request, so interruption does not trigger a duplicate on rerun.
        record_path.write_text(json.dumps({**record, "status": "started"}, indent=2))
        start = time.monotonic()
        print(json.dumps({"model": model, "brief": brief, "status": "started"}), flush=True)
        try:
            if provider == "openai":
                result = generate_openai_image(prompt, api_key=values.get("OPENAI_API_KEY"), model=model)
            else:
                result = generate_google_image(prompt, api_key=values.get("GEMINI_API_KEY"), model=model)
            result.image.save(output / filename)
            record.update(status="success", file=filename, size=list(result.image.size), usage=result.usage,
                          sha256=hashlib.sha256((output / filename).read_bytes()).hexdigest())
        except ImageGenerationError as exc:
            record.update(status="failed", code=exc.code, http_status=exc.status)
        record["elapsed_seconds"] = round(time.monotonic() - start, 2)
        record_path.write_text(json.dumps(record, indent=2))
        results.append(record)
        print(json.dumps({k: v for k, v in record.items() if k not in {"prompt", "usage", "sha256"}}), flush=True)
        if record.get("http_status") in {401, 402, 403, 404, 429}:
            print("Stopping this batch after a provider access/quota failure.", flush=True)
            break


if __name__ == "__main__":
    main()
