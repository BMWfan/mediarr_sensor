# Quality and compatibility (M)

Parent: #19. Implements remaining SPEC-002/003; governance and manual release authorization are already merged. User authorized direct implementation instead of Copilot on 2026-11-09.

Acceptance: read-only, non-mutating checks; pinned scanner versions and action commits; dependency and current-tree secret scanning; shared synthetic contract examples consumed by both repositories; existing backend authorization/error and browser fallback tests remain mandatory. No runtime/version change, credentials, release, deployment or ruleset changes.

Scope limits: dependency audits evaluate the resolver/lockfile at scan time, not every deployed HA installation. A clean current-tree secret scan does not certify historical commits. Contract examples supplement existing request/permission tests; they do not prove production connectivity.
