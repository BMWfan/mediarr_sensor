"""Summarize available Plex episodes relative to the furthest watched position."""


def episode_progress(records):
    slots = {}
    for raw in records:
        try:
            season, episode = int(raw["parentIndex"]), int(raw["index"])
            viewed = int(raw.get("viewCount", 0)) > 0
            started = viewed or int(raw.get("viewOffset", 0)) > 0
        except (KeyError, ValueError, TypeError):
            return {"available": False}
        if season <= 0 or episode <= 0:
            continue  # Specials must not revive old seasons in the main selection.
        slot = slots.setdefault((season, episode), {"viewed": False, "started": False})
        slot["viewed"] |= viewed
        slot["started"] |= started
    frontier = max(
        (key for key, value in slots.items() if value["started"]), default=None
    )
    pending = sorted(
        key
        for key, value in slots.items()
        if not value["viewed"] and (frontier is None or key > frontier)
    )
    ranges = []
    for season, episode in pending:
        if (
            ranges
            and ranges[-1]["season"] == season
            and ranges[-1]["last"] == episode - 1
        ):
            ranges[-1]["last"] = episode
        else:
            ranges.append({"season": season, "first": episode, "last": episode})
    return {
        "available": True,
        "started": frontier is not None,
        "position": (
            {"season": frontier[0], "episode": frontier[1]} if frontier else None
        ),
        "unwatched_count": len(pending),
        "ranges": ranges,
    }


async def section_episode_progress(client, source, section):
    """One paged section query, not one request per show or episode."""
    groups, start = {}, 0
    while True:
        container = (
            await client.get(
                source,
                f"/library/sections/{section}/all",
                type=4,
                **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": 1000},
            )
        ).get("MediaContainer", {})
        records = container.get("Metadata", [])
        for raw in records:
            key = str(raw.get("grandparentRatingKey", ""))
            if key.isdigit():
                groups.setdefault(key, []).append(raw)
        start += len(records)
        if start >= int(container.get("totalSize", container.get("size", start))):
            break
        if not records:
            # Do not present an incomplete page as zero new episodes.
            from .media_details import MediaDetailsError

            raise MediaDetailsError(
                "library_incomplete", "Plex episode progress is incomplete."
            )
    return {key: episode_progress(records) for key, records in groups.items()}
