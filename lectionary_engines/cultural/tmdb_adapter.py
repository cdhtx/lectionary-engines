"""
TMDB Adapter for Cultural Sources

Queries The Movie Database (TMDB) for films from the target era.
TMDB offers a free API with comprehensive movie data.

API Key: Requires TMDB_API_KEY environment variable
Get a free key at: https://www.themoviedb.org/settings/api
"""

import os
import aiohttp
import ssl
import certifi
from typing import List, Optional, Dict, Any
from .base_adapter import BaseAdapter, CulturalArtifact


def get_ssl_context():
    """Get SSL context that works on macOS"""
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except:
        # Fallback: disable verification (dev only)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


class TMDBAdapter(BaseAdapter):
    """
    Adapter for The Movie Database (TMDB).

    Fetches movie data including titles, overviews, release dates,
    and genres from the comprehensive TMDB API.
    """

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

    # Genre mapping for theological/thematic connections
    GENRE_THEMES = {
        18: ["struggle", "human condition", "relationships", "mortality"],  # Drama
        35: ["joy", "community", "absurdity", "grace"],  # Comedy
        28: ["conflict", "heroism", "good vs evil", "sacrifice"],  # Action
        12: ["journey", "discovery", "faith", "transformation"],  # Adventure
        27: ["fear", "evil", "darkness", "spiritual warfare"],  # Horror
        878: ["transcendence", "creation", "future", "humanity"],  # Sci-Fi
        10749: ["love", "covenant", "devotion", "sacrifice"],  # Romance
        53: ["tension", "danger", "trust", "survival"],  # Thriller
        10751: ["family", "belonging", "generations", "home"],  # Family
        14: ["wonder", "magic", "other worlds", "imagination"],  # Fantasy
        80: ["justice", "sin", "redemption", "consequences"],  # Crime
        36: ["memory", "legacy", "providence", "meaning"],  # History
        10752: ["sacrifice", "duty", "loss", "courage"],  # War
    }

    @property
    def name(self) -> str:
        return "TMDB"

    @property
    def category(self) -> str:
        return "film"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key") or os.getenv("TMDB_API_KEY")
        if not self.api_key:
            print("Warning: TMDB_API_KEY not set. TMDB adapter will not function.")

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated request to TMDB API"""
        if not self.api_key:
            return None

        url = f"{self.BASE_URL}{endpoint}"
        request_params = {"api_key": self.api_key}
        if params:
            request_params.update(params)

        try:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=request_params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            print(f"TMDB request error: {e}")
            return None

    async def search(
        self,
        themes: List[str],
        limit: int = 5,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None
    ) -> List[CulturalArtifact]:
        """
        Search TMDB for movies matching themes within era.

        Uses keyword search and filters by release year.
        """
        if not self.api_key:
            return []

        start = year_start or self.era_start
        end = year_end or self.era_end

        artifacts = []

        for theme in themes[:3]:
            # Search movies by keyword
            data = await self._make_request("/search/movie", {
                "query": theme,
                "include_adult": "false",
            })

            if data and data.get("results"):
                for movie in data["results"]:
                    # Extract year from release date
                    release_date = movie.get("release_date", "")
                    if release_date:
                        year = int(release_date[:4])
                        if start <= year <= end:
                            artifact = await self._movie_to_artifact(movie, [theme])
                            if artifact:
                                artifacts.append(artifact)

                            if len(artifacts) >= limit:
                                break

            if len(artifacts) >= limit:
                break

        return artifacts[:limit]

    async def get_by_year(
        self,
        year: int,
        limit: int = 10
    ) -> List[CulturalArtifact]:
        """
        Get popular/notable movies from a specific year.

        Uses TMDB's discover endpoint to find top-rated films.
        """
        if not self.api_key or not self.is_in_era(year):
            return []

        data = await self._make_request("/discover/movie", {
            "primary_release_year": year,
            "sort_by": "vote_average.desc",
            "vote_count.gte": 100,  # Ensure some popularity
            "include_adult": "false",
        })

        artifacts = []
        if data and data.get("results"):
            for movie in data["results"][:limit]:
                artifact = await self._movie_to_artifact(movie)
                if artifact:
                    artifacts.append(artifact)

        return artifacts

    async def get_iconic_films(
        self,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        limit: int = 20
    ) -> List[CulturalArtifact]:
        """
        Get the most iconic/highly-rated films from the era.

        These are the films most likely to resonate with the target audience.
        """
        if not self.api_key:
            return []

        start = year_start or self.era_start
        end = year_end or self.era_end

        data = await self._make_request("/discover/movie", {
            "primary_release_date.gte": f"{start}-01-01",
            "primary_release_date.lte": f"{end}-12-31",
            "sort_by": "vote_average.desc",
            "vote_count.gte": 500,  # Only well-known films
            "include_adult": "false",
        })

        artifacts = []
        if data and data.get("results"):
            for movie in data["results"][:limit]:
                artifact = await self._movie_to_artifact(movie)
                if artifact:
                    artifacts.append(artifact)

        return artifacts

    async def _movie_to_artifact(
        self,
        movie: Dict[str, Any],
        search_themes: Optional[List[str]] = None
    ) -> Optional[CulturalArtifact]:
        """Convert TMDB movie data to CulturalArtifact"""
        try:
            title = movie.get("title", "Unknown")
            release_date = movie.get("release_date", "")
            year = int(release_date[:4]) if release_date else 0
            overview = movie.get("overview", "")
            genre_ids = movie.get("genre_ids", [])
            poster_path = movie.get("poster_path", "")
            movie_id = movie.get("id")

            # Extract themes from genres
            themes = search_themes or []
            for genre_id in genre_ids:
                themes.extend(self.GENRE_THEMES.get(genre_id, []))
            themes = list(set(themes))[:5]  # Dedupe and limit

            return CulturalArtifact(
                title=title,
                creator=await self._get_director(movie_id) if movie_id else "Unknown",
                year=year,
                category="film",
                source_name=self.name,
                quote_or_description=overview,
                context=f"Released in {year}. {'Highly rated film of the era.' if movie.get('vote_average', 0) > 7 else ''}",
                themes=themes,
                theological_hooks=self._infer_theological_hooks(themes),
                url=f"https://www.themoviedb.org/movie/{movie_id}" if movie_id else "",
                image_url=f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else "",
                confidence=0.85,
            )
        except Exception as e:
            print(f"Error converting movie to artifact: {e}")
            return None

    async def _get_director(self, movie_id: int) -> str:
        """Get director name for a movie"""
        credits = await self._make_request(f"/movie/{movie_id}/credits")
        if credits and credits.get("crew"):
            for person in credits["crew"]:
                if person.get("job") == "Director":
                    return person.get("name", "Unknown")
        return "Unknown"

    def _infer_theological_hooks(self, themes: List[str]) -> List[str]:
        """Infer theological connection points from themes"""
        hooks = []
        theme_to_theology = {
            "journey": ["exodus", "pilgrimage"],
            "sacrifice": ["atonement", "cross"],
            "redemption": ["salvation", "grace"],
            "good vs evil": ["spiritual warfare", "kingdom conflict"],
            "love": ["agape", "covenant"],
            "family": ["household of God", "belonging"],
            "fear": ["trust", "faith over fear"],
            "transformation": ["sanctification", "new creation"],
            "heroism": ["Christ figure", "servant leadership"],
            "mortality": ["resurrection hope", "eschatology"],
        }
        for theme in themes:
            hooks.extend(theme_to_theology.get(theme, []))
        return list(set(hooks))[:4]
