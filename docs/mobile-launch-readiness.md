# Mobile release and launch assessment — 8 October 2026

The creator workflow is: start with an idea or an exact source, inspect its
provenance, create a design, review every page, edit a separate caption, then save,
export, schedule, or publish to the intended account.

This interface release improves that workflow. **It does not approve an unrestricted
public launch.** Creator, qualified source/context, and physical-device reviews
remain outstanding. The series assistant remains future internal work.

## Changes

- Feed previews use the available phone width (284 px on a 320 px viewport,
  354 px on a 390 px viewport). A larger reader shows the original image and
  pager, including Story overlays, without duplicating render or review state.
  Escape returns to the editor, and changing pages resets the reader scroll.
- Single-page posts retain their source/page label without disabled pager buttons.
  The review checkbox remains explicit and only enables after all images load.
- Reflection suggestions now appear in Source & reflection. The obsolete Ask pane
  caused a runtime failure after a successful provider response. Acceptance and
  undo preserve canonical source text and invalidate the old visual.
- Saving is compact, has a busy state, and distinguishes device recovery from
  workspace persistence. Export is in More. Early work without an Instagram
  account is explicitly local; the home screen explains how to connect an account.
- Caption editing remains independent; its generated preview is collapsed rather
  than repeating the entire caption above the field.
- Sharing presents account, source, and an explicit later/now choice. Only the
  selected publishing action is visible. Enter cannot submit a hidden schedule
  action. A repeated image preview is collapsed below the phone controls.
- Scheduling shows the device timezone and uses local calendar components for
  datetime-local defaults. Past dates fail before a save. Account-health requests
  have a timeout and ignore results from a different account/editor session.
- Removed the Studio discard link that targeted a different, hidden post modal.
  Keep as a draft is available; this change adds no deletion behavior.

The canonical source, card, visual, Cloudinary, draft, automation, and publishing
services are unchanged. No schema migration or production data rewrite is needed.
CSS/JS asset versions are advanced. Rollback is the preceding application release.

## Evidence and limits

Local verification uses controlled HTTP fixtures and existing actual Arabic-first
rendered images. It imports no production database, scheduler, or provider client.
Fixtures verify interaction, not live provider behavior. Cases exercised: guided
Qur'an and Hadith entry; search failure and retry; reflection comparison,
acceptance, undo; feed and two-page Story preview; every-page review; Escape and
focus restoration; draft save/reload recovery; explicit publishing mode; and early
saving without an account. Responsive checks cover 320, 390, 430 and 1280 px.
No horizontal overflow was observed in inspected editor controls.

Automated verification includes existing source/ownership/publishing/provider/
recovery tests, new UI regression cases, disposable PostgreSQL concurrency and
backup/restore checks, a new registration/login/workspace-isolation case, and real
application startup with external jobs disabled. No production post is scheduled
or published by these checks. The production follow-up must verify health, the
served assets, a real draft's source/design/caption persistence, export and account
health. Record the deployed SHA and results in the evidence bundle.

The evidence bundle is outside Git at
`Sabeel Model Evaluation/2026-10-08-mobile-launch-readiness/review.html`.
It distinguishes local fixtures, real production flows, automated assertions,
Codex visual assessment, and unperformed human reviews. It contains the final
counts and deployment verification rather than treating a screenshot as proof of
backend readiness.

## Public-launch decision: hold

| Requirement | Current evidence | Remaining acceptance condition |
|---|---|---|
| Mobile interaction | Responsive browser walkthrough; automated failure/recovery checks | Actual iOS Safari and Android Chrome, keyboard open, navigation/back, reconnect, download and share-sheet tasks with creators |
| Source and visual quality | Existing Arabic-first 36-case matrix: 29 compositions rendered, seven blocked by page limits; readability recovery tested separately | Complete qualified source/context review and creator assessments, plus an explicit product treatment for sources exceeding the supported sequence length |
| Admission and AI spending | Private-preview signup gate, PostgreSQL daily attempt/concurrency budgets, login throttling and creator allowance UI are implemented; see `launch-protections.md` and its deployment evidence | Keep admission closed pending controlled cohort onboarding. Verify upstream spending limits/alerts and edge controls separately; app call counters are not a currency ledger |
| New creator onboarding | Isolated PostgreSQL registration, login and private workspace checks; disconnected UI explains account requirement | Fresh creator completes Meta connection and feed/Story eligibility checks. Current product requires Instagram even for workspace drafts/export; account-independent drafting is a separate product change |
| Operations | Live health/readiness checks; disposable PostgreSQL dump/restore; hardened publishing regressions; backup freshness/recovery checks and the isolated restore tool/runbook in `backup-recovery.md` | Run the current S3 restore with available operator credentials; verify external alert delivery. A passing fixture restore does not verify the current S3 backup. Low-load capacity observations do not establish launch capacity |
| Railway status | App and Postgres online; one opaque Postgres warning remains exposed by the plugin | Inspect warning details in Railway; do not assume the count proves failure or resolution |

The current audit is not a load test, penetration test, new live Instagram
publication, real-device review, or human creator/source approval. The existing
quality gate and manual approval remain enforced. Do not mark the human review
forms complete on a creator's or qualified reviewer's behalf.

## Order of remaining work

1. Close admission, abuse, and paid-generation budget gaps before promoting public
   signup. Confirm current backups, alerting, recovery and operational capacity.
2. Run a small controlled creator pilot on physical phones and a separate qualified
   source/context review. Test first-account connection, draft/export, reconnect,
   and explicitly authorized test scheduling/publication in an isolated workspace.
3. Resolve observed usability problems and agree on supported long-source behavior;
   rerun the affected quality gate. Make a documented launch decision from evidence.
4. Develop the series planner privately using the shared canonical services,
   resumable per-post jobs, explicit batch budgets, and creator review. It is not a
   prerequisite that should expand this interface release.
