# SDD-Light contributor rules

Use the workflow in order: Specify → Clarify → Plan → Tasks → Analyze →
Implement → Verify → AI Review → owner-approved Merge. Do not skip a stage;
record decisions and unresolved questions before implementation.

ChatGPT coordinates and reviews. Copilot implements only on an isolated branch
and opens a draft PR for review. Only the repository owner may approve a merge.
Never merge or release, deploy, or publish without explicit owner approval.

Choose the smallest fitting size:
- **S:** GitHub issue and PR, with regression proof.
- **M:** also maintain `spec.md`, `plan.md`, `tasks.md`, and `verification.md`.
- **L:** also maintain `research.md`, `contracts.md`, `risks.md`,
  `migration.md`, and `rollback.md`.

Run Python tests with the Home Assistant dependencies pinned by
`.github/workflows/metadata-tests.yml`; do not change CI or release workflows
under this SDD-Light setup. The current test command is:

```sh
docker run --rm --entrypoint python \
  -v "$PWD:/work:ro" -w /work \
  ghcr.io/home-assistant/home-assistant@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133 \
  -m unittest discover -s tests -v
```

Tests and examples must use synthetic fixtures and mock transports, never real
services or credentials. Do not commit credentials, tokens, HA runtime data
(including `.storage`), or runtime artifacts; keep secrets in Home Assistant's
secret handling and out of logs and PR evidence.

Preserve backward compatibility with mediarr-card: keep existing documented
sensor fields, services, and response contracts working. For intentional
contract changes, document them, test old-card behavior, and coordinate the
paired card change before claiming compatibility.

## Release policy

Publish HACS developer prereleases from working branches first (prerelease=true,
make_latest=false). Never merge to main or publish stable updates before the user
has tested the developer version and explicitly approved. Preserve existing tags.
Do not expose credentials, TMDB account tokens or HA runtime storage in artifacts.

Do not publish any prerelease until the user has explicitly approved it.
Prerelease approval does not approve merging to `main` or publishing a stable
release; each requires explicit user approval after testing.
