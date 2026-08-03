import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_risk_agent():
    print("\n" + "="*50)
    print("🌤️ TESTING RISK PREDICTION AGENT")
    print("="*50)
    
    # Test districts
    response = requests.get(f"{BASE_URL}/api/risk/districts")
    print(f"✅ Districts: {response.json()['count']} districts")
    
    # Test predict Colombo
    response = requests.get(f"{BASE_URL}/api/risk/predict/Colombo")
    data = response.json()
    print(f"✅ Colombo Risk: {data.get('prediction', {}).get('risk_level', 'N/A')} ({data.get('prediction', {}).get('risk_score', 0)}%)")
    
    # Test predict all
    response = requests.get(f"{BASE_URL}/api/risk/predict-all")
    data = response.json()
    print(f"✅ All districts: {data.get('total', 0)} predictions")

def test_infrastructure_agent():
    print("\n" + "="*50)
    print("🏗️ TESTING INFRASTRUCTURE AGENT")
    print("="*50)
    
    # Test analyze
    response = requests.get(f"{BASE_URL}/api/infrastructure/analyze/Colombo")
    data = response.json()
    print(f"✅ Infrastructure analysis: {data.get('total_roads_analyzed', 0)} roads analyzed")
    print(f"   Blocked: {data.get('blocked_roads', 0)}")
    print(f"   Normal: {data.get('normal_roads', 0)}")
    
    # Test status
    response = requests.get(f"{BASE_URL}/api/infrastructure/status")
    data = response.json()
    print(f"✅ Agent status: {data.get('status', 'N/A')}")
    print(f"   Roads monitored: {data.get('roads_monitored', 0)}")

def test_evacuation_agent():
    print("\n" + "="*50)
    print("🚗 TESTING EVACUATION AGENT")
    print("="*50)
    
    # Test shelters
    response = requests.get(f"{BASE_URL}/api/evacuation/shelters/Gampaha")
    data = response.json()
    print(f"✅ Shelters in Gampaha: {data.get('total_shelters', 0)}")
    
    # Test plan
    response = requests.get(f"{BASE_URL}/api/evacuation/plan/Colombo?lat=6.9271&lon=79.8612")
    data = response.json()
    print(f"✅ Evacuation plan: {data.get('nearest_shelter', {}).get('name', 'N/A')}")
    
    # Test status
    response = requests.get(f"{BASE_URL}/api/evacuation/status")
    data = response.json()
    print(f"✅ Agent status: {data.get('status', 'N/A')}")
    print(f"   Shelters: {data.get('shelters_available', 0)}")

def test_citizen_agent():
    print("\n" + "="*50)
    print("💬 TESTING CITIZEN INTELLIGENCE AGENT")
    print("="*50)
    
    # Test text report
    payload = {"text": "Severe flooding in Colombo", "language": "en", "location": "Colombo"}
    response = requests.post(f"{BASE_URL}/api/citizen/report/text", json=payload)
    data = response.json()
    print(f"✅ Report submitted: {data.get('success', False)}")
    if data.get('success'):
        print(f"   Report ID: {data.get('report', {}).get('id', 'N/A')}")
    
    # Test chat
    payload = {"query": "What should I do during a flood?", "language": "en"}
    response = requests.post(f"{BASE_URL}/api/citizen/chat", json=payload)
    data = response.json()
    print(f"✅ Chat response: {data.get('response', 'N/A')[:50]}...")
    
    # Test status
    response = requests.get(f"{BASE_URL}/api/citizen/status")
    data = response.json()
    print(f"✅ Agent status: {data.get('status', 'N/A')}")
    print(f"   Reports: {data.get('total_reports', 0)}")

def test_resource_agent():
    print("\n" + "="*50)
    print("📊 TESTING RESOURCE ALLOCATION AGENT")
    print("="*50)
    
    # Test allocate
    response = requests.post(f"{BASE_URL}/api/resource/allocate")
    data = response.json()
    print(f"✅ Resource allocation: {data.get('total_districts', 0)} districts")
    print(f"   Resources used: {sum(data.get('resources_used', {}).values())}")
    
    # Test Gemini analyze
    payload = {"district": "Colombo", "risk_score": 85, "risk_level": "High"}
    response = requests.post(f"{BASE_URL}/api/resource/gemini-analyze", json=payload)
    data = response.json()
    if data.get('success'):
        print(f"✅ Gemini analysis: {len(data.get('analysis', {}).get('recommendations', []))} recommendations")
    else:
        print(f"⚠️ Gemini: {data.get('error', 'Unknown error')}")
    
    # Test historical summary
    response = requests.get(f"{BASE_URL}/api/resource/historical-summary")
    data = response.json()
    print(f"✅ Historical data: {data.get('total_historical_events', 0):,} events")
    print(f"   Districts: {data.get('districts_with_data', 0)}")
    
    # Test status
    response = requests.get(f"{BASE_URL}/api/resource/status")
    data = response.json()
    print(f"✅ Agent status: {data.get('status', 'N/A')}")
    print(f"   Utilization: {data.get('summary', {}).get('utilization_percentage', 0)}%")

def main():
    print("="*60)
    print("🧪 DISASTER-SHIELD AI - COMPLETE SYSTEM TEST")
    print("="*60)
    
    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is running!")
        else:
            print("❌ Server not responding!")
            return
    except:
        print("❌ Could not connect to server. Make sure it's running!")
        return
    
    test_risk_agent()
    test_infrastructure_agent()
    test_evacuation_agent()
    test_citizen_agent()
    test_resource_agent()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETE!")
    print("="*60)
    print("\n📊 Summary:")
    print("   - Risk Prediction: Predicts flood/landslide risk")
    print("   - Infrastructure: Analyzes 335,419 roads")
    print("   - Evacuation: Plans routes to 34 shelters")
    print("   - Citizen Intelligence: Processes reports + Gemini")
    print("   - Resource: Allocates resources using DesInventar data")

if __name__ == "__main__":
    main()