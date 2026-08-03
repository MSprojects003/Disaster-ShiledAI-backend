from ..models.risk_model import RiskPredictionModel
from ..database.models import RiskPrediction, Alert
from ..database.db import db
from ..services.data_collector import DataCollector
from ..services.alert_service import AlertService
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RiskAgent:
    """Risk Prediction Agent"""
    
    def __init__(self):
        self.model = RiskPredictionModel()
        self.data_collector = DataCollector()
        self.alert_service = AlertService()
        self.districts = [
            'Colombo', 'Gampaha', 'Kalutara', 'Galle', 'Matara',
            'Hambantota', 'Kandy', 'Matale', 'Nuwara Eliya',
            'Kurunegala', 'Puttalam', 'Anuradhapura', 'Polonnaruwa',
            'Badulla', 'Monaragala', 'Ratnapura', 'Kegalle'
        ]
    
    def initialize(self):
        """Initialize agent"""
        logger.info("🚀 Initializing Risk Prediction Agent...")
        try:
            if not self.model.load_models():
                logger.info("Training new models...")
                self.model.train()
            logger.info("✅ Risk Prediction Agent ready!")
            return {"status": "initialized"}
        except Exception as e:
            logger.error(f"❌ Initialization error: {e}")
            return {"status": "error", "message": str(e)}
    
    def predict_district(self, district):
        """Predict risk for a district"""
        try:
            features = self.data_collector.collect_data(district)
            prediction = self.model.predict(features)
            factors = self.model.get_risk_factors(features)
            
            # Save to database
            try:
                risk_record = RiskPrediction(
                    district=district,
                    risk_score=prediction['risk_score'],
                    risk_level=prediction['risk_level'],
                    rainfall_mm=features.get('rainfall_mm'),
                    river_level_m=features.get('river_level_m'),
                    elevation_m=features.get('elevation_m'),
                    slope_degree=features.get('slope_degree'),
                    soil_moisture=features.get('soil_moisture'),
                    temperature_c=features.get('temperature_c'),
                    humidity_percent=features.get('humidity_percent'),
                    action_required=prediction['action_required'],
                    alert_triggered=prediction['risk_level'] in ['High', 'Critical']
                )
                db.session.add(risk_record)
                db.session.commit()
                logger.info(f"✅ Saved prediction for {district}")
            except Exception as db_error:
                logger.error(f"⚠️ Database error for {district}: {db_error}")
                # Continue even if database fails
            
            result = {
                'district': district,
                'timestamp': datetime.utcnow().isoformat(),
                'prediction': prediction,
                'risk_factors': factors,
                'alert_triggered': prediction['risk_level'] in ['High', 'Critical']
            }
            
            # Generate alert if needed
            if result['alert_triggered']:
                try:
                    alert = self.alert_service.generate_alert(district, prediction, factors)
                    result['alert'] = alert
                except Exception as alert_error:
                    logger.error(f"⚠️ Alert error for {district}: {alert_error}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error predicting {district}: {e}")
            return {'error': str(e), 'district': district}
    
    def predict_all_districts(self):
        """Predict risk for all districts"""
        results = []
        for district in self.districts:
            result = self.predict_district(district)
            results.append(result)
            logger.info(f"✅ {district}: {result.get('prediction', {}).get('risk_level', 'Error')}")
        return results
    
    def get_high_risk(self, threshold=70):
        """Get high risk districts"""
        try:
            high_risk = RiskPrediction.query.filter(
                RiskPrediction.risk_score >= threshold
            ).order_by(RiskPrediction.risk_score.desc()).limit(10).all()
            return [r.to_dict() for r in high_risk]
        except Exception as e:
            logger.error(f"❌ Error fetching high risk: {e}")
            return []

# Create singleton instance
risk_agent = RiskAgent()
# Initialize agent on import
risk_agent.initialize()