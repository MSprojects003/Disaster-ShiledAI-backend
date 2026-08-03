from .db import db
from datetime import datetime, timedelta
import jwt
import os
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()


class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # User details
    full_name = db.Column(db.String(200))
    address = db.Column(db.String(500))
    city = db.Column(db.String(100))
    district = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    phone_number = db.Column(db.String(20))
    
    # Role and status
    role = db.Column(db.String(50), default='citizen')  # citizen, authority, admin
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    predictions = db.relationship('RiskPrediction', backref='user', lazy=True)
    alerts = db.relationship('Alert', backref='user', lazy=True)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Check password against hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def generate_token(self):
        """Generate JWT token"""
        payload = {
            'user_id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'exp': datetime.utcnow() + timedelta(days=7)
        }
        return jwt.encode(payload, os.getenv('SECRET_KEY', 'your-secret-key'), algorithm='HS256')
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'address': self.address,
            'city': self.city,
            'district': self.district,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'phone_number': self.phone_number,
            'role': self.role,
            'is_verified': self.is_verified,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class RiskPrediction(db.Model):
    """Store risk predictions"""
    __tablename__ = 'risk_predictions'
    
    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False)
    risk_score = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(20), nullable=False)
    
    # Features used
    rainfall_mm = db.Column(db.Float)
    river_level_m = db.Column(db.Float)
    elevation_m = db.Column(db.Float)
    slope_degree = db.Column(db.Float)
    soil_moisture = db.Column(db.Float)
    temperature_c = db.Column(db.Float)
    humidity_percent = db.Column(db.Float)
    wind_speed_kmh = db.Column(db.Float)
    pressure_hpa = db.Column(db.Float)
    
    # Results
    action_required = db.Column(db.String(200))
    alert_triggered = db.Column(db.Boolean, default=False)
    
    # User association
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'district': self.district,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'action_required': self.action_required,
            'alert_triggered': self.alert_triggered,
            'features': {
                'rainfall_mm': self.rainfall_mm,
                'river_level_m': self.river_level_m,
                'elevation_m': self.elevation_m,
                'slope_degree': self.slope_degree,
                'soil_moisture': self.soil_moisture,
                'temperature_c': self.temperature_c,
                'humidity_percent': self.humidity_percent,
                'wind_speed_kmh': self.wind_speed_kmh,
                'pressure_hpa': self.pressure_hpa
            },
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Alert(db.Model):
    """Store alerts generated"""
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False)
    risk_score = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text)
    phone_number = db.Column(db.String(20))
    channel = db.Column(db.String(20), default='sms')  # sms, whatsapp, email
    
    # Status
    sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime)
    delivered = db.Column(db.Boolean, default=False)
    delivered_at = db.Column(db.DateTime)
    
    # User association
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'district': self.district,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'message': self.message,
            'phone_number': self.phone_number,
            'channel': self.channel,
            'sent': self.sent,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivered': self.delivered,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DistrictRiskHistory(db.Model):
    """Historical risk data per district"""
    __tablename__ = 'district_risk_history'
    
    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False)
    risk_score = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(20), nullable=False)
    rainfall_mm = db.Column(db.Float)
    river_level_m = db.Column(db.Float)
    temperature_c = db.Column(db.Float)
    humidity_percent = db.Column(db.Float)
    
    # User association
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'district': self.district,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'rainfall_mm': self.rainfall_mm,
            'river_level_m': self.river_level_m,
            'temperature_c': self.temperature_c,
            'humidity_percent': self.humidity_percent,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class UserPreference(db.Model):
    """User preferences for alerts and notifications"""
    __tablename__ = 'user_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Notification preferences
    sms_enabled = db.Column(db.Boolean, default=True)
    whatsapp_enabled = db.Column(db.Boolean, default=False)
    email_enabled = db.Column(db.Boolean, default=False)
    
    # Alert thresholds
    alert_threshold = db.Column(db.Float, default=60.0)  # Only alert above this risk score
    notify_critical_only = db.Column(db.Boolean, default=False)
    
    # Districts to monitor
    monitored_districts = db.Column(db.Text, default='[]')  # JSON array
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        import json
        return {
            'id': self.id,
            'user_id': self.user_id,
            'sms_enabled': self.sms_enabled,
            'whatsapp_enabled': self.whatsapp_enabled,
            'email_enabled': self.email_enabled,
            'alert_threshold': self.alert_threshold,
            'notify_critical_only': self.notify_critical_only,
            'monitored_districts': json.loads(self.monitored_districts) if self.monitored_districts else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Feedback(db.Model):
    """User feedback on predictions and alerts"""
    __tablename__ = 'feedback'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Feedback details
    prediction_id = db.Column(db.Integer, db.ForeignKey('risk_predictions.id'), nullable=True)
    feedback_type = db.Column(db.String(50))  # accurate, inaccurate, helpful, etc.
    rating = db.Column(db.Integer)  # 1-5
    comment = db.Column(db.Text)
    
    # Location context
    district = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'prediction_id': self.prediction_id,
            'feedback_type': self.feedback_type,
            'rating': self.rating,
            'comment': self.comment,
            'district': self.district,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class NotificationLog(db.Model):
    """Log of all notifications sent"""
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    alert_id = db.Column(db.Integer, db.ForeignKey('alerts.id'), nullable=True)
    
    # Notification details
    type = db.Column(db.String(20))  # sms, whatsapp, email, push
    recipient = db.Column(db.String(100))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    status = db.Column(db.String(20))  # sent, delivered, failed
    error = db.Column(db.Text)
    
    # Timestamps
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'alert_id': self.alert_id,
            'type': self.type,
            'recipient': self.recipient,
            'subject': self.subject,
            'message': self.message[:200] + '...' if len(self.message) > 200 else self.message,
            'status': self.status,
            'error': self.error,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None
        }




        # backend/app/database/models.py - Add this class

class ResourceAllocation(db.Model):
    """Store resource allocation history"""
    __tablename__ = 'resource_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False)
    allocation_plan = db.Column(db.JSON, nullable=False)  # Store the entire plan
    resources_used = db.Column(db.JSON)  # Resources used
    resources_remaining = db.Column(db.JSON)  # Resources remaining
    priority_score = db.Column(db.Float)
    risk_level = db.Column(db.String(20))
    risk_score = db.Column(db.Float)
    urgency = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'district': self.district,
            'allocation_plan': self.allocation_plan,
            'resources_used': self.resources_used,
            'resources_remaining': self.resources_remaining,
            'priority_score': self.priority_score,
            'risk_level': self.risk_level,
            'risk_score': self.risk_score,
            'urgency': self.urgency,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }