"""
Notify.lk SMS Service
Replacement for Twilio SMS
"""

import os
import json
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotifyLKService:
    """
    SMS Service using Notify.lk API
    """
    
    def __init__(self):
        self.api_key = os.getenv('NOTIFY_LK_API_KEY', 'rG5Tegfix8588hYbubgD')
        self.user_id = os.getenv('NOTIFY_LK_USER_ID', '32441')
        self.sender_id = os.getenv('NOTIFY_LK_SENDER_ID', 'NotifyDEMO')
        self.api_url = "https://app.notify.lk/api/v1/send"
        
        self.enabled = False
        self._init_service()
    
    def _init_service(self):
        """Initialize the Notify.lk service"""
        try:
            if not self.api_key or not self.user_id:
                logger.warning("⚠️ Notify.lk credentials not configured. SMS disabled.")
                return
            
            self.enabled = True
            logger.info(f"✅ Notify.lk service initialized with Sender ID: {self.sender_id}")
            logger.info(f"   User ID: {self.user_id}")
            
        except Exception as e:
            logger.error(f"❌ Notify.lk initialization failed: {e}")
            self.enabled = False
    
    def send_sms(self, to_number: str, message: str) -> dict:
        """Send SMS using Notify.lk API"""
        if not self.enabled:
            return {'success': False, 'error': 'Notify.lk not configured'}
        
        try:
            cleaned_number = self._clean_phone_number(to_number)
            
            payload = {
                'user_id': self.user_id,
                'api_key': self.api_key,
                'sender_id': self.sender_id,
                'to': cleaned_number,
                'message': message
            }
            
            logger.info(f"📱 Sending SMS via Notify.lk to {cleaned_number}")
            
            response = requests.post(
                self.api_url,
                data=payload,
                timeout=30
            )
            
            logger.info(f"   Status Code: {response.status_code}")
            logger.info(f"   Response Text: {response.text[:200]}...")
            
            # Parse response - handle both dict and string
            try:
                if response.text and response.text.strip():
                    result = response.json()
                else:
                    result = {'status': 'error', 'message': 'Empty response'}
            except Exception as json_error:
                logger.error(f"JSON parse error: {json_error}")
                # If response is not JSON, treat as string
                result = {'status': 'unknown', 'message': response.text}
            
            # Check response properly
            if response.status_code == 200:
                # Success
                if isinstance(result, dict):
                    # Check if it's a success response
                    status = result.get('status', '')
                    if status == 'success' or result.get('success') == True:
                        return {
                            'success': True,
                            'message_id': result.get('data', {}).get('message_id', 'Sent'),
                            'to': cleaned_number,
                            'status': 'sent',
                            'timestamp': datetime.now().isoformat(),
                            'provider': 'notify.lk'
                        }
                    else:
                        # Error response
                        error_msg = result.get('message', result.get('error', 'Unknown error'))
                        return {
                            'success': False,
                            'error': f"Notify.lk error: {error_msg}",
                            'response': result
                        }
                else:
                    # Response is not a dict (string or other)
                    return {
                        'success': True,
                        'message_id': 'Sent',
                        'to': cleaned_number,
                        'status': 'sent',
                        'timestamp': datetime.now().isoformat(),
                        'provider': 'notify.lk'
                    }
            else:
                # Non-200 status code
                error_msg = result.get('message', result.get('error', f'HTTP {response.status_code}')) if isinstance(result, dict) else f'HTTP {response.status_code}'
                return {
                    'success': False,
                    'error': f"Notify.lk API error: {error_msg}",
                    'response': result
                }
            
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Request timeout'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Connection error'}
        except Exception as e:
            logger.error(f"❌ Notify.lk SMS error: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_bulk_sms(self, to_numbers: list, message: str) -> list:
        """Send SMS to multiple recipients"""
        results = []
        for number in to_numbers:
            result = self.send_sms(number, message)
            results.append(result)
        return results
    
    def _clean_phone_number(self, number: str) -> str:
        """Clean phone number for Notify.lk"""
        cleaned = number.replace('+', '').replace(' ', '').replace('-', '')
        cleaned = ''.join(filter(str.isdigit, cleaned))
        
        if cleaned.startswith('0'):
            cleaned = '94' + cleaned[1:]
        
        if not cleaned.startswith('94') and len(cleaned) == 10:
            cleaned = '94' + cleaned
        
        return cleaned
    
    def send_alert(self, to_number: str, district: str, risk_level: str, risk_score: float) -> dict:
        """Send formatted disaster alert"""
        message = self._build_alert_message(district, risk_level, risk_score)
        return self.send_sms(to_number, message)
    
    def send_bulk_alerts(self, recipients: list, district: str, risk_level: str, risk_score: float) -> list:
        """Send alerts to multiple recipients"""
        message = self._build_alert_message(district, risk_level, risk_score)
        results = []
        
        for recipient in recipients:
            result = self.send_sms(recipient, message)
            results.append(result)
        
        return results
    
    def _build_alert_message(self, district: str, risk_level: str, risk_score: float) -> str:
        """Build formatted alert message (fallback)"""
        if risk_level == 'Critical':
            urgency = 'IMMEDIATE EVACUATION REQUIRED'
        elif risk_level == 'High':
            urgency = 'TAKE PRECAUTIONARY MEASURES'
        elif risk_level == 'Medium':
            urgency = 'PREPARE FOR EVACUATION'
        else:
            urgency = 'MONITOR CONDITIONS'
        
        message = f"""{district} DISASTER ALERT

Risk: {risk_level} ({risk_score:.0f}%)
Action: {urgency}

1. {'EVACUATE NOW' if risk_level in ['Critical', 'High'] else 'Be prepared'}
2. Follow official instructions
3. Call 117 for help

- Disaster-Shield AI"""
        
        return message
    
    def get_status(self) -> dict:
        """Get Notify.lk service status"""
        return {
            'enabled': self.enabled,
            'api_key_configured': bool(self.api_key),
            'user_id_configured': bool(self.user_id),
            'sender_id': self.sender_id,
            'provider': 'notify.lk',
            'api_url': self.api_url
        }

# Singleton instance
notify_lk = NotifyLKService()