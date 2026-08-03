from flask import Blueprint, request, jsonify
from ..agents.evacuation_agent import evacuation_agent
from ..agents.risk_agent import risk_agent
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

evacuation_bp = Blueprint('evacuation', __name__)

# Initialize agent
evacuation_agent.initialize()

@evacuation_bp.route('/plan/<district>', methods=['GET'])
def plan_evacuation(district):
    """
    Plan safest evacuation route using Gemini API + A* pathfinding
    """
    try:
        logger.info(f"🗺️ Planning evacuation route for {district}")
        
        # Get risk prediction
        risk_result = risk_agent.predict_district(district)
        
        if 'error' in risk_result:
            return jsonify({'error': risk_result['error']}), 400
        
        prediction = risk_result.get('prediction', {})
        features = risk_result.get('features', {})
        risk_level = prediction.get('risk_level', 'Low')
        
        origin_lat = request.args.get('lat', None, type=float)
        origin_lon = request.args.get('lon', None, type=float)
        
        input_data = {
            'district': district,
            'risk_level': risk_level,
            'risk_score': prediction.get('risk_score', 0),
            'water_level_m': features.get('water_level_m', 0),
            'origin_lat': origin_lat,
            'origin_lon': origin_lon
        }
        
        result = evacuation_agent.process(input_data)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Evacuation planning error: {e}")
        return jsonify({'error': str(e)}), 500

@evacuation_bp.route('/shelters/<district>', methods=['GET'])
def get_shelters(district):
    """Get all shelters in a district"""
    try:
        shelters = evacuation_agent.get_shelters_in_district(district)
        return jsonify({
            'district': district,
            'data_source': evacuation_agent.data_source,
            'total_shelters': len(shelters),
            'shelters': shelters
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@evacuation_bp.route('/gemini-shelters', methods=['POST'])
def find_gemini_shelters():
    """
    Find shelters using Gemini API
    Body: {"lat": 6.9271, "lon": 79.8612, "district": "Colombo", "radius_km": 10}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        lat = data.get('lat')
        lon = data.get('lon')
        district = data.get('district', 'Colombo')
        radius = data.get('radius_km', 10)
        
        if not lat or not lon:
            return jsonify({'error': 'Missing coordinates'}), 400
        
        result = evacuation_agent.find_shelters_with_gemini(lat, lon, district, radius)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Gemini search failed'}), 500
        
    except Exception as e:
        logger.error(f"❌ Gemini shelter search error: {e}")
        return jsonify({'error': str(e)}), 500

@evacuation_bp.route('/route', methods=['POST'])
def calculate_route():
    """Calculate route between two points"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        origin_lat = data.get('origin_lat')
        origin_lon = data.get('origin_lon')
        dest_lat = data.get('dest_lat')
        dest_lon = data.get('dest_lon')
        district = data.get('district', 'Colombo')
        
        if not all([origin_lat, origin_lon, dest_lat, dest_lon]):
            return jsonify({'error': 'Missing coordinates'}), 400
        
        route = evacuation_agent.calculate_route(
            origin_lat, origin_lon,
            dest_lat, dest_lon,
            district
        )
        
        return jsonify(route)
        
    except Exception as e:
        logger.error(f"❌ Route calculation error: {e}")
        return jsonify({'error': str(e)}), 500

@evacuation_bp.route('/status', methods=['GET'])
def get_agent_status():
    """Get evacuation agent status"""
    return jsonify(evacuation_agent.get_status())

@evacuation_bp.route('/map-data/<district>', methods=['GET'])
def get_map_data(district):
    """Get map data for visualization"""
    try:
        result = evacuation_agent.get_map_data(district)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ================================================================
# NEW: Sync shelters to RAG
# ================================================================
@evacuation_bp.route('/sync-shelters', methods=['POST'])
def sync_shelters_to_rag():
    """
    Sync shelters to RAG vector store
    Body: {"source": "dmc"} or {"source": "gemini"}
    """
    try:
        data = request.get_json() or {}
        source = data.get('source', 'dmc')
        
        logger.info(f"🔄 Syncing shelters from '{source}' to RAG...")
        
        # Get shelters from agent
        shelters = evacuation_agent.shelters
        
        if not shelters:
            return jsonify({
                'error': 'No shelters available to sync',
                'shelters_count': 0
            }), 400
        
        # Sync to RAG
        from ..services.rag_service import rag_service
        synced = rag_service.sync_shelters_to_rag(shelters)
        
        return jsonify({
            'success': True,
            'message': f'Successfully synced {synced} shelters to RAG',
            'source': source,
            'total_shelters': len(shelters),
            'synced_count': synced,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Sync shelters error: {e}")
        return jsonify({'error': str(e)}), 500

@evacuation_bp.route('/rag-search', methods=['POST'])
def rag_search_shelters():
    """
    Search shelters using RAG
    Body: {"query": "Find shelters in Colombo", "district": "Colombo", "k": 5}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        query = data.get('query', '')
        district = data.get('district', None)
        k = data.get('k', 10)
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        from ..services.rag_service import rag_service
        
        results = rag_service.find_shelters_rag(query, district, k)
        
        return jsonify({
            'success': True,
            'query': query,
            'district': district,
            'num_results': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ RAG search error: {e}")
        return jsonify({'error': str(e)}), 500