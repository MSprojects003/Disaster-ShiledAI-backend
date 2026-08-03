"""
Emergency Bulk Alert Service - Enhanced with Location Filtering
Handles filtering high-risk areas and sending bulk SMS alerts
"""

import logging
import math
from datetime import datetime
from typing import Dict, Any, List, Tuple
from flask import current_app

from .notify_lk_service import notify_lk
from ..agents.risk_agent import risk_agent
from ..agents.infrastructure_agent import infrastructure_agent
from ..agents.resource_agent import resource_agent
from ..agents.evacuation_agent import evacuation_agent
from ..database.models import User, RiskPrediction, Alert
from ..database.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmergencyBulkService:
    """
    Service for filtering high-risk areas and sending bulk alerts
    """
    
    def __init__(self):
        self.risk_agent = risk_agent
        self.infrastructure_agent = infrastructure_agent
        self.resource_agent = resource_agent
        self.evacuation_agent = evacuation_agent
        self.critical_threshold = 70  # Lowered to 70% for testing
    
    def get_high_risk_districts(self, threshold: float = 70.0) -> List[Dict[str, Any]]:
        """
        Get all districts with risk score above threshold
        
        Args:
            threshold: Risk score threshold (default 70%)
        
        Returns:
            List of high-risk districts with risk info
        """
        high_risk_districts = []
        
        try:
            # Use the risk_agent's internal districts list
            districts = self.risk_agent.districts
            
            for district in districts:
                try:
                    # Get risk prediction for this district
                    risk_result = self.risk_agent.predict_district(district)
                    
                    if 'error' in risk_result:
                        logger.warning(f"⚠️ Error predicting {district}: {risk_result['error']}")
                        continue
                    
                    # Extract prediction
                    prediction = risk_result.get('prediction', {})
                    risk_score = prediction.get('risk_score', 0)
                    risk_level = prediction.get('risk_level', 'Low')
                    
                    # Check if risk exceeds threshold
                    if risk_score >= threshold:
                        high_risk_districts.append({
                            'district': district,
                            'risk_score': risk_score,
                            'risk_level': risk_level,
                            'features': prediction.get('features', {}),
                            'timestamp': datetime.now().isoformat()
                        })
                        logger.info(f"🚨 HIGH RISK: {district} - {risk_score:.2f}%")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {district}: {e}")
                    continue
            
            logger.info(f"✅ Found {len(high_risk_districts)} high-risk districts (threshold: {threshold}%)")
            return high_risk_districts
            
        except Exception as e:
            logger.error(f"❌ Error getting high-risk districts: {e}")
            return []
    
    def get_users_in_district(self, district: str) -> List[Dict[str, Any]]:
        """
        Get all users in a specific district with location data
        
        Args:
            district: District name
        
        Returns:
            List of users with phone numbers and location
        """
        try:
            # Get all active users
            users = User.query.filter_by(is_active=True).all()
            
            user_list = []
            for user in users:
                user_dict = user.to_dict()
                
                # Check if user's district matches
                if user_dict.get('district') == district:
                    # Only include users with phone numbers
                    if user_dict.get('phone_number'):
                        user_list.append(user_dict)
                        logger.debug(f"✅ Found user {user_dict.get('full_name')} in {district}")
            
            logger.info(f"✅ Found {len(user_list)} active users in {district}")
            return user_list
            
        except Exception as e:
            logger.error(f"❌ Error getting users in {district}: {e}")
            return []
    
    def get_users_near_location(self, district: str, radius_km: float = 50.0) -> List[Dict[str, Any]]:
        """
        Get users near a district center using lat/lon
        
        Args:
            district: District name
            radius_km: Radius in kilometers to search
        
        Returns:
            List of users within radius
        """
        try:
            # Get district center
            center = self._get_district_center(district)
            if not center:
                logger.warning(f"⚠️ No center coordinates for {district}")
                return self.get_users_in_district(district)
            
            center_lat, center_lon = center
            
            # Get all active users
            users = User.query.filter_by(is_active=True).all()
            
            nearby_users = []
            for user in users:
                user_dict = user.to_dict()
                
                # Skip if no phone number
                if not user_dict.get('phone_number'):
                    continue
                
                # Check if user has location data
                user_lat = user_dict.get('latitude')
                user_lon = user_dict.get('longitude')
                
                if user_lat and user_lon:
                    # Calculate distance
                    distance = self._calculate_distance(
                        center_lat, center_lon,
                        float(user_lat), float(user_lon)
                    )
                    
                    if distance <= radius_km:
                        user_dict['distance_km'] = round(distance, 2)
                        nearby_users.append(user_dict)
                        logger.debug(f"📍 User {user_dict.get('full_name')} is {distance:.1f}km from {district}")
                else:
                    # If no lat/lon, check by district name
                    if user_dict.get('district') == district:
                        nearby_users.append(user_dict)
            
            logger.info(f"✅ Found {len(nearby_users)} users near {district} (within {radius_km}km)")
            return nearby_users
            
        except Exception as e:
            logger.error(f"❌ Error getting users near {district}: {e}")
            return []
    
    def get_all_users_in_high_risk_areas(self, threshold: float = 70.0) -> Dict[str, Any]:
        """
        Get all users in high-risk districts with location filtering
        
        Args:
            threshold: Risk score threshold
        
        Returns:
            Dictionary with high-risk districts and users
        """
        # Get high-risk districts
        high_risk_districts = self.get_high_risk_districts(threshold)
        
        if not high_risk_districts:
            return {
                'status': 'monitoring',
                'message': f'No districts with risk above {threshold}%',
                'high_risk_districts': [],
                'total_users_affected': 0,
                'timestamp': datetime.now().isoformat()
            }
        
        # Get users in each high-risk district
        result = {
            'status': 'emergency',
            'threshold': threshold,
            'high_risk_districts': [],
            'total_users_affected': 0,
            'all_users': [],
            'timestamp': datetime.now().isoformat()
        }
        
        for district_info in high_risk_districts:
            district = district_info['district']
            
            # First try to get users by location (lat/lon)
            users = self.get_users_near_location(district, radius_km=50.0)
            
            # If no users found by location, try by district name
            if not users:
                users = self.get_users_in_district(district)
            
            district_info['users'] = users
            district_info['user_count'] = len(users)
            
            result['high_risk_districts'].append(district_info)
            result['total_users_affected'] += len(users)
            result['all_users'].extend(users)
        
        return result
    
    def _get_district_center(self, district: str) -> Tuple[float, float]:
        """Get district center coordinates"""
        centers = {
            'Colombo': (6.9271, 79.8612),
            'Gampaha': (7.0889, 79.9967),
            'Kalutara': (6.5833, 79.9667),
            'Galle': (6.0535, 80.2210),
            'Matara': (5.9484, 80.5410),
            'Kandy': (7.2906, 80.6337),
            'Ratnapura': (6.6833, 80.4000),
            'Kurunegala': (7.4833, 80.3667),
            'Anuradhapura': (8.3114, 80.4037),
            'Badulla': (6.9833, 81.0500),
            'Nuwara Eliya': (6.9667, 80.7667),
            'Matale': (7.4667, 80.6167),
            'Hambantota': (6.1241, 81.1185),
            'Monaragala': (6.8667, 81.3500),
            'Polonnaruwa': (7.9333, 81.0000),
            'Puttalam': (8.0333, 79.8333),
            'Kegalle': (7.2500, 80.3333)
        }
        return centers.get(district)
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates (Haversine formula)"""
        R = 6371  # Earth's radius in km
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def get_district_infrastructure(self, district: str, risk_level: str, risk_score: float) -> Dict[str, Any]:
        """Get infrastructure information for a district"""
        try:
            result = self.infrastructure_agent.process({
                'district': district,
                'risk_level': risk_level,
                'risk_score': risk_score
            })
            return result
        except Exception as e:
            logger.error(f"❌ Error getting infrastructure for {district}: {e}")
            return {'error': str(e)}
    
    def get_district_resources(self, district: str, risk_level: str, risk_score: float) -> Dict[str, Any]:
        """Get resource allocation information for a district"""
        try:
            result = self.resource_agent.process({
                'action': 'allocate',
                'risk_predictions': {
                    district: {
                        'risk_score': risk_score,
                        'risk_level': risk_level
                    }
                }
            })
            return result
        except Exception as e:
            logger.error(f"❌ Error getting resources for {district}: {e}")
            return {'error': str(e)}
    
    def get_district_evacuation_plan(self, district: str, risk_level: str, risk_score: float) -> Dict[str, Any]:
        """Get evacuation plan for a district"""
        try:
            result = self.evacuation_agent.process({
                'district': district,
                'risk_level': risk_level,
                'risk_score': risk_score
            })
            return result
        except Exception as e:
            logger.error(f"❌ Error getting evacuation plan for {district}: {e}")
            return {'error': str(e)}
    
    def build_emergency_alert_message(
        self,
        district: str,
        risk_level: str,
        risk_score: float,
        infrastructure_info: Dict[str, Any] = None,
        resource_info: Dict[str, Any] = None,
        evacuation_info: Dict[str, Any] = None
    ) -> str:
        """Build comprehensive emergency alert message"""
        
        # Risk emoji and urgency
        if risk_level == 'Critical' or risk_score >= 80:
            emoji = '🚨🚨🚨'
            urgency = 'IMMEDIATE EVACUATION REQUIRED'
            priority = 'CRITICAL'
        elif risk_level == 'High' or risk_score >= 60:
            emoji = '🚨⚠️'
            urgency = 'URGENT: TAKE PRECAUTIONARY MEASURES'
            priority = 'HIGH'
        elif risk_level == 'Medium' or risk_score >= 40:
            emoji = '⚠️📢'
            urgency = 'PREPARE FOR POSSIBLE EVACUATION'
            priority = 'MEDIUM'
        else:
            emoji = 'ℹ️'
            urgency = 'MONITOR CONDITIONS CLOSELY'
            priority = 'LOW'
        
        # Start building message
        message_lines = [
            f"{emoji} DISASTER ALERT - {district}",
            f"{'='*40}",
            f"Risk Level: {risk_level} ({risk_score:.1f}%)",
            f"Priority: {priority}",
            f"Action Required: {urgency}",
            f"{'='*40}",
            "",
            "📍 AFFECTED AREA:",
            f"   - District: {district}",
        ]
        
        # Add risk factors
        message_lines.append("")
        message_lines.append("🌧️ RISK FACTORS:")
        message_lines.append(f"   - Flood Risk: {risk_level}")
        message_lines.append(f"   - Probability: {risk_score:.1f}%")
        
        # Add infrastructure information
        if infrastructure_info and not infrastructure_info.get('error'):
            message_lines.append("")
            message_lines.append("🏗️ INFRASTRUCTURE STATUS:")
            
            infrastructure = infrastructure_info.get('infrastructure', {})
            critical = infrastructure.get('critical', {})
            
            # Roads
            roads = critical.get('roads', {})
            if roads:
                road_status = roads.get('status', 'Unknown')
                message_lines.append(f"   - Roads: {road_status}")
            
            # Bridges
            bridges = critical.get('bridges', {})
            if bridges:
                bridge_status = bridges.get('status', 'Unknown')
                message_lines.append(f"   - Bridges: {bridge_status}")
            
            # Utilities
            utilities = critical.get('utilities', {})
            if utilities:
                power = utilities.get('power', 'Normal')
                water = utilities.get('water', 'Normal')
                message_lines.append(f"   - Power Supply: {power}")
                message_lines.append(f"   - Water Supply: {water}")
            
            # Shelters
            shelters = infrastructure.get('shelters', [])
            if shelters:
                total_shelters = len(shelters)
                total_capacity = sum(s.get('capacity', 0) for s in shelters)
                message_lines.append(f"   - Shelters Available: {total_shelters}")
                message_lines.append(f"   - Total Capacity: {total_capacity} people")
        
        # Add resource information
        if resource_info and not resource_info.get('error'):
            message_lines.append("")
            message_lines.append("📦 RESOURCES ALLOCATED:")
            
            allocations = resource_info.get('allocations', {})
            if allocations:
                for resource_type, details in allocations.items():
                    if isinstance(details, dict):
                        quantity = details.get('quantity', 'N/A')
                        status = details.get('status', 'Available')
                        message_lines.append(f"   - {resource_type}: {quantity} ({status})")
                    else:
                        message_lines.append(f"   - {resource_type}: {details}")
        
        # Add evacuation information
        if evacuation_info and not evacuation_info.get('error'):
            message_lines.append("")
            message_lines.append("🚶 EVACUATION PLAN:")
            
            # Evacuation routes
            routes = evacuation_info.get('evacuation_routes', [])
            if routes:
                message_lines.append("   Recommended Routes:")
                for idx, route in enumerate(routes[:2], 1):
                    route_name = route.get('name', f'Route {idx}')
                    distance = route.get('distance', 'N/A')
                    message_lines.append(f"   {idx}. {route_name} ({distance})")
            
            # Assembly points
            assembly_points = evacuation_info.get('assembly_points', [])
            if assembly_points:
                message_lines.append("   Assembly Points:")
                for point in assembly_points[:2]:
                    name = point.get('name', 'Unknown')
                    capacity = point.get('capacity', 'N/A')
                    message_lines.append(f"   - {name} (Capacity: {capacity})")
            
            # Safety tips
            safety_tips = evacuation_info.get('safety_tips', [])
            if safety_tips:
                message_lines.append("")
                message_lines.append("💡 SAFETY TIPS:")
                for tip in safety_tips[:2]:
                    message_lines.append(f"   • {tip}")
        
        # Add emergency contacts
        message_lines.append("")
        message_lines.append("📞 EMERGENCY CONTACTS:")
        message_lines.append("   - Police: 119")
        message_lines.append("   - Ambulance: 110")
        message_lines.append("   - Disaster Management: 117")
        message_lines.append("   - National Hospital: 011-2691111")
        
        # Add footer
        message_lines.append("")
        message_lines.append(f"⚠️ Automated Alert from Disaster-Shield AI")
        message_lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Join all lines with newlines
        return '\n'.join(message_lines)
    
    def send_emergency_alerts_to_high_risk_areas(
        self,
        threshold: float = 70.0,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Main method: Send emergency alerts to all users in high-risk areas
        
        Args:
            threshold: Risk score threshold (default 70%)
            dry_run: If True, only simulate (don't actually send SMS)
        
        Returns:
            Complete response with all details
        """
        logger.info(f"🚨 Starting emergency alert process (threshold: {threshold}%)")
        
        # Step 1: Get high-risk districts and users
        risk_data = self.get_all_users_in_high_risk_areas(threshold)
        
        if risk_data['status'] == 'monitoring':
            logger.info(f"✅ No high-risk districts found (threshold: {threshold}%)")
            return risk_data
        
        # Check if there are any users to notify
        if risk_data['total_users_affected'] == 0:
            logger.warning(f"⚠️ High-risk districts found but NO users to notify")
            return {
                'status': 'no_users_to_notify',
                'message': f'High-risk districts found but no users with phone numbers',
                'high_risk_districts': risk_data['high_risk_districts'],
                'total_users_affected': 0,
                'timestamp': datetime.now().isoformat()
            }
        
        # Step 2: Process each high-risk district
        results = {
            'status': 'emergency_response_triggered',
            'threshold': threshold,
            'timestamp': datetime.now().isoformat(),
            'total_districts': len(risk_data['high_risk_districts']),
            'total_users_affected': risk_data['total_users_affected'],
            'districts_processed': [],
            'alerts_sent': [],
            'alerts_failed': [],
            'summary': {
                'total_alerts_attempted': 0,
                'total_alerts_sent': 0,
                'total_alerts_failed': 0
            }
        }
        
        # Process each high-risk district
        for district_info in risk_data['high_risk_districts']:
            district = district_info['district']
            risk_score = district_info['risk_score']
            risk_level = district_info['risk_level']
            users = district_info['users']
            
            # Skip if no users in this district
            if not users:
                logger.info(f"ℹ️ No users found in {district}, skipping alerts")
                continue
            
            logger.info(f"📋 Processing {district} - Risk: {risk_level} ({risk_score:.1f}%) - Users: {len(users)}")
            
            # Get infrastructure, resource, and evacuation information
            infrastructure_info = self.get_district_infrastructure(district, risk_level, risk_score)
            resource_info = self.get_district_resources(district, risk_level, risk_score)
            evacuation_info = self.get_district_evacuation_plan(district, risk_level, risk_score)
            
            # Build comprehensive alert message
            message = self.build_emergency_alert_message(
                district=district,
                risk_level=risk_level,
                risk_score=risk_score,
                infrastructure_info=infrastructure_info,
                resource_info=resource_info,
                evacuation_info=evacuation_info
            )
            
            # Prepare district result
            district_result = {
                'district': district,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'user_count': len(users),
                'phone_numbers': [u.get('phone_number') for u in users if u.get('phone_number')],
                'message_preview': message[:200] + '...',
                'alerts_sent': [],
                'alerts_failed': []
            }
            
            # Send alerts to each user in this district
            sent_count = 0
            failed_count = 0
            
            for user in users:
                phone_number = user.get('phone_number')
                if not phone_number:
                    continue
                
                if dry_run:
                    # Dry run - just log
                    logger.info(f"🔍 DRY RUN: Would send alert to {phone_number}")
                    district_result['alerts_sent'].append({
                        'phone_number': phone_number,
                        'user_id': user.get('id'),
                        'user_name': user.get('full_name', 'Unknown'),
                        'dry_run': True
                    })
                    sent_count += 1
                else:
                    # Actually send SMS
                    sms_result = notify_lk.send_sms(phone_number, message)
                    
                    # Save to database
                    try:
                        alert = Alert(
                            district=district,
                            risk_score=risk_score,
                            risk_level=risk_level,
                            message=message,
                            phone_number=phone_number,
                            sent=sms_result.get('success', False),
                            sent_at=datetime.now() if sms_result.get('success') else None,
                            user_id=user.get('id')
                        )
                        db.session.add(alert)
                        db.session.commit()
                    except Exception as e:
                        logger.error(f"❌ Error saving alert to DB: {e}")
                    
                    if sms_result.get('success', False):
                        logger.info(f"✅ Alert sent to {phone_number} in {district}")
                        district_result['alerts_sent'].append({
                            'phone_number': phone_number,
                            'user_id': user.get('id'),
                            'user_name': user.get('full_name', 'Unknown'),
                            'message_id': sms_result.get('message_id', 'N/A'),
                            'success': True
                        })
                        sent_count += 1
                    else:
                        logger.error(f"❌ Failed to send alert to {phone_number}: {sms_result.get('error', 'Unknown error')}")
                        district_result['alerts_failed'].append({
                            'phone_number': phone_number,
                            'user_id': user.get('id'),
                            'user_name': user.get('full_name', 'Unknown'),
                            'error': sms_result.get('error', 'Unknown error')
                        })
                        failed_count += 1
                
                results['alerts_sent'].extend(district_result['alerts_sent'])
                results['alerts_failed'].extend(district_result['alerts_failed'])
            
            district_result['sent_count'] = sent_count
            district_result['failed_count'] = failed_count
            
            # Only add to processed districts if there were users
            if users:
                results['districts_processed'].append(district_result)
            
            # Save risk prediction
            try:
                prediction = RiskPrediction(
                    district=district,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    alert_triggered=True,
                    action_required=f'Bulk alerts sent to {sent_count} users'
                )
                db.session.add(prediction)
                db.session.commit()
            except Exception as e:
                logger.error(f"❌ Error saving risk prediction: {e}")
        
        # Update summary
        results['summary']['total_alerts_attempted'] = (
            len(results['alerts_sent']) + len(results['alerts_failed'])
        )
        results['summary']['total_alerts_sent'] = len(results['alerts_sent'])
        results['summary']['total_alerts_failed'] = len(results['alerts_failed'])
        
        # Log summary
        logger.info(f"✅ Emergency alert process complete!")
        logger.info(f"   Districts: {results['total_districts']}")
        logger.info(f"   Users affected: {results['total_users_affected']}")
        logger.info(f"   Alerts sent: {results['summary']['total_alerts_sent']}")
        logger.info(f"   Alerts failed: {results['summary']['total_alerts_failed']}")
        
        return results
    
    def get_emergency_statistics(self) -> Dict[str, Any]:
        """Get statistics about emergency alerts"""
        try:
            # Get all alerts
            alerts = Alert.query.all()
            
            # Get high-risk predictions
            high_risk = RiskPrediction.query.filter(
                RiskPrediction.risk_score >= 70
            ).all()
            
            return {
                'total_alerts_sent': len(alerts),
                'successful_alerts': len([a for a in alerts if a.sent]),
                'failed_alerts': len([a for a in alerts if not a.sent]),
                'high_risk_predictions': len(high_risk),
                'districts_with_high_risk': list(set([p.district for p in high_risk])),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
            return {'error': str(e)}

# Singleton instance
emergency_bulk_service = EmergencyBulkService()