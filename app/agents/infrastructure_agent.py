import pandas as pd
import numpy as np
import os
from datetime import datetime
import logging
from typing import Dict, Any, List
from ..models.infrastructure_model import infrastructure_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InfrastructureAgent:
    """
    Agent 3: Infrastructure Intelligence Agent
    Uses ML model (Logistic Regression + Random Forest) for road status prediction
    """
    
    def __init__(self):
        self.name = "InfrastructureAgent"
        self.status = "idle"
        self.roads = []
        self.ml_model = infrastructure_model
        self.use_ml = self.ml_model._load_models()
        
        self._load_road_data()
        
        # Road vulnerability weights (from ML model)
        self.road_vulnerability = {
            'motorway': 0.1,
            'trunk': 0.15,
            'primary': 0.2,
            'secondary': 0.3,
            'tertiary': 0.4,
            'residential': 0.6,
            'living_street': 0.6,
            'service': 0.5,
            'unclassified': 0.7,
            'track': 0.8,
            'path': 0.85,
            'footway': 0.8
        }
        
        # District vulnerability (from ML model)
        self.district_vulnerability = {
            'Colombo': 0.95, 'Gampaha': 0.90, 'Kalutara': 0.85,
            'Galle': 0.85, 'Matara': 0.80, 'Ratnapura': 0.85,
            'Kandy': 0.40, 'Kegalle': 0.70, 'Badulla': 0.55,
            'Nuwara Eliya': 0.30, 'Kurunegala': 0.60, 'Puttalam': 0.70,
            'Anuradhapura': 0.40, 'Polonnaruwa': 0.45,
            'Hambantota': 0.60, 'Monaragala': 0.50, 'Matale': 0.45
        }
        
        logger.info(f"✅ Infrastructure Agent initialized (ML: {'Enabled' if self.use_ml else 'Disabled'})")
    
    def _load_road_data(self):
        """Load road data from CSV"""
        try:
            road_file = 'data/infrastructure/processed/sri_lanka_roads.csv'
            if os.path.exists(road_file):
                self.roads = pd.read_csv(road_file).to_dict('records')
                logger.info(f"✅ Loaded {len(self.roads)} road segments")
            else:
                self._create_default_roads()
        except Exception as e:
            logger.error(f"❌ Error loading road data: {e}")
            self._create_default_roads()
    
    def _create_default_roads(self):
        """Create default roads"""
        self.roads = [
            {'road_id': 'A1', 'name': 'Colombo-Kandy Rd', 'highway': 'primary', 
             'elevation': 50, 'districts': 'Colombo,Gampaha,Kandy'},
            {'road_id': 'A2', 'name': 'Colombo-Galle Rd', 'highway': 'primary',
             'elevation': 10, 'districts': 'Colombo,Kalutara,Galle,Matara'},
            {'road_id': 'A4', 'name': 'Colombo-Ratnapura Rd', 'highway': 'primary',
             'elevation': 100, 'districts': 'Colombo,Kalutara,Ratnapura'},
        ]
        logger.info(f"✅ Created {len(self.roads)} default roads")
    
    def initialize(self):
        """Initialize the agent"""
        logger.info("🚀 Initializing Infrastructure Agent with ML model...")
        self.status = "ready"
        logger.info(f"✅ Infrastructure Agent ready (ML: {'✅ Enabled' if self.use_ml else '❌ Disabled'})")
        return {"status": "initialized", "agent": self.name}
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main processing method"""
        district = input_data.get('district', 'Colombo')
        risk_level = input_data.get('risk_level', 'Low')
        risk_score = input_data.get('risk_score', 0)
        water_level = input_data.get('water_level_m', 0)
        rainfall = input_data.get('rainfall_mm', 0)
        
        # Analyze roads using ML model
        road_status = self._analyze_roads_with_ml(
            district, water_level, rainfall, risk_level
        )
        
        return {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'road_status': road_status,
            'total_roads_analyzed': len(road_status),
            'blocked_roads': len([r for r in road_status if r['status'] == 'Blocked']),
            'impassable_roads': len([r for r in road_status if r['status'] == 'Impassable']),
            'safe_roads': len([r for r in road_status if r['status'] == 'Safe']),
            'model_used': 'ML Ensemble' if self.use_ml else 'Rule-based',
            'alert_triggered': risk_level in ['High', 'Critical']
        }
    
    def _analyze_roads_with_ml(self, district, water_level, rainfall, risk_level):
        """
        Analyze roads using ML model
        """
        results = []
        
        # Get roads for this district
        district_roads = []
        for road in self.roads:
            road_districts = road.get('districts', '').split(',')
            if district in road_districts:
                district_roads.append(road)
        
        if not district_roads:
            district_roads = self.roads[:20]
        
        # Get district vulnerability
        district_risk = self.district_vulnerability.get(district, 0.5)
        
        for road in district_roads[:50]:  # Limit for performance
            road_type = road.get('highway', 'unclassified')
            vulnerability = self.road_vulnerability.get(road_type, 0.5)
            elevation = road.get('elevation', 50)
            
            # Features for ML prediction
            features = {
                'water_level_m': water_level,
                'rainfall_mm': rainfall,
                'road_vulnerability': vulnerability,
                'elevation_m': elevation,
                'district_risk': district_risk
            }
            
            if self.use_ml:
                # Use ML model
                prediction = self.ml_model.predict(features)
                if 'error' in prediction:
                    # Fallback to rule-based
                    prediction = self._rule_based_predict(features)
            else:
                # Rule-based fallback
                prediction = self._rule_based_predict(features)
            
            results.append({
                'road_id': road.get('road_id', 'Unknown'),
                'road_name': road.get('name', 'Unknown Road'),
                'road_type': road_type,
                'elevation_m': elevation,
                'status': prediction.get('status', 'Safe'),
                'status_code': prediction.get('status_code', 0),
                'confidence': prediction.get('confidence', 0),
                'recommendation': prediction.get('recommendation', 'Monitor conditions')
            })
        
        return results
    
    def _rule_based_predict(self, features):
        """
        Fallback rule-based prediction
        """
        water_level = features.get('water_level_m', 0)
        rainfall = features.get('rainfall_mm', 0)
        vulnerability = features.get('road_vulnerability', 0.5)
        
        # Calculate damage probability
        damage_prob = (
            (water_level / 8) * 0.35 +
            (rainfall / 200) * 0.20 +
            vulnerability * 0.25 +
            0.20
        )
        damage_prob = np.clip(damage_prob, 0, 0.95)
        
        if damage_prob < 0.3:
            status = 'Safe'
            confidence = (1 - damage_prob) * 100
            recommendation = 'Road is safe to use'
        elif damage_prob < 0.6:
            status = 'Impassable'
            confidence = damage_prob * 100
            recommendation = 'Road is impassable - Avoid this road'
        else:
            status = 'Blocked'
            confidence = damage_prob * 100
            recommendation = 'ROAD BLOCKED - Do not use'
        
        return {
            'status': status,
            'status_code': 0 if status == 'Safe' else 1 if status == 'Impassable' else 2,
            'confidence': round(confidence, 2),
            'recommendation': recommendation
        }
    
    def get_status(self):
        """Get agent status"""
        return {
            'name': self.name,
            'status': self.status,
            'roads_monitored': len(self.roads),
            'model_loaded': self.use_ml,
            'model_info': self.ml_model.get_model_info() if self.use_ml else None
        }

# Create singleton instance
infrastructure_agent = InfrastructureAgent()