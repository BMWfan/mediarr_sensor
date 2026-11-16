# Plan — library provenance

## Specify / clarify
Use the confirmed defect and prepared pilot handoff in card Issue #44. M size for the producer/card boundary. All data synthetic. Latest user request authorizes implementation and separate reviewable Draft PRs, not deployment. No new feature choices are needed: retain waiting/discover/ready categories, fix only evidence and request labels.

## Design and tasks
Implement additive producer status contract. Add failing focused regressions first; preserve request status verbatim in producer and use separate explicit media evidence in consumer. Keep strict file booleans and ID merge rules. Add meaningful real-HA browser regression for categories/legacy labels; run existing nearby model and backend suites before full affected browser coverage.

## Analyze / risks / rollback
Legacy status4-only rows move from ready to waiting intentionally. Failed requests with real library/file evidence remain ready. Unknown/malformed codes do not imply availability. Partial TV does not claim complete seasons. Existing producer date fields are not import evidence; leave them unchanged. Additional fields do not repair old frontend logic. Rollback the paired source commits separately, with no storage migration; document compatibility limits.

## Validation and token discipline
Read only source status paths, closest tests and interface docs. Record actual red/green outputs, pinned HA version and tested commits. Use SPEC-046 measurement format: this is a single pilot, no controlled A/B or claimed token savings. Tokens/cached usage UNMEASURED if counters unavailable. Log duration/tool calls only with explicit coverage boundaries and keep failures/rework visible.
