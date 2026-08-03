import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Use the credentials from your .env file
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'disaster_db'),
        user=os.getenv('DB_USER', 'disaster_user'),  # Changed from 'postgres'
        password=os.getenv('DB_PASSWORD', '0787987255Aa__')
    )
    print("✅ PostgreSQL connection successful!")
    print(f"📁 Connected to: {os.getenv('DB_NAME', 'disaster_db')}")
    print(f"👤 User: {os.getenv('DB_USER', 'disaster_user')}")
    
    # Test query
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"📊 PostgreSQL Version: {version[0][:50]}...")
    
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\n💡 Troubleshooting:")
    print("1. Make sure PostgreSQL is running")
    print("2. Check your .env file has correct credentials")
    print("3. Try connecting with: psql -U disaster_user -d disaster_db")