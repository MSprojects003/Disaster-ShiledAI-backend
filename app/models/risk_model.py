import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb
import joblib
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskPredictionModel:
    """
    Ensemble model: Random Forest + XGBoost
    Predicts flood and landslide risk (0-100)
    """
    
    def __init__(self, model_path='models_saved/'):
        self.model_path = model_path
        self.rf_model = None
        self.xgb_model = None
        self.feature_columns = [
            'rainfall_mm', 'river_level_m', 'elevation_m', 
            'slope_degree', 'soil_moisture', 'historical_risk',
            'temperature_c', 'humidity_percent', 'wind_speed_kmh'
        ]
        self._ensure_model_dir()
    
    def _ensure_model_dir(self):
        """Create model directory if it doesn't exist"""
        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)
    
    def generate_training_data(self, n_samples=2000):
        """
        Generate realistic training data for Sri Lanka
        """
        np.random.seed(42)
        
        data = pd.DataFrame()
        
        # Rainfall (mm) - Gamma distribution
        data['rainfall_mm'] = np.random.gamma(shape=2, scale=20, size=n_samples)
        data['rainfall_mm'] = np.clip(data['rainfall_mm'], 0, 200)
        
        # River level (m) - Correlated with rainfall
        data['river_level_m'] = 2 + 0.02 * data['rainfall_mm'] + np.random.normal(0, 0.5, n_samples)
        data['river_level_m'] = np.clip(data['river_level_m'], 1, 8)
        
        # Elevation (m) - Sri Lanka terrain
        data['elevation_m'] = np.random.uniform(0, 500, n_samples)
        
        # Slope (degrees)
        data['slope_degree'] = np.random.exponential(scale=5, size=n_samples)
        data['slope_degree'] = np.clip(data['slope_degree'], 0, 30)
        
        # Soil moisture (%)
        data['soil_moisture'] = 30 + 0.3 * data['rainfall_mm'] + np.random.normal(0, 10, n_samples)
        data['soil_moisture'] = np.clip(data['soil_moisture'], 0, 100)
        
        # Historical risk (0-100)
        data['historical_risk'] = np.random.uniform(0, 100, n_samples)
        
        # Weather conditions
        data['temperature_c'] = np.random.uniform(20, 35, n_samples)
        data['humidity_percent'] = 60 + 0.2 * data['rainfall_mm'] + np.random.normal(0, 10, n_samples)
        data['humidity_percent'] = np.clip(data['humidity_percent'], 30, 100)
        data['wind_speed_kmh'] = np.random.exponential(scale=15, size=n_samples)
        
        # Calculate risk (realistic logic)
        flood_risk = (
            (data['rainfall_mm'] > 70) * 0.35 +
            (data['river_level_m'] > 4) * 0.25 +
            (data['elevation_m'] < 50) * 0.20 +
            (data['soil_moisture'] > 70) * 0.20
        )
        
        landslide_risk = (
            (data['rainfall_mm'] > 60) * 0.25 +
            (data['slope_degree'] > 15) * 0.35 +
            (data['soil_moisture'] > 75) * 0.25 +
            (data['historical_risk'] > 50) * 0.15
        )
        
        # Combined risk score (0-100)
        combined_risk = (flood_risk + landslide_risk) * 50
        data['risk_score'] = np.clip(combined_risk, 0, 100)
        
        # Binary target (1 = high risk > 50)
        data['target'] = (data['risk_score'] > 50).astype(int)
        
        return data
    
    def train(self, historical_data=None):
        """
        Train on REAL historical data
        """
        if historical_data is None:
        # Load historical data
          from ..data.historical_data import HistoricalDataLoader
          loader = HistoricalDataLoader()
          historical_data = loader.load_data()
    
    # Prepare features and target
        X = historical_data[self.feature_columns]
        y = historical_data['flood_occurred']  # Use REAL flood data
    
    # Split data
        X_train, X_test, y_train, y_test = train_test_split(
           X, y, test_size=0.2, random_state=42
        )
    
    # Train models...
    # (Rest of the training code remains the same)
    
    # Evaluate on REAL data
        accuracy = accuracy_score(y_test, ensemble_pred)
        logger.info(f"✅ Model Accuracy on REAL Data: {accuracy:.2%}")
    
        return {'accuracy': accuracy}

    

    def save_models(self):
        """Save trained models"""
        joblib.dump(self.rf_model, os.path.join(self.model_path, 'rf_model.pkl'))
        joblib.dump(self.xgb_model, os.path.join(self.model_path, 'xgb_model.pkl'))
        logger.info(f"✅ Models saved to {self.model_path}")
    
    def load_models(self):
        """Load trained models"""
        try:
            rf_path = os.path.join(self.model_path, 'rf_model.pkl')
            xgb_path = os.path.join(self.model_path, 'xgb_model.pkl')
            
            if os.path.exists(rf_path) and os.path.exists(xgb_path):
                self.rf_model = joblib.load(rf_path)
                self.xgb_model = joblib.load(xgb_path)
                logger.info("✅ Models loaded successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error loading models: {e}")
            return False
    
    def predict(self, features):
        """
        Predict risk score for given features
        """
        if not self.rf_model or not self.xgb_model:
            if not self.load_models():
                logger.info("Training new models...")
                self.train()
        
        # Prepare feature vector
        feature_vector = np.array([[
            features.get('rainfall_mm', 50),
            features.get('river_level_m', 3),
            features.get('elevation_m', 100),
            features.get('slope_degree', 10),
            features.get('soil_moisture', 50),
            features.get('historical_risk', 30),
            features.get('temperature_c', 28),
            features.get('humidity_percent', 75),
            features.get('wind_speed_kmh', 15)
        ]])
        
        # Get predictions
        rf_prob = self.rf_model.predict_proba(feature_vector)[0][1]
        xgb_prob = self.xgb_model.predict_proba(feature_vector)[0][1]
        
        # Ensemble
        risk_prob = (rf_prob + xgb_prob) / 2
        risk_score = risk_prob * 100
        
        # Determine risk level
        if risk_score < 30:
            level = "Low"
            action = "Monitor conditions"
        elif risk_score < 60:
            level = "Medium"
            action = "Be prepared, stay alert"
        elif risk_score < 80:
            level = "High"
            action = "Take precautionary measures"
        else:
            level = "Critical"
            action = "IMMEDIATE EVACUATION REQUIRED!"
        
        return {
            'risk_score': round(risk_score, 2),
            'risk_level': level,
            'action_required': action,
            'confidence': round((1 - abs(rf_prob - xgb_prob)) * 100, 2)
        }
    
    def get_risk_factors(self, features):
        """Identify key risk factors"""
        factors = []
        
        rainfall = features.get('rainfall_mm', 0)
        if rainfall > 80:
            factors.append(f"Heavy rainfall ({rainfall:.1f}mm)")
        elif rainfall > 50:
            factors.append(f"Moderate rainfall ({rainfall:.1f}mm)")
        
        river_level = features.get('river_level_m', 0)
        if river_level > 4:
            factors.append(f"High river level ({river_level:.1f}m)")
        
        elevation = features.get('elevation_m', 500)
        if elevation < 50:
            factors.append(f"Low elevation ({elevation:.0f}m) - flood prone")
        
        slope = features.get('slope_degree', 0)
        if slope > 15:
            factors.append(f"Steep slope ({slope:.1f}°) - landslide risk")
        
        soil_moisture = features.get('soil_moisture', 0)
        if soil_moisture > 70:
            factors.append(f"Saturated soil ({soil_moisture:.1f}%)")
        
        return factors[:5]