"""Sonarr2 integration for Mediarr."""
from .sonarr import SonarrMediarrSensor


class Sonarr2MediarrSensor(SonarrMediarrSensor):
    def __init__(self, session, api_key, url, max_items, days_to_check):
        super().__init__(session, api_key, url, max_items, days_to_check, instance_name="Sonarr2")
