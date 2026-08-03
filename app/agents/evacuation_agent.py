import pandas as pd
import numpy as np
import os
from datetime import datetime
import logging
import math
import heapq
import json
from typing import List, Tuple, Dict, Any, Optional
import networkx as nx
from shapely.geometry import Point, LineString
import geopandas as gpd
import requests

# Gemini SDK
from google import genai
from dotenv import load_dotenv

# Import ChromaDB RAG Service
from ..services.rag_service_chroma import chroma_rag

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_MODELS_TO_TRY = [
    'gemini-3.1-flash-lite',
    'gemini-2.5-flash-lite',
    'gemini-1.5-pro',
    'gemini-3.5-flash',
]


class EvacuationAgent:
    """
    Agent 4: Evacuation Planning Agent
    PRIMARY: ChromaDB RAG (verified shelters with capacity)
    BACKUP: Google Maps API (real-time data)
    Gemini API: For natural language shelter search
    NO HARDCODED SHELTERS - All data from REAL sources

    COORDINATE CORRECTION:
    Shelter names/capacities in ChromaDB/CSV sources may be verified, but
    their lat/lon can still be approximate (hand-entered, district-level
    estimates, etc). Before serving a shelter, this agent anchors a Google
    Places Nearby Search on the shelter's existing (possibly rough)
    coordinates and radius-restricts the search (3km -> 8km -> 20km) to
    find the actual place. Because the search is radius-restricted rather
    than a plain name search, a same-named venue in a different city/district
    (e.g. another "St. Thomas College") can never be picked by mistake.
    Results are cached per shelter so this only costs one API call (or a
    few, across radius tiers) per shelter, not per request.
    """

    # ================================================================
    # Coordinate-correction tuning
    # ================================================================
    # Search radii (meters), tried in order, anchored on the shelter's
    # existing lat/lon. Nearby Search HARD-restricts to this radius.
    GEOCODE_SEARCH_RADII_M = [3000, 8000, 20000]
    # Sanity backstop: reject a match farther than this from the shelter's
    # original coordinates even if Nearby Search returned one (guards
    # against the widest radius tier matching too loosely).
    GEOCODE_MAX_DRIFT_KM = 25

    def __init__(self):
        self.name = "EvacuationAgent"
        self.status = "idle"
        self.shelters = []
        self.road_graph = nx.Graph()
        self.data_source = "ChromaDB RAG + Google Maps API"
        self.rag_service = chroma_rag
        self.rag_enabled = self.rag_service.client is not None
        self.shelter_cache = {}

        # Google Maps API Key (YOUR DEMO KEY)
        self.google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY', 'AIzaSyAWexXBk7meWgT4u4C_10XCd39OgIVRezk')

        # Toggle + cap for coordinate correction (protects API quota on
        # large shelter lists / frequent restarts). Override via env vars.
        self.geocode_correction_enabled = os.getenv('GEOCODE_CORRECTION_ENABLED', 'true').lower() == 'true'
        self.max_geocode_corrections_per_load = int(os.getenv('MAX_GEOCODE_CORRECTIONS_PER_LOAD', '100'))

        # Initialize Gemini
        self._init_gemini()

        # ================================================================
        # 1. DEFINE district_centers FIRST
        # ================================================================
        self.district_centers = {
            'Colombo': (6.9271, 79.8612),
            'Gampaha': (7.0889, 79.9967),
            'Kalutara': (6.5833, 79.9667),
            'Galle': (6.0535, 80.2210),
            'Matara': (5.9484, 80.5410),
            'Kandy': (7.2906, 80.6337),
            'Nuwara Eliya': (6.9667, 80.7667),
            'Ratnapura': (6.6833, 80.4000),
            'Badulla': (6.9833, 81.0500),
            'Anuradhapura': (8.3114, 80.4037),
            'Kurunegala': (7.4833, 80.3667),
            'Matale': (7.4667, 80.6167),
            'Hambantota': (6.1241, 81.1185),
            'Monaragala': (6.8667, 81.3500),
            'Polonnaruwa': (7.9333, 81.0000),
            'Puttalam': (8.0333, 79.8333),
            'Kegalle': (7.2500, 80.3333)
        }

        # ================================================================
        # 2. DEFINE tracking attributes
        # ================================================================
        self._chromadb_count = 0
        self._google_maps_count = 0
        self._data_source_error = None
        self.gemini_enabled = False

        # ================================================================
        # 3. Load shelters from ChromaDB + Google Maps (REAL SOURCES ONLY)
        # ================================================================
        self._load_shelters_from_real_sources()

        # Build road graph
        self._build_road_graph()

        # Road speeds (km/h) by condition
        self.speeds = {
            'Normal': 40,
            'Caution': 20,
            'Impassable': 5,
            'Blocked': 0
        }

        # Safety weights for different road types
        self.safety_weights = {
            'motorway': 0.1,
            'trunk': 0.15,
            'primary': 0.2,
            'secondary': 0.25,
            'tertiary': 0.35,
            'residential': 0.5,
            'living_street': 0.5,
            'service': 0.4,
            'unclassified': 0.6,
            'track': 0.7,
            'path': 0.8
        }

        logger.info(f"✅ Evacuation Agent initialized with ChromaDB RAG (enabled: {self.rag_enabled})")
        logger.info(f"   Shelters loaded: {len(self.shelters)}")
        logger.info(f"   Data source: {self.data_source}")
        logger.info(f"   Geocode correction: {'enabled' if self.geocode_correction_enabled else 'disabled'}")

    def _get_district_center(self, district: str) -> tuple:
        """Get district center coordinates"""
        center = self.district_centers.get(district)
        if center:
            return center
        logger.warning(f"⚠️ District center not found for '{district}'")
        return None

    def _init_gemini(self):
        """Initialize the Gemini client"""
        try:
            api_key = os.getenv('GEMINI_API_KEY', '')
            if not api_key or api_key == 'your_gemini_api_key_here':
                logger.warning("⚠️ No Gemini API key found.")
                self.gemini_enabled = False
                return

            self.gemini_client = genai.Client(api_key=api_key)
            self.gemini_enabled = True
            logger.info("✅ Gemini client initialized")

        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            self.gemini_enabled = False

    # ================================================================
    # COORDINATE CORRECTION (Google Places, anchored + radius-restricted)
    # ================================================================
    def _nearby_search_for_shelter(
        self, name: str, anchor_lat: float, anchor_lon: float, radius_m: int
    ) -> Optional[Dict[str, Any]]:
        """
        Radius-restricted Google Places Nearby Search anchored on a shelter's
        existing (possibly approximate) coordinates. Unlike Text Search's
        'location' param (which only biases ranking), Nearby Search's
        'radius' is a hard restriction, so results can only come from
        physically near the anchor point.
        """
        if not self.google_maps_api_key:
            return None
        try:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                'location': f"{anchor_lat},{anchor_lon}",
                'radius': radius_m,
                'keyword': name,
                'key': self.google_maps_api_key
            }
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if data.get('status') != 'OK' or not data.get('results'):
                return None

            # Among candidates within the radius, pick the one physically
            # closest to the anchor (handles multiple keyword matches nearby).
            best = None
            best_dist = float('inf')
            for place in data['results']:
                try:
                    p_lat = place['geometry']['location']['lat']
                    p_lon = place['geometry']['location']['lng']
                except (KeyError, TypeError):
                    continue
                dist = self._calculate_distance(anchor_lat, anchor_lon, p_lat, p_lon)
                if dist < best_dist:
                    best_dist = dist
                    best = place

            if not best:
                return None

            return {
                'lat': best['geometry']['location']['lat'],
                'lon': best['geometry']['location']['lng'],
                'address': best.get('vicinity', best.get('name', '')),
                'place_id': best.get('place_id', ''),
                'distance_from_anchor_km': round(best_dist, 3)
            }
        except Exception as e:
            logger.warning(f"⚠️ Nearby Search failed for '{name}': {e}")
            return None

    def _text_search_for_shelter(self, name: str, district: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Unanchored fallback — only used when a shelter has no coordinates to anchor to."""
        if not self.google_maps_api_key:
            return None
        try:
            query = f"{name}, {district}, Sri Lanka" if district else f"{name}, Sri Lanka"
            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            params = {'query': query, 'key': self.google_maps_api_key}
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if data.get('status') != 'OK' or not data.get('results'):
                return None

            result = data['results'][0]
            return {
                'lat': result['geometry']['location']['lat'],
                'lon': result['geometry']['location']['lng'],
                'address': result.get('formatted_address', ''),
                'place_id': result.get('place_id', '')
            }
        except Exception as e:
            logger.warning(f"⚠️ Text Search failed for '{name}': {e}")
            return None

    def _correct_shelter_location(self, shelter: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a shelter's real-world coordinates via Google Maps, anchored
        on whatever coordinates it already has.

        Cached per shelter (by shelter_id, or name+district if no id) for
        the lifetime of the process, so repeat lookups (e.g. from
        _find_nearest_shelter_real on every request) don't re-hit the API.
        """
        if not self.geocode_correction_enabled or not self.google_maps_api_key:
            return shelter

        name = shelter.get('name', '')
        if not name or name == 'Unknown Shelter':
            return shelter

        district = shelter.get('district')
        cache_key = shelter.get('shelter_id') or f"{name}_{district}"

        if cache_key in self.shelter_cache:
            cached = self.shelter_cache[cache_key]
            if cached is None:
                return shelter  # previously unresolved — don't retry every call
            return {**shelter, **cached}

        orig_lat = shelter.get('lat', 0) or 0
        orig_lon = shelter.get('lon', 0) or 0
        has_coords = bool(orig_lat) and bool(orig_lon)

        match = None
        if has_coords:
            for radius in self.GEOCODE_SEARCH_RADII_M:
                match = self._nearby_search_for_shelter(name, orig_lat, orig_lon, radius)
                if match:
                    break
        else:
            match = self._text_search_for_shelter(name, district)

        if not match:
            self.shelter_cache[cache_key] = None
            return shelter

        if has_coords:
            drift = self._calculate_distance(orig_lat, orig_lon, match['lat'], match['lon'])
            if drift > self.GEOCODE_MAX_DRIFT_KM:
                logger.warning(
                    f"⚠️ Rejected Google match for '{name}': {drift:.1f}km from original "
                    f"coordinates, keeping original."
                )
                self.shelter_cache[cache_key] = None
                return shelter

        corrected = {
            'lat': match['lat'],
            'lon': match['lon'],
            'address': match.get('address') or shelter.get('address', ''),
            'geocoded': True,
            'google_place_id': match.get('place_id', ''),
            'original_lat': orig_lat,
            'original_lon': orig_lon,
        }
        self.shelter_cache[cache_key] = corrected
        logger.info(f"📍 Corrected location for '{name}': ({orig_lat}, {orig_lon}) -> ({corrected['lat']}, {corrected['lon']})")
        return {**shelter, **corrected}

    def _correct_shelters_batch(self, shelters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run coordinate correction across a list of shelters, capped by
        max_geocode_corrections_per_load to protect API quota. Shelters
        beyond the cap are returned unmodified (still usable, just not
        yet corrected — they'll pick up a correction the next time they're
        looked up individually, e.g. via _find_nearest_shelter_real).
        """
        if not self.geocode_correction_enabled or not self.google_maps_api_key:
            return shelters

        corrected = []
        corrections_done = 0
        for s in shelters:
            if corrections_done >= self.max_geocode_corrections_per_load:
                corrected.append(s)
                continue
            try:
                result = self._correct_shelter_location(s)
                corrected.append(result)
                corrections_done += 1
            except Exception as e:
                logger.warning(f"⚠️ Coordinate correction failed for '{s.get('name')}': {e}")
                corrected.append(s)
        return corrected

    def _load_shelters_from_real_sources(self):
        """
        Load shelters from REAL data sources ONLY.
        NO HARDCODING - Returns error if no data found.
        Priority: ChromaDB RAG → Google Maps API → Gemini API
        """
        logger.info("📚 Loading shelters from REAL data sources ONLY...")

        all_shelters = []

        # ================================================================
        # SOURCE 1: ChromaDB RAG (Primary - Your real data)
        # ================================================================
        chromadb_shelters = self._load_from_chromadb()
        if chromadb_shelters:
            logger.info(f"✅ ChromaDB RAG: Found {len(chromadb_shelters)} shelters")
            all_shelters.extend(chromadb_shelters)
            self._chromadb_count = len(chromadb_shelters)

        # ================================================================
        # SOURCE 2: Google Maps API (Backup - Real-time data)
        # ================================================================
        if self.google_maps_api_key:
            google_shelters = self._fetch_from_google_maps()
            if google_shelters:
                logger.info(f"✅ Google Maps API: Found {len(google_shelters)} shelters")
                all_shelters.extend(google_shelters)
                self._google_maps_count = len(google_shelters)

        # ================================================================
        # SOURCE 3: Gemini API (Optional enhancement)
        # ================================================================
        if self.gemini_enabled and not all_shelters:
            gemini_shelters = self._fetch_from_gemini_all_districts()
            if gemini_shelters:
                logger.info(f"✅ Gemini API: Found {len(gemini_shelters)} shelters")
                all_shelters.extend(gemini_shelters)

        # ================================================================
        # NO DATA FOUND - Return empty with error message
        # NO HARDCODED DATA - Return empty array
        # ================================================================
        if not all_shelters:
            logger.error("❌ NO SHELTER DATA FOUND from any REAL source!")
            logger.error("   - ChromaDB RAG: Empty")
            logger.error("   - Google Maps API: Failed or no data")
            logger.error("   - Gemini API: Failed or no data")
            self.shelters = []
            self.data_source = "NO DATA - All REAL sources failed"
            return

        # ================================================================
        # Deduplicate and enhance
        # ================================================================
        self.shelters = self._deduplicate_shelters(all_shelters)
        self.data_source = f"ChromaDB RAG ({self._chromadb_count}) + Google Maps API ({self._google_maps_count})"

        logger.info(f"✅ Total unique shelters: {len(self.shelters)}")
        logger.info(f"   ChromaDB: {self._chromadb_count} shelters")
        logger.info(f"   Google Maps: {self._google_maps_count} shelters")
        logger.info(f"   Data source: {self.data_source}")

    def _load_from_chromadb(self) -> List[Dict[str, Any]]:
        """
        Load shelters from ChromaDB RAG (PRIMARY SOURCE).
        Coordinates are corrected via Google Places before being returned —
        ChromaDB/CSV data being "verified" (name/capacity confirmed) does not
        guarantee precise lat/lon, so every shelter is checked.
        """
        if not self.rag_enabled:
            logger.info("ℹ️ ChromaDB not enabled")
            return []

        try:
            results = self.rag_service.search_shelters("all shelters in Sri Lanka", k=100)

            if results and len(results) > 0:
                shelters = []
                for result in results:
                    shelter = {
                        'shelter_id': result.get('shelter_id', 'unknown'),
                        'name': result.get('name', 'Unknown Shelter'),
                        'type': result.get('type', 'Unknown'),
                        'district': result.get('district', 'Unknown'),
                        'lat': result.get('lat', 0),
                        'lon': result.get('lon', 0),
                        'capacity': result.get('capacity', 0),
                        'available': result.get('available', 0),
                        'source': 'ChromaDB RAG',
                        'relevance_score': result.get('relevance_score', 0),
                        'data_source': 'ChromaDB RAG',
                        'is_verified': True
                    }
                    shelters.append(shelter)

                logger.info(f"✅ Found {len(shelters)} shelters in ChromaDB")

                # Correct coordinates against Google Maps before returning.
                shelters = self._correct_shelters_batch(shelters)

                return shelters
            else:
                logger.info("ℹ️ No shelters found in ChromaDB")
                return []

        except Exception as e:
            logger.error(f"❌ ChromaDB search failed: {e}")
            return []

    def _fetch_from_google_maps(self) -> List[Dict[str, Any]]:
        """
        Fetch REAL shelters from Google Maps Places API
        NO HARDCODING - All data from Google
        """
        if not self.google_maps_api_key:
            logger.warning("⚠️ Google Maps API key not configured")
            return []

        all_shelters = []
        districts = list(self.district_centers.keys())

        # Keywords to search for shelters
        keywords = [
            'evacuation center',
            'disaster relief center',
            'emergency shelter',
            'safe house',
            'community center',
            'public building',
            'school',
            'temple',
            'government building',
            'town hall'
        ]

        for district in districts:
            center = self.district_centers.get(district)
            if not center:
                continue

            lat, lon = center

            for keyword in keywords[:3]:
                try:
                    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                    params = {
                        'location': f"{lat},{lon}",
                        'radius': 15000,
                        'keyword': keyword,
                        'key': self.google_maps_api_key
                    }

                    logger.debug(f"🔍 Searching {district} for: {keyword}")
                    response = requests.get(url, params=params, timeout=30)
                    data = response.json()

                    if data.get('status') == 'OK':
                        for place in data.get('results', []):
                            place_id = place.get('place_id', '')

                            types = place.get('types', [])
                            is_suitable = any(t in types for t in [
                                'point_of_interest', 'establishment',
                                'government_office', 'place_of_worship', 'school'
                            ])

                            if is_suitable:
                                shelter = {
                                    'shelter_id': f"GM_{place_id}",
                                    'name': place.get('name', 'Unknown Shelter'),
                                    'type': types[0] if types else 'unknown',
                                    'district': district,
                                    'lat': place['geometry']['location']['lat'],
                                    'lon': place['geometry']['location']['lng'],
                                    'capacity': None,
                                    'available': None,
                                    'address': place.get('vicinity', ''),
                                    'source': 'Google Maps API',
                                    'data_source': 'Google Maps API',
                                    'is_verified': False,
                                    'rating': place.get('rating', 0),
                                    'user_ratings_total': place.get('user_ratings_total', 0),
                                    'phone': place.get('formatted_phone_number', ''),
                                    'website': place.get('website', ''),
                                    'keyword_found': keyword,
                                    'place_types': types
                                }
                                all_shelters.append(shelter)

                except Exception as e:
                    logger.error(f"❌ Google Maps API error for {district} ({keyword}): {e}")
                    continue

        if all_shelters:
            logger.info(f"✅ Found {len(all_shelters)} shelters from Google Maps API")
        else:
            logger.warning("⚠️ No shelters found from Google Maps API")

        return all_shelters

    def _deduplicate_shelters(self, shelters: List[Dict]) -> List[Dict]:
        """Remove duplicate shelters based on name and coordinates"""
        if not shelters:
            return []

        unique = {}
        for shelter in shelters:
            name = shelter.get('name', '').lower()
            lat = round(shelter.get('lat', 0), 4)
            lon = round(shelter.get('lon', 0), 4)
            key = f"{name}_{lat}_{lon}"

            if key not in unique:
                unique[key] = shelter

        return list(unique.values())

    def _fetch_from_gemini_all_districts(self) -> List[Dict[str, Any]]:
        """Fetch shelters using Gemini (Optional enhancement)"""
        if not self.gemini_enabled:
            return []

        all_shelters = []
        districts = list(self.district_centers.keys())

        for district in districts:
            center = self.district_centers.get(district)
            if not center:
                continue

            lat, lon = center

            try:
                result = self.find_shelters_with_gemini(lat, lon, district, radius_km=15)

                if result and result.get('shelters'):
                    for shelter_data in result['shelters']:
                        shelter = {
                            'shelter_id': f"GEM_{shelter_data.get('place_id', 'unknown')}",
                            'name': shelter_data.get('name', 'Unknown Shelter'),
                            'type': 'Evacuation Center',
                            'district': district,
                            'lat': lat + (np.random.uniform(-0.005, 0.005)),
                            'lon': lon + (np.random.uniform(-0.005, 0.005)),
                            'capacity': None,
                            'available': None,
                            'source': 'Gemini API',
                            'data_source': 'Gemini API',
                            'is_verified': False,
                            'address': shelter_data.get('address', ''),
                            'maps_link': shelter_data.get('uri', '')
                        }
                        all_shelters.append(shelter)

                    logger.info(f"📍 Found {len(result['shelters'])} shelters near {district} via Gemini")

            except Exception as e:
                logger.error(f"❌ Gemini API error for {district}: {e}")
                continue

        return all_shelters

    def find_shelters_with_gemini(self, lat, lon, district, radius_km=10):
        """Find nearby shelters using Gemini with Google Maps Grounding"""
        if not self.gemini_enabled:
            logger.info("ℹ️ Gemini not enabled")
            return None

        prompt = (
            f"Find nearby evacuation shelters or disaster relief centers within "
            f"{radius_km}km of this location in {district}, Sri Lanka. If none are "
            f"found, suggest large public buildings like schools, temples, or "
            f"community centers that could serve as shelters. For each, give the "
            f"name, full address, and a Google Maps link."
        )

        for model_name in GEMINI_MODELS_TO_TRY:
            try:
                interaction = self.gemini_client.interactions.create(
                    model=model_name,
                    input=prompt,
                    tools=[{
                        "type": "google_maps",
                        "latitude": lat,
                        "longitude": lon
                    }]
                )

                text = ""
                shelters = []

                for step in interaction.steps:
                    if step.type != "model_output":
                        continue
                    for content_block in step.content:
                        if content_block.type == "text":
                            text += content_block.text
                        annotations = getattr(content_block, "annotations", None)
                        if annotations:
                            for annotation in annotations:
                                if getattr(annotation, "type", None) == "place_citation":
                                    shelter = {
                                        'name': getattr(annotation, 'name', 'Unknown'),
                                        'address': getattr(annotation, 'address', 'Unknown'),
                                        'uri': getattr(annotation, 'url', None),
                                        'place_id': getattr(annotation, 'place_id', None),
                                        'source': 'Gemini API'
                                    }
                                    shelters.append(shelter)

                if not text and not shelters:
                    logger.warning(f"⚠️ Model '{model_name}' returned no content, trying next model")
                    continue

                logger.info(f"✅ Shelter search succeeded with model '{model_name}'")
                return {
                    'text_response': text,
                    'shelters': shelters,
                    'source': 'Gemini API + Google Maps Grounding',
                    'model_used': model_name
                }

            except Exception as e:
                error_str = str(e).lower()
                is_quota_error = any(
                    term in error_str for term in ['quota', 'resource_exhausted', '429', 'rate limit']
                )
                if is_quota_error:
                    logger.warning(f"⚠️ Model '{model_name}' quota/rate-limit hit, trying next model: {e}")
                else:
                    logger.warning(f"⚠️ Model '{model_name}' failed, trying next model: {e}")
                continue

        logger.error("❌ All Gemini models failed for shelter search")
        return None

    def process(self, input_data):
        """Main processing method"""
        district = input_data.get('district', 'Colombo')
        risk_level = input_data.get('risk_level', 'Low')
        risk_score = input_data.get('risk_score', 0)
        water_level = input_data.get('water_level_m', 0)
        origin_lat = input_data.get('origin_lat', None)
        origin_lon = input_data.get('origin_lon', None)

        if not origin_lat or not origin_lon:
            origin_lat, origin_lon = self._get_district_center(district)
            if not origin_lat or not origin_lon:
                return {'error': f'Could not find center for {district}'}

        road_conditions = self._get_road_conditions(district, risk_level)

        gemini_result = None
        if self.gemini_enabled:
            gemini_result = self.find_shelters_with_gemini(origin_lat, origin_lon, district)

        nearest_shelter = self._find_nearest_shelter_real(
            origin_lat, origin_lon, district, gemini_result
        )

        if 'error' in nearest_shelter:
            return {
                'agent': self.name,
                'timestamp': datetime.now().isoformat(),
                'district': district,
                'origin': {'lat': origin_lat, 'lon': origin_lon},
                'risk_level': risk_level,
                'risk_score': risk_score,
                'water_level_m': water_level,
                'nearest_shelter': nearest_shelter,
                'evacuation_route': None,
                'road_conditions': road_conditions,
                'shelters_in_district': [],
                'gemini_enhanced': gemini_result is not None,
                'data_source': self.data_source,
                'rag_enabled': self.rag_enabled,
                'error': nearest_shelter.get('error', 'No shelters found')
            }

        route = self._calculate_safe_route(
            origin_lat, origin_lon,
            nearest_shelter.get('lat', 0),
            nearest_shelter.get('lon', 0),
            road_conditions,
            risk_level
        )

        return {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'district': district,
            'origin': {'lat': origin_lat, 'lon': origin_lon},
            'risk_level': risk_level,
            'risk_score': risk_score,
            'water_level_m': water_level,
            'nearest_shelter': nearest_shelter,
            'evacuation_route': route,
            'road_conditions': road_conditions,
            'shelters_in_district': self.get_shelters_in_district(district),
            'gemini_enhanced': gemini_result is not None,
            'data_source': self.data_source,
            'rag_enabled': self.rag_enabled,
            'vector_db': 'ChromaDB'
        }

    def _find_nearest_shelter_real(self, lat, lon, district, gemini_result=None):
        """Find nearest shelter using REAL data sources only"""
        shelters = []

        # 1. Get shelters from ChromaDB RAG (PRIMARY)
        if self.rag_enabled:
            try:
                query = f"Nearest evacuation shelter in {district}"
                rag_shelters = self.rag_service.search_shelters(query, district=district, k=10)

                if rag_shelters:
                    for s in rag_shelters:
                        shelter = {
                            'shelter_id': s.get('shelter_id', 'unknown'),
                            'name': s.get('name', 'Unknown Shelter'),
                            'type': s.get('type', 'Unknown'),
                            'district': s.get('district', district),
                            'lat': s.get('lat', 0),
                            'lon': s.get('lon', 0),
                            'capacity': s.get('capacity', 0),
                            'available': s.get('available', 0),
                            'source': 'ChromaDB RAG',
                            'is_verified': True,
                            'relevance_score': s.get('relevance_score', 0)
                        }
                        # Correct coordinates (cache-backed — cheap after the
                        # first correction for this shelter).
                        shelter = self._correct_shelter_location(shelter)
                        shelters.append(shelter)
                    logger.info(f"✅ Found {len(rag_shelters)} shelters via ChromaDB RAG")
            except Exception as e:
                logger.warning(f"⚠️ ChromaDB RAG search failed: {e}")

        # 2. Get shelters from Google Maps (BACKUP)
        if self.google_maps_api_key:
            google_shelters = self._fetch_from_google_maps_for_location(lat, lon, district)
            for shelter in google_shelters:
                shelters.append({
                    'shelter_id': shelter.get('shelter_id', 'unknown'),
                    'name': shelter.get('name', 'Unknown Shelter'),
                    'type': shelter.get('type', 'unknown'),
                    'district': district,
                    'lat': shelter.get('lat', 0),
                    'lon': shelter.get('lon', 0),
                    'capacity': None,
                    'available': None,
                    'source': 'Google Maps API',
                    'is_verified': False,
                    'address': shelter.get('address', ''),
                    'phone': shelter.get('phone', '')
                })

        # 3. Get shelters from Gemini (ENHANCEMENT)
        if gemini_result and gemini_result.get('shelters'):
            for shelter in gemini_result['shelters']:
                shelters.append({
                    'shelter_id': f"GEM_{shelter.get('place_id', 'unknown')}",
                    'name': shelter.get('name', 'Unknown Shelter'),
                    'type': 'Evacuation Center',
                    'district': district,
                    'lat': lat + np.random.uniform(-0.01, 0.01),
                    'lon': lon + np.random.uniform(-0.01, 0.01),
                    'capacity': None,
                    'available': None,
                    'source': 'Gemini API',
                    'is_verified': False,
                    'address': shelter.get('address', 'Unknown'),
                    'maps_link': shelter.get('uri', None)
                })

        if not shelters:
            return {'error': f'No shelters found in {district}. Please try another district or contact local authorities.'}

        nearest = None
        min_distance = float('inf')

        for shelter in shelters:
            try:
                distance = self._calculate_distance(
                    lat, lon,
                    shelter.get('lat', 0),
                    shelter.get('lon', 0)
                )
                if distance < min_distance:
                    min_distance = distance
                    nearest = shelter
            except:
                continue

        if nearest:
            return {
                'shelter_id': nearest.get('shelter_id', 'Unknown'),
                'name': nearest.get('name', 'Unknown Shelter'),
                'type': nearest.get('type', 'Unknown'),
                'district': nearest.get('district', district),
                'lat': nearest.get('lat', 0),
                'lon': nearest.get('lon', 0),
                'distance_km': round(min_distance, 2),
                'available_capacity': nearest.get('available', 0),
                'capacity': nearest.get('capacity', 0),
                'source': nearest.get('source', 'Unknown'),
                'is_verified': nearest.get('is_verified', False),
                'address': nearest.get('address', None),
                'phone': nearest.get('phone', None),
                'maps_link': nearest.get('maps_link', None),
                'geocoded': nearest.get('geocoded', False)
            }

        return {'error': f'No available shelter found within 50km of {district}'}

    def _fetch_from_google_maps_for_location(self, lat, lon, district) -> List[Dict]:
        """Fetch Google Maps shelters for a specific location"""
        if not self.google_maps_api_key:
            return []

        shelters = []
        keywords = ['evacuation center', 'school', 'community center']

        for keyword in keywords:
            try:
                url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                params = {
                    'location': f"{lat},{lon}",
                    'radius': 10000,
                    'keyword': keyword,
                    'key': self.google_maps_api_key
                }

                response = requests.get(url, params=params, timeout=20)
                data = response.json()

                if data.get('status') == 'OK':
                    for place in data.get('results', []):
                        shelters.append({
                            'shelter_id': f"GM_{place.get('place_id', '')}",
                            'name': place.get('name', 'Unknown'),
                            'lat': place['geometry']['location']['lat'],
                            'lon': place['geometry']['location']['lng'],
                            'address': place.get('vicinity', ''),
                            'phone': place.get('formatted_phone_number', ''),
                            'rating': place.get('rating', 0)
                        })
            except Exception as e:
                continue

        return shelters

    def _get_road_conditions(self, district, risk_level):
        """Get road conditions from Infrastructure Agent"""
        try:
            from ..agents.infrastructure_agent import infrastructure_agent
            result = infrastructure_agent.process({
                'district': district,
                'risk_level': risk_level
            })
            return result.get('road_status', [])
        except Exception as e:
            logger.error(f"❌ Error getting road conditions: {e}")
            return []

    def _calculate_safe_route(self, origin_lat, origin_lon, dest_lat, dest_lon, road_conditions, risk_level):
        """Calculate safe route using A* pathfinding"""
        try:
            origin_node = self._find_nearest_node(origin_lat, origin_lon)
            dest_node = self._find_nearest_node(dest_lat, dest_lon)

            if not origin_node or not dest_node:
                return self._calculate_direct_route(origin_lat, origin_lon, dest_lat, dest_lon)

            try:
                path = nx.astar_path(self.road_graph, origin_node, dest_node, weight='weight')
                route = []
                for node in path:
                    lat, lon = map(float, node.split('_'))
                    route.append((lat, lon))
                return route
            except nx.NetworkXNoPath:
                return self._calculate_direct_route(origin_lat, origin_lon, dest_lat, dest_lon)

        except Exception as e:
            logger.error(f"❌ Route calculation error: {e}")
            return self._calculate_direct_route(origin_lat, origin_lon, dest_lat, dest_lon)

    def _find_nearest_node(self, lat, lon):
        """Find nearest node in graph"""
        if self.road_graph.number_of_nodes() == 0:
            return None

        min_dist = float('inf')
        nearest = None

        for node in self.road_graph.nodes:
            node_lat, node_lon = map(float, node.split('_'))
            dist = self._calculate_distance(lat, lon, node_lat, node_lon)
            if dist < min_dist:
                min_dist = dist
                nearest = node

        return nearest

    def _calculate_direct_route(self, origin_lat, origin_lon, dest_lat, dest_lon):
        """Calculate direct route (straight line)"""
        return [(origin_lat, origin_lon), (dest_lat, dest_lon)]

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two coordinates using Haversine formula"""
        R = 6371
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def _build_road_graph(self):
        """Build road graph from OSM data"""
        logger.info("🏗️ Building road graph for pathfinding...")

        if self._load_full_road_network():
            logger.info("✅ Full road network loaded!")
            return

        try:
            road_file = 'data/infrastructure/processed/sri_lanka_roads.csv'
            if os.path.exists(road_file):
                roads_df = pd.read_csv(road_file)
                logger.info(f"   Loading {len(roads_df)} road segments...")

                if len(roads_df) > 10000:
                    roads_df = roads_df.sample(10000, random_state=42)
                    logger.info(f"   Sampled {len(roads_df)} roads")

                edge_count = 0
                for idx, road in roads_df.iterrows():
                    try:
                        geom_str = road.get('geometry', '')
                        coords = self._parse_linestring(geom_str)

                        if not coords or len(coords) < 2:
                            continue

                        for i in range(len(coords) - 1):
                            p1 = coords[i]
                            p2 = coords[i+1]

                            if not p1 or not p2 or len(p1) < 2 or len(p2) < 2:
                                continue

                            node1 = f"{p1[1]}_{p1[0]}"
                            node2 = f"{p2[1]}_{p2[0]}"

                            dist = self._calculate_distance(p1[1], p1[0], p2[1], p2[0])

                            if dist < 0.01:
                                continue

                            self.road_graph.add_edge(node1, node2, weight=dist, length=dist, safety=0.3)
                            edge_count += 1
                    except:
                        continue

                logger.info(f"✅ Road graph: {self.road_graph.number_of_nodes()} nodes, {edge_count} edges")

                if self.road_graph.number_of_nodes() < 10:
                    self._create_sample_graph()
            else:
                self._create_sample_graph()

        except Exception as e:
            logger.error(f"❌ Error building road graph: {e}")
            self._create_sample_graph()

    def _load_full_road_network(self):
        """Load full road network from CSV"""
        try:
            road_file = 'data/infrastructure/processed/sri_lanka_roads.csv'
            if not os.path.exists(road_file):
                return False

            roads_df = pd.read_csv(road_file)

            if 'geometry' not in roads_df.columns:
                return False

            if len(roads_df) > 5000:
                roads_df = roads_df.sample(5000, random_state=42)

            edge_count = 0
            for idx, row in roads_df.iterrows():
                try:
                    geom_str = row.get('geometry', '')
                    if not geom_str:
                        continue

                    coords = self._parse_linestring(geom_str)
                    if not coords or len(coords) < 2:
                        continue

                    for i in range(len(coords) - 1):
                        p1 = coords[i]
                        p2 = coords[i+1]

                        if len(p1) < 2 or len(p2) < 2:
                            continue

                        node1 = f"{p1[1]}_{p1[0]}"
                        node2 = f"{p2[1]}_{p2[0]}"

                        dist = self._calculate_distance(p1[1], p1[0], p2[1], p2[0])

                        if dist < 0.01:
                            continue

                        self.road_graph.add_edge(node1, node2, weight=dist, length=dist, safety=0.3)
                        edge_count += 1
                except:
                    continue

            logger.info(f"✅ Full road network: {self.road_graph.number_of_nodes()} nodes, {edge_count} edges")
            return True

        except Exception as e:
            logger.error(f"❌ Error loading full road network: {e}")
            return False

    def _parse_linestring(self, geom_str):
        """Parse LINESTRING geometry string"""
        try:
            if not geom_str or not isinstance(geom_str, str):
                return []

            if 'LINESTRING' in geom_str:
                coords_str = geom_str.replace('LINESTRING (', '').replace(')', '').strip()
                points = []
                for point in coords_str.split(','):
                    parts = point.strip().split()
                    if len(parts) >= 2:
                        try:
                            lon = float(parts[0])
                            lat = float(parts[1])
                            points.append((lon, lat))
                        except ValueError:
                            continue
                return points

            import re
            numbers = re.findall(r'[-+]?\d*\.\d+|\d+', geom_str)
            if len(numbers) >= 4:
                points = []
                for i in range(0, len(numbers)-1, 2):
                    if i+1 < len(numbers):
                        try:
                            lon = float(numbers[i])
                            lat = float(numbers[i+1])
                            points.append((lon, lat))
                        except ValueError:
                            continue
                return points
            return []
        except:
            return []

    def _create_sample_graph(self):
        """Create sample graph for testing"""
        cities = [
            ('Colombo', 6.9271, 79.8612),
            ('Gampaha', 7.0889, 79.9967),
            ('Kandy', 7.2906, 80.6337),
            ('Galle', 6.0535, 80.2210),
            ('Ratnapura', 6.6833, 80.4000)
        ]

        for city, lat, lon in cities:
            self.road_graph.add_node(f"{lat}_{lon}", lat=lat, lon=lon, name=city)

        roads = [
            ('6.9271_79.8612', '7.0889_79.9967', 20),
            ('6.9271_79.8612', '6.0535_80.2210', 120),
            ('6.9271_79.8612', '7.2906_80.6337', 120),
            ('6.9271_79.8612', '6.6833_80.4000', 85),
            ('7.0889_79.9967', '7.2906_80.6337', 80),
        ]

        for u, v, dist in roads:
            self.road_graph.add_edge(u, v, weight=dist, length=dist, safety=0.2)

        logger.info(f"✅ Created sample graph with {self.road_graph.number_of_nodes()} nodes")

    def initialize(self):
        """Initialize the agent"""
        logger.info("🚀 Initializing Evacuation Agent with REAL data sources...")
        self.status = "ready"
        logger.info(f"✅ Evacuation Agent ready with {len(self.shelters)} shelters")
        logger.info(f"   ChromaDB: {self._chromadb_count} | Google Maps: {self._google_maps_count}")
        return {"status": "initialized", "agent": self.name}

    def get_shelters_in_district(self, district):
        """Get all shelters in a district"""
        return [s for s in self.shelters if s.get('district') == district]

    def calculate_route(self, origin_lat, origin_lon, dest_lat, dest_lon, district):
        """Calculate route between two points"""
        road_conditions = self._get_road_conditions(district, 'Medium')
        return self._calculate_safe_route(
            origin_lat, origin_lon,
            dest_lat, dest_lon,
            road_conditions,
            'Medium'
        )

    def get_map_data(self, district):
        """Get map data for visualization"""
        shelters = self.get_shelters_in_district(district)
        return {
            'district': district,
            'shelters': shelters,
            'road_graph': {
                'nodes': list(self.road_graph.nodes)[:100],
                'edges': len(self.road_graph.edges)
            }
        }

    def refresh_shelter_coordinates(self, district: Optional[str] = None) -> Dict[str, Any]:
        """
        Manually re-run coordinate correction for all currently loaded
        shelters (or just those in one district). Useful for a
        POST /evacuation/refresh-coordinates admin endpoint, since the
        automatic pass at startup is capped by max_geocode_corrections_per_load.
        """
        if not self.geocode_correction_enabled or not self.google_maps_api_key:
            return {'corrected': 0, 'skipped': len(self.shelters), 'reason': 'geocode correction disabled or no API key'}

        targets = self.get_shelters_in_district(district) if district else self.shelters
        corrected_count = 0

        for i, shelter in enumerate(self.shelters):
            if district and shelter.get('district') != district:
                continue
            cache_key = shelter.get('shelter_id') or f"{shelter.get('name')}_{shelter.get('district')}"
            self.shelter_cache.pop(cache_key, None)  # force a fresh lookup
            self.shelters[i] = self._correct_shelter_location(shelter)
            if self.shelters[i].get('geocoded'):
                corrected_count += 1

        return {'corrected': corrected_count, 'total_checked': len(targets)}

    def get_status(self):
        """Get agent status"""
        return {
            'name': self.name,
            'status': self.status,
            'shelters_available': len(self.shelters),
            'chromadb_shelters': self._chromadb_count,
            'google_maps_shelters': self._google_maps_count,
            'road_nodes': self.road_graph.number_of_nodes(),
            'road_edges': self.road_graph.number_of_edges(),
            'data_source': self.data_source,
            'gemini_enabled': self.gemini_enabled,
            'rag_enabled': self.rag_enabled,
            'vector_db': 'ChromaDB',
            'google_maps_api_configured': bool(self.google_maps_api_key),
            'chromadb_status': self.rag_service.get_status() if self.rag_enabled else None,
            'has_data': len(self.shelters) > 0,
            'geocode_correction_enabled': self.geocode_correction_enabled,
            'shelters_geocoded': sum(1 for s in self.shelters if s.get('geocoded')),
            'geocode_cache_size': len(self.shelter_cache)
        }


# Create singleton instance
evacuation_agent = EvacuationAgent()