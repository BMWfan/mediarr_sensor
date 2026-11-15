# Compatibility

Recommended pair: Card 0.6.0-dev.11 / sensor 0.8.0-dev.10, on the existing pinned
HA Core 2026.11.1 test target. Existing entities/services and old library commands
remain supported. Optional revision/scope fields are additive. Older backend
responses omit revision, so the new card uses the original full-page contract.
Old cards do not gain the new frontend behavior or request reduction.

Install sensor first and restart HA; then select the card beta in HACS and
reload the frontend. No user configuration migration or production write is
required. These branches include the earlier movie-collections developer work;
PRs are stacked on that branch, not a duplicate merge into main.
