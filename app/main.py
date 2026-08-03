from flask import Flask, jsonify
from flask_cors import CORS
from .config import config
from .database.db import init_db
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    CORS(app)
    init_db(app)
    
    # Import blueprints from correct files
    from .routes.risk_routes import risk_bp
    from .routes.infrastructure_routes import infra_bp
    from .routes.evacuation_routes import evacuation_bp
    from .routes.resource_routes import resource_bp      # ✅ CORRECT - from resource_routes
    from .routes.citizen_routes import citizen_bp        # ✅ CORRECT - from citizen_routes
    

    from .routes.orchestrator_routes import orchestrator_bp
    from .routes.alert_routes import alert_bp
    from.routes.emergency_routes import emergency_bp

# Register blueprint
    app.register_blueprint(alert_bp, url_prefix='/api/alerts')
 
    app.register_blueprint(orchestrator_bp, url_prefix='/api/orchestrator')
    
    # Register blueprints
    app.register_blueprint(risk_bp, url_prefix='/api/risk')
    app.register_blueprint(infra_bp, url_prefix='/api/infrastructure')
    app.register_blueprint(evacuation_bp, url_prefix='/api/evacuation')
    app.register_blueprint(resource_bp, url_prefix='/api/resource')
    app.register_blueprint(citizen_bp, url_prefix='/api/citizen')
    
    @app.route('/')
    def index():
        return jsonify({
            'name': 'Disaster-ShieldAI',
            'version': '1.0.0',
            'agents': ['Risk Prediction', 'Infrastructure', 'Evacuation', 'Resource', 'Citizen Intelligence'],
            'status': 'operational',
            'endpoints': {
                'risk': '/api/risk/',
                'infrastructure': '/api/infrastructure/',
                'evacuation': '/api/evacuation/',
                'resource': '/api/resource/',
                'citizen': '/api/citizen/'
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy'})
    
    @app.route('/routes')
    def list_routes():
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                'endpoint': rule.endpoint,
                'methods': list(rule.methods),
                'url': str(rule)
            })
        return jsonify({'routes': routes})
    
    logger.info("✅ Disaster-ShieldAI initialized with all 5 agents!")
    return app