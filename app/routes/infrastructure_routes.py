from flask import Blueprint, request, jsonify
from ..agents.infrastructure_agent import infrastructure_agent
from ..agents.risk_agent import risk_agent
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create blueprint
infra_bp = Blueprint('infrastructure', __name__)

# Initialize agent
infrastructure_agent.initialize()

@infra_bp.route('/analyze/<district>', methods=['GET'])
def analyze_infrastructure(district):
    """
    Analyze infrastructure for a district
    Uses risk predictions from Risk Agent
    """
    try:
        logger.info(f"🔍 Analyzing infrastructure for {district}")
        
        # Get risk prediction
        risk_result = risk_agent.predict_district(district)
        
        if 'error' in risk_result:
            return jsonify({'error': risk_result['error']}), 400
        
        # Extract risk data
        prediction = risk_result.get('prediction', {})
        features = risk_result.get('features', {})
        
        # Prepare input for infrastructure agent
        input_data = {
            'district': district,
            'risk_level': prediction.get('risk_level', 'Low'),
            'risk_score': prediction.get('risk_score', 0),
            'water_level_m': features.get('water_level_m', 0),
            'rainfall_mm': features.get('rainfall_mm', 0),
            'flood_extent': features.get('flood_extent', 0)
        }
        
        # Analyze infrastructure
        result = infrastructure_agent.process(input_data)
        
        # Add risk prediction reference
        result['risk_prediction'] = {
            'risk_level': prediction.get('risk_level'),
            'risk_score': prediction.get('risk_score')
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Infrastructure analysis error: {e}")
        return jsonify({'error': str(e)}), 500

@infra_bp.route('/road-status/<district>', methods=['GET'])
def get_road_status(district):
    """Get current road status for a district"""
    try:
        logger.info(f"🛣️ Getting road status for {district}")
        
        # Get risk prediction
        risk_result = risk_agent.predict_district(district)
        
        if 'error' in risk_result:
            return jsonify({'error': risk_result['error']}), 400
        
        prediction = risk_result.get('prediction', {})
        features = risk_result.get('features', {})
        
        input_data = {
            'district': district,
            'risk_level': prediction.get('risk_level', 'Low'),
            'water_level_m': features.get('water_level_m', 0)
        }
        
        result = infrastructure_agent.process(input_data)
        
        return jsonify({
            'district': district,
            'risk_level': result.get('risk_level', 'Low'),
            'roads': result.get('road_status', []),
            'total_roads': len(result.get('road_status', [])),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Road status error: {e}")
        return jsonify({'error': str(e)}), 500

@infra_bp.route('/status', methods=['GET'])
def get_agent_status():
    """Get infrastructure agent status"""
    return jsonify(infrastructure_agent.get_status())

@infra_bp.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify routes are working"""
    return jsonify({
        'message': 'Infrastructure routes are working!',
        'timestamp': datetime.now().isoformat()
    })