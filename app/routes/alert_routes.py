from flask import Blueprint, request, jsonify
from ..services.notify_lk_service import notify_lk
from ..services.alert_service import alert_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

alert_bp = Blueprint('alert', __name__)

@alert_bp.route('/status', methods=['GET'])
def get_alert_status():
    """Get Notify.lk service status"""
    return jsonify({
        'provider': 'notify.lk',
        'status': notify_lk.get_status(),
        'timestamp': datetime.now().isoformat()
    })

@alert_bp.route('/send', methods=['POST'])
def send_alert():
    """
    Send a single SMS alert via Notify.lk
    Body: {"to": "94781467718", "district": "Colombo", "risk_level": "High", "risk_score": 85.5}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        to_number = data.get('to')
        district = data.get('district', 'Colombo')
        risk_level = data.get('risk_level', 'High')
        risk_score = data.get('risk_score', 80)
        custom_message = data.get('custom_message', '')
        
        if not to_number:
            return jsonify({'error': 'Phone number required'}), 400
        
        # If custom message provided, use it directly
        if custom_message:
            result = notify_lk.send_sms(to_number, custom_message)
        else:
            result = alert_service.send_single_alert(to_number, district, risk_level, risk_score)
        
        return jsonify({
            'success': result.get('success', False),
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Alert send error: {e}")
        return jsonify({'error': str(e)}), 500

@alert_bp.route('/send-bulk', methods=['POST'])
def send_bulk_alerts():
    """
    Send bulk SMS alerts via Notify.lk
    Body: {"recipients": ["94781467718", "94787987255"], "district": "Colombo", "risk_level": "High"}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        recipients = data.get('recipients', [])
        district = data.get('district', 'Colombo')
        risk_level = data.get('risk_level', 'High')
        risk_score = data.get('risk_score', 80)
        custom_message = data.get('custom_message', '')
        
        if not recipients:
            return jsonify({'error': 'No recipients provided'}), 400
        
        # Send bulk alerts
        if custom_message:
            results = notify_lk.send_bulk_sms(recipients, custom_message)
        else:
            results = notify_lk.send_bulk_alerts(recipients, district, risk_level, risk_score)
        
        success_count = sum(1 for r in results if r.get('success', False))
        
        return jsonify({
            'success': True,
            'total_recipients': len(recipients),
            'sent': success_count,
            'failed': len(recipients) - success_count,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Bulk alert error: {e}")
        return jsonify({'error': str(e)}), 500

@alert_bp.route('/test-sms', methods=['POST'])
def test_sms():
    """
    Send a test SMS via Notify.lk
    Body: {"to": "94781467718"}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        to_number = data.get('to')
        
        if not to_number:
            return jsonify({'error': 'Phone number required'}), 400
        
        test_message = "🧪 This is a test SMS from Disaster-Shield AI via Notify.lk!"
        
        result = notify_lk.send_sms(to_number, test_message)
        
        return jsonify({
            'success': result.get('success', False),
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Test SMS error: {e}")
        return jsonify({'error': str(e)}), 500

@alert_bp.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify routes are working"""
    return jsonify({
        'message': 'Alert routes are working with Notify.lk!',
        'provider': 'notify.lk',
        'timestamp': datetime.now().isoformat()
    })