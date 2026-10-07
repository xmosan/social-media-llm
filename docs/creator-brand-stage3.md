# Creator identity and editorial control — Stage 3

Studio and automation cards share `brand_kit`, `image_card`, measured typography,
Cloudinary media and the existing signed sequence/publication path. OpenAI model
configuration is unchanged. Manual visual review remains required.

## Persistent identity

`orgs.brand_kit` is a nullable JSON workspace default. Four curated palettes, two
bundled type styles, creator signature, series title, preferred family and two
composition variants are supported. `varied` deterministically chooses a
composition by source reference, with the same composition throughout a sequence.
Signature/title must fit at readable size; unsupported symbols or overwide names
are rejected instead of reduced or clipped. Arabic and English passages containing
Arabic honorifics use the bundled Arabic-supporting serif face in either type style.

Studio edits are per draft until **Save workspace brand** is selected. The endpoint
is organization scoped, requires login, locks the workspace row, and compares a
revision digest to prevent concurrent overwrites. Existing drafts retain the kit
in their signed media manifest; caption-only edits and export keep that snapshot.
Automation generation/preview consumes the same workspace kit while keeping the
plan's selected design family. Changing the default does not rewrite old posts.

Audience and purpose guide newly generated commentary only. Optional reflection,
canonical source, social caption, photograph and layout remain distinct. Full
Arabic, source metadata and returned attribution are visible during review; absent
narrator, grade or translator is shown as missing. No guessed attribution is added.

## Arabic display excerpts

For the exact Bukhari 1 Arabic and English source revisions, a hash-pinned boundary
separates narration from quoted speech for typography only. Narration stays at
42–44 px (15–16 px at a 390 px phone width), with larger type for the Hadith itself.
Source characters and order do not change. A compact footer and smaller photo band
let the full Arabic chain and full message share one page; the full translation
occupies another. There are no chain-only introductory slides in this example.
Unknown records retain the existing complete-source layout until their boundaries
are inspected. No punctuation heuristic or language model labels Prophet's speech.

The full provider Arabic is always stored in `card_message.arabic_text` and source
metadata. A separate `arabic_display` contains the exact display range and source
hash. The initial optional boundary is **only** the reviewed fixture revision of
Sahih al-Bukhari 1: start at Umar's name and retain the rest of the returned report.
It is a literal excerpt, not a rewritten chain or an inferred narrator.

The control requires an explicit creator selection. Images label it **Arabic
excerpt**, review shows the full chain and excerpt, and exports include the full
source plus exact range. Captions retain full canonical Arabic. Changed references,
provider revisions, ranges, other narrations and Qur'an excerpts are rejected. Other
Hadith records default to full narration. No automatic "last three narrators"
heuristic exists. This is an editorial option, **not qualified scholarly approval**;
expanding the catalog requires checking each exact record and a meaningful boundary.

## Deployment

Before deploying, run `scripts/migrate_brand_kit.py` with DATABASE_URL supplied
securely. It adds one nullable JSON column using explicit PostgreSQL DDL, a five
second lock timeout and a thirty second statement timeout. No table rewrite,
backfill, deletion or startup auto-migration. The script is idempotent. Startup
continues to validate schema read-only. Rollback the application if needed and leave
the added column in place to preserve saved kits. Test the migration on disposable
PostgreSQL first. Existing published posts and receipts remain compatible.

## Verification boundary

Automated tests cover workspace isolation and stale edits, real PostgreSQL
concurrency/migration/startup, signed draft snapshots/export, automation branding,
source equality, excerpt offsets/tampering, contrast at glyphs, Story safe areas,
overwide signatures and browser recovery/stale-response behavior. The Stage 3 visual
report uses the three original source fixtures, an existing genuine OpenAI photo,
and actual final JPEGs. Phone-size visual assessment is by Codex, not creator or
qualified source review. The 36-output release matrix and creator testing belong
to Stage 4 and subsequent work. No creator permissions are provisioned in Stage 3.
