from flask import Blueprint, request, jsonify
from ..agents.resource_agent import resource_agent
from ..agents.risk_agent import risk_agent
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

resource_bp = Blueprint('resource', __name__)

# Initialize agent
resource_agent.initialize()

@resource_bp.route('/allocate', methods=['POST'])
def allocate_resources():
    """Allocate resources using CSV data + Gemini"""
    try:
        logger.info("📊 Allocating resources...")
        
        risk_results = risk_agent.predict_all_districts()
        
        risk_predictions = {}
        for result in risk_results:
            district = result.get('district')
            if district:
                prediction = result.get('prediction', {})
                features = result.get('features', {})
                
                risk_predictions[district] = {
                    'risk_score': prediction.get('risk_score', 0),
                    'risk_level': prediction.get('risk_level', 'Low'),
                    'water_level_m': features.get('water_level_m', 0),
                    'rainfall_mm': features.get('rainfall_mm', 0),
                    'flood_extent': features.get('flood_extent', 0)
                }
        
        input_data = {
            'action': 'allocate',
            'risk_predictions': risk_predictions
        }
        
        result = resource_agent.process(input_data)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Resource allocation error: {e}")
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/gemini-analyze', methods=['POST'])
def gemini_analyze():
    """Use Gemini to analyze disaster situation"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        result = resource_agent.process({
            'action': 'gemini_analyze',
            'district': data.get('district', 'Colombo'),
            'risk_score': data.get('risk_score', 50),
            'risk_level': data.get('risk_level', 'Medium')
        })
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Gemini analysis error: {e}")
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/status', methods=['GET'])
def get_resource_status():
    """Get current resource status"""
    try:
        result = resource_agent.process({'action': 'get_status'})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/update', methods=['POST'])
def update_resources():
    """Update resource levels"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        result = resource_agent.process({
            'action': 'update_resources',
            'resources': data.get('resources', {}),
            'district': data.get('district', 'National')
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/deployment/<district>', methods=['GET'])
def get_deployment_plan(district):
    """Get deployment plan for a specific district"""
    try:
        result = resource_agent.process({
            'action': 'deployment_plan',
            'district': district
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/summary', methods=['GET'])
def get_resource_summary():
    """Get summary of all resource allocations"""
    try:
        status = resource_agent.get_status()
        return jsonify({
            'status': status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"❌ Error loading DesInventar data: {e}")
        return False
    

@resource_bp.route('/historical-summary', methods=['GET'])
def get_historical_summary():
    """Get summary of DesInventar historical data"""
    try:
        result = resource_agent.process({'action': 'get_historical_summary'})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

    # In resource_routes.py

@resource_bp.route('/history', methods=['GET'])
def get_allocation_history():
    """Get allocation history from database"""
    try:
        from ..database.models import ResourceAllocation
        from ..database.db import db
        
        # Get recent allocations
        records = ResourceAllocation.query.order_by(
            ResourceAllocation.created_at.desc()
        ).limit(50).all()
        
        return jsonify({
            'success': True,
            'total': len(records),
            'allocations': [r.to_dict() for r in records],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ History error: {e}")
        return jsonify({'error': str(e)}), 500

@resource_bp.route('/history/<district>', methods=['GET'])
def get_district_allocation_history(district):
    """Get allocation history for a specific district"""
    try:
        from ..database.models import ResourceAllocation
        from ..database.db import db
        
        records = ResourceAllocation.query.filter_by(
            district=district
        ).order_by(
            ResourceAllocation.created_at.desc()
        ).limit(20).all()
        
        return jsonify({
            'success': True,
            'district': district,
            'total': len(records),
            'allocations': [r.to_dict() for r in records],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ District history error: {e}")
        return jsonify({'error': str(e)}), 500