import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # PostgreSQL Connection
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'disaster_db')
    DB_USER = os.getenv('DB_USER', 'disaster_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '0787987255Aa__')
    
    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Model paths
    MODEL_PATH = os.getenv('MODEL_PATH', 'models_saved/')
    
    # Alert thresholds
    HIGH_RISK_THRESHOLD = int(os.getenv('HIGH_RISK_THRESHOLD', 70))
    CRITICAL_RISK_THRESHOLD = int(os.getenv('CRITICAL_RISK_THRESHOLD', 85))
    
    # Districts
    DISTRICTS = [
        'Colombo', 'Gampaha', 'Kalutara', 'Galle', 'Matara',
        'Hambantota', 'Kandy', 'Matale', 'Nuwara Eliya',
        'Kurunegala', 'Puttalam', 'Anuradhapura', 'Polonnaruwa',
        'Badulla', 'Monaragala', 'Ratnapura', 'Kegalle'
    ]

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}