# Release policy

Publish HACS developer prereleases from working branches first (prerelease=true,
make_latest=false). Never merge to main or publish stable updates before the user
has tested the developer version and explicitly approved. Preserve existing tags.
Do not expose credentials, TMDB account tokens or HA runtime storage in artifacts.
