# backend/app/__init__.py

from flask import Flask
from flask_cors import CORS
from .config import config
from .database.db import init_db, get_db_stats
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)
    
    # Load config
    app.config.from_object(config[config_name])
    
    # ============================================================
    # FIXED CORS CONFIGURATION
    # ============================================================
    CORS(app, resources={
        r"/api/*": {
            "origins": [
                "http://localhost:5173",
                "http://localhost:3000", 
                "http://127.0.0.1:5173",
                "http://127.0.0.1:3000"
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": [
                "Content-Type", 
                "Authorization", 
                "Accept",
                "X-Requested-With"
            ],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": 3600
        }
    })
    
    # Initialize database
    init_db(app)
    
    # Register blueprints
    from .routes.risk_routes import risk_bp
    app.register_blueprint(risk_bp, url_prefix='/api/risk')
    
    from .routes.infrastructure_routes import infra_bp
    app.register_blueprint(infra_bp, url_prefix='/api/infrastructure')
    
    from .routes.evacuation_routes import evacuation_bp
    app.register_blueprint(evacuation_bp, url_prefix='/api/evacuation')
    
    from .routes.citizen_routes import citizen_bp
    app.register_blueprint(citizen_bp, url_prefix='/api/citizen')
    
    from .routes.resource_routes import resource_bp
    app.register_blueprint(resource_bp, url_prefix='/api/resource')
    
    from .routes.orchestrator_routes import orchestrator_bp
    app.register_blueprint(orchestrator_bp, url_prefix='/api/orchestrator')
    
    from .routes.alert_routes import alert_bp
    app.register_blueprint(alert_bp, url_prefix='/api/alerts')
    
    from .routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    from .routes.emergency_routes import emergency_bp
    app.register_blueprint(emergency_bp, url_prefix='/api/emergency')
    
    from .routes.emergency_bulk_routes import emergency_bulk_bp
    app.register_blueprint(emergency_bulk_bp, url_prefix='/api/emergency-bulk')

    # Root endpoint
    @app.route('/')
    def index():
        stats = get_db_stats()
        return {
            'name': 'Disaster-ShieldAI',
            'version': '1.0.0',
            'status': 'operational',
            'agents': ['Risk Prediction', 'Infrastructure', 'Evacuation', 'Citizen Intelligence', 'Resource Management'],
            'endpoints': {
                'risk': '/api/risk/',
                'infrastructure': '/api/infrastructure/',
                'evacuation': '/api/evacuation/',
                'citizen': '/api/citizen/',
                'resource': '/api/resource/'
            }
        }
    
    @app.route('/health')
    def health():
        return {'status': 'healthy'}
    
    logger.info("✅ Disaster-ShieldAI initialized with Risk + Infrastructure Agents!")
    return app