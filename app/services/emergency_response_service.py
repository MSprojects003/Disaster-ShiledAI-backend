"""
Emergency Response Service
Orchestrates all 5 agents during critical emergencies
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
import math

from ..agents.risk_agent import risk_agent
from ..agents.infrastructure_agent import infrastructure_agent
from ..agents.evacuation_agent import evacuation_agent
from ..agents.resource_agent import resource_agent
from ..database.models import User, RiskPrediction, Alert
from ..database.db import db
from .notify_lk_service import notify_lk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmergencyResponseService:
    """
    Orchestrates all 5 agents for complete emergency response
    """
    
    def __init__(self):
        self.risk_agent = risk_agent
        self.infrastructure_agent = infrastructure_agent
        self.evacuation_agent = evacuation_agent
        self.resource_agent = resource_agent
        self.default_threshold = 60.0
    
    def handle_critical_emergency(self, district: str, threshold: float = None) -> Dict[str, Any]:
        """Handle emergency using all agents"""
        if threshold is None:
            threshold = self.default_threshold
            
        logger.info(f"Processing emergency check for {district} (threshold: {threshold}%)")
        
        risk_result = self.risk_agent.predict_district(district)
        
        if 'error' in risk_result:
            return {'error': f'Risk prediction failed: {risk_result["error"]}'}
        
        prediction = risk_result.get('prediction', {})
        risk_score = prediction.get('risk_score', 0)
        risk_level = prediction.get('risk_level', 'Low')
        features = prediction.get('features', {})
        
        logger.info(f"{district} - Risk: {risk_score:.2f}% ({risk_level})")
        
        if risk_score < threshold:
            return {
                'status': 'monitoring',
                'message': f'Risk score {risk_score:.2f}% is below threshold ({threshold}%)',
                'risk_score': risk_score,
                'risk_level': risk_level,
                'threshold': threshold,
                'district': district,
                'timestamp': datetime.now().isoformat()
            }
        
        logger.info(f"EMERGENCY: {district} has {risk_score:.2f}% risk")
        
        # Get all agent data
        try:
            infra_result = self.infrastructure_agent.process({
                'district': district,
                'risk_level': risk_level,
                'risk_score': risk_score
            })
        except Exception as e:
            logger.error(f"Infrastructure error: {e}")
            infra_result = {'error': str(e)}
        
        try:
            evac_result = self.evacuation_agent.process({
                'district': district,
                'risk_level': risk_level,
                'risk_score': risk_score
            })
        except Exception as e:
            logger.error(f"Evacuation error: {e}")
            evac_result = {'error': str(e)}
        
        try:
            resource_result = self.resource_agent.process({
                'action': 'allocate',
                'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
            })
        except Exception as e:
            logger.error(f"Resource error: {e}")
            resource_result = {'error': str(e)}
        
        nearby_users = self._get_nearby_users_with_priority(district)
        
        alert_results = self._send_alerts_to_users(
            nearby_users, district, risk_level, risk_score,
            infra_result, evac_result, resource_result, features
        )
        
        self._save_emergency_record(district, risk_score, risk_level, nearby_users, features)
        
        return {
            'status': 'emergency_response',
            'timestamp': datetime.now().isoformat(),
            'district': district,
            'risk_score': risk_score,
            'risk_level': risk_level,
            'threshold': threshold,
            'features': features,
            'risk_prediction': risk_result,
            'infrastructure_status': infra_result,
            'evacuation_plan': evac_result,
            'resource_allocation': resource_result,
            'nearby_users': nearby_users,
            'alerts_sent': alert_results,
            'total_people_notified': len(nearby_users),
            'recommendation': self._get_recommendation(risk_level)
        }
    
    def _get_unique_users(self, users: List[Dict]) -> List[Dict]:
        """
        Get unique users by phone number to prevent duplicates
        This prevents the same user from getting multiple SMS
        """
        seen_phone_numbers = set()
        unique_users = []
        
        for user in users:
            phone_number = user.get('phone_number')
            if phone_number and phone_number not in seen_phone_numbers:
                seen_phone_numbers.add(phone_number)
                unique_users.append(user)
            else:
                logger.debug(f"Skipping duplicate user: {phone_number}")
        
        if len(unique_users) < len(users):
            logger.info(f"Deduplicated: {len(users)} -> {len(unique_users)} unique users")
        
        return unique_users
    
    def _send_alerts_to_users(self, users: List[Dict], district: str, risk_level: str, 
                              risk_score: float, infra_result: Dict = None, 
                              evac_result: Dict = None, resource_result: Dict = None,
                              features: Dict = None) -> List[Dict]:
        """
        Send alerts to all nearby users with COMPREHENSIVE information
        Prevents duplicate SMS to same user
        """
        results = []
        
        if not users:
            logger.warning(f"No users to notify for {district}")
            return results
        
        # DEDUPLICATE USERS - Prevent multiple SMS to same person
        unique_users = self._get_unique_users(users)
        
        # Build COMPREHENSIVE alert message with ALL details
        message = self._build_comprehensive_alert_message(
            district, risk_level, risk_score, 
            infra_result, evac_result, resource_result, features
        )
        
        logger.info(f"Sending alerts to {len(unique_users)} unique users in {district}")
        logger.info(f"Message length: {len(message)} characters")
        
        for user in unique_users:
            phone_number = user.get('phone_number')
            if not phone_number:
                continue
            
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
                
                result_entry = {
                    'user_id': user.get('id'),
                    'user_name': user.get('full_name', 'Unknown'),
                    'phone_number': phone_number,
                    'distance_km': user.get('distance_km', 'N/A'),
                    'match_type': user.get('match_type', 'unknown'),
                    'success': sms_result.get('success', False),
                    'message_id': sms_result.get('message_id', 'N/A')
                }
                results.append(result_entry)
                
                if sms_result.get('success', False):
                    logger.info(f"Alert sent to {phone_number}")
                else:
                    logger.error(f"Failed to send to {phone_number}: {sms_result.get('error', 'Unknown')}")
                
            except Exception as e:
                logger.error(f"Error sending alert to {phone_number}: {e}")
                results.append({
                    'user_id': user.get('id'),
                    'phone_number': phone_number,
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    def _get_nearby_users_with_priority(self, district: str, radius_km: float = 50.0) -> List[Dict[str, Any]]:
        """
        Get users near district, prioritizing exact matches first
        This prevents duplicates and prioritizes people actually in the district
        """
        try:
            users = User.query.filter_by(is_active=True).all()
            
            if not users:
                return []
            
            exact_match_users = []
            nearby_users = []
            dist_center = self._get_district_center(district)
            
            for user in users:
                user_dict = user.to_dict()
                
                if not user_dict.get('phone_number'):
                    continue
                
                # Check exact district match first (highest priority)
                if user.district and user.district.lower() == district.lower():
                    user_dict['match_type'] = 'exact_district'
                    user_dict['distance_km'] = 0
                    exact_match_users.append(user_dict)
                    logger.debug(f"Exact match: {user.full_name} in {district}")
                    continue
                
                # Then check nearby (within radius)
                if dist_center and user.latitude and user.longitude:
                    try:
                        distance = self._calculate_distance(
                            float(user.latitude), float(user.longitude),
                            dist_center[0], dist_center[1]
                        )
                        if distance <= radius_km:
                            user_dict['match_type'] = 'nearby'
                            user_dict['distance_km'] = round(distance, 2)
                            nearby_users.append(user_dict)
                            logger.debug(f"Nearby: {user.full_name} is {distance:.1f}km from {district}")
                    except Exception as e:
                        logger.warning(f"Error calculating distance for user {user.id}: {e}")
                        continue
            
            # Combine: exact matches first, then nearby
            all_users = exact_match_users + nearby_users
            
            # Final deduplication by phone number
            unique_users = self._get_unique_users(all_users)
            
            logger.info(f"Found {len(unique_users)} unique users near {district}")
            return unique_users
            
        except Exception as e:
            logger.error(f"Error getting nearby users: {e}")
            return []
    
    def _build_comprehensive_alert_message(self, district: str, risk_level: str, risk_score: float,
                                          infra_result: Dict = None, evac_result: Dict = None, 
                                          resource_result: Dict = None, features: Dict = None) -> str:
        """
        Build PROFESSIONAL emergency alert message with REAL data from ALL agents
        Clean, human-readable format
        """
        
        # Risk level text
        if risk_level == 'Critical' or risk_score >= 80:
            level_text = "CRITICAL - EVACUATE NOW"
        elif risk_level == 'High' or risk_score >= 60:
            level_text = "HIGH RISK - Take Action"
        elif risk_level == 'Medium' or risk_score >= 40:
            level_text = "MEDIUM RISK - Be Prepared"
        else:
            level_text = "LOW RISK - Monitor"
        
        parts = []
        
        # ===== HEADER =====
        parts.append(f"EMERGENCY ALERT: {district}")
        parts.append(f"Risk: {risk_level} ({risk_score:.0f}%) - {level_text}")
        parts.append("")
        
        # ===== RISK FACTORS =====
        if features and any(features.values()):
            risk_items = []
            if features.get('rainfall_mm') and features.get('rainfall_mm') != 'N/A':
                risk_items.append(f"Rainfall: {features.get('rainfall_mm')}mm")
            if features.get('river_level_m') and features.get('river_level_m') != 'N/A':
                risk_items.append(f"River Level: {features.get('river_level_m')}m")
            if features.get('soil_moisture') and features.get('soil_moisture') != 'N/A':
                risk_items.append(f"Soil Moisture: {features.get('soil_moisture')}%")
            if features.get('temperature_c') and features.get('temperature_c') != 'N/A':
                risk_items.append(f"Temperature: {features.get('temperature_c')}C")
            if features.get('humidity_percent') and features.get('humidity_percent') != 'N/A':
                risk_items.append(f"Humidity: {features.get('humidity_percent')}%")
            
            if risk_items:
                parts.append("Weather Conditions:")
                for item in risk_items:
                    parts.append(f"  - {item}")
            else:
                parts.append("Weather data: Currently being monitored")
        else:
            parts.append("Weather data: Currently being monitored")
        parts.append("")
        
        # ===== INFRASTRUCTURE STATUS =====
        if infra_result and not infra_result.get('error'):
            road_status = infra_result.get('road_status', [])
            if road_status:
                safe = sum(1 for r in road_status if r.get('status') == 'Safe')
                impassable = sum(1 for r in road_status if r.get('status') == 'Impassable')
                blocked = sum(1 for r in road_status if r.get('status') == 'Blocked')
                total = len(road_status)
                
                parts.append(f"Road Status: {total} roads analyzed")
                parts.append(f"  - Safe: {safe} | Impassable: {impassable} | Blocked: {blocked}")
                
                # Show affected roads if any
                if impassable > 0 or blocked > 0:
                    affected = [r for r in road_status if r.get('status') in ['Blocked', 'Impassable']]
                    if affected:
                        road_names = []
                        for r in affected[:3]:
                            name = r.get('road_name', '')
                            if name and name != 'Unknown Road' and name != 'Road_0' and name != f'Road_{r.get("road_id", 0)}':
                                road_names.append(name)
                        
                        if road_names:
                            parts.append(f"  Affected: {', '.join(road_names)}")
                        else:
                            parts.append(f"  Affected: {len(affected)} road segments")
            else:
                parts.append("Road Status: No data available")
        else:
            parts.append("Road Status: Currently being monitored")
        parts.append("")
        
        # ===== EVACUATION PLAN =====
        if evac_result and not evac_result.get('error'):
            nearest = evac_result.get('nearest_shelter', {})
            if nearest and not nearest.get('error'):
                name = nearest.get('name', '')
                if name and name != 'Unknown':
                    dist = nearest.get('distance_km', 'N/A')
                    cap = nearest.get('available_capacity', 'N/A')
                    parts.append(f"Nearest Shelter: {name}")
                    parts.append(f"  - Distance: {dist}km | Capacity: {cap} people")
                else:
                    parts.append("Nearest Shelter: Available in your district")
            else:
                parts.append("Nearest Shelter: Available in your district")
        else:
            parts.append("Nearest Shelter: Available in your district")
        parts.append("")
        
        # ===== RESOURCES =====
        resource_items = []
        if resource_result and not resource_result.get('error'):
            allocation_plan = resource_result.get('allocation_plan', [])
            if allocation_plan:
                for alloc in allocation_plan:
                    if alloc.get('district') == district:
                        resources = alloc.get('allocated_resources', {})
                        if resources:
                            for r_type, qty in resources.items():
                                if qty > 0:
                                    name = r_type.replace('_', ' ').title()
                                    resource_items.append(f"{name}: {qty}")
                        break
            
            if resource_items:
                parts.append("Resources Deployed:")
                for item in resource_items[:4]:
                    parts.append(f"  - {item}")
            else:
                parts.append("Resources: Being deployed")
        else:
            parts.append("Resources: Being deployed")
        parts.append("")
        
        # ===== ACTION PLAN =====
        if risk_level in ['Critical', 'High']:
            parts.append("ACTION REQUIRED:")
            parts.append("  1. Evacuate immediately if instructed")
            parts.append("  2. Go to nearest shelter")
            parts.append("  3. Take emergency kit with you")
            parts.append("  4. Avoid flooded roads")
        else:
            parts.append("ACTION REQUIRED:")
            parts.append("  1. Prepare emergency kit")
            parts.append("  2. Stay informed via updates")
            parts.append("  3. Be ready to evacuate if needed")
        parts.append("")
        
        # ===== EMERGENCY CONTACTS =====
        parts.append("Emergency Contacts:")
        parts.append("  Police: 119 | Ambulance: 110 | DMC: 117")
        parts.append("")
        
        # ===== FOOTER =====
        parts.append(f"Alert Time: {datetime.now().strftime('%H:%M %d-%m-%Y')}")
        parts.append("Disaster-Shield AI System")
        
        # Join with single line breaks
        message = "\n".join(parts)
        
        # Keep under 800 characters to save credits
        if len(message) > 780:
            # Remove less critical info
            lines = message.split("\n")
            # Keep header (3 lines), action (5 lines), contacts (2 lines), footer (2 lines)
            if len(lines) > 15:
                # Remove middle sections if too long
                first_part = lines[:5]  # Header + weather
                last_part = lines[-8:]  # Action + contacts + footer
                message = "\n".join(first_part + ["..."] + last_part)
            if len(message) > 780:
                message = message[:780] + "..."
        
        return message
    
    def _get_district_center(self, district: str) -> tuple:
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
        return centers.get(district, (7.0, 80.0))
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two coordinates"""
        try:
            R = 6371
            lat1_rad = math.radians(float(lat1))
            lat2_rad = math.radians(float(lat2))
            delta_lat = math.radians(float(lat2) - float(lat1))
            delta_lon = math.radians(float(lon2) - float(lon1))
            a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return R * c
        except Exception:
            return 9999
    
    def _get_recommendation(self, risk_level: str) -> str:
        """Get recommendation based on risk level"""
        recommendations = {
            'Critical': 'IMMEDIATE EVACUATION REQUIRED',
            'High': 'URGENT - Prepare to evacuate',
            'Medium': 'Monitor and prepare',
            'Low': 'Safe - Continue monitoring'
        }
        return recommendations.get(risk_level, 'Monitor conditions')
    
    def _save_emergency_record(self, district: str, risk_score: float, risk_level: str, 
                               users: List[Dict], features: Dict = None):
        """Save emergency record to database"""
        try:
            prediction = RiskPrediction(
                district=district,
                risk_score=risk_score,
                risk_level=risk_level,
                alert_triggered=True,
                action_required=f'Emergency response triggered for {len(users)} users',
                rainfall_mm=features.get('rainfall_mm') if features else None,
                river_level_m=features.get('river_level_m') if features else None,
                elevation_m=features.get('elevation_m') if features else None,
                slope_degree=features.get('slope_degree') if features else None,
                soil_moisture=features.get('soil_moisture') if features else None,
                temperature_c=features.get('temperature_c') if features else None,
                humidity_percent=features.get('humidity_percent') if features else None
            )
            db.session.add(prediction)
            db.session.commit()
            logger.info(f"Emergency record saved for {district}")
        except Exception as e:
            logger.error(f"Failed to save emergency record: {e}")
    
    def handle_emergency_for_all_districts(self, threshold: float = None) -> Dict[str, Any]:
        """Check all districts"""
        if threshold is None:
            threshold = self.default_threshold
            
        logger.info(f"Scanning all districts for risk above {threshold}%...")
        
        districts = self.risk_agent.districts
        results = {}
        critical_districts = []
        
        for district in districts:
            try:
                result = self.handle_critical_emergency(district, threshold)
                results[district] = result
                if result.get('status') == 'emergency_response':
                    critical_districts.append(district)
            except Exception as e:
                logger.error(f"Error handling {district}: {e}")
                results[district] = {'error': str(e)}
        
        return {
            'total_districts_checked': len(districts),
            'critical_districts': critical_districts,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_emergency_summary(self, district: str = None) -> Dict[str, Any]:
        """Get emergency summary"""
        try:
            query = RiskPrediction.query.filter_by(alert_triggered=True)
            if district:
                query = query.filter_by(district=district)
            records = query.order_by(RiskPrediction.created_at.desc()).limit(10).all()
            
            return {
                'total_emergencies': len(records),
                'recent_emergencies': [r.to_dict() for r in records],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting emergency summary: {e}")
            return {'error': str(e)}
    
    def force_trigger_emergency(self, district: str, risk_score: float = 85.0) -> Dict[str, Any]:
        """Force trigger emergency for testing"""
        logger.info(f"FORCE TRIGGER: {district} with {risk_score}% risk")
        
        nearby_users = self._get_nearby_users_with_priority(district)
        
        if not nearby_users:
            return {
                'status': 'no_users',
                'message': f'No users found in {district}',
                'district': district
            }
        
        # Get all agent data
        try:
            infra_result = self.infrastructure_agent.process({
                'district': district,
                'risk_level': 'Critical',
                'risk_score': risk_score
            })
        except Exception as e:
            infra_result = {'error': str(e)}
        
        try:
            evac_result = self.evacuation_agent.process({
                'district': district,
                'risk_level': 'Critical',
                'risk_score': risk_score
            })
        except Exception as e:
            evac_result = {'error': str(e)}
        
        try:
            resource_result = self.resource_agent.process({
                'action': 'allocate',
                'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': 'Critical'}}
            })
        except Exception as e:
            resource_result = {'error': str(e)}
        
        # Send alerts with comprehensive message
        alert_results = self._send_alerts_to_users(
            nearby_users, district, 'Critical', risk_score,
            infra_result, evac_result, resource_result
        )
        
        self._save_emergency_record(district, risk_score, 'Critical', nearby_users)
        
        return {
            'status': 'emergency_triggered',
            'timestamp': datetime.now().isoformat(),
            'district': district,
            'risk_score': risk_score,
            'risk_level': 'Critical',
            'users_notified': len(nearby_users),
            'alerts_sent': alert_results,
            'message': f'Emergency triggered for {district}. {len(nearby_users)} users notified.'
        }

# Singleton instance
emergency_response = EmergencyResponseService()