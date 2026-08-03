import pandas as pd
import numpy as np
import joblib
import os
import json
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PredictionService:
    """
    Service for making risk predictions using trained models
    """
    
    def __init__(self):
        self.model_dir = "models_saved/"
        self.models = {}
        self.feature_info = None
        self.features = [
            'water_level_m', 
            'rainfall_mm',
            'temperature_c',
            'humidity_percent',
            'wind_speed_kmh',
            'pressure_hpa'
        ]
        self.target_mapping = {0: 'Low', 1: 'Medium', 2: 'High', 3: 'Critical'}
        self.load_models()
    
    def load_models(self):
        """Load trained models"""
        try:
            # Load Random Forest
            rf_path = os.path.join(self.model_dir, 'random_forest_model.pkl')
            if os.path.exists(rf_path):
                self.models['random_forest'] = joblib.load(rf_path)
                logger.info("✅ Loaded Random Forest model")
            
            # Load XGBoost
            xgb_path = os.path.join(self.model_dir, 'xgboost_model.pkl')
            if os.path.exists(xgb_path):
                self.models['xgboost'] = joblib.load(xgb_path)
                logger.info("✅ Loaded XGBoost model")
            
            # Load feature info
            info_path = os.path.join(self.model_dir, 'feature_info.json')
            if os.path.exists(info_path):
                with open(info_path, 'r') as f:
                    self.feature_info = json.load(f)
                logger.info("✅ Loaded feature info")
            
            if not self.models:
                logger.warning("⚠️ No models found! Train models first.")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading models: {e}")
            return False
    
    def predict(self, features):
        """
        Make prediction using ensemble of models
        
        Args:
            features: dict with feature values
        
        Returns:
            dict: Prediction results
        """
        if not self.models:
            return {'error': 'Models not loaded. Please train models first.'}
        
        try:
            logger.info(f"📊 Features received: {features}")
            
            # Prepare feature vector with proper defaults
            feature_vector = []
            feature_dict = {}
            
            for feature in self.features:
                # Get value from features dict
                value = features.get(feature, 0)
                
                # Handle None or empty values
                if value is None or value == '':
                    value = 0
                
                # Convert to float
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = 0
                
                feature_vector.append(value)
                feature_dict[feature] = value
            
            logger.info(f"📊 Feature vector: {feature_vector}")
            
            # Convert to DataFrame
            X = pd.DataFrame([feature_vector], columns=self.features)
            
            # Get predictions from each model
            predictions = {}
            probabilities = {}
            
            for name, model in self.models.items():
                try:
                    pred = model.predict(X)[0]
                    pred_proba = model.predict_proba(X)[0]
                    
                    predictions[name] = int(pred)
                    probabilities[name] = pred_proba.tolist()
                except Exception as e:
                    logger.error(f"❌ Error with {name}: {e}")
                    predictions[name] = 0
                    probabilities[name] = [1.0, 0.0]
            
            # Ensemble: average predictions
            ensemble_pred = round(np.mean(list(predictions.values())))
            
            # Get probability for ensemble
            if probabilities:
                ensemble_proba = np.mean(list(probabilities.values()), axis=0)
            else:
                ensemble_proba = np.array([1.0, 0.0])
            
            # Get risk level
            risk_level = self.target_mapping.get(ensemble_pred, 'Unknown')
            
            # Get confidence
            if len(ensemble_proba) > ensemble_pred:
                risk_score = ensemble_proba[ensemble_pred] * 100
                confidence = max(ensemble_proba) * 100
            else:
                risk_score = 50
                confidence = 50
            
            # Get feature importance from Random Forest (if available)
            feature_importance = None
            if 'random_forest' in self.models:
                rf = self.models['random_forest']
                if hasattr(rf, 'feature_importances_'):
                    importance = rf.feature_importances_
                    feature_importance = {
                        self.features[i]: round(importance[i], 4) 
                        for i in range(len(self.features))
                    }
            
            return {
                'success': True,
                'risk_level': risk_level,
                'risk_score': round(risk_score, 2),
                'confidence': round(confidence, 2),
                'ensemble_prediction': int(ensemble_pred),
                'model_predictions': predictions,
                'feature_importance': feature_importance,
                'features_used': feature_dict,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def predict_batch(self, features_list):
        """
        Make predictions for multiple records
        
        Args:
            features_list: List of feature dictionaries
        
        Returns:
            list: List of prediction results
        """
        results = []
        for features in features_list:
            result = self.predict(features)
            results.append(result)
        return results
    
    def get_model_info(self):
        """Get information about loaded models"""
        return {
            'models_loaded': list(self.models.keys()),
            'features': self.features,
            'target_mapping': self.target_mapping,
            'feature_info': self.feature_info
        }

# Singleton instance
prediction_service = PredictionService()