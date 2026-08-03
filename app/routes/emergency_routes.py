from flask import Blueprint, request, jsonify
from ..services.emergency_response_service import emergency_response
from ..database.models import Alert, RiskPrediction
from ..database.db import db
from ..services.notify_lk_service import notify_lk
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

emergency_bp = Blueprint('emergency', __name__)

@emergency_bp.route('/check/<district>', methods=['GET'])
def check_emergency(district):
    """
    Check and handle emergency for a specific district
    Query params: ?threshold=60
    """
    try:
        threshold = float(request.args.get('threshold', 60.0))
        result = emergency_response.handle_critical_emergency(district, threshold)
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Emergency check error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/check-all', methods=['GET'])
def check_all_emergencies():
    """
    Check all districts for emergencies
    Query params: ?threshold=60
    """
    try:
        threshold = float(request.args.get('threshold', 60.0))
        result = emergency_response.handle_emergency_for_all_districts(threshold)
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Emergency check all error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/summary', methods=['GET'])
def get_emergency_summary():
    """
    Get summary of recent emergencies
    Query params: ?district=Colombo
    """
    try:
        district = request.args.get('district', None)
        result = emergency_response.get_emergency_summary(district)
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Emergency summary error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/users-nearby/<district>', methods=['GET'])
def get_users_nearby(district):
    """
    Get users near a district (for debugging)
    Uses _get_nearby_users_with_priority for better results
    """
    try:
        users = emergency_response._get_nearby_users_with_priority(district)
        return jsonify({
            'district': district,
            'total_users': len(users),
            'users': users
        })
    except Exception as e:
        logger.error(f"❌ Nearby users error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/auto-alert', methods=['POST'])
def auto_alert_high_risk_areas():
    """
    AUTOMATICALLY find high-risk districts and send alerts to all affected users
    Sends ONE SMS per unique user (deduplicated by phone number)
    """
    try:
        data = request.get_json() or {}
        threshold = float(data.get('threshold', 60.0))
        dry_run = data.get('dry_run', False)
        
        logger.info(f"🚨 AUTO-ALERT: Scanning for districts with risk > {threshold}%")
        
        all_districts = emergency_response.risk_agent.districts
        
        high_risk_districts = []
        # Use dictionary to deduplicate users by phone number
        users_dict = {}  # phone_number -> user_data
        
        for district in all_districts:
            try:
                risk_result = emergency_response.risk_agent.predict_district(district)
                
                if 'error' in risk_result:
                    continue
                
                prediction = risk_result.get('prediction', {})
                risk_score = prediction.get('risk_score', 0)
                risk_level = prediction.get('risk_level', 'Low')
                
                if risk_score >= threshold:
                    logger.info(f"⚠️ HIGH RISK: {district} - {risk_score:.2f}% ({risk_level})")
                    
                    # Get users in this district
                    users = emergency_response._get_nearby_users_with_priority(district)
                    
                    # Get agent data
                    try:
                        infra_result = emergency_response.infrastructure_agent.process({
                            'district': district,
                            'risk_level': risk_level,
                            'risk_score': risk_score
                        })
                    except Exception as e:
                        infra_result = {'error': str(e)}
                    
                    try:
                        evac_result = emergency_response.evacuation_agent.process({
                            'district': district,
                            'risk_level': risk_level,
                            'risk_score': risk_score
                        })
                    except Exception as e:
                        evac_result = {'error': str(e)}
                    
                    try:
                        resource_result = emergency_response.resource_agent.process({
                            'action': 'allocate',
                            'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
                        })
                    except Exception as e:
                        resource_result = {'error': str(e)}
                    
                    # Store district info with agent data
                    district_data = {
                        'district': district,
                        'risk_score': risk_score,
                        'risk_level': risk_level,
                        'users_found': len(users),
                        'users': users,
                        'infrastructure': infra_result,
                        'evacuation': evac_result,
                        'resources': resource_result
                    }
                    high_risk_districts.append(district_data)
                    
                    # Add users to dictionary (deduplication by phone number)
                    for user in users:
                        phone_number = user.get('phone_number')
                        if phone_number:
                            # Only keep the HIGHEST risk district for this user
                            if phone_number not in users_dict or risk_score > users_dict[phone_number]['risk_score']:
                                user['affected_district'] = district
                                user['risk_score'] = risk_score
                                user['risk_level'] = risk_level
                                user['features'] = prediction.get('features', {})
                                users_dict[phone_number] = user
                                logger.debug(f"📱 Added/Updated user {phone_number} for {district} (risk: {risk_score:.1f}%)")
                    
            except Exception as e:
                logger.error(f"❌ Error processing {district}: {e}")
                continue
        
        # Convert dict to list
        users_to_notify = list(users_dict.values())
        
        # Check if any high-risk districts found
        if not high_risk_districts:
            return jsonify({
                'status': 'monitoring',
                'message': f'No districts with risk above {threshold}%',
                'threshold': threshold,
                'timestamp': datetime.now().isoformat()
            })
        
        if not users_to_notify:
            return jsonify({
                'status': 'no_users',
                'message': f'Found {len(high_risk_districts)} high-risk districts but NO users with phone numbers',
                'threshold': threshold,
                'high_risk_districts': high_risk_districts,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"📱 Found {len(users_to_notify)} UNIQUE users across {len(high_risk_districts)} districts")
        
        # Send ONE SMS per UNIQUE user
        alert_results = []
        sent_count = 0
        failed_count = 0
        
        for user in users_to_notify:
            phone_number = user.get('phone_number')
            if not phone_number:
                continue
            
            district = user.get('affected_district')
            risk_score = user.get('risk_score', 0)
            risk_level = user.get('risk_level', 'Low')
            
            # Get agent data for this district (from high_risk_districts)
            district_info = next((d for d in high_risk_districts if d['district'] == district), None)
            
            if district_info:
                # Build comprehensive message
                message = emergency_response._build_comprehensive_alert_message(
                    district,
                    risk_level,
                    risk_score,
                    district_info.get('infrastructure'),
                    district_info.get('evacuation'),
                    district_info.get('resources'),
                    user.get('features', {})
                )
            else:
                # Fallback message
                message = emergency_response._build_alert_message(district, risk_level, risk_score)
            
            # Truncate to safe length
            if len(message) > 1200:
                message = message[:1200] + "..."
            
            if dry_run:
                logger.info(f"🔍 DRY RUN: Would send to {phone_number} ({user.get('full_name')}) for {district}")
                alert_results.append({
                    'user_id': user.get('id'),
                    'user_name': user.get('full_name', 'Unknown'),
                    'phone_number': phone_number,
                    'district': district,
                    'dry_run': True,
                    'success': True
                })
                sent_count += 1
            else:
                try:
                    sms_result = notify_lk.send_sms(phone_number, message)
                    
                    alert = Alert(
                        district=district,
                        risk_score=risk_score,
                        risk_level=risk_level,
                        message=message[:500],
                        phone_number=phone_number,
                        sent=sms_result.get('success', False),
                        sent_at=datetime.now() if sms_result.get('success') else None,
                        user_id=user.get('id')
                    )
                    db.session.add(alert)
                    db.session.commit()
                    
                    if sms_result.get('success', False):
                        logger.info(f"✅ Alert sent to {phone_number} ({user.get('full_name')}) for {district}")
                        alert_results.append({
                            'user_id': user.get('id'),
                            'user_name': user.get('full_name', 'Unknown'),
                            'phone_number': phone_number,
                            'district': district,
                            'distance_km': user.get('distance_km', 'N/A'),
                            'success': True,
                            'message_id': sms_result.get('message_id', 'N/A')
                        })
                        sent_count += 1
                    else:
                        logger.error(f"❌ Failed to send to {phone_number}: {sms_result.get('error')}")
                        alert_results.append({
                            'user_id': user.get('id'),
                            'user_name': user.get('full_name', 'Unknown'),
                            'phone_number': phone_number,
                            'district': district,
                            'success': False,
                            'error': sms_result.get('error', 'Unknown')
                        })
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error sending to {phone_number}: {e}")
                    alert_results.append({
                        'user_id': user.get('id'),
                        'phone_number': phone_number,
                        'district': district,
                        'success': False,
                        'error': str(e)
                    })
                    failed_count += 1
        
        return jsonify({
            'status': 'auto_alert_complete',
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'dry_run': dry_run,
            'summary': {
                'total_high_risk_districts': len(high_risk_districts),
                'total_unique_users': len(users_to_notify),
                'alerts_sent': sent_count,
                'alerts_failed': failed_count,
                'success_rate': f"{(sent_count/(sent_count+failed_count)*100):.1f}%" if (sent_count+failed_count) > 0 else "0%"
            },
            'high_risk_districts': high_risk_districts,
            'alert_results': alert_results,
            'message': f"✅ Auto-alert completed! {sent_count} alerts sent to {len(users_to_notify)} unique users."
        })
        
    except Exception as e:
        logger.error(f"❌ Auto-alert error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
@emergency_bp.route('/auto-alert-status', methods=['GET'])
def auto_alert_status():
    """
    Check if there are any high-risk districts (without sending alerts)
    Query params: ?threshold=60
    """
    try:
        threshold = float(request.args.get('threshold', 60.0))
        
        all_districts = emergency_response.risk_agent.districts
        high_risk_districts = []
        
        for district in all_districts:
            try:
                risk_result = emergency_response.risk_agent.predict_district(district)
                if 'error' in risk_result:
                    continue
                
                prediction = risk_result.get('prediction', {})
                risk_score = prediction.get('risk_score', 0)
                risk_level = prediction.get('risk_level', 'Low')
                
                if risk_score >= threshold:
                    users = emergency_response._get_nearby_users_with_priority(district)
                    high_risk_districts.append({
                        'district': district,
                        'risk_score': risk_score,
                        'risk_level': risk_level,
                        'users_affected': len(users)
                    })
            except Exception as e:
                continue
        
        return jsonify({
            'status': 'success',
            'threshold': threshold,
            'high_risk_districts': high_risk_districts,
            'total_high_risk_districts': len(high_risk_districts),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Auto-alert status error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/force-trigger/<district>', methods=['POST'])
def force_trigger_emergency(district):
    """
    FORCE trigger emergency for testing (bypasses ML model)
    Body: {"risk_score": 85.0}
    """
    try:
        data = request.get_json() or {}
        risk_score = data.get('risk_score', 85.0)
        
        result = emergency_response.force_trigger_emergency(district, risk_score)
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Force trigger error: {e}")
        return jsonify({'error': str(e)}), 500

@emergency_bp.route('/test-comprehensive-alert', methods=['POST'])
def test_comprehensive_alert():
    """
    TEST ENDPOINT: Send comprehensive SMS with data from ALL agents
    Even when there's no real emergency (for testing)
    """
    try:
        data = request.get_json() or {}
        district = data.get('district', 'Colombo')
        phone_number = data.get('phone_number', None)
        risk_score = data.get('risk_score', 85.0)
        risk_level = data.get('risk_level', 'Critical')
        dry_run = data.get('dry_run', False)
        
        logger.info(f"🧪 TEST: Sending comprehensive alert for {district}")
        
        # Step 1: Get Infrastructure Data
        logger.info("🏗️ Getting infrastructure data...")
        infra_result = emergency_response.infrastructure_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score
        })
        
        # Step 2: Get Evacuation Data
        logger.info("🚶 Getting evacuation data...")
        evac_result = emergency_response.evacuation_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'origin_lat': None,
            'origin_lon': None
        })
        
        # Step 3: Get Resource Data
        logger.info("📦 Getting resource data...")
        resource_result = emergency_response.resource_agent.process({
            'action': 'allocate',
            'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
        })
        
        # Step 4: Get Risk Features
        risk_result = emergency_response.risk_agent.predict_district(district)
        features = risk_result.get('prediction', {}).get('features', {})
        
        # Step 5: Build Comprehensive Message
        message = emergency_response._build_comprehensive_alert_message(
            district=district,
            risk_level=risk_level,
            risk_score=risk_score,
            infra_result=infra_result,
            evac_result=evac_result,
            resource_result=resource_result,
            features=features
        )
        
        # Truncate to safe length
        original_length = len(message)
        max_length = 800
        
        if len(message) > max_length:
            truncate_at = message.rfind('\n', 0, max_length)
            if truncate_at == -1:
                truncate_at = max_length
            message = message[:truncate_at] + "\n... (truncated)"
            logger.info(f"✂️ Truncated message from {original_length} to {len(message)} chars")
        else:
            logger.info(f"✅ Message length: {len(message)} chars")
        
        # Step 6: Get Users (or use provided phone number)
        if phone_number:
            users = [{'phone_number': phone_number, 'full_name': 'Test User', 'id': 999}]
        else:
            users = emergency_response._get_nearby_users_with_priority(district)
        
        # Step 7: Send SMS
        results = []
        sent_count = 0
        
        for user in users:
            phone = user.get('phone_number')
            if not phone:
                continue
            
            if dry_run:
                logger.info(f"🔍 DRY RUN: Would send to {phone}")
                results.append({
                    'phone_number': phone,
                    'user_name': user.get('full_name', 'Test User'),
                    'success': True,
                    'dry_run': True,
                    'message_id': 'DRY_RUN',
                    'error': None
                })
                sent_count += 1
            else:
                logger.info(f"📱 Sending test SMS to {phone}")
                
                sms_result = notify_lk.send_sms(phone, message)
                
                results.append({
                    'phone_number': phone,
                    'user_name': user.get('full_name', 'Test User'),
                    'success': sms_result.get('success', False),
                    'message_id': sms_result.get('message_id', 'N/A'),
                    'error': sms_result.get('error', None)
                })
                
                if sms_result.get('success', False):
                    sent_count += 1
        
        # Step 8: Return Results
        return jsonify({
            'status': 'test_complete',
            'timestamp': datetime.now().isoformat(),
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'message_length': len(message),
            'original_length': original_length,
            'truncated': original_length > max_length,
            'max_allowed_length': max_length,
            'message_preview': message[:400] + '...' if len(message) > 400 else message,
            'users_notified': len(results),
            'alerts_sent': sent_count,
            'results': results,
            'data_sources': {
                'infrastructure': '✅ Data included' if not infra_result.get('error') else '❌ Error',
                'evacuation': '✅ Data included' if not evac_result.get('error') else '❌ Error',
                'resources': '✅ Data included' if not resource_result.get('error') else '❌ Error',
                'risk_features': '✅ Data included' if features else '❌ Error'
            },
            'message': f"✅ Test alert {'would be sent' if dry_run else 'sent'} to {sent_count} users with comprehensive data!"
        })
        
    except Exception as e:
        logger.error(f"❌ Test comprehensive alert error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    
@emergency_bp.route('/auto-alert-fixed', methods=['POST'])
def auto_alert_fixed():
    """
    FIXED: Step-by-step auto-alert
    1. Find high-risk districts
    2. Get ALL users from DB
    3. Filter users by location (within 50km of high-risk districts)
    4. Send ONE SMS per unique user
    """
    try:
        data = request.get_json() or {}
        threshold = float(data.get('threshold', 60.0))
        dry_run = data.get('dry_run', False)
        
        logger.info(f"🚨 AUTO-ALERT: Step 1 - Finding high-risk districts...")
        
        # ===== STEP 1: Find high-risk districts =====
        all_districts = emergency_response.risk_agent.districts
        high_risk_districts = []
        
        for district in all_districts:
            risk_result = emergency_response.risk_agent.predict_district(district)
            if 'error' in risk_result:
                continue
            
            prediction = risk_result.get('prediction', {})
            risk_score = prediction.get('risk_score', 0)
            risk_level = prediction.get('risk_level', 'Low')
            
            if risk_score >= threshold:
                high_risk_districts.append({
                    'district': district,
                    'risk_score': risk_score,
                    'risk_level': risk_level,
                    'features': prediction.get('features', {})
                })
                logger.info(f"⚠️ HIGH RISK: {district} - {risk_score:.2f}%")
        
        if not high_risk_districts:
            return jsonify({
                'status': 'monitoring',
                'message': f'No districts with risk above {threshold}%',
                'threshold': threshold,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"📊 Found {len(high_risk_districts)} high-risk districts")
        
        # ===== STEP 2: Get ALL users from database =====
        logger.info("👤 Step 2 - Getting all users from database...")
        from ..database.models import User
        all_users = User.query.filter_by(is_active=True).all()
        logger.info(f"📊 Found {len(all_users)} active users")
        
        if not all_users:
            return jsonify({
                'status': 'no_users',
                'message': 'No active users found in database',
                'high_risk_districts': high_risk_districts,
                'timestamp': datetime.now().isoformat()
            })
        
        # ===== STEP 3: Filter users by location =====
        logger.info("📍 Step 3 - Filtering users by location...")
        users_to_notify = []
        radius_km = 50.0
        
        for user in all_users:
            user_dict = user.to_dict()
            
            # Skip users without phone numbers
            if not user_dict.get('phone_number'):
                continue
            
            # Check if user is within 50km of ANY high-risk district
            user_lat = user_dict.get('latitude')
            user_lon = user_dict.get('longitude')
            found = False
            
            for district_info in high_risk_districts:
                district = district_info['district']
                
                # Get district center
                center = emergency_response._get_district_center(district)
                if not center:
                    continue
                
                center_lat, center_lon = center
                
                # Calculate distance
                if user_lat and user_lon:
                    distance = emergency_response._calculate_distance(
                        user_lat, user_lon,
                        center_lat, center_lon
                    )
                    
                    if distance <= radius_km:
                        user_dict['affected_district'] = district
                        user_dict['distance_km'] = round(distance, 2)
                        user_dict['risk_score'] = district_info['risk_score']
                        user_dict['risk_level'] = district_info['risk_level']
                        users_to_notify.append(user_dict)
                        found = True
                        logger.info(f"✅ User {user_dict['full_name']} ({user_dict['phone_number']}) is {distance:.1f}km from {district}")
                        break  # User found, stop checking other districts
            
            if not found and user_dict.get('district'):
                # If user has a district, check if it's in high-risk list
                if user_dict['district'] in [d['district'] for d in high_risk_districts]:
                    user_dict['affected_district'] = user_dict['district']
                    user_dict['distance_km'] = 0
                    user_dict['risk_score'] = next(d['risk_score'] for d in high_risk_districts if d['district'] == user_dict['district'])
                    user_dict['risk_level'] = next(d['risk_level'] for d in high_risk_districts if d['district'] == user_dict['district'])
                    users_to_notify.append(user_dict)
                    logger.info(f"✅ User {user_dict['full_name']} ({user_dict['phone_number']}) is in {user_dict['district']} (exact match)")
        
        if not users_to_notify:
            return jsonify({
                'status': 'no_users',
                'message': f'No users found within {radius_km}km of high-risk districts',
                'high_risk_districts': high_risk_districts,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"📱 Found {len(users_to_notify)} users near high-risk districts")
        
        # ===== STEP 4: Deduplicate by phone number =====
        logger.info("📱 Step 4 - Deduplicating users by phone number...")
        unique_users = {}
        for user in users_to_notify:
            phone = user.get('phone_number')
            if phone and phone not in unique_users:
                unique_users[phone] = user
            elif phone:
                # Keep the one with higher risk
                if user.get('risk_score', 0) > unique_users[phone].get('risk_score', 0):
                    unique_users[phone] = user
        
        final_users = list(unique_users.values())
        logger.info(f"📱 {len(final_users)} unique users after deduplication")
        
        # ===== STEP 5: Send SMS =====
        logger.info("📱 Step 5 - Sending SMS to unique users...")
        alert_results = []
        sent_count = 0
        failed_count = 0
        
        for user in final_users:
            phone_number = user.get('phone_number')
            district = user.get('affected_district')
            risk_score = user.get('risk_score', 0)
            risk_level = user.get('risk_level', 'Low')
            
            logger.info(f"📤 Sending to {phone_number} ({user.get('full_name')}) for {district}")
            
            if dry_run:
                alert_results.append({
                    'phone_number': phone_number,
                    'user_name': user.get('full_name', 'Unknown'),
                    'district': district,
                    'dry_run': True,
                    'success': True
                })
                sent_count += 1
            else:
                # Build message and send
                message = emergency_response._build_comprehensive_alert_message(
                    district,
                    risk_level,
                    risk_score,
                    None, None, None,
                    user.get('features', {})
                )
                
                # Truncate to safe length
                if len(message) > 1200:
                    message = message[:1200] + "..."
                
                sms_result = notify_lk.send_sms(phone_number, message)
                
                if sms_result.get('success', False):
                    sent_count += 1
                    alert_results.append({
                        'phone_number': phone_number,
                        'user_name': user.get('full_name', 'Unknown'),
                        'district': district,
                        'success': True,
                        'message_id': sms_result.get('message_id', 'N/A')
                    })
                else:
                    failed_count += 1
                    alert_results.append({
                        'phone_number': phone_number,
                        'user_name': user.get('full_name', 'Unknown'),
                        'district': district,
                        'success': False,
                        'error': sms_result.get('error', 'Unknown')
                    })
        
        # Return results
        return jsonify({
            'status': 'auto_alert_complete',
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'dry_run': dry_run,
            'high_risk_districts': high_risk_districts,
            'summary': {
                'total_high_risk_districts': len(high_risk_districts),
                'total_users_found': len(users_to_notify),
                'unique_users_notified': len(final_users),
                'alerts_sent': sent_count,
                'alerts_failed': failed_count,
                'success_rate': f"{(sent_count/(sent_count+failed_count)*100):.1f}%" if (sent_count+failed_count) > 0 else "0%"
            },
            'users_notified': final_users,
            'alert_results': alert_results,
            'message': f"✅ Auto-alert completed! {sent_count} alerts sent to {len(final_users)} unique users."
        })
        
    except Exception as e:
        logger.error(f"❌ Auto-alert error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@emergency_bp.route('/send-to-risk-areas', methods=['POST'])
def send_to_risk_areas():
    """
    MAIN ENDPOINT: Send alerts to ALL users in high-risk areas
    Step 1: Find all districts with risk > threshold
    Step 2: Get ALL users from database
    Step 3: Filter users by location (within 50km of high-risk districts)
    Step 4: Send ONE SMS per unique user with comprehensive data
    
    Body: {"threshold": 60, "dry_run": false}
    """
    try:
        data = request.get_json() or {}
        threshold = float(data.get('threshold', 60.0))
        dry_run = data.get('dry_run', False)
        
        logger.info(f"🚨 SEND TO RISK AREAS: Scanning for districts with risk > {threshold}%")
        
        # ===== STEP 1: Find high-risk districts =====
        all_districts = emergency_response.risk_agent.districts
        high_risk_districts = []
        
        for district in all_districts:
            try:
                risk_result = emergency_response.risk_agent.predict_district(district)
                if 'error' in risk_result:
                    continue
                
                prediction = risk_result.get('prediction', {})
                risk_score = prediction.get('risk_score', 0)
                risk_level = prediction.get('risk_level', 'Low')
                features = prediction.get('features', {})
                
                if risk_score >= threshold:
                    # Get agent data for this district
                    try:
                        infra_result = emergency_response.infrastructure_agent.process({
                            'district': district,
                            'risk_level': risk_level,
                            'risk_score': risk_score
                        })
                    except Exception as e:
                        infra_result = {'error': str(e)}
                    
                    try:
                        evac_result = emergency_response.evacuation_agent.process({
                            'district': district,
                            'risk_level': risk_level,
                            'risk_score': risk_score
                        })
                    except Exception as e:
                        evac_result = {'error': str(e)}
                    
                    try:
                        resource_result = emergency_response.resource_agent.process({
                            'action': 'allocate',
                            'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
                        })
                    except Exception as e:
                        resource_result = {'error': str(e)}
                    
                    high_risk_districts.append({
                        'district': district,
                        'risk_score': risk_score,
                        'risk_level': risk_level,
                        'features': features,
                        'infrastructure': infra_result,
                        'evacuation': evac_result,
                        'resources': resource_result
                    })
                    logger.info(f"⚠️ HIGH RISK: {district} - {risk_score:.2f}% ({risk_level})")
                    
            except Exception as e:
                logger.error(f"Error checking {district}: {e}")
                continue
        
        if not high_risk_districts:
            return jsonify({
                'status': 'monitoring',
                'message': f'No districts with risk above {threshold}%',
                'threshold': threshold,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"📊 Found {len(high_risk_districts)} high-risk districts")
        
        # ===== STEP 2: Get ALL users from database =====
        from ..database.models import User
        all_users = User.query.filter_by(is_active=True).all()
        logger.info(f"👤 Found {len(all_users)} active users in database")
        
        if not all_users:
            return jsonify({
                'status': 'no_users',
                'message': 'No active users found in database',
                'high_risk_districts': high_risk_districts,
                'timestamp': datetime.now().isoformat()
            })
        
        # ===== STEP 3: Filter users by location =====
        logger.info("📍 Filtering users by location...")
        users_to_notify = []
        radius_km = 50.0
        
        for user in all_users:
            user_dict = user.to_dict()
            
            # Skip users without phone numbers
            if not user_dict.get('phone_number'):
                continue
            
            user_lat = user_dict.get('latitude')
            user_lon = user_dict.get('longitude')
            
            # Check if user is in or near ANY high-risk district
            found = False
            for district_info in high_risk_districts:
                district = district_info['district']
                
                # Check exact district match first
                if user_dict.get('district') == district:
                    user_dict['affected_district'] = district
                    user_dict['distance_km'] = 0
                    user_dict['match_type'] = 'exact_district'
                    user_dict['risk_score'] = district_info['risk_score']
                    user_dict['risk_level'] = district_info['risk_level']
                    user_dict['features'] = district_info.get('features', {})
                    user_dict['infrastructure'] = district_info.get('infrastructure', {})
                    user_dict['evacuation'] = district_info.get('evacuation', {})
                    user_dict['resources'] = district_info.get('resources', {})
                    users_to_notify.append(user_dict)
                    found = True
                    logger.info(f"✅ {user_dict['full_name']} ({user_dict['phone_number']}) in {district} (exact match)")
                    break
                
                # Check if user is within 50km of district center
                if user_lat and user_lon:
                    center = emergency_response._get_district_center(district)
                    if center:
                        center_lat, center_lon = center
                        distance = emergency_response._calculate_distance(
                            user_lat, user_lon,
                            center_lat, center_lon
                        )
                        
                        if distance <= radius_km:
                            user_dict['affected_district'] = district
                            user_dict['distance_km'] = round(distance, 2)
                            user_dict['match_type'] = 'nearby'
                            user_dict['risk_score'] = district_info['risk_score']
                            user_dict['risk_level'] = district_info['risk_level']
                            user_dict['features'] = district_info.get('features', {})
                            user_dict['infrastructure'] = district_info.get('infrastructure', {})
                            user_dict['evacuation'] = district_info.get('evacuation', {})
                            user_dict['resources'] = district_info.get('resources', {})
                            users_to_notify.append(user_dict)
                            found = True
                            logger.info(f"📍 {user_dict['full_name']} ({user_dict['phone_number']}) is {distance:.1f}km from {district}")
                            break
            
            if not found:
                logger.debug(f"❌ {user_dict['full_name']} ({user_dict['phone_number']}) not near any high-risk district")
        
        if not users_to_notify:
            return jsonify({
                'status': 'no_users_in_risk_areas',
                'message': f'No users found within {radius_km}km of high-risk districts',
                'high_risk_districts': high_risk_districts,
                'timestamp': datetime.now().isoformat()
            })
        
        logger.info(f"📱 Found {len(users_to_notify)} users near high-risk districts")
        
        # ===== STEP 4: Deduplicate by phone number =====
        unique_users = {}
        for user in users_to_notify:
            phone = user.get('phone_number')
            if phone and phone not in unique_users:
                unique_users[phone] = user
            elif phone:
                # Keep the one with higher risk
                if user.get('risk_score', 0) > unique_users[phone].get('risk_score', 0):
                    unique_users[phone] = user
        
        final_users = list(unique_users.values())
        logger.info(f"📱 {len(final_users)} unique users after deduplication")
        
        # ===== STEP 5: Send SMS to each user =====
        alert_results = []
        sent_count = 0
        failed_count = 0
        
        for user in final_users:
            phone_number = user.get('phone_number')
            district = user.get('affected_district')
            risk_score = user.get('risk_score', 0)
            risk_level = user.get('risk_level', 'Low')
            features = user.get('features', {})
            infra_result = user.get('infrastructure', {})
            evac_result = user.get('evacuation', {})
            resource_result = user.get('resources', {})
            
            logger.info(f"📤 Sending to {phone_number} ({user.get('full_name')}) for {district}")
            
            if dry_run:
                alert_results.append({
                    'phone_number': phone_number,
                    'user_name': user.get('full_name', 'Unknown'),
                    'district': district,
                    'dry_run': True,
                    'success': True
                })
                sent_count += 1
            else:
                # Build comprehensive message with all agent data
                message = emergency_response._build_comprehensive_alert_message(
                    district=district,
                    risk_level=risk_level,
                    risk_score=risk_score,
                    infra_result=infra_result,
                    evac_result=evac_result,
                    resource_result=resource_result,
                    features=features
                )
                
                # Truncate to safe length
                if len(message) > 800:
                    message = message[:800] + "..."
                
                sms_result = notify_lk.send_sms(phone_number, message)
                
                if sms_result.get('success', False):
                    sent_count += 1
                    alert_results.append({
                        'phone_number': phone_number,
                        'user_name': user.get('full_name', 'Unknown'),
                        'district': district,
                        'success': True,
                        'message_id': sms_result.get('message_id', 'N/A')
                    })
                    logger.info(f"✅ Sent to {phone_number}")
                else:
                    failed_count += 1
                    alert_results.append({
                        'phone_number': phone_number,
                        'user_name': user.get('full_name', 'Unknown'),
                        'district': district,
                        'success': False,
                        'error': sms_result.get('error', 'Unknown')
                    })
                    logger.error(f"❌ Failed to send to {phone_number}: {sms_result.get('error')}")
        
        # ===== Return Results =====
        return jsonify({
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'dry_run': dry_run,
            'summary': {
                'total_high_risk_districts': len(high_risk_districts),
                'total_users_found_in_db': len(all_users),
                'users_near_risk_areas': len(users_to_notify),
                'unique_users_notified': len(final_users),
                'alerts_sent': sent_count,
                'alerts_failed': failed_count,
                'success_rate': f"{(sent_count/(sent_count+failed_count)*100):.1f}%" if (sent_count+failed_count) > 0 else "0%"
            },
            'high_risk_districts': high_risk_districts,
            'users_notified': final_users,
            'alert_results': alert_results,
            'message': f"✅ Completed! {sent_count} alerts sent to {len(final_users)} unique users in {len(high_risk_districts)} high-risk districts."
        })
        
    except Exception as e:
        logger.error(f"❌ Send to risk areas error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500