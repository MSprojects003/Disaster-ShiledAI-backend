"""
Emergency Bulk Alert Routes - Enhanced
"""

from flask import Blueprint, request, jsonify
from ..services.emergency_bulk_service import emergency_bulk_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

emergency_bulk_bp = Blueprint('emergency_bulk', __name__)

@emergency_bulk_bp.route('/high-risk-districts', methods=['GET'])
def get_high_risk_districts():
    """Get all districts with risk score above threshold"""
    try:
        threshold = float(request.args.get('threshold', 70.0))
        result = emergency_bulk_service.get_high_risk_districts(threshold)
        
        return jsonify({
            'status': 'success',
            'threshold': threshold,
            'districts': result,
            'total_high_risk': len(result),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting high-risk districts: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bulk_bp.route('/users-in-high-risk', methods=['GET'])
def get_users_in_high_risk_areas():
    """Get all users in high-risk districts with location filtering"""
    try:
        threshold = float(request.args.get('threshold', 70.0))
        result = emergency_bulk_service.get_all_users_in_high_risk_areas(threshold)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error getting users in high-risk areas: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bulk_bp.route('/send-alerts', methods=['POST'])
def send_emergency_alerts():
    """
    Send emergency alerts to all users in high-risk areas
    Body: {"threshold": 70, "dry_run": false}
    """
    try:
        data = request.get_json() or {}
        threshold = data.get('threshold', 70.0)
        dry_run = data.get('dry_run', False)
        
        result = emergency_bulk_service.send_emergency_alerts_to_high_risk_areas(
            threshold=threshold,
            dry_run=dry_run
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error sending emergency alerts: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bulk_bp.route('/send-alerts/<district>', methods=['POST'])
def send_alerts_to_district(district):
    """
    Send emergency alerts to users in a specific district
    Body: {"threshold": 70, "dry_run": false}
    """
    try:
        data = request.get_json() or {}
        threshold = data.get('threshold', 70.0)
        dry_run = data.get('dry_run', False)
        
        # Get risk for the district
        risk_result = emergency_bulk_service.risk_agent.predict_district(district)
        
        if 'error' in risk_result:
            return jsonify({'error': f'Failed to get risk for {district}: {risk_result["error"]}'}), 400
        
        prediction = risk_result.get('prediction', {})
        risk_score = prediction.get('risk_score', 0)
        risk_level = prediction.get('risk_level', 'Low')
        
        if risk_score < threshold:
            return jsonify({
                'status': 'monitoring',
                'message': f'Risk score {risk_score:.1f}% is below threshold {threshold}%',
                'district': district,
                'risk_score': risk_score,
                'risk_level': risk_level
            })
        
        # Get users in district (first try by location, then by district)
        users = emergency_bulk_service.get_users_near_location(district, radius_km=50.0)
        if not users:
            users = emergency_bulk_service.get_users_in_district(district)
        
        if not users:
            return jsonify({
                'status': 'no_users',
                'message': f'No active users found in or near {district}',
                'district': district,
                'risk_score': risk_score,
                'risk_level': risk_level
            })
        
        # Build and send alerts
        infrastructure_info = emergency_bulk_service.get_district_infrastructure(
            district, risk_level, risk_score
        )
        resource_info = emergency_bulk_service.get_district_resources(
            district, risk_level, risk_score
        )
        evacuation_info = emergency_bulk_service.get_district_evacuation_plan(
            district, risk_level, risk_score
        )
        
        message = emergency_bulk_service.build_emergency_alert_message(
            district=district,
            risk_level=risk_level,
            risk_score=risk_score,
            infrastructure_info=infrastructure_info,
            resource_info=resource_info,
            evacuation_info=evacuation_info
        )
        
        # Send alerts
        sent_alerts = []
        failed_alerts = []
        
        for user in users:
            phone_number = user.get('phone_number')
            if not phone_number:
                continue
            
            if dry_run:
                sent_alerts.append({
                    'phone_number': phone_number,
                    'user_id': user.get('id'),
                    'user_name': user.get('full_name', 'Unknown'),
                    'distance': user.get('distance_km', 'N/A'),
                    'dry_run': True
                })
            else:
                sms_result = emergency_bulk_service.notify_lk.send_sms(
                    phone_number, message
                )
                
                if sms_result.get('success', False):
                    sent_alerts.append({
                        'phone_number': phone_number,
                        'user_id': user.get('id'),
                        'user_name': user.get('full_name', 'Unknown'),
                        'distance': user.get('distance_km', 'N/A'),
                        'message_id': sms_result.get('message_id', 'N/A')
                    })
                else:
                    failed_alerts.append({
                        'phone_number': phone_number,
                        'user_id': user.get('id'),
                        'user_name': user.get('full_name', 'Unknown'),
                        'error': sms_result.get('error', 'Unknown error')
                    })
        
        return jsonify({
            'status': 'success',
            'district': district,
            'risk_score': risk_score,
            'risk_level': risk_level,
            'total_users': len(users),
            'alerts_sent': len(sent_alerts),
            'alerts_failed': len(failed_alerts),
            'sent_alerts': sent_alerts,
            'failed_alerts': failed_alerts,
            'message_preview': message[:200] + '...',
            'message_length': len(message),
            'dry_run': dry_run,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error sending alerts to {district}: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bulk_bp.route('/stats', methods=['GET'])
def get_emergency_stats():
    """Get emergency statistics"""
    try:
        result = emergency_bulk_service.get_emergency_statistics()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error getting statistics: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bulk_bp.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint for emergency bulk routes"""
    return jsonify({
        'message': 'Emergency Bulk Alert routes are working!',
        'services': {
            'high_risk_districts': '/high-risk-districts?threshold=70',
            'users_in_high_risk': '/users-in-high-risk?threshold=70',
            'send_alerts': '/send-alerts (POST)',
            'send_alerts_to_district': '/send-alerts/<district> (POST)',
            'stats': '/stats'
        },
        'timestamp': datetime.now().isoformat()
    })