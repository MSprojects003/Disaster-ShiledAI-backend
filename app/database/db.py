from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()

def init_db(app):
    """
    Initialize database with app
    
    This function:
    1. Configures the database connection
    2. Initializes SQLAlchemy
    3. Sets up migrations
    4. Creates tables if they don't exist
    """
    try:
        # Log database configuration
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')
        logger.info(f"📁 Database URI: {db_uri.replace('://', '://***:***@') if '://' in db_uri else db_uri}")
        
        # Initialize extensions with app
        db.init_app(app)
        migrate.init_app(app, db)
        bcrypt.init_app(app)
        
        # Create tables
        with app.app_context():
            # Import models here to avoid circular imports
            from .models import (
                User,
                RiskPrediction,
                Alert,
                DistrictRiskHistory,
                UserPreference,
                Feedback,
                NotificationLog
            )
            
            # Create all tables
            db.create_all()
            
            # Log success
            logger.info("✅ PostgreSQL database connected successfully!")
            
            # Count tables for verification
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            logger.info(f"📊 Tables in database: {len(tables)}")
            for table in tables:
                logger.info(f"   📋 {table}")
            
            # Create default admin user if not exists
            _create_default_admin()
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        logger.error("Please check your PostgreSQL credentials in .env file")
        logger.error("Make sure PostgreSQL is running and the database exists")
        raise

def _create_default_admin():
    """Create default admin user if no users exist"""
    try:
        from .models import User
        
        # Check if any users exist
        if User.query.count() == 0:
            logger.info("👤 Creating default admin user...")
            
            admin = User(
                username="admin",
                email="admin@disastershield.com",
                full_name="System Administrator",
                role="admin",
                is_verified=True,
                is_active=True
            )
            admin.set_password("admin123")
            
            db.session.add(admin)
            db.session.commit()
            
            logger.info("✅ Default admin created!")
            logger.info("   Username: admin")
            logger.info("   Password: admin123")
            logger.info("   Email: admin@disastershield.com")
            
    except Exception as e:
        logger.warning(f"⚠️ Could not create default admin: {e}")

def check_db_connection():
    """Check if database connection is working"""
    try:
        # Execute a simple query
        from sqlalchemy import text
        result = db.session.execute(text("SELECT 1")).scalar()
        return result == 1
    except Exception as e:
        logger.error(f"❌ Database connection check failed: {e}")
        return False

def get_db_stats():
    """Get database statistics"""
    try:
        from .models import User, RiskPrediction, Alert
        
        stats = {
            'users': User.query.count(),
            'predictions': RiskPrediction.query.count(),
            'alerts': Alert.query.count(),
            'tables': len(db.metadata.tables)
        }
        return stats
    except Exception as e:
        logger.error(f"❌ Error getting DB stats: {e}")
        return {}

def reset_database(app):
    """
    Reset database (drop all tables and recreate)
    USE WITH CAUTION - This will delete all data!
    """
    try:
        logger.warning("⚠️ Resetting database - ALL DATA WILL BE LOST!")
        
        with app.app_context():
            db.drop_all()
            db.create_all()
            logger.info("✅ Database reset successfully!")
            _create_default_admin()
            
        return True
    except Exception as e:
        logger.error(f"❌ Database reset failed: {e}")
        return False

def backup_database(app, backup_path=None):
    """
    Backup database (PostgreSQL pg_dump)
    Requires pg_dump to be installed
    """
    try:
        import subprocess
        import datetime
        
        if not backup_path:
            backup_path = f"backup_disaster_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        
        db_name = os.getenv('DB_NAME', 'disaster_db')
        db_user = os.getenv('DB_USER', 'postgres')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        
        cmd = f"pg_dump -h {db_host} -p {db_port} -U {db_user} -F c -b -v -f {backup_path} {db_name}"
        
        logger.info(f"📤 Backing up database to: {backup_path}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Database backed up successfully to {backup_path}")
            return backup_path
        else:
            logger.error(f"❌ Backup failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Backup error: {e}")
        return None