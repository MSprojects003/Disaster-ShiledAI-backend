"""
Script to clear all users from the database
Run: python clear_users.py
"""

import sys
import os

# Add the project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.db import db
from app.database.models import User, Alert, RiskPrediction, DistrictRiskHistory, UserPreference, Feedback, NotificationLog
from app import create_app

def clear_all_users():
    """Delete all users and related data"""
    app = create_app('default')
    
    with app.app_context():
        print("🗑️ Clearing all users and related data...")
        
        # Delete in correct order (child tables first)
        
        # 1. Delete Notification Logs (related to alerts and users)
        print("   📋 Deleting notification logs...")
        NotificationLog.query.delete()
        
        # 2. Delete Feedback (related to users and predictions)
        print("   📋 Deleting feedback...")
        Feedback.query.delete()
        
        # 3. Delete User Preferences (related to users)
        print("   📋 Deleting user preferences...")
        UserPreference.query.delete()
        
        # 4. Delete Alerts (related to users)
        print("   📋 Deleting alerts...")
        Alert.query.delete()
        
        # 5. Delete Risk Predictions (related to users)
        print("   📋 Deleting risk predictions...")
        RiskPrediction.query.delete()
        
        # 6. Delete District Risk History (related to users)
        print("   📋 Deleting district risk history...")
        DistrictRiskHistory.query.delete()
        
        # 7. Finally, delete Users
        print("   📋 Deleting users...")
        User.query.delete()
        
        # Commit all changes
        db.session.commit()
        
        print("✅ All users and related data cleared successfully!")
        
        # Verify
        user_count = User.query.count()
        print(f"📊 Remaining users: {user_count}")

if __name__ == "__main__":
    clear_all_users()