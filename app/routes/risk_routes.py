# backend/app/routes/risk_routes.py

from flask import Blueprint, request, jsonify
from ..services.data_collector import DataCollector
from ..services.prediction_service import prediction_service
from ..agents.risk_agent import risk_agent 
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
risk_bp = Blueprint('risk', __name__)

# Initialize data collector
data_collector = DataCollector()

# ============================================================
# ADDED: HIGH-RISK ENDPOINT (MISSING)
# ============================================================
@risk_bp.route('/high-risk', methods=['GET'])
def get_high_risk():
    """Get high risk districts"""
    try:
        # Get high risk districts from risk agent
        high_risk = risk_agent.get_high_risk()
        return jsonify({
            'high_risk_districts': high_risk,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ High risk error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# EXISTING ENDPOINTS (NO CHANGES)
# ============================================================

@risk_bp.route('/predict/<district>', methods=['GET'])
def predict_district(district):
    """Predict risk for a specific district using ALL data sources"""
    try:
        # Collect data from ALL sources
        logger.info(f"📊 Collecting data for {district}...")
        features = data_collector.collect_data(district)
        
        logger.info(f"📊 Features collected: {features}")
        
        # Make prediction
        prediction = prediction_service.predict(features)
        
        if prediction.get('success'):
            prediction['district'] = district
            
            # Generate alert if high risk
            if prediction.get('risk_level') in ['High', 'Critical']:
                prediction['alert'] = {
                    'level': prediction['risk_level'],
                    'message': f"⚠️ {prediction['risk_level']} risk detected! Take immediate action.",
                    'triggered_at': datetime.utcnow().isoformat()
                }
            
            # Add data source info
            prediction['data_sources'] = {
                'weather': 'OpenWeatherMap API (Real)',
                'river_gauge': 'DMC River Gauge Data (Real)',
                'satellite': 'UNOSAT Satellite Data (Real)',
                'terrain': 'SRTM Terrain Data'
            }
            
            return jsonify(prediction)
        else:
            return jsonify(prediction), 400
            
    except Exception as e:
        logger.error(f"❌ Prediction error for {district}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@risk_bp.route('/model-predict', methods=['POST'])
def model_predict():
    """
    Make prediction using trained ML model
    Expects JSON with district name
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # If district is provided, collect all data
        if 'district' in data:
            district = data['district']
            logger.info(f"📊 Collecting ALL data for {district}...")
            
            # Collect data from ALL sources
            features = data_collector.collect_data(district)
            
            # Override with any user-provided values
            for key, value in data.items():
                if key != 'district':
                    features[key] = value
            
            logger.info(f"📊 Final features: {features}")
            
        else:
            # Use provided features directly
            features = data
            logger.info(f"📊 Using provided features: {features}")
        
        # Make prediction
        prediction = prediction_service.predict(features)
        
        if prediction.get('success'):
            # Add district info if available
            if 'district' in data:
                prediction['district'] = data['district']
            
            # Generate alert if high risk
            if prediction.get('risk_level') in ['High', 'Critical']:
                prediction['alert'] = {
                    'level': prediction['risk_level'],
                    'message': f"⚠️ {prediction['risk_level']} risk detected! Take immediate action.",
                    'triggered_at': datetime.utcnow().isoformat()
                }
            
            # Add data source info
            prediction['data_sources'] = {
                'weather': 'OpenWeatherMap API (Real)',
                'river_gauge': 'DMC River Gauge Data (Real)',
                'satellite': 'UNOSAT Satellite Data (Real)',
                'terrain': 'SRTM Terrain Data'
            }
            
            return jsonify(prediction)
        else:
            return jsonify(prediction), 400
            
    except Exception as e:
        logger.error(f"❌ Prediction API error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@risk_bp.route('/collect-data/<district>', methods=['GET'])
def collect_data(district):
    """Debug endpoint to see what data is collected"""
    try:
        features = data_collector.collect_data(district)
        return jsonify({
            'district': district,
            'features': features,
            'data_sources': {
                'weather': 'OpenWeatherMap API',
                'river': 'DMC River Gauges',
                'satellite': 'UNOSAT',
                'terrain': 'SRTM'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@risk_bp.route('/model-info', methods=['GET'])
def get_model_info():
    """Get information about the loaded model"""
    info = prediction_service.get_model_info()
    return jsonify(info)

@risk_bp.route('/districts', methods=['GET'])
def get_districts():
    """Get list of all districts"""
    districts = [
        'Colombo', 'Gampaha', 'Kalutara', 'Galle', 'Matara',
        'Hambantota', 'Kandy', 'Matale', 'Nuwara Eliya',
        'Kurunegala', 'Puttalam', 'Anuradhapura', 'Polonnaruwa',
        'Badulla', 'Monaragala', 'Ratnapura', 'Kegalle'
    ]
    return jsonify({
        'districts': districts,
        'count': len(districts)
    })

@risk_bp.route('/status', methods=['GET'])
def get_status():
    """Get agent status"""
    return jsonify({
        'agent': 'RiskPredictionAgent',
        'status': 'operational',
        'model_loaded': bool(prediction_service.models),
        'districts_available': 17
    })

@risk_bp.route('/predict-all', methods=['GET'])
def predict_all():
    """Predict risk for all districts"""
    try:
        results = risk_agent.predict_all_districts()
        return jsonify({
            'total': len(results),
            'predictions': results,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ Predict all error: {e}")
        return jsonify({'error': str(e)}), 500