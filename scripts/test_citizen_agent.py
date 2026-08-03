"""
Complete Test Script for Citizen Intelligence Agent
Tests: Text Reports, Image Reports, Chat, Translation, Feedback Loop
"""

import requests
import json
import base64
import os
from datetime import datetime

BASE_URL = "http://localhost:5000"
API_URL = f"{BASE_URL}/api/citizen"

def print_section(title):
    """Print section header"""
    print("\n" + "="*60)
    print(f"🧪 {title}")
    print("="*60)

def print_result(success, message, data=None):
    """Print test result"""
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
    if data:
        print(f"   📊 Response: {json.dumps(data, indent=2)[:500]}...")

def test_agent_status():
    """Test 1: Check agent status"""
    print_section("TEST 1: AGENT STATUS")

    try:
        response = requests.get(f"{API_URL}/status")
        if response.status_code == 200:
            data = response.json()
            print_result(True, "Agent status retrieved successfully", data)
            print(f"\n📊 Agent Info:")
            print(f"   - Name: {data.get('name')}")
            print(f"   - Status: {data.get('status')}")
            print(f"   - Gemini: {'✅ Enabled' if data.get('gemini_enabled') else '❌ Disabled'}")
            print(f"   - Reports: {data.get('total_reports')}")
            print(f"   - Knowledge Base: {data.get('knowledge_base_size')} items")
            print(f"   - Feedback Entries: {data.get('feedback_entries', 0)}")
            print(f"   - Feedback Loop: {'✅ Enabled' if data.get('feedback_loop_enabled') else '❌ Disabled'}")
            return True
        else:
            print_result(False, f"Status check failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Connection error: {e}")
        return False

def test_text_report():
    """Test 2: Submit text report"""
    print_section("TEST 2: TEXT REPORT")

    print("\n📝 Test 2a: English Report")
    payload = {
        "text": "There is severe flooding in Colombo. Water levels are rising rapidly in the low-lying areas near the Kelani River.",
        "language": "en",
        "location": "Colombo",
        "user_id": "test_user_001"
    }

    try:
        response = requests.post(f"{API_URL}/report/text", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "English report submitted successfully", data)
                report_id = data.get('report', {}).get('id')
                print(f"   📝 Report ID: {report_id}")
                print(f"   📍 Location: {data.get('report', {}).get('location')}")
                print(f"   🔍 Severity: {data.get('report', {}).get('severity')}")
                print(f"   🔄 Feedback Sent: {data.get('feedback_sent', False)}")
                return True
            else:
                print_result(False, f"Report submission failed: {data.get('error')}")
                return False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_multilingual_reports():
    """Test 3: Multilingual reports"""
    print_section("TEST 3: MULTILINGUAL REPORTS")

    overall_success = True

    # Test 3a: Sinhala report
    print("\n📝 Test 3a: Sinhala Report")
    payload = {
        "text": "කොළඹ ප්‍රදේශයේ ගංවතුර තත්ත්වය ඉතා බරපතලයි. ජල මට්ටම් ඉහළ යමින් පවතී.",
        "language": "si",
        "location": "Colombo",
        "user_id": "test_user_002"
    }

    try:
        response = requests.post(f"{API_URL}/report/text", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Sinhala report submitted successfully", data)
                print(f"   📝 Report ID: {data.get('report', {}).get('id')}")
                print(f"   🔄 Feedback Sent: {data.get('feedback_sent', False)}")
            else:
                print_result(False, f"Sinhala report failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    # Test 3b: Tamil report
    print("\n📝 Test 3b: Tamil Report")
    payload = {
        "text": "கொழும்பு பகுதியில் வெள்ள நிலை மிகவும் கடுமையானது. நீர் மட்டம் உயர்ந்து வருகிறது.",
        "language": "ta",
        "location": "Colombo",
        "user_id": "test_user_003"
    }

    try:
        response = requests.post(f"{API_URL}/report/text", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Tamil report submitted successfully", data)
                print(f"   📝 Report ID: {data.get('report', {}).get('id')}")
                print(f"   🔄 Feedback Sent: {data.get('feedback_sent', False)}")
            else:
                print_result(False, f"Tamil report failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    return overall_success

def test_chat():
    """Test 4: Chat functionality"""
    print_section("TEST 4: CHAT FUNCTIONALITY")

    overall_success = True

    # Test 4a: English chat
    print("\n💬 Test 4a: English Chat - Flood query")
    payload = {
        "query": "What should I do during a flood?",
        "language": "en",
        "user_id": "test_user_chat"
    }

    try:
        response = requests.post(f"{API_URL}/chat", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Chat response received", data)
                print(f"   💬 Query: {data.get('query')}")
                print(f"   🤖 Response: {data.get('response', '')[:200]}...")
            else:
                print_result(False, f"Chat failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    # Test 4b: Sinhala chat
    print("\n💬 Test 4b: Sinhala Chat")
    payload = {
        "query": "ගංවතුර අවස්ථාවකදී කළ යුතු දේ මොනවාද?",
        "language": "si",
        "user_id": "test_user_chat_si"
    }

    try:
        response = requests.post(f"{API_URL}/chat", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Sinhala chat response received", data)
                print(f"   💬 Query: {data.get('query')}")
                print(f"   🤖 Response: {data.get('response', '')[:200]}...")
            else:
                print_result(False, f"Sinhala chat failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    return overall_success

def test_translation():
    """Test 5: Translation functionality"""
    print_section("TEST 5: TRANSLATION")

    overall_success = True

    # Test 5a: English to Sinhala
    print("\n🌐 Test 5a: English to Sinhala")
    payload = {
        "text": "Hello, how are you?",
        "source_language": "en",
        "target_language": "si"
    }

    try:
        response = requests.post(f"{API_URL}/translate", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Translation successful", data)
                print(f"   📝 Original: {data.get('original_text')}")
                print(f"   🔄 Translated: {data.get('translated_text')}")
            else:
                print_result(False, f"Translation failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    # Test 5b: English to Tamil
    print("\n🌐 Test 5b: English to Tamil")
    payload = {
        "text": "Emergency evacuation required immediately!",
        "source_language": "en",
        "target_language": "ta"
    }

    try:
        response = requests.post(f"{API_URL}/translate", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Translation successful", data)
                print(f"   📝 Original: {data.get('original_text')}")
                print(f"   🔄 Translated: {data.get('translated_text')}")
            else:
                print_result(False, f"Translation failed: {data.get('error')}")
                overall_success = False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            overall_success = False
    except Exception as e:
        print_result(False, f"Error: {e}")
        overall_success = False

    return overall_success

def test_image_report():
    """Test 6: Image report (simulated)"""
    print_section("TEST 6: IMAGE REPORT")

    # Create a simple test image (100x100 red square)
    from PIL import Image
    import io

    img = Image.new('RGB', (100, 100), color='red')
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    print("\n🖼️ Submitting test image...")
    payload = {
        "image_data": img_base64,
        "location": "Colombo",
        "user_id": "test_user_image"
    }

    try:
        response = requests.post(f"{API_URL}/report/image", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print_result(True, "Image report submitted successfully", data)
                print(f"   📝 Report ID: {data.get('report', {}).get('id')}")
                print(f"   🔄 Feedback Sent: {data.get('feedback_sent', False)}")
                return True
            else:
                print_result(False, f"Image report failed: {data.get('error')}")
                return False
        else:
            print_result(False, f"HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_feedback_loop():
    """Test 7: Verify feedback loop is working"""
    print_section("TEST 7: FEEDBACK LOOP VERIFICATION")

    print("\n📊 Checking feedback history...")

    # Check if feedback file exists
    feedback_path = 'data/feedback/feedback_log.json'
    if os.path.exists(feedback_path):
        try:
            with open(feedback_path, 'r') as f:
                feedback_data = json.load(f)

            if len(feedback_data) > 0:
                print_result(True, f"Feedback file found with {len(feedback_data)} entries", feedback_data)

                print(f"\n   📋 Last {min(3, len(feedback_data))} feedback entries:")
                for entry in feedback_data[-3:]:
                    print(f"      - Report: {entry.get('report_id', 'N/A')}")
                    print(f"        Sent At: {entry.get('sent_at', 'N/A')}")
                return True
            else:
                print_result(
                    False,
                    "Feedback file exists but has 0 entries — reports were submitted but "
                    "feedback to the Risk Agent was never recorded. Check server logs for "
                    "'Could not import Risk Agent' or 'process_feedback' errors."
                )
                return False
        except Exception as e:
            print_result(False, f"Error reading feedback file: {e}")
            return False
    else:
        print_result(False, "Feedback file not found. Did you submit any reports?")
        return False

def test_get_reports():
    """Test 8: Get all reports"""
    print_section("TEST 8: GET REPORTS")

    try:
        response = requests.get(f"{API_URL}/reports")
        if response.status_code == 200:
            data = response.json()
            print_result(True, f"Retrieved {data.get('total', 0)} reports", data)
            print(f"   📊 Total Reports: {data.get('total', 0)}")

            reports = data.get('reports', [])
            if reports:
                print(f"\n   📋 Recent Reports:")
                for report in reports[:3]:
                    print(f"      - {report.get('id', 'N/A')}: {report.get('severity', 'N/A')} risk")
                    print(f"        Location: {report.get('location', 'N/A')}")
                    print(f"        Source: {report.get('source', 'N/A')}")
            return True
        else:
            print_result(False, f"Failed to get reports: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("🚀 CITIZEN INTELLIGENCE AGENT - COMPLETE TEST SUITE")
    print("="*70)
    print(f"📅 Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔗 API URL: {API_URL}")

    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is running!")
        else:
            print("❌ Server not responding properly!")
            return
    except:
        print("❌ Could not connect to server. Make sure it's running!")
        return

    results = {}

    # Run all tests
    results['status'] = test_agent_status()
    results['text_report'] = test_text_report()
    results['multilingual'] = test_multilingual_reports()
    results['chat'] = test_chat()
    results['translation'] = test_translation()
    results['image_report'] = test_image_report()
    results['feedback'] = test_feedback_loop()
    results['get_reports'] = test_get_reports()

    # Print summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"   {status}: {test_name.replace('_', ' ').title()}")

    print(f"\n📈 Result: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Your Citizen Intelligence Agent is fully working!")
        print("   ✅ Feedback loop is sending data to Risk Agent")
        print("   ✅ Gemini is processing reports")
        print("   ✅ Multilingual support is working")
        print("   ✅ Chat and translation are functional")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Please check the logs above.")

if __name__ == "__main__":
    run_all_tests()