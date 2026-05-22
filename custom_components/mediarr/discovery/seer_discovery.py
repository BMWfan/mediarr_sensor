"""Jellyseerr/Overseerr discovery features for Mediarr."""
import logging
import asyncio
from datetime import datetime
from ..common.tmdb_sensor import TMDBMediaSensor
import async_timeout

_LOGGER = logging.getLogger(__name__)

# In seer_discovery.py
class SeerDiscoveryMediarrSensor(TMDBMediaSensor):
    """Seer sensor for discover/trending/popular."""
    
    def __init__(self, session, api_key, url, tmdb_api_key, max_items, content_type, media_type=None, filters=None):
        """Initialize the sensor."""
        # Initialize TMDBMediaSensor with tmdb_api_key
        super().__init__(session, tmdb_api_key)
        
        self._seer_api_key = api_key
        self._url = url.rstrip('/')
        self._max_items = max_items
        self._content_type = content_type
        self._media_type = media_type
        
        # Initialize default filters
        self._filters = {
            'language': 'en',
            'min_year': 0,
            'exclude_talk_shows': True,
            'exclude_genres': [10763, 10764, 10767],  # News, Reality, Talk shows
            'exclude_non_english': True
        }
        
        # Update with user-provided filters
        if filters:
            self._filters.update(filters)
        
        # Customize name based on content type and media type
        if content_type in ["popular_movies", "popular_tv"]:
            self._name = f"Seer Mediarr Popular {'Movies' if media_type == 'movies' else 'TV'}"
        else:
            self._name = f"Seer Mediarr {content_type.title()}"
        self._empty_warning_emitted = False

    @staticmethod
    def _normalize_media_type(value, default="movie"):
        """Normalize seer media type values to movie/tv."""
        if not value:
            return default

        text = str(value).strip().lower()
        if text in {"movie", "movies", "film"}:
            return "movie"
        if text in {"tv", "show", "shows", "series"}:
            return "tv"
        return default

    @staticmethod
    def _extract_year_from_item(item, media_type):
        """Extract a 4-digit year string from Seer payload."""
        if media_type == "movie":
            date_value = item.get("release_date") or item.get("releaseDate")
        else:
            date_value = item.get("first_air_date") or item.get("firstAirDate")
        if not date_value:
            return ""
        try:
            return str(date_value).split("-")[0]
        except Exception:
            return ""

    @staticmethod
    def _seer_image_url(path, size):
        """Build image URL from Seer/TMDB path format."""
        if not path:
            return ""
        value = str(path).strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"https://image.tmdb.org/t/p/{size}{value}"
            
    def should_include_item(self, item, media_type):
        """Apply filters to determine if an item should be included."""
        if not item:
            return False

        # Support both snake_case (TMDB direct) and camelCase (Overseerr proxy)
        if media_type == 'tv':
            date_str = item.get('first_air_date') or item.get('firstAirDate') or ''
        else:
            date_str = item.get('release_date') or item.get('releaseDate') or ''

        if date_str:
            try:
                year = int(str(date_str).split('-')[0])
                if year < self._filters.get('min_year', 0):
                    return False
            except (ValueError, IndexError, TypeError):
                pass

        # Overseerr returns 'originalLanguage'; TMDB direct returns 'original_language'
        lang = item.get('original_language') or item.get('originalLanguage') or ''
        if self._filters.get('exclude_non_english', True) and lang != 'en':
            return False

        # Overseerr returns 'genreIds'; TMDB direct returns 'genre_ids'
        genre_ids = item.get('genre_ids') or item.get('genreIds') or []
        excluded_genres = self._filters.get('exclude_genres', [])
        if excluded_genres and any(gid in excluded_genres for gid in genre_ids):
            return False

        if media_type == 'tv' and self._filters.get('exclude_talk_shows', True):
            title = item.get('name', '') or item.get('title', '')
            if self.is_talk_show(title):
                return False

        return True
       
    def is_talk_show(self, title):
        """Check if a show title appears to be a talk show or similar format."""
        if not self._filters.get('exclude_talk_shows', True) or not title:
            return False
           
        keywords = [
            'tonight show', 'late show', 'late night', 'daily show',
            'talk show', 'with seth meyers', 'with james corden',
            'with jimmy', 'with stephen', 'with trevor', 'news',
            'live with', 'watch what happens live', 'the view',
            'good morning', 'today show', 'kimmel', 'colbert',
            'fallon', 'ellen', 'conan', 'graham norton', 'meet the press',
            'face the nation', 'last week tonight', 'real time',
            'kelly and', 'kelly &', 'jeopardy', 'wheel of fortune',
            'daily mail', 'entertainment tonight', 'zeiten', 'schlechte'
        ]
       
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in keywords)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        if self._content_type in ["popular_movies", "popular_tv"]:
            return f"seer_mediarr_{self._content_type}_{self._url}"
        return f"seer_mediarr_{self._content_type}_{self._url}"

    async def _fetch_media_list(self, media_type=None):
        """Fetch media list from Seer."""
        try:
            headers = {'X-Api-Key': self._seer_api_key}
            params = {}
            
            # Build the correct URL and parameters
            if self._content_type == "trending":
                url = f"{self._url}/api/v1/discover/trending"
            elif self._content_type == "popular_movies":
                url = f"{self._url}/api/v1/discover/movies"
                params["sortBy"] = "popularity.desc"
            elif self._content_type == "popular_tv":
                url = f"{self._url}/api/v1/discover/tv"
                params["sortBy"] = "popularity.desc"
            elif self._content_type == "discover":
                # Use provided media_type or default to movies
                media_type = media_type or "movies"
                url = f"{self._url}/api/v1/discover/{media_type}"
            else:
                _LOGGER.error("Unknown content type: %s", self._content_type)
                return None
            
            _LOGGER.debug("Making request to URL: %s with params: %s", url, params)
            
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    _LOGGER.error("Failed request to %s with params %s, status: %s", url, params, response.status)
                    raise Exception(f"Failed to fetch {self._content_type}. Status: {response.status}")
                    
        except Exception as err:
            _LOGGER.error("Error fetching %s: %s", self._content_type, err)
            return None
    async def _fetch_all_requests(self):
        """Fetch all current requests from Overseerr/Jellyseerr."""
        try:
            url = f"{self._url}/api/v1/request"
            headers = {"X-Api-Key": self._seer_api_key}
            params = {"take": 100, "skip": 0}  # Adjust take value as needed
            all_requests = set()

            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('results'):
                            for request in data['results']:
                                if request.get('media'):
                                    tmdb_id = request['media'].get('tmdbId')
                                    if tmdb_id:
                                        all_requests.add(str(tmdb_id))
            
            return all_requests
        except Exception as err:
            _LOGGER.error("Error fetching all requests: %s", err)
            return set()

    async def _process_media_items(self, data, media_type, requested_ids):
        """Process media items in parallel with filtering."""
        if not data or not data.get('results'):
            _LOGGER.debug("[mediarr-diag] No data or results for %s (data=%s)", media_type, type(data).__name__)
            return []
        _LOGGER.debug("[mediarr-diag] Processing %d items for %s, first item keys: %s",
                      len(data['results']), media_type,
                      list(data['results'][0].keys()) if data['results'] else [])

        filtered_count = 0
        requested_count = 0
        detail_failure_count = 0
        success_count = 0
        
        async def process_item(item):
            nonlocal filtered_count, requested_count, detail_failure_count, success_count
            
            try:
                tmdb_id = str(item.get('id'))
                if not tmdb_id:
                    _LOGGER.debug("Item has no TMDB ID")
                    return None
                    
                if tmdb_id in requested_ids:
                    requested_count += 1
                    _LOGGER.debug("Item %s already requested, skipping", tmdb_id)
                    return None
                
                item_media_type = media_type
                if self._content_type == "trending":
                    item_media_type = self._normalize_media_type(
                        item.get("mediaType") or item.get("media_type") or item.get("type"),
                        default=media_type,
                    )

                # Apply filters
                if not self.should_include_item(item, item_media_type):
                    filtered_count += 1
                    lang = item.get('original_language') or item.get('originalLanguage') or 'MISSING'
                    genre_ids = item.get('genre_ids') or item.get('genreIds') or []
                    _LOGGER.debug("[mediarr-diag] Item %s filtered: lang=%s genres=%s", tmdb_id, lang, genre_ids)
                    return None

                details = None
                if self._tmdb_api_key:
                    details = await self._get_tmdb_details(tmdb_id, item_media_type)
                    if not details:
                        detail_failure_count += 1
                        _LOGGER.debug("Failed to get TMDB details for %s", tmdb_id)

                if not details:
                    details = {
                        "title": item.get("title") if item_media_type == "movie" else item.get("name"),
                        "overview": item.get("overview") or "No overview available",
                        "year": self._extract_year_from_item(item, item_media_type),
                    }

                poster_url = backdrop_url = main_backdrop_url = ""
                if self._tmdb_api_key:
                    tmdb_poster, tmdb_backdrop, tmdb_main_backdrop = await self._get_tmdb_images(
                        tmdb_id, item_media_type
                    )
                    poster_url = str(tmdb_poster or "")
                    backdrop_url = str(tmdb_backdrop or "")
                    main_backdrop_url = str(tmdb_main_backdrop or "")

                if not poster_url:
                    poster_url = self._seer_image_url(item.get("posterPath"), "w500")
                if not backdrop_url:
                    backdrop_url = self._seer_image_url(item.get("backdropPath"), "w780")
                if not main_backdrop_url:
                    main_backdrop_url = self._seer_image_url(item.get("backdropPath"), "original") or backdrop_url

                success_count += 1
                return {
                    'title': details.get('title') or item.get('title') or item.get('name') or 'Unknown',
                    'overview': (
                        details['overview'][:100] + '...'
                        if details.get('overview')
                        else 'No overview available'
                    ),
                    'year': details.get('year') or '',
                    'poster': str(poster_url or ""),
                    'fanart': str(main_backdrop_url or backdrop_url or ""),
                    'banner': str(backdrop_url or ""),
                    'release': details.get('year') or '',
                    'type': item_media_type,
                    'flag': 1,
                    'id': tmdb_id
                }
            except Exception as err:
                _LOGGER.error("Error processing item %s: %s", tmdb_id if 'tmdb_id' in locals() else 'unknown', err)
                return None

        # Process items in parallel
        _LOGGER.debug("Processing %d items for %s", len(data['results']), media_type)
        tasks = [process_item(item) for item in data['results']]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            _LOGGER.error("Got %d exceptions during processing", len(exceptions))
            for exc in exceptions[:3]:  # Log first 3 exceptions
                _LOGGER.error("Exception: %s", exc)
        
        # Filter out None values and exceptions
        processed_results = [item for item in results if item is not None and not isinstance(item, Exception)]
        
        _LOGGER.debug("Processing summary for %s: %d items total, %d already requested, %d filtered out, "
                    "%d failed to get details, %d successful", 
                    media_type, len(data['results']), requested_count, filtered_count, 
                    detail_failure_count, success_count)
        
        return processed_results

    async def async_update(self):
        """Update the sensor."""
        try:
            # Fetch all current requests first
            requested_ids = await self._fetch_all_requests()
            _LOGGER.debug("Fetched %d requested IDs from Seer", len(requested_ids))
            
            all_items = []
            
            if self._content_type == "discover":
                # Fetch both movies and TV
                for media_type in ['movies', 'tv']:
                    _LOGGER.debug("Fetching %s data from Seer for discover", media_type)
                    data = await self._fetch_media_list(media_type)
                    
                    if data and 'results' in data:
                        _LOGGER.debug("Received %d %s items from Seer", len(data['results']), media_type)
                        # Debug the first item to see its structure
                        if data['results']:
                            _LOGGER.debug("Sample item structure: %s", data['results'][0])
                    else:
                        _LOGGER.debug("No %s data or no results received from Seer", media_type)
                    
                    _LOGGER.debug("Processing %s items through filters", media_type)
                    processed_items = await self._process_media_items(
                        data,
                        'movie' if media_type == 'movies' else 'tv',
                        requested_ids
                    )
                    _LOGGER.debug("After filtering: %d %s items remaining", len(processed_items), media_type)
                    all_items.extend(processed_items)
            else:
                # Fetch single type (trending, popular movies, or popular TV)
                _LOGGER.debug("Fetching %s data from Seer", self._content_type)
                data = await self._fetch_media_list()
                
                if data and 'results' in data:
                    _LOGGER.debug("Received %d items from Seer for %s", len(data['results']), self._content_type)
                    # Debug the first item to see its structure
                    if data['results']:
                        _LOGGER.debug("Sample item structure: %s", data['results'][0])
                else:
                    _LOGGER.debug("No data or no results received from Seer for %s", self._content_type)
                
                media_type = 'movie' if self._content_type == 'popular_movies' else 'tv'
                _LOGGER.debug("Processing %s items through filters", self._content_type)
                processed_items = await self._process_media_items(data, media_type, requested_ids)
                _LOGGER.debug("After filtering: %d items remaining", len(processed_items))
                all_items.extend(processed_items)

            # Ensure max_items limit is respected
            all_items = all_items[:self._max_items]
            _LOGGER.debug("Final number of items after max_items limit: %d", len(all_items))

            if not all_items:
                if not self._empty_warning_emitted:
                    _LOGGER.warning(
                        "No items passed filters for %s, using fallback (repeated empties now logged as debug)",
                        self._content_type,
                    )
                    self._empty_warning_emitted = True
                else:
                    _LOGGER.debug("No items passed filters for %s, using fallback", self._content_type)
                all_items.append({
                    'title_default': '$title',
                    'line1_default': '$type',
                    'line2_default': '$overview',
                    'line3_default': '$year',
                    'icon': 'mdi:movie-search'
                })
            else:
                self._empty_warning_emitted = False

            self._state = len(all_items)
            self._attributes = {'data': all_items}
            self._available = True

        except Exception as err:
            _LOGGER.error("Error updating %s sensor: %s", self._content_type, err)
            self._state = 0
            self._attributes = {'data': []}
            self._available = False
