"""
Infrastructure Agent ML Model
Uses Logistic Regression + Random Forest ensemble
Predicts road passability status
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
import os
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InfrastructureModel:
    """
    ML Model for Infrastructure Agent
    Predicts road status: 0=Safe, 1=Impassable, 2=Blocked
    """
    
    def __init__(self, model_path='models_saved/infrastructure/'):
        self.model_path = model_path
        os.makedirs(model_path, exist_ok=True)
        
        self.rf_model = None
        self.lr_model = None
        self.scaler = None
        self.label_encoder = None
        
        self.feature_columns = [
            'water_level_m',
            'rainfall_mm',
            'road_vulnerability',
            'elevation_m',
            'district_risk'
        ]
        
        self.target_column = 'road_status'
        self.class_names = ['Safe', 'Impassable', 'Blocked']
        
        self._load_models()
    
    def _load_models(self):
        """Load trained models if they exist"""
        try:
            rf_path = os.path.join(self.model_path, 'random_forest_model.pkl')
            lr_path = os.path.join(self.model_path, 'logistic_regression_model.pkl')
            scaler_path = os.path.join(self.model_path, 'scaler.pkl')
            encoder_path = os.path.join(self.model_path, 'label_encoder.pkl')
            
            if all(os.path.exists(p) for p in [rf_path, lr_path, scaler_path, encoder_path]):
                self.rf_model = joblib.load(rf_path)
                self.lr_model = joblib.load(lr_path)
                self.scaler = joblib.load(scaler_path)
                self.label_encoder = joblib.load(encoder_path)
                logger.info("✅ Infrastructure models loaded successfully")
                return True
            else:
                logger.info("ℹ️ No infrastructure models found. Train first.")
                return False
        except Exception as e:
            logger.error(f"❌ Error loading infrastructure models: {e}")
            return False
    
    def train(self, training_data=None):
        """
        Train infrastructure ML models
        """
        if training_data is None:
            data_path = 'data/infrastructure/training/infrastructure_training_data.csv'
            if os.path.exists(data_path):
                training_data = pd.read_csv(data_path)
            else:
                logger.error("❌ Training data not found. Run generate_infrastructure_training_data.py first.")
                return None
        
        logger.info(f"📊 Training infrastructure models on {len(training_data)} samples...")
        
        # Prepare features and target
        X = training_data[self.feature_columns]
        y = training_data[self.target_column]
        
        # Encode target
        self.label_encoder = LabelEncoder()
        y_encoded = self.label_encoder.fit_transform(y)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        logger.info("🌲 Training Random Forest...")
        self.rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
        self.rf_model.fit(X_train_scaled, y_train)
        
        # Train Logistic Regression
        logger.info("📈 Training Logistic Regression...")
        self.lr_model = LogisticRegression(
            multi_class='multinomial',
            max_iter=1000,
            class_weight='balanced',
            random_state=42
        )
        self.lr_model.fit(X_train_scaled, y_train)
        
        # Evaluate
        rf_pred = self.rf_model.predict(X_test_scaled)
        lr_pred = self.lr_model.predict(X_test_scaled)
        
        # Ensemble: average probabilities
        rf_proba = self.rf_model.predict_proba(X_test_scaled)
        lr_proba = self.lr_model.predict_proba(X_test_scaled)
        ensemble_proba = (rf_proba + lr_proba) / 2
        ensemble_pred = np.argmax(ensemble_proba, axis=1)
        
        # Metrics
        rf_acc = accuracy_score(y_test, rf_pred)
        lr_acc = accuracy_score(y_test, lr_pred)
        ensemble_acc = accuracy_score(y_test, ensemble_pred)
        
        logger.info(f"\n📊 Model Performance:")
        logger.info(f"   Random Forest: {rf_acc:.2%}")
        logger.info(f"   Logistic Regression: {lr_acc:.2%}")
        logger.info(f"   Ensemble: {ensemble_acc:.2%}")
        
        # Save models
        self._save_models()
        
        # Save feature importance
        self._save_feature_importance()
        
        return {
            'random_forest_accuracy': rf_acc,
            'logistic_regression_accuracy': lr_acc,
            'ensemble_accuracy': ensemble_acc,
            'class_names': self.class_names
        }
    
    def _save_models(self):
        """Save trained models"""
        try:
            joblib.dump(self.rf_model, os.path.join(self.model_path, 'random_forest_model.pkl'))
            joblib.dump(self.lr_model, os.path.join(self.model_path, 'logistic_regression_model.pkl'))
            joblib.dump(self.scaler, os.path.join(self.model_path, 'scaler.pkl'))
            joblib.dump(self.label_encoder, os.path.join(self.model_path, 'label_encoder.pkl'))
            
            # Save feature info
            feature_info = {
                'features': self.feature_columns,
                'class_names': self.class_names,
                'trained_date': datetime.now().isoformat()
            }
            with open(os.path.join(self.model_path, 'feature_info.json'), 'w') as f:
                json.dump(feature_info, f, indent=2)
            
            logger.info(f"✅ Models saved to {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Error saving models: {e}")
            return False
    
    def _save_feature_importance(self):
        """Save feature importance from Random Forest"""
        if self.rf_model:
            importance = pd.DataFrame({
                'feature': self.feature_columns,
                'importance': self.rf_model.feature_importances_
            }).sort_values('importance', ascending=False)
            
            importance_path = os.path.join(self.model_path, 'feature_importance.csv')
            importance.to_csv(importance_path, index=False)
            logger.info("\n📊 Feature Importance:")
            print(importance)
    
    def predict(self, features):
        """
        Predict road status for given features
        
        Args:
            features: dict with feature values
            
        Returns:
            dict: Prediction with status and confidence
        """
        if not self.rf_model or not self.lr_model:
            if not self._load_models():
                return {'error': 'Models not loaded. Train first.'}
        
        try:
            # Prepare feature vector
            feature_vector = np.array([[
                features.get('water_level_m', 0),
                features.get('rainfall_mm', 0),
                features.get('road_vulnerability', 0.5),
                features.get('elevation_m', 50),
                features.get('district_risk', 0.5)
            ]])
            
            # Scale features
            feature_scaled = self.scaler.transform(feature_vector)
            
            # Get predictions
            rf_pred = self.rf_model.predict(feature_scaled)[0]
            lr_pred = self.lr_model.predict(feature_scaled)[0]
            
            # Ensemble: average probabilities
            rf_proba = self.rf_model.predict_proba(feature_scaled)[0]
            lr_proba = self.lr_model.predict_proba(feature_scaled)[0]
            ensemble_proba = (rf_proba + lr_proba) / 2
            ensemble_pred = np.argmax(ensemble_proba)
            
            # Get class labels
            status = self.class_names[ensemble_pred]
            confidence = ensemble_proba[ensemble_pred] * 100
            
            # Get all probabilities
            probabilities = {
                self.class_names[i]: round(ensemble_proba[i] * 100, 2)
                for i in range(len(self.class_names))
            }
            
            # Determine recommendation
            recommendations = {
                'Safe': 'Road is safe to use',
                'Impassable': 'Road is impassable - Avoid this road',
                'Blocked': 'ROAD BLOCKED - Do not use'
            }
            
            return {
                'status': status,
                'status_code': int(ensemble_pred),
                'confidence': round(confidence, 2),
                'probabilities': probabilities,
                'recommendation': recommendations.get(status, 'Unknown'),
                'model_predictions': {
                    'random_forest': self.class_names[rf_pred],
                    'logistic_regression': self.class_names[lr_pred]
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            return {'error': str(e)}
    
    def predict_batch(self, features_list):
        """
        Predict for multiple roads
        """
        results = []
        for features in features_list:
            result = self.predict(features)
            results.append(result)
        return results
    
    def get_feature_importance(self):
        """Get feature importance"""
        if self.rf_model:
            importance = pd.DataFrame({
                'feature': self.feature_columns,
                'importance': self.rf_model.feature_importances_
            }).sort_values('importance', ascending=False)
            return importance.to_dict('records')
        return None
    
    def get_model_info(self):
        """Get model information"""
        return {
            'model_type': 'Ensemble (Random Forest + Logistic Regression)',
            'features': self.feature_columns,
            'classes': self.class_names,
            'model_path': self.model_path,
            'loaded': self.rf_model is not None
        }

# Create singleton instance
infrastructure_model = InfrastructureModel()