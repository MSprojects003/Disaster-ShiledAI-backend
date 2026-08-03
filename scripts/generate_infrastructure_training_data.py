"""
Generate training data for Infrastructure Agent ML model
Uses DMC flood reports + OSM road data
"""

import pandas as pd
import numpy as np
import os
import json
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InfrastructureDataGenerator:
    """
    Generate training data for Infrastructure Agent ML model
    """
    
    def __init__(self):
        self.data_dir = "data/infrastructure/"
        self.processed_dir = os.path.join(self.data_dir, "processed/")
        self.training_dir = os.path.join(self.data_dir, "training/")
        
        os.makedirs(self.training_dir, exist_ok=True)
        
        # Road types and their vulnerability weights
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
        
        # Sri Lanka districts with flood risk
        self.districts = [
            'Colombo', 'Gampaha', 'Kalutara', 'Galle', 'Matara',
            'Ratnapura', 'Kandy', 'Kegalle', 'Badulla', 'Nuwara Eliya',
            'Kurunegala', 'Puttalam', 'Anuradhapura', 'Polonnaruwa',
            'Hambantota', 'Monaragala', 'Matale'
        ]
        
        # District flood vulnerability (0-1)
        self.district_vulnerability = {
            'Colombo': 0.95,
            'Gampaha': 0.90,
            'Kalutara': 0.85,
            'Galle': 0.85,
            'Matara': 0.80,
            'Ratnapura': 0.85,
            'Kandy': 0.40,
            'Kegalle': 0.70,
            'Badulla': 0.55,
            'Nuwara Eliya': 0.30,
            'Kurunegala': 0.60,
            'Puttalam': 0.70,
            'Anuradhapura': 0.40,
            'Polonnaruwa': 0.45,
            'Hambantota': 0.60,
            'Monaragala': 0.50,
            'Matale': 0.45
        }
    
    def load_historical_flood_data(self):
        """
        Load historical flood data from DMC reports
        """
        try:
            # Load river data from DMC
            river_path = 'data/river_gauges/processed/river_data_extracted.csv'
            if os.path.exists(river_path):
                df = pd.read_csv(river_path)
                logger.info(f"✅ Loaded {len(df)} river records")
                return df
            else:
                logger.warning("⚠️ River data not found")
                return None
        except Exception as e:
            logger.error(f"❌ Error loading river data: {e}")
            return None
    
    def load_road_data(self):
        """
        Load road network data
        """
        try:
            road_path = 'data/infrastructure/processed/sri_lanka_roads.csv'
            if os.path.exists(road_path):
                df = pd.read_csv(road_path)
                logger.info(f"✅ Loaded {len(df)} road segments")
                return df
            else:
                logger.warning("⚠️ Road data not found")
                return None
        except Exception as e:
            logger.error(f"❌ Error loading road data: {e}")
            return None
    
    def generate_training_data(self, n_samples=10000):
        """
        Generate synthetic training data based on real patterns
        """
        logger.info(f"📊 Generating {n_samples} training samples...")
        
        data = []
        
        # Load real data for patterns
        river_data = self.load_historical_flood_data()
        road_data = self.load_road_data()
        
        # Use known patterns from DMC data
        flood_patterns = {
            'Colombo': {'water_level': (3.0, 6.5), 'rainfall': (50, 150), 'flood_freq': 0.8},
            'Gampaha': {'water_level': (2.5, 5.5), 'rainfall': (40, 120), 'flood_freq': 0.7},
            'Ratnapura': {'water_level': (3.5, 7.0), 'rainfall': (60, 180), 'flood_freq': 0.85},
            'Galle': {'water_level': (2.0, 5.0), 'rainfall': (50, 130), 'flood_freq': 0.75},
            'Matara': {'water_level': (2.0, 4.5), 'rainfall': (40, 110), 'flood_freq': 0.7},
            'Kandy': {'water_level': (1.0, 3.0), 'rainfall': (30, 80), 'flood_freq': 0.3},
            'Kurunegala': {'water_level': (1.5, 4.0), 'rainfall': (35, 90), 'flood_freq': 0.5},
            'Puttalam': {'water_level': (2.0, 4.5), 'rainfall': (40, 100), 'flood_freq': 0.6},
            'Kalutara': {'water_level': (2.5, 6.0), 'rainfall': (45, 140), 'flood_freq': 0.8},
            'Kegalle': {'water_level': (2.0, 5.0), 'rainfall': (40, 120), 'flood_freq': 0.65},
            'Badulla': {'water_level': (1.5, 4.0), 'rainfall': (30, 90), 'flood_freq': 0.5},
            'Nuwara Eliya': {'water_level': (0.5, 2.0), 'rainfall': (20, 60), 'flood_freq': 0.2},
            'Anuradhapura': {'water_level': (1.0, 3.0), 'rainfall': (25, 70), 'flood_freq': 0.35},
            'Polonnaruwa': {'water_level': (1.0, 3.5), 'rainfall': (25, 75), 'flood_freq': 0.4},
            'Hambantota': {'water_level': (1.5, 4.0), 'rainfall': (30, 85), 'flood_freq': 0.5},
            'Monaragala': {'water_level': (1.0, 3.5), 'rainfall': (25, 80), 'flood_freq': 0.4},
            'Matale': {'water_level': (1.0, 3.0), 'rainfall': (25, 70), 'flood_freq': 0.35}
        }
        
        # Road types for training
        road_types = list(self.road_vulnerability.keys())
        
        for i in range(n_samples):
            # Random district
            district = np.random.choice(self.districts)
            flood_pattern = flood_patterns.get(district, {'water_level': (1.0, 4.0), 'rainfall': (20, 80), 'flood_freq': 0.4})
            
            # Generate features
            water_level = np.random.uniform(flood_pattern['water_level'][0], flood_pattern['water_level'][1])
            rainfall = np.random.uniform(flood_pattern['rainfall'][0], flood_pattern['rainfall'][1])
            
            # Road type (weighted by frequency)
            road_type = np.random.choice(road_types, p=[0.1, 0.05, 0.15, 0.15, 0.1, 0.2, 0.05, 0.05, 0.05, 0.05, 0.03, 0.02])
            road_vulnerability = self.road_vulnerability.get(road_type, 0.5)
            
            # Elevation (0-500m)
            elevation = np.random.uniform(0, 500)
            
            # District vulnerability
            district_risk = self.district_vulnerability.get(district, 0.5)
            
            # Calculate damage probability (0-1)
            damage_prob = (
                (water_level / 8) * 0.35 +
                (rainfall / 200) * 0.20 +
                road_vulnerability * 0.20 +
                district_risk * 0.15 +
                (1 - elevation / 500) * 0.10
            )
            damage_prob = np.clip(damage_prob, 0, 0.95)
            
            # Determine road status (0=Safe, 1=Impassable, 2=Blocked)
            if damage_prob < 0.3:
                status = 0  # Safe
            elif damage_prob < 0.6:
                status = 1  # Impassable
            else:
                status = 2  # Blocked
            
            # Add some noise (5% random flip)
            if np.random.random() < 0.05:
                status = np.random.choice([0, 1, 2])
            
            data.append({
                'district': district,
                'water_level_m': water_level,
                'rainfall_mm': rainfall,
                'road_type': road_type,
                'road_vulnerability': road_vulnerability,
                'elevation_m': elevation,
                'district_risk': district_risk,
                'damage_probability': damage_prob,
                'road_status': status,
                'status_label': ['Safe', 'Impassable', 'Blocked'][status]
            })
        
        df = pd.DataFrame(data)
        
        # Save training data
        csv_path = os.path.join(self.training_dir, 'infrastructure_training_data.csv')
        df.to_csv(csv_path, index=False)
        
        logger.info(f"✅ Saved {len(df)} training samples to {csv_path}")
        logger.info(f"   Status distribution:")
        logger.info(df['status_label'].value_counts())
        
        return df

if __name__ == "__main__":
    generator = InfrastructureDataGenerator()
    df = generator.generate_training_data(n_samples=10000)