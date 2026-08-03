import os
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TwilioAlertService:
    """
    Service for sending SMS and WhatsApp alerts using Twilio
    """
    
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID', '')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN', '')
        self.phone_number = os.getenv('TWILIO_PHONE_NUMBER', '')
        self.whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER', '+14155238886')
        
        self.enabled = False
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Twilio client"""
        try:
            if not self.account_sid or not self.auth_token:
                logger.warning("⚠️ Twilio credentials not configured. Alerts disabled.")
                return
            
            # Check if phone number is valid (not the placeholder)
            if self.phone_number == '+12345678900':
                logger.warning("⚠️ Twilio phone number not configured. Alerts disabled.")
                logger.info("   Please update TWILIO_PHONE_NUMBER in .env with your Twilio number")
                return
            
            self.client = Client(self.account_sid, self.auth_token)
            self.enabled = True
            logger.info(f"✅ Twilio client initialized with number: {self.phone_number}")
            
        except Exception as e:
            logger.error(f"❌ Twilio initialization failed: {e}")
            self.enabled = False
    
    def send_sms(self, to_number: str, message: str) -> dict:
        """
        Send SMS alert
        """
        if not self.enabled:
            return {'success': False, 'error': 'Twilio not configured'}
        
        # Validate sender number
        if not self.phone_number or self.phone_number == '+12345678900':
            return {'success': False, 'error': 'Invalid sender phone number. Please configure TWILIO_PHONE_NUMBER in .env'}
        
        try:
            to_number = self._clean_phone_number(to_number)
            
            # Log the attempt
            logger.info(f"📱 Sending SMS from {self.phone_number} to {to_number}")
            
            sms = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_number
            )
            
            logger.info(f"✅ SMS sent: {sms.sid}")
            
            return {
                'success': True,
                'sid': sms.sid,
                'to': to_number,
                'status': sms.status,
                'timestamp': datetime.now().isoformat()
            }
            
        except TwilioRestException as e:
            error_msg = str(e)
            logger.error(f"❌ SMS failed: {e}")
            
            # Check for specific errors
            if 'not a Twilio phone number' in error_msg:
                error_msg = f"Your Twilio phone number '{self.phone_number}' is not valid. Please check your Twilio Console for the correct number."
            elif 'Invalid phone number' in error_msg:
                error_msg = f"Recipient number '{to_number}' is invalid. Please use format: +947XXXXXXXX"
            
            return {'success': False, 'error': error_msg}
        except Exception as e:
            logger.error(f"❌ SMS error: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_whatsapp(self, to_number: str, message: str) -> dict:
        """
        Send WhatsApp alert using Twilio Sandbox
        """
        if not self.enabled:
            return {'success': False, 'error': 'Twilio not configured'}
        
        try:
            to_number = self._clean_phone_number(to_number)
            
            # WhatsApp requires 'whatsapp:' prefix
            from_whatsapp = f'whatsapp:{self.whatsapp_number}'
            to_whatsapp = f'whatsapp:{to_number}'
            
            logger.info(f"💬 Sending WhatsApp from {self.whatsapp_number} to {to_number}")
            
            whatsapp = self.client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            
            logger.info(f"✅ WhatsApp sent: {whatsapp.sid}")
            
            return {
                'success': True,
                'sid': whatsapp.sid,
                'to': to_number,
                'status': whatsapp.status,
                'timestamp': datetime.now().isoformat()
            }
            
        except TwilioRestException as e:
            error_msg = str(e)
            logger.error(f"❌ WhatsApp failed: {e}")
            
            if 'Channel with the specified From address' in error_msg:
                error_msg = f"WhatsApp sandbox not configured. Send 'join <code>' to {self.whatsapp_number} first."
            
            return {'success': False, 'error': error_msg}
        except Exception as e:
            logger.error(f"❌ WhatsApp error: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_alert(self, to_number: str, district: str, risk_level: str, risk_score: float, channel: str = 'both') -> dict:
        """Send formatted disaster alert"""
        message = self._build_alert_message(district, risk_level, risk_score)
        
        results = {}
        
        if channel in ['sms', 'both']:
            results['sms'] = self.send_sms(to_number, message)
        
        if channel in ['whatsapp', 'both']:
            results['whatsapp'] = self.send_whatsapp(to_number, message)
        
        return {
            'district': district,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'channel': channel,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def send_bulk_alerts(self, recipients: list, district: str, risk_level: str, risk_score: float, channel: str = 'both') -> list:
        """Send alerts to multiple recipients"""
        results = []
        
        for recipient in recipients:
            result = self.send_alert(recipient, district, risk_level, risk_score, channel)
            results.append(result)
        
        return results
    
    def _build_alert_message(self, district: str, risk_level: str, risk_score: float) -> str:
        """Build formatted alert message - SHORTENED VERSION"""
    
        if risk_level == 'Critical':
          emoji = '🚨'
          urgency = 'EVACUATE NOW'
        elif risk_level == 'High':
           emoji = '⚠️'
           urgency = 'TAKE ACTION'
        else:
           emoji = '📢'
           urgency = 'MONITOR'
    
    # SHORTENED message for trial accounts
        message = f"""{emoji} {district} ALERT
    Risk: {risk_level} ({risk_score:.0f}%)
    Action: {urgency}

    1. Evacuate if told
    2. Monitor updates
    3. Call 117 for help"""
    
        return message
    
    def _clean_phone_number(self, number: str) -> str:
        """Clean phone number format"""
        # Remove spaces and special characters
        cleaned = ''.join(filter(str.isdigit, number))
        
        # If number starts with 0, replace with +94 for Sri Lanka
        if cleaned.startswith('0'):
            cleaned = '94' + cleaned[1:]
        
        # If number doesn't start with +, add it
        if not number.startswith('+'):
            return '+' + cleaned
        
        return number
    
    def get_status(self) -> dict:
        """Get Twilio service status"""
        return {
            'enabled': self.enabled,
            'phone_number': self.phone_number,
            'whatsapp_number': self.whatsapp_number,
            'account_sid_configured': bool(self.account_sid),
            'auth_token_configured': bool(self.auth_token),
            'phone_number_configured': self.phone_number and self.phone_number != '+12345678900'
        }

    def get_message_status(self, message_sid: str) -> dict:
        """Fetch the current delivery status of a previously sent message"""
        if not self.enabled:
           return {'success': False, 'error': 'Twilio not configured'}
        try:
           msg = self.client.messages(message_sid).fetch()
           return {
              'success': True,
              'sid': msg.sid,
              'status': msg.status,
              'error_code': msg.error_code,
              'error_message': msg.error_message,
            }
        except TwilioRestException as e:
           return {'success': False, 'error': str(e)}

# Singleton instance
twilio_alert = TwilioAlertService()