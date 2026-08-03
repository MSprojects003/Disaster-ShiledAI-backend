# backend/app/routes/__init__.py

from .risk_routes import risk_bp
from .infrastructure_routes import infra_bp
from .evacuation_routes import evacuation_bp
from .resource_routes import resource_bp
from .citizen_routes import citizen_bp
from .orchestrator_routes import orchestrator_bp
from .alert_routes import alert_bp
from .emergency_routes import emergency_bp
from .emergency_bulk_routes import emergency_bulk_bp

__all__ = [
    'risk_bp',
    'infra_bp',
    'evacuation_bp',
    'resource_bp',
    'citizen_bp',
    'orchestrator_bp',
    'alert_bp',
    'emergency_bp',
    'emergency_bulk_bp'
]
