from ..database.models import Alert, User
from ..database.db import db
from .notify_lk_service import notify_lk
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AlertService:
    """Generates and manages alerts using Notify.lk"""
    
    def generate_alert(self, district, prediction, risk_factors):
        """Generate an alert and send via Notify.lk"""
        risk_level = prediction['risk_level']
        risk_score = prediction['risk_score']
        
        message = f"""
⚠️ FLOOD/LANDSLIDE ALERT ⚠️

District: {district}
Risk Level: {risk_level} ({risk_score:.1f}%)
Action: {prediction['action_required']}

Key Risk Factors:
{chr(10).join(['• ' + f for f in risk_factors[:3]])}

Actions:
1. {'EVACUATE NOW!' if risk_level == 'Critical' else 'Prepare for evacuation'}
2. Monitor official updates
3. Keep emergency contacts ready
        """
        
        # Save to database
        alert = Alert(
            district=district,
            risk_score=risk_score,
            risk_level=risk_level,
            message=message,
            sent=False
        )
        db.session.add(alert)
        db.session.commit()
        
        # Send SMS via Notify.lk if risk is High or Critical
        if risk_level in ['High', 'Critical']:
            self._send_sms_alerts(district, risk_level, risk_score)
        
        logger.info(f"🚨 Alert generated for {district}")
        return alert.to_dict()
    
    def _send_sms_alerts(self, district, risk_level, risk_score):
        """
        Send SMS alerts via Notify.lk using DATABASE users
        """
        recipients = self._get_alert_recipients(district)
        
        if not recipients:
            logger.warning(f"⚠️ No recipients found for {district}")
            return
        
        # Build comprehensive message using all agents
        from .emergency_response_service import emergency_response
        
        # Get agent data
        infra_result = emergency_response.infrastructure_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score
        })
        
        evac_result = emergency_response.evacuation_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score
        })
        
        resource_result = emergency_response.resource_agent.process({
            'action': 'allocate',
            'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
        })
        
        # Build comprehensive message
        message = emergency_response._build_comprehensive_alert_message(
            district=district,
            risk_level=risk_level,
            risk_score=risk_score,
            infra_result=infra_result,
            evac_result=evac_result,
            resource_result=resource_result
        )
        
        # Truncate to 1300 characters (safe for Notify.lk)
        if len(message) > 1300:
            message = message[:1300] + "..."
        
        # Send to all recipients
        results = []
        for recipient in recipients:
            if recipient:
                sms_result = notify_lk.send_sms(recipient, message)
                results.append(sms_result)
                
                # Save to database
                try:
                    alert = Alert(
                        district=district,
                        risk_score=risk_score,
                        risk_level=risk_level,
                        message=message[:500],
                        phone_number=recipient,
                        sent=sms_result.get('success', False),
                        sent_at=datetime.now() if sms_result.get('success') else None
                    )
                    db.session.add(alert)
                    db.session.commit()
                except Exception as e:
                    logger.error(f"❌ Error saving alert: {e}")
        
        success_count = sum(1 for r in results if r.get('success', False))
        logger.info(f"📱 Sent {success_count}/{len(results)} SMS alerts for {district}")
        
        return results
    
    def _get_alert_recipients(self, district):
        """
        Get list of recipients for a district from DATABASE
        """
        try:
            # Get all active users in this district
            users = User.query.filter_by(
                district=district,
                is_active=True
            ).all()
            
            # Extract phone numbers
            recipients = [user.phone_number for user in users if user.phone_number]
            
            logger.info(f"📱 Found {len(recipients)} recipients for {district} from database")
            
            # If no users found in district, try location-based search
            if not recipients:
                logger.info(f"ℹ️ No exact district match for {district}, trying location-based...")
                from .emergency_response_service import emergency_response
                nearby_users = emergency_response._get_nearby_users_with_priority(district)
                recipients = [user.get('phone_number') for user in nearby_users if user.get('phone_number')]
                logger.info(f"📱 Found {len(recipients)} recipients via location search")
            
            return recipients
            
        except Exception as e:
            logger.error(f"❌ Error getting recipients for {district}: {e}")
            return []
    
    def send_single_alert(self, phone_number: str, district: str, risk_level: str, risk_score: float) -> dict:
        """
        Send a single SMS alert via Notify.lk to a specific phone number
        """
        # Build comprehensive message
        from .emergency_response_service import emergency_response
        
        infra_result = emergency_response.infrastructure_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score
        })
        
        evac_result = emergency_response.evacuation_agent.process({
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score
        })
        
        resource_result = emergency_response.resource_agent.process({
            'action': 'allocate',
            'risk_predictions': {district: {'risk_score': risk_score, 'risk_level': risk_level}}
        })
        
        message = emergency_response._build_comprehensive_alert_message(
            district=district,
            risk_level=risk_level,
            risk_score=risk_score,
            infra_result=infra_result,
            evac_result=evac_result,
            resource_result=resource_result
        )
        
        # Truncate to 1300 characters
        if len(message) > 1300:
            message = message[:1300] + "..."
        
        result = notify_lk.send_sms(phone_number, message)
        
        # Save to database if sent
        try:
            alert = Alert(
                district=district,
                risk_score=risk_score,
                risk_level=risk_level,
                message=message[:500],
                phone_number=phone_number,
                sent=result.get('success', False),
                sent_at=datetime.now() if result.get('success') else None
            )
            db.session.add(alert)
            db.session.commit()
        except Exception as e:
            logger.error(f"❌ Error saving alert: {e}")
        
        if result.get('success'):
            logger.info(f"✅ SMS sent to {phone_number}")
        else:
            logger.error(f"❌ SMS failed to {phone_number}: {result.get('error')}")
        
        return result

# Create singleton instance
alert_service = AlertService()