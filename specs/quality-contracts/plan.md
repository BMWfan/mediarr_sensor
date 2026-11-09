# Plan

1. Use a separate branch from current main.
2. Add read-only CI for syntax, dependency advisories and redacted secret scanning.
3. Publish identical v1 JSON fixtures and test actual frontend adapters/backend unavailable response.
4. Run new checks and existing synthetic suites; review diff for runtime changes.
5. Open draft PR for owner review. Existing developer runtime stays byte-identical; no release is performed.

Risks: scanners can fail on network/advisory service outages; fail visibly rather than treating failures as clean. No broad allowlist or ignored vulnerabilities. Restore previous workflows to roll back; fixtures are additive.
