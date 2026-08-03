from app import create_app
import os

from app.scheduler import start_scheduler

app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting Disaster-ShieldAI")
    print("📍 Risk Prediction Agent")
    print("=" * 60)
    print(f"📊 API available at: http://localhost:5000")
    print(f"📡 Health check: http://localhost:5000/health")
    print(f"📈 Predict all: http://localhost:5000/api/risk/predict-all")
    print(f"🗄️  Database: PostgreSQL (disaster_db)")
    print("=" * 60)
    
    # Run the app
     
    scheduler = start_scheduler(app)

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=True,
            use_reloader=False
        )
    finally:
        scheduler.shutdown()

    app.run(host='0.0.0.0', port=5000, debug=True)