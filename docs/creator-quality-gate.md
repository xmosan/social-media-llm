# Creator quality gate — 8 October 2026

The first full matrix is **held**, not creator-validated. It attempted 36 complete
compositions, rendered 79 pages in 29 compositions, and safely blocked seven
compositions at the existing ten-page limit. Automated success is not a design,
context, scholarly, or real-device approval.

## Reproduce the evidence

Use the normal isolated application Python environment with Pillow RAQM support.
Install optional audit dependencies from `tests/quality/requirements.txt`. They
are not production dependencies. Provide six photographs explicitly, named after
the source keys in `tests/quality/sources.json`.

```sh
python -B scripts/evaluate_creator_quality.py --backgrounds /path/to/backgrounds --output /path/to/bundle
python -B scripts/build_quality_review.py /path/to/bundle
python -B scripts/evaluate_creator_quality.py --assess --output /path/to/bundle
```

Rendering completes the report even when individual cases are blocked. The
separate `--assess` command exits **1** until the release conditions pass. It checks
image bytes against their saved digests. `--human-reviews /path/to/reviews.json`
accepts independently completed declarations in the generated template format.
Never prefill reviewer identities, ratings, dates, or approvals on their behalf.
Declarations are evidence bookkeeping, not authentication: the release owner must
verify reviewer identity, qualifications, and provenance.

The report runs locally without third-party scripts. It contains exact source
records, per-page audits, phone previews at 320/390 CSS pixels, sequence navigation,
and blank human review forms. Image URLs include content hashes to avoid reviewing
stale cached pixels. `?batch=0` through `?batch=26` show all 79 pages in phone-width
contact sheets for this particular run.

The runner calls the actual card builder, sequence planner, and renderer, but
blocks network connections, uses local media, and imports neither app startup nor
the scheduler. It performs no database writes, Cloudinary uploads, or publishing.
Fresh photography is a separate explicit step through the existing Sabeel OpenAI
background service; six successful photos were reused across the comparison.

## Coverage and decision

Source snapshots were obtained from the connected canonical Qur'an library and
the collection-scoped sunnah.now Bukhari provider on 8 October 2026. The complete
normalized source record and returned metadata are retained with a digest. No
grade, narrator, translation, or quotation was invented. Length categories reflect
combined English and Arabic density, including the chain.

| Source | English words | Arabic characters | Feed / Story |
|---|---:|---:|---|
| Qur'an 94:6 | 6 | 28 | All three families render one page |
| Qur'an 2:153 | 17 | 110 | All three families render one page |
| Qur'an 2:282 | 261 | 1,208 | Editorial/paper 10 / 7; photography blocked / 8 |
| Bukhari 12 | 43 | 327 | Editorial/paper 2 / 2; photography 3 / 2 |
| Bukhari 1 | 47 | 632 | All three families render 2 / 2 |
| Bukhari 3 | 544 | 2,689 | All six combinations exceed the ten-page limit |

The controlled configuration is olive palette, modern typography, creator
signature, series title, English-first reading order, and **no optional reflection**.
It does not cover all palettes, brands, translations, generated reflections,
captions, source selection, or every possible generated background.

Automated evidence checks full contiguous canonical slices, painted source words
(whitespace layout may differ), font codepoint coverage, detached combining marks,
measured and painted safe bounds, dimensions, and minimum opaque-glyph contrast
in the final decoded JPEG against the backing pixels. It is not OCR and cannot
certify semantic context or the aesthetic quality of shaping. Narration/message
blocks additionally compare codepoint coverage; canonical slices retain order.

Release requires all 36 distinct cases, all engineering checks, intact artifacts,
all 36 creator assessments, at least 33 usable-without-repair creator ratings, and
all 36 qualified source/context approvals. Each declaration is tied to the exact
artifact digest; changing a source, composition, or image invalidates it.

Manual review remains required in production. The existing automation regression
test verifies that even `auto_approve` plus forced execution cannot publish cards
whose generation metadata requires visual review. The offline gate does not
modify publishing permission or turn automation on.

## Findings and fixes

The visual assessment covered every rendered page at 320 CSS pixels in Chromium.
It is a Codex assessment, not human validation. The following defects were repaired
in the shared renderer:

- A provider-separated Qur'anic pause mark could wrap onto a new line/page and
  acquire a dotted-circle base. Break opportunities now keep combining marks with
  the preceding word. All original source characters and slice offsets remain.
- Shorter continuation pages previously enlarged their font after partitioning,
  causing visible type-size jumps. Sequence pages now retain the established
  reading scale used to fit the sequence. Single cards keep their existing sizing.

The rendered batch still exposes these release limitations:

- The long-source limit is a real product limitation. Do not silently raise the
  publishing limit, omit Arabic, or shrink the entire source onto one card.
- Some long-source pages end mid-clause or bracketed phrase. All text survives,
  but context can be lost when a slide is viewed alone. Qualified review and a
  deliberate long-form treatment are needed.
- Bukhari 12 in feed photography produces a largely narration-only Arabic page.
  Its editorial alternative fits in two pages. Do not infer arbitrary narration
  boundaries or abbreviate chains with AI to improve a benchmark score.
- Editorial and paper designs are insufficiently distinct under the same modern
  brand kit. References/signatures are small at compact-phone scale.
- English containing the honorific currently uses the Arabic-capable serif font,
  which weakens modern-brand consistency. A proper mixed-font implementation must
  preserve shaping; replacing or dropping the honorific is not an acceptable fix.
- Photography is credible in the short Qur'an examples, but tiny photograph strips
  and aggressive object crops weaken some denser Hadith layouts.

The local visual evidence bundle is in the engineering workspace at
`Sabeel Model Evaluation/2026-10-08-quality-gate/final/review.html`. Baseline and
intermediate renderings are retained alongside it for comparison. No new database
migration, provider switch, automatic publication, or user-data rewrite is needed.

## Before creator trials

Use existing authenticated workspace roles for invited testers; no new public
admin access, shared credentials, or production publishing privileges are implied.
Create an isolated tester workspace and use draft/export tasks first when trials
are authorized. Do not contact or invite creators without an explicit instruction.

On physical iOS Safari and Android Chrome, ask solo creators to:

1. Start from a topic, inspect the proposed source, and choose a different source.
2. Edit reflection/caption independently, adjust layout without regenerating a
   good background, and preview every page at normal phone size.
3. Leave and recover the draft, including after a lost connection.
4. Review attribution and account, export a sequence, and explain the difference
   between saving, scheduling, and publishing before submitting anything.

Record completion, assistance needed, wrong taps, recovery failures, keyboard
obstruction, and misunderstandings about canonical source versus reflection.
No task-completion rate or physical-device result has been measured yet. Source
review should separately address translation attribution, full context, narrator
meaning, and the risk of isolated slides. Creator usability is not scholarly approval.
