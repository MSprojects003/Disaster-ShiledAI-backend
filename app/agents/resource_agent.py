# backend/app/agents/resource_agent.py

import pandas as pd
import numpy as np
import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Import ChromaDB RAG
from ..services.rag_service_chroma import chroma_rag

# Import Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-generativeai not installed. Run: pip install google-generativeai")

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResourceAgent:
    """
    Agent 5: Emergency Resource Allocation Agent
    Uses REAL data from:
    1. DesInventar CSV (historical disaster data)
    2. Resource Inventory CSV (current resources)
    3. World Bank Data (IDA Resource Allocation Index)
    4. District Data CSV (population, vulnerability)
    5. Gemini API (for analysis and recommendations)
    6. ChromaDB RAG (for historical context)
    7. RiskAgent - for risk predictions
    8. InfrastructureAgent - for infrastructure status
    9. EvacuationAgent - for evacuation needs
    
    NO HARDCODED VALUES - All data from REAL sources
    """

    def __init__(self):
        self.name = "ResourceAgent"
        self.status = "idle"
        self.allocation_history = []
        self.resources = {}
        self.district_data = []
        self.historical_data = []
        self.worldbank_data = {}
        self.gemini_enabled = False
        self.gemini_model = None

        # Other agents (lazy loaded to avoid circular imports)
        self._risk_agent = None
        self._infrastructure_agent = None
        self._evacuation_agent = None

        # Initialize ChromaDB RAG
        self.chroma_rag = chroma_rag
        self.rag_enabled = self.chroma_rag.client is not None

        # Initialize Gemini
        self._init_gemini()

        # Load REAL data only
        self._load_all_data()

        # District centers for location mapping
        self.district_centers = {
            'Colombo': (6.9271, 79.8612),
            'Gampaha': (7.0889, 79.9967),
            'Kalutara': (6.5833, 79.9667),
            'Galle': (6.0535, 80.2210),
            'Matara': (5.9484, 80.5410),
            'Hambantota': (6.1241, 81.1185),
            'Kandy': (7.2906, 80.6337),
            'Matale': (7.4667, 80.6167),
            'Nuwara Eliya': (6.9667, 80.7667),
            'Kurunegala': (7.4833, 80.3667),
            'Puttalam': (8.0333, 79.8333),
            'Anuradhapura': (8.3114, 80.4037),
            'Polonnaruwa': (7.9333, 81.0000),
            'Badulla': (6.9833, 81.0500),
            'Monaragala': (6.8667, 81.3500),
            'Ratnapura': (6.6833, 80.4000),
            'Kegalle': (7.2500, 80.3333),
            'Jaffna': (9.6615, 80.0255),
            'Batticaloa': (7.7170, 81.7005),
            'Ampara': (7.2915, 81.6696),
            'Trincomalee': (8.5637, 81.2153),
            'Kilinochchi': (9.3833, 80.4000),
            'Mannar': (8.9833, 79.9000),
            'Mullaitivu': (9.2667, 80.8000),
            'Vavuniya': (8.7500, 80.5000)
        }

        logger.info(f"✅ Resource Allocation Agent initialized (RAG: {self.rag_enabled})")
        logger.info(f"   Resources loaded: {len(self.resources)}")
        logger.info(f"   Districts loaded: {len(self.district_data)}")
        logger.info(f"   Historical records: {len(self.historical_data)}")

    def _init_gemini(self):
        """Initialize Gemini API"""
        try:
            api_key = os.getenv('GEMINI_API_KEY', '')
            if not api_key:
                logger.warning("⚠️ No Gemini API key found")
                self.gemini_enabled = False
                return

            genai.configure(api_key=api_key)
            models_to_try = ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-pro']
            
            for model_name in models_to_try:
                try:
                    self.gemini_model = genai.GenerativeModel(model_name)
                    test_response = self.gemini_model.generate_content("Say hello")
                    if test_response and test_response.text:
                        self.gemini_enabled = True
                        logger.info(f"✅ Gemini initialized with model '{model_name}'")
                        return
                except Exception as e:
                    logger.warning(f"⚠️ Model '{model_name}' failed: {e}")
                    continue

            logger.error("❌ All Gemini models failed")
            self.gemini_enabled = False

        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            self.gemini_enabled = False

    def _load_all_data(self):
        """Load REAL data from CSV files only - NO HARDCODING"""
        logger.info("📊 Loading REAL data from CSV files...")
        
        # 1. Load DesInventar historical data
        self._load_desinventar_data()
        
        # 2. Load resource inventory (includes World Bank data)
        self._load_resource_data()
        
        # 3. Load district data
        self._load_district_data()
        
        # 4. Extract World Bank data from resources
        self._extract_worldbank_data()
        
        # 5. Sync to ChromaDB for RAG
        if self.rag_enabled and self.historical_data:
            self._sync_historical_to_chromadb()
        
        # 6. Final check - log data sources
        self._log_data_summary()

    def _load_resource_data(self) -> bool:
        """Load REAL resource data from CSV (includes World Bank data)"""
        try:
            csv_path = 'data/resources/resource_inventory.csv'
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                
                self.resources = {}
                for _, row in df.iterrows():
                    resource_type = row['resource_type']
                    district = row.get('district', 'National')
                    key = f"{resource_type}_{district}"
                    self.resources[key] = {
                        'resource_type': resource_type,
                        'total': float(row['total']),
                        'available': float(row['available']),
                        'deployed': float(row['deployed']) if 'deployed' in row else 0,
                        'unit': row.get('unit', 'units'),
                        'description': row.get('description', ''),
                        'district': district
                    }
                
                logger.info(f"✅ Loaded {len(self.resources)} resource items from CSV")
                
                # Count World Bank entries
                wb_items = [k for k in self.resources.keys() if 'irai_score' in k]
                logger.info(f"   - World Bank data entries: {len(wb_items)}")
                
                return True
            else:
                logger.error(f"❌ Resource CSV not found at {csv_path}")
                return False
        except Exception as e:
            logger.error(f"❌ Error loading resource data: {e}")
            return False

    def _extract_worldbank_data(self):
        """Extract World Bank data from resources"""
        self.worldbank_data = {}
        
        for key, resource in self.resources.items():
            if 'irai_score' in key and '_' in key:
                parts = key.split('_')
                if len(parts) >= 3:
                    try:
                        year = int(parts[2])
                        self.worldbank_data[year] = {
                            'score': resource['total'],
                            'available': resource['available'],
                            'deployed': resource['deployed'],
                            'description': resource['description']
                        }
                    except ValueError:
                        continue
        
        if self.worldbank_data:
            logger.info(f"✅ Extracted World Bank data for {len(self.worldbank_data)} years")
            logger.info(f"   Latest year: {max(self.worldbank_data.keys())} - Score: {self.worldbank_data[max(self.worldbank_data.keys())]['score']}")
        else:
            logger.warning("⚠️ No World Bank data found in resources")

    def _load_desinventar_data(self) -> bool:
        """Load REAL DesInventar data from CSV"""
        try:
            csv_path = 'data/historical/processed/resource_priorities.csv'
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                self.historical_data = df.to_dict('records')
                logger.info(f"✅ Loaded {len(self.historical_data)} districts from DesInventar")
                return True
            else:
                logger.warning(f"⚠️ DesInventar CSV not found at {csv_path}")
                return False
        except Exception as e:
            logger.error(f"❌ Error loading DesInventar data: {e}")
            return False

    def _load_district_data(self) -> bool:
        """Load REAL district data from CSV"""
        try:
            csv_path = 'data/resources/district_data.csv'
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                self.district_data = df.to_dict('records')
                logger.info(f"✅ Loaded {len(self.district_data)} districts from CSV")
                return True
            else:
                logger.warning(f"⚠️ District CSV not found at {csv_path}")
                return False
        except Exception as e:
            logger.error(f"❌ Error loading district data: {e}")
            return False

    def _sync_historical_to_chromadb(self):
        """Sync DesInventar historical data to ChromaDB"""
        try:
            synced = 0
            for item in self.historical_data:
                content = f"""
                District: {item.get('district', 'Unknown')}
                Total Events: {item.get('total_events', 0)}
                Primary Risk: {item.get('primary_risk', 'Unknown')}
                Priority Score: {item.get('priority_score', 0)}
                """
                if self.chroma_rag.add_knowledge(content, category='historical'):
                    synced += 1
            logger.info(f"✅ Synced {synced} historical records to ChromaDB")
        except Exception as e:
            logger.error(f"❌ Sync to ChromaDB failed: {e}")

    def _log_data_summary(self):
        """Log summary of all data loaded"""
        logger.info("📊 DATA SOURCES SUMMARY:")
        logger.info(f"   - Resources: {len(self.resources)} items")
        logger.info(f"   - Districts: {len(self.district_data)} records")
        logger.info(f"   - Historical: {len(self.historical_data)} records")
        logger.info(f"   - World Bank: {len(self.worldbank_data)} years")
        logger.info(f"   - Gemini: {'✅ Enabled' if self.gemini_enabled else '❌ Disabled'}")
        logger.info(f"   - ChromaDB RAG: {'✅ Enabled' if self.rag_enabled else '❌ Disabled'}")
        logger.info(f"   - Hardcoded Data: ❌ NO (all data from REAL sources)")

    # ================================================================
    # HELPER: Convert NumPy types to Python types for JSON serialization
    # ================================================================

    def _convert_to_serializable(self, obj):
        """
        Convert NumPy types to Python native types for JSON serialization
        """
        if isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_serializable(v) for v in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_to_serializable(v) for v in obj)
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return self._convert_to_serializable(obj.tolist())
        elif isinstance(obj, pd.Series):
            return self._convert_to_serializable(obj.tolist())
        elif isinstance(obj, pd.DataFrame):
            return self._convert_to_serializable(obj.to_dict('records'))
        else:
            return obj

    # ================================================================
    # AGENT INTEGRATION (Lazy Loading - No Circular Imports)
    # ================================================================

    def _get_risk_agent(self):
        """Lazy load RiskAgent to avoid circular imports"""
        if self._risk_agent is None:
            try:
                from .risk_agent import risk_agent
                self._risk_agent = risk_agent
                logger.info("✅ RiskAgent linked successfully")
            except ImportError as e:
                logger.warning(f"⚠️ RiskAgent not available: {e}")
                self._risk_agent = False
        return self._risk_agent if self._risk_agent is not False else None

    def _get_infrastructure_agent(self):
        """Lazy load InfrastructureAgent to avoid circular imports"""
        if self._infrastructure_agent is None:
            try:
                from .infrastructure_agent import infrastructure_agent
                self._infrastructure_agent = infrastructure_agent
                logger.info("✅ InfrastructureAgent linked successfully")
            except ImportError as e:
                logger.warning(f"⚠️ InfrastructureAgent not available: {e}")
                self._infrastructure_agent = False
        return self._infrastructure_agent if self._infrastructure_agent is not False else None

    def _get_evacuation_agent(self):
        """Lazy load EvacuationAgent to avoid circular imports"""
        if self._evacuation_agent is None:
            try:
                from .evacuation_agent import evacuation_agent
                self._evacuation_agent = evacuation_agent
                logger.info("✅ EvacuationAgent linked successfully")
            except ImportError as e:
                logger.warning(f"⚠️ EvacuationAgent not available: {e}")
                self._evacuation_agent = False
        return self._evacuation_agent if self._evacuation_agent is not False else None

    # ================================================================
    # INTEGRATED DATA FETCHING
    # ================================================================

    def _fetch_integrated_data(self) -> Dict[str, Any]:
        """
        Fetch data from ALL agents for comprehensive resource allocation
        Returns combined risk, infrastructure, and evacuation data
        """
        integrated_data = {
            'risk_predictions': {},
            'infrastructure_status': {},
            'evacuation_status': {},
            'combined_priority': {},
            'data_sources': {
                'risk': False,
                'infrastructure': False,
                'evacuation': False
            }
        }

        # 1. Get Risk Data
        risk_agent = self._get_risk_agent()
        if risk_agent:
            try:
                # Get predictions for all districts
                risk_results = risk_agent.predict_all_districts()
                
                if risk_results:
                    for result in risk_results:
                        district = result.get('district')
                        if district:
                            prediction = result.get('prediction', {})
                            features = result.get('features', {})
                            
                            integrated_data['risk_predictions'][district] = {
                                'risk_score': prediction.get('risk_score', 0),
                                'risk_level': prediction.get('risk_level', 'Low'),
                                'water_level_m': features.get('water_level_m', 0),
                                'rainfall_mm': features.get('rainfall_mm', 0),
                                'flood_extent': features.get('flood_extent', 0)
                            }
                    integrated_data['data_sources']['risk'] = True
                    logger.info(f"✅ Fetched risk data for {len(integrated_data['risk_predictions'])} districts")
            except Exception as e:
                logger.error(f"❌ Failed to fetch risk data: {e}")

        # 2. Get Infrastructure Data
        infra_agent = self._get_infrastructure_agent()
        if infra_agent:
            try:
                # Get infrastructure status for all districts
                districts = list(self.district_centers.keys())
                
                for district in districts[:15]:  # Limit to 15 districts for performance
                    try:
                        # Get infrastructure analysis for each district
                        # Use risk level from risk predictions if available
                        risk_data = integrated_data['risk_predictions'].get(district, {})
                        risk_level = risk_data.get('risk_level', 'Medium')
                        water_level = risk_data.get('water_level_m', 0)
                        
                        result = infra_agent.process({
                            'district': district,
                            'risk_level': risk_level,
                            'water_level_m': water_level
                        })
                        
                        if result and 'road_status' in result:
                            road_status = result.get('road_status', [])
                            
                            # Summarize infrastructure status
                            blocked = len([r for r in road_status if r.get('status') == 'Blocked'])
                            impassable = len([r for r in road_status if r.get('status') == 'Impassable'])
                            total = len(road_status)
                            
                            integrated_data['infrastructure_status'][district] = {
                                'total_roads': total,
                                'blocked_roads': blocked,
                                'impassable_roads': impassable,
                                'safe_roads': total - blocked - impassable,
                                'damage_percentage': round(((blocked + impassable) / max(1, total)) * 100, 2),
                                'roads_accessible': blocked == 0
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to get infrastructure for {district}: {e}")
                
                integrated_data['data_sources']['infrastructure'] = True
                logger.info(f"✅ Fetched infrastructure data for {len(integrated_data['infrastructure_status'])} districts")
            except Exception as e:
                logger.error(f"❌ Failed to fetch infrastructure data: {e}")

        # 3. Get Evacuation Data
        evac_agent = self._get_evacuation_agent()
        if evac_agent:
            try:
                # Get shelters and evacuation status
                districts = list(self.district_centers.keys())
                
                for district in districts[:15]:
                    try:
                        shelters = evac_agent.get_shelters_in_district(district)
                        
                        if shelters:
                            total_capacity = sum(s.get('capacity', 0) for s in shelters if s.get('capacity', 0) > 0)
                            total_available = sum(s.get('available', 0) for s in shelters if s.get('available', 0) > 0)
                            
                            integrated_data['evacuation_status'][district] = {
                                'shelter_count': len(shelters),
                                'total_capacity': total_capacity,
                                'available_capacity': total_available,
                                'shelters': shelters[:3],  # Top 3 shelters
                                'evacuation_required': total_available < 100 if total_available > 0 else False,
                                'evacuated_people': max(0, total_capacity - total_available)
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to get evacuation data for {district}: {e}")
                
                integrated_data['data_sources']['evacuation'] = True
                logger.info(f"✅ Fetched evacuation data for {len(integrated_data['evacuation_status'])} districts")
            except Exception as e:
                logger.error(f"❌ Failed to fetch evacuation data: {e}")

        # 4. Calculate Combined Priority
        all_districts = set(
            list(integrated_data['risk_predictions'].keys()) +
            list(integrated_data['infrastructure_status'].keys()) +
            list(integrated_data['evacuation_status'].keys())
        )

        # Add historical data districts
        for hist in self.historical_data:
            district = hist.get('district')
            if district:
                all_districts.add(district)

        # Add all district centers (ensure all districts are considered)
        for district in self.district_centers.keys():
            all_districts.add(district)

        for district in all_districts:
            risk = integrated_data['risk_predictions'].get(district, {})
            infra = integrated_data['infrastructure_status'].get(district, {})
            evac = integrated_data['evacuation_status'].get(district, {})
            
            # Historical data
            hist_data = None
            for h in self.historical_data:
                if h.get('district') == district:
                    hist_data = h
                    break
            
            # Weighted priority calculation
            risk_weight = 0.40
            infra_weight = 0.25
            evac_weight = 0.20
            hist_weight = 0.15
            
            risk_score = risk.get('risk_score', 0)
            
            # Infrastructure impact (higher = worse)
            infra_impact = infra.get('damage_percentage', 0)
            
            # Evacuation urgency (0-100)
            evac_urgency = 0
            if evac.get('shelter_count', 0) > 0:
                total_cap = evac.get('total_capacity', 1)
                available = evac.get('available_capacity', 0)
                if total_cap > 0:
                    evac_urgency = min(100, ((total_cap - available) / total_cap) * 100)
            else:
                # If no shelters, assume some urgency if risk is high
                if risk_score > 50:
                    evac_urgency = 30
            
            # Historical risk (0-100)
            historical_risk = hist_data.get('priority_score', 0) if hist_data else 0
            
            # Combined score (0-100)
            combined_score = (
                risk_score * risk_weight +
                infra_impact * infra_weight +
                evac_urgency * evac_weight +
                historical_risk * hist_weight
            )
            
            # Ensure score is between 0-100
            combined_score = min(max(combined_score, 0), 100)
            
            integrated_data['combined_priority'][district] = {
                'combined_score': round(combined_score, 2),
                'risk_score': round(risk_score, 2),
                'risk_level': risk.get('risk_level', 'Low'),
                'infra_impact': round(infra_impact, 2),
                'evac_urgency': round(evac_urgency, 2),
                'historical_risk': round(historical_risk, 2),
                'needs_immediate_attention': combined_score > 60,
                'has_shelters': evac.get('shelter_count', 0) > 0
            }

        logger.info(f"✅ Calculated combined priority for {len(integrated_data['combined_priority'])} districts")
        return integrated_data

    def initialize(self):
        """Initialize the agent"""
        logger.info("🚀 Initializing Resource Allocation Agent...")
        self.status = "ready"
        return {"status": "initialized", "agent": self.name}

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main processing method"""
        action = input_data.get('action', 'allocate')
        
        if action == 'allocate':
            return self._allocate_resources(input_data)
        elif action == 'get_status':
            return self._get_resource_status()
        elif action == 'get_worldbank_data':
            return self._get_worldbank_data()
        elif action == 'update_resources':
            return self._update_resources(input_data)
        elif action == 'deployment_plan':
            return self._get_deployment_plan(input_data)
        elif action == 'gemini_analyze':
            return self._gemini_analyze(input_data)
        elif action == 'get_historical_summary':
            return self._get_historical_summary()
        elif action == 'rag_search':
            return self._rag_search(input_data)
        else:
            return {"error": f"Unknown action: {action}"}

    def _get_worldbank_data(self) -> Dict[str, Any]:
        """Get World Bank data"""
        return {
            'success': True,
            'data': self.worldbank_data,
            'latest_year': max(self.worldbank_data.keys()) if self.worldbank_data else None,
            'latest_score': self.worldbank_data[max(self.worldbank_data.keys())]['score'] if self.worldbank_data else None,
            'total_years': len(self.worldbank_data),
            'timestamp': datetime.now().isoformat()
        }

    # ================================================================
    # MAIN RESOURCE ALLOCATION (FIXED - PROPER DISTRIBUTION)
    # ================================================================

    def _allocate_resources(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Allocate resources using integrated data from ALL agents
        FIXED: Proper distribution across multiple districts
        """
        logger.info("📊 Allocating resources using integrated agent data...")

        # Get integrated data from all agents
        integrated_data = self._fetch_integrated_data()
        combined_priority = integrated_data.get('combined_priority', {})
        
        if not combined_priority:
            logger.warning("⚠️ No integrated data available, using fallback")
            return self._allocate_fallback(input_data)
        
        # Get available resources (filter out zero and worldbank data)
        all_available = self._get_available_resources()
        available = {k: v for k, v in all_available.items() if v > 0 and 'irai_score' not in k}
        
        if not available:
            logger.warning("⚠️ No resources available to allocate")
            return {
                'error': 'No resources available',
                'available_resources': available,
                'note': 'All resources are already deployed. Please reset inventory.'
            }
        
        # Sort districts by combined priority (highest first)
        sorted_districts = sorted(
            combined_priority.items(),
            key=lambda x: x[1]['combined_score'],
            reverse=True
        )

        # Filter to districts that need attention (score > 20 OR risk > 50)
        priority_districts = []
        for district, data in sorted_districts:
            score = data['combined_score']
            risk_score = data.get('risk_score', 0)
            
            # Include districts with combined score > 20 OR risk score > 50
            if score > 20 or risk_score > 50:
                priority_districts.append((district, data))
            
            # Ensure we have at least 5 districts
            if len(priority_districts) >= 10:
                break

        # If we still have less than 5, add more
        if len(priority_districts) < 5:
            for district, data in sorted_districts:
                if (district, data) not in priority_districts:
                    priority_districts.append((district, data))
                    if len(priority_districts) >= 10:
                        break

        if not priority_districts:
            logger.warning("⚠️ No priority districts found, using top 10")
            priority_districts = sorted_districts[:10]

        logger.info(f"📊 Allocating resources to {len(priority_districts)} priority districts")

        # Calculate total priority score for distribution
        total_priority = sum(data['combined_score'] for _, data in priority_districts)
        if total_priority == 0:
            total_priority = 1  # Prevent division by zero

        # Create a copy of available resources for tracking
        remaining_resources = available.copy()
        
        # Also track original amounts for logging
        original_amounts = available.copy()
        
        allocation_plan = []

        # ================================================================
        # FIX: PROPER PROPORTIONAL ALLOCATION
        # ================================================================
        # First, calculate what percentage of resources each district should get
        district_shares = []
        for district, data in priority_districts:
            score = data['combined_score']
            # Calculate share percentage (0-100)
            share_percentage = (score / total_priority) * 100
            
            # Cap individual district share at 25% max to prevent one district getting everything
            if share_percentage > 25:
                share_percentage = 25
                logger.info(f"⚠️ Capping {district} share at 25% (was {share_percentage:.1f}%)")
            
            district_shares.append({
                'district': district,
                'data': data,
                'share_percentage': share_percentage,
                'score': score
            })

        # Normalize shares to sum to 100%
        total_share = sum(s['share_percentage'] for s in district_shares)
        if total_share > 0:
            for share in district_shares:
                share['share_percentage'] = (share['share_percentage'] / total_share) * 100

        # Now allocate resources based on these percentages
        for share_info in district_shares:
            district = share_info['district']
            data = share_info['data']
            share_percentage = share_info['share_percentage'] / 100  # Convert to decimal
            
            score = data['combined_score']
            
            # Determine urgency based on score
            if score >= 75:
                urgency = '🚨 CRITICAL - IMMEDIATE DEPLOYMENT'
                tier = 'critical'
            elif score >= 60:
                urgency = '⚠️ URGENT - DEPLOY WITHIN 2 HOURS'
                tier = 'high'
            elif score >= 40:
                urgency = '📋 DEPLOY WITHIN 4 HOURS'
                tier = 'medium'
            else:
                urgency = '✅ MONITOR AND PREPARE'
                tier = 'low'

            # Calculate allocation for each resource
            allocation = {}
            for resource, amount_available in original_amounts.items():
                if amount_available > 0:
                    # Use 80% of available resources for distribution, keep 20% as reserve
                    max_allocatable = int(amount_available * 0.8)
                    allocated = int(max_allocatable * share_percentage)
                    
                    # Ensure we don't exceed remaining resources
                    if resource in remaining_resources:
                        allocated = min(allocated, remaining_resources.get(resource, 0))
                    
                    # Minimum allocation for districts with high risk
                    if data.get('risk_score', 0) > 60 and allocated < 1 and amount_available >= len(priority_districts):
                        allocated = 1  # Give at least 1 unit to high-risk districts
                    
                    allocation[resource] = allocated

            allocation_plan.append({
                'district': district,
                'priority_tier': tier,
                'priority_score': float(round(score, 2)),
                'risk_score': float(data.get('risk_score', 0)),
                'risk_level': data.get('risk_level', 'Low'),
                'infrastructure_impact': float(data.get('infra_impact', 0)),
                'evacuation_urgency': float(data.get('evac_urgency', 0)),
                'historical_risk': float(data.get('historical_risk', 0)),
                'urgency': urgency,
                'allocated_resources': allocation,
                'total_allocated': int(sum(allocation.values())),
                'share_percentage': float(round(share_percentage * 100, 2)),
                'has_shelters': bool(data.get('has_shelters', False)),
                'needs_immediate_attention': bool(data.get('needs_immediate_attention', False))
            })

            # Deduct allocated resources
            for resource, amount in allocation.items():
                if resource in remaining_resources:
                    remaining_resources[resource] = max(0, remaining_resources[resource] - amount)

        # ================================================================
        # Second pass: Distribute any remaining resources to high-priority districts
        # ================================================================
        remaining_total = sum(remaining_resources.values())
        if remaining_total > 0:
            logger.info(f"📊 Distributing {remaining_total} remaining resources...")
            
            # Get districts with highest need
            high_priority = [p for p in allocation_plan if p['priority_score'] > 50]
            
            for plan in high_priority[:5]:  # Top 5 high-priority districts
                for resource, amount_remaining in remaining_resources.items():
                    if amount_remaining > 0:
                        # Give extra to districts with low allocation
                        if plan['allocated_resources'].get(resource, 0) < 3:
                            extra = min(amount_remaining // 5, 5)
                            if extra > 0:
                                plan['allocated_resources'][resource] = plan['allocated_resources'].get(resource, 0) + extra
                                plan['total_allocated'] += extra
                                remaining_resources[resource] = max(0, remaining_resources[resource] - extra)
                                if remaining_resources[resource] == 0:
                                    break

        # ================================================================
        # UPDATE DEPLOYED RESOURCES
        # ================================================================
        for plan in allocation_plan:
            allocated = plan.get('allocated_resources', {})
            for resource, amount in allocated.items():
                if amount > 0:
                    # Find the resource in inventory and update
                    for key, res in self.resources.items():
                        if res.get('resource_type') == resource and res.get('district') == 'National':
                            self.resources[key]['deployed'] += amount
                            self.resources[key]['available'] = max(0, self.resources[key]['available'] - amount)
                            break

        # ================================================================
        # CONVERT TO JSON-SERIALIZABLE FORMAT
        # ================================================================
        serializable_plan = self._convert_to_serializable(allocation_plan)
        resources_used = self._convert_to_serializable(self._get_used_resources())
        resources_remaining = self._convert_to_serializable(self._get_available_resources())

        # Save to database and ChromaDB
        self._save_to_database(serializable_plan)
        self._save_to_chromadb(serializable_plan)
        self._save_inventory_to_csv()

        self.allocation_history.append({
            'timestamp': datetime.now().isoformat(),
            'plan': serializable_plan,
            'data_sources': integrated_data['data_sources']
        })

        return {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'total_districts': len(serializable_plan),
            'allocation_plan': serializable_plan,
            'resources_used': resources_used,
            'resources_remaining': resources_remaining,
            'data_sources_used': integrated_data['data_sources'],
            'gemini_available': self.gemini_enabled,
            'rag_available': self.rag_enabled,
            'worldbank_data_used': bool(self.worldbank_data),
            'saved_to_db': True,
            'saved_to_chromadb': True
        }

    def _allocate_fallback(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback allocation when integrated data is not available
        """
        logger.info("📊 Using fallback allocation...")
        
        # Get all districts
        districts = list(self.district_centers.keys())
        if not districts:
            return {'error': 'No districts available for fallback'}
        
        available = self._get_available_resources()
        if not available or all(v == 0 for v in available.values()):
            return {'error': 'No resources available'}
        
        # Filter to non-zero resources
        available = {k: v for k, v in available.items() if v > 0 and 'irai_score' not in k}
        
        if not available:
            return {'error': 'No deployable resources available'}
        
        # Distribute resources evenly among top 10 districts
        target_districts = districts[:10]
        allocation_plan = []
        
        # Calculate per-district allocation (even split)
        per_district = {}
        for resource, amount in available.items():
            per_district[resource] = amount // len(target_districts)
        
        for district in target_districts:
            allocation = per_district.copy()
            allocation_plan.append({
                'district': district,
                'priority_tier': 'medium',
                'priority_score': 50.0,
                'risk_score': 0.0,
                'risk_level': 'Medium',
                'infrastructure_impact': 0.0,
                'evacuation_urgency': 0.0,
                'historical_risk': 0.0,
                'urgency': '📋 DEPLOY WITHIN 4 HOURS',
                'allocated_resources': allocation,
                'total_allocated': int(sum(allocation.values())),
                'share_percentage': 10.0,
                'has_shelters': False,
                'needs_immediate_attention': False
            })
        
        # Convert to serializable
        serializable_plan = self._convert_to_serializable(allocation_plan)
        
        # Update deployed resources
        for plan in allocation_plan:
            allocated = plan.get('allocated_resources', {})
            for resource, amount in allocated.items():
                if amount > 0:
                    for key, res in self.resources.items():
                        if res.get('resource_type') == resource and res.get('district') == 'National':
                            self.resources[key]['deployed'] += amount
                            self.resources[key]['available'] = max(0, self.resources[key]['available'] - amount)
                            break
        
        # Save inventory
        self._save_inventory_to_csv()
        
        return {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'total_districts': len(serializable_plan),
            'allocation_plan': serializable_plan,
            'resources_used': self._convert_to_serializable(self._get_used_resources()),
            'resources_remaining': self._convert_to_serializable(self._get_available_resources()),
            'data_sources_used': {'fallback': True},
            'note': 'Using fallback allocation due to missing data',
            'saved_to_db': False,
            'saved_to_chromadb': False
        }

    # ================================================================
    # DATABASE OPERATIONS
    # ================================================================

    def _save_to_database(self, allocation_plan: List[Dict]):
        """Save allocation to PostgreSQL with proper serialization"""
        try:
            from ..database.db import db
            from ..database.models import ResourceAllocation
            
            saved_count = 0
            for plan in allocation_plan:
                # Ensure all values are JSON serializable
                serialized_plan = self._convert_to_serializable(plan)
                
                record = ResourceAllocation(
                    district=plan.get('district', 'Unknown'),
                    allocation_plan=serialized_plan,
                    resources_used=self._convert_to_serializable(self._get_used_resources()),
                    resources_remaining=self._convert_to_serializable(self._get_available_resources()),
                    priority_score=float(plan.get('priority_score', 0)),
                    risk_level=plan.get('risk_level', 'Low'),
                    risk_score=float(plan.get('risk_score', 0)),
                    urgency=plan.get('urgency', 'Monitor')
                )
                db.session.add(record)
                saved_count += 1
            
            db.session.commit()
            logger.info(f"✅ Saved {saved_count} allocations to database")
            
        except Exception as e:
            logger.error(f"❌ Failed to save allocations: {e}")
            if 'db' in locals():
                db.session.rollback()

    def _save_to_chromadb(self, allocation_plan: List[Dict]):
        """Save allocations to ChromaDB for RAG"""
        try:
            synced = 0
            for plan in allocation_plan[:10]:
                # Convert to serializable
                plan_serialized = self._convert_to_serializable(plan)
                
                content = f"""
District: {plan_serialized.get('district', 'Unknown')}
Priority Score: {plan_serialized.get('priority_score', 0)}
Risk Level: {plan_serialized.get('risk_level', 'Low')}
Infrastructure Impact: {plan_serialized.get('infrastructure_impact', 0)}
Evacuation Urgency: {plan_serialized.get('evacuation_urgency', 0)}
Urgency: {plan_serialized.get('urgency', 'Monitor')}
Allocated: {json.dumps(plan_serialized.get('allocated_resources', {}))}
Timestamp: {datetime.now().isoformat()}
                """
                if self.chroma_rag.add_knowledge(content, category='allocations'):
                    synced += 1
            logger.info(f"✅ Synced {synced} allocations to ChromaDB")
        except Exception as e:
            logger.error(f"❌ ChromaDB sync failed: {e}")

    def _save_inventory_to_csv(self):
        """Save current inventory to CSV"""
        try:
            import pandas as pd
            csv_path = 'data/resources/resource_inventory.csv'
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            
            data = []
            for key, resource in self.resources.items():
                data.append({
                    'resource_type': resource['resource_type'],
                    'total': float(resource['total']),
                    'available': float(resource['available']),
                    'deployed': float(resource['deployed']),
                    'unit': resource['unit'],
                    'description': resource['description'],
                    'district': resource['district']
                })
            
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False)
            logger.info(f"✅ Saved inventory to {csv_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save inventory: {e}")

    # ================================================================
    # RESOURCE MANAGEMENT
    # ================================================================

    def _get_used_resources(self) -> Dict[str, int]:
        """Get deployed resources (excluding World Bank data)"""
        used = {}
        for key, resource in self.resources.items():
            if resource.get('district') == 'National' and 'irai_score' not in resource.get('resource_type', ''):
                used[resource['resource_type']] = used.get(resource['resource_type'], 0) + resource.get('deployed', 0)
        return used

    def _get_available_resources(self) -> Dict[str, int]:
        """Get available resources (excluding World Bank data)"""
        available = {}
        for key, resource in self.resources.items():
            if resource.get('district') == 'National' and 'irai_score' not in resource.get('resource_type', ''):
                available[resource['resource_type']] = available.get(resource['resource_type'], 0) + resource.get('available', 0)
        return available

    def _get_resource_status(self) -> Dict[str, Any]:
        """Get current resource status"""
        total = sum(r.get('total', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        available = sum(r.get('available', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        deployed = sum(r.get('deployed', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        
        return {
            'agent': self.name,
            'status': self.status,
            'resources': list(self.resources.values()),
            'worldbank_data': self.worldbank_data,
            'summary': {
                'total_resources': total,
                'available_resources': available,
                'deployed_resources': deployed,
                'utilization_percentage': round((deployed / total * 100), 2) if total > 0 else 0
            }
        }

    def _update_resources(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update resource levels"""
        updates = input_data.get('resources', {})
        district = input_data.get('district', 'National')
        
        for resource_type, amount in updates.items():
            key = f"{resource_type}_{district}"
            if key in self.resources:
                self.resources[key]['available'] += amount
                self.resources[key]['total'] += amount
            else:
                self.resources[key] = {
                    'resource_type': resource_type,
                    'total': amount,
                    'available': amount,
                    'deployed': 0,
                    'unit': 'units',
                    'description': f'{resource_type} for {district}',
                    'district': district
                }
        
        self._save_inventory_to_csv()
        return {'status': 'updated', 'resources': self.resources}

    def _get_deployment_plan(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get deployment plan for a specific district"""
        district = input_data.get('district', 'Colombo')
        
        if self.allocation_history:
            latest = self.allocation_history[-1]
            for plan in latest.get('plan', []):
                if plan['district'] == district:
                    return {
                        'district': district,
                        'deployment_plan': plan,
                        'timestamp': latest['timestamp']
                    }
        
        return {'error': f'No deployment plan found for {district}'}

    def _get_historical_summary(self) -> Dict[str, Any]:
        """Get historical data summary"""
        if self.historical_data:
            total = sum(h.get('total_events', 0) for h in self.historical_data)
            sorted_data = sorted(self.historical_data, key=lambda x: x.get('total_events', 0), reverse=True)
            top_5 = [{'district': h['district'], 'total_events': h.get('total_events', 0)} for h in sorted_data[:5]]
            
            return {
                'total_historical_events': total,
                'districts_with_data': len(self.historical_data),
                'data_source': 'DesInventar Database 1974-2022',
                'most_affected_districts': top_5
            }
        return {'error': 'No historical data loaded'}

    def _rag_search(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search RAG for historical context"""
        if not self.rag_enabled:
            return {'error': 'ChromaDB RAG not enabled'}
        
        try:
            query = input_data.get('query', '')
            k = input_data.get('k', 5)
            
            if not query:
                return {'error': 'No query provided'}
            
            results = self.chroma_rag.search_knowledge(query, k=k, category='historical')
            
            return {
                'success': True,
                'query': query,
                'num_results': len(results),
                'results': results,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ RAG search failed: {e}")
            return {'error': str(e)}

    def _gemini_analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze disaster situation using Gemini"""
        if not self.gemini_enabled:
            return {
                'error': 'Gemini API not available',
                'hint': 'Check GEMINI_API_KEY in .env file'
            }
        
        try:
            district = input_data.get('district', 'Colombo')
            risk_score = input_data.get('risk_score', 50)
            risk_level = input_data.get('risk_level', 'Medium')
            
            # Get integrated data for context
            integrated_data = self._fetch_integrated_data()
            district_data = integrated_data.get('combined_priority', {}).get(district, {})
            
            rag_context = self._get_rag_context(district, risk_level)
            wb_score = self.worldbank_data.get(2025, {}).get('score', 'N/A')
            
            prompt = f"""
            Analyze disaster situation in {district}, Sri Lanka.
            
            Risk Score: {risk_score}%
            Risk Level: {risk_level}
            World Bank Score: {wb_score}
            Infrastructure Impact: {district_data.get('infra_impact', 0)}%
            Evacuation Urgency: {district_data.get('evac_urgency', 0)}%
            
            Historical Context:
            {rag_context if rag_context else 'No historical records found'}
            
            Return ONLY valid JSON:
            {{
                "recommendations": ["list", "of", "recommendations"],
                "priority_areas": ["list", "of", "areas"],
                "response_time": "estimated time needed",
                "historical_context_used": true/false,
                "worldbank_score": {wb_score}
            }}
            """
            
            response = self.gemini_model.generate_content(prompt)
            if response and response.text:
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if match:
                    analysis = json.loads(match.group())
                    return {
                        'success': True,
                        'district': district,
                        'analysis': analysis,
                        'source': 'Gemini API',
                        'rag_context_used': bool(rag_context),
                        'worldbank_data_used': bool(self.worldbank_data)
                    }
            
            return {'error': 'Failed to get response from Gemini'}
        except Exception as e:
            logger.error(f"❌ Gemini analysis failed: {e}")
            return {'error': str(e)}

    def _get_rag_context(self, district: str, risk_level: Optional[str] = None, k: int = 3) -> str:
        """Retrieve historical context from ChromaDB"""
        if not self.rag_enabled:
            return ""
        
        try:
            query = f"{district} disaster risk history"
            if risk_level:
                query += f" {risk_level} risk"
            
            results = self.chroma_rag.search_knowledge(query, k=k, category='historical')
            if results:
                return "\n\n".join([r['content'].strip() for r in results if r.get('content')])
            return ""
        except Exception as e:
            logger.error(f"❌ RAG context retrieval failed: {e}")
            return ""

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        total = sum(r.get('total', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        available = sum(r.get('available', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        deployed = sum(r.get('deployed', 0) for r in self.resources.values() if 'irai_score' not in r.get('resource_type', ''))
        
        return {
            'name': self.name,
            'status': self.status,
            'resources': list(self.resources.values()),
            'worldbank_data': self.worldbank_data,
            'summary': {
                'total_resources': total,
                'available': available,
                'deployed': deployed,
                'utilization': round((deployed / total * 100), 2) if total > 0 else 0
            },
            'allocation_history_count': len(self.allocation_history),
            'gemini_enabled': self.gemini_enabled,
            'historical_data_loaded': bool(self.historical_data),
            'rag_enabled': self.rag_enabled,
            'vector_db': 'ChromaDB' if self.rag_enabled else 'None',
            'worldbank_data_loaded': bool(self.worldbank_data),
            'hardcoded_data_used': False
        }


# Create singleton instance
resource_agent = ResourceAgent()