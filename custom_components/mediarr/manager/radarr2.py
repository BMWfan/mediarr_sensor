"""Radarr2 integration for Mediarr."""
from .radarr import RadarrMediarrSensor


class Radarr2MediarrSensor(RadarrMediarrSensor):
    def __init__(self, session, api_key, url, max_items, days_to_check):
        super().__init__(session, api_key, url, max_items, days_to_check, instance_name="Radarr2")
