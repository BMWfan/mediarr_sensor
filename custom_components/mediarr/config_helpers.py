"""Helpers for combining YAML/config-entry/options data."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return effective config for an entry.

    Entry options are merged over entry data, so options can override values
    configured at first setup.
    """
    data = deepcopy(dict(entry.data))
    if entry.options:
        data = _deep_merge(data, dict(entry.options))
    return data

