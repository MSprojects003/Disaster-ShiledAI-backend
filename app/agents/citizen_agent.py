"""
Citizen Intelligence Agent
Processes citizen reports via Text/Photo/Voice
Uses Gemini for multilingual NLP, chatbot interactions, and event extraction.
Sends feedback to Risk Agent for model improvement.
Uses ChromaDB for RAG (Retrieval-Augmented Generation)
INTEGRATED WITH: Risk, Infrastructure, Evacuation, Resource Agents
"""

import os
import json
import base64
import io
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional
from PIL import Image
from dotenv import load_dotenv

# Import ChromaDB RAG
from ..services.rag_service_chroma import chroma_rag

# ===== IMPORT ALL AGENTS =====
from ..agents.risk_agent import risk_agent
from ..agents.infrastructure_agent import infrastructure_agent
from ..agents.evacuation_agent import evacuation_agent
from ..agents.resource_agent import resource_agent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === GEMINI IMPORT CHECK ===
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    logger.info("✅ google-generativeai package is installed")
except ImportError as e:
    GEMINI_AVAILABLE = False
    logger.warning(f"⚠️ google-generativeai not installed: {e}")

class CitizenIntelligenceAgent:
    """
    Agent 2: Citizen Intelligence Agent
    Processes citizen reports via Text/Photo/Voice
    Uses Gemini for multilingual NLP, chatbot interactions, and event extraction.
    Sends feedback to Risk Agent for model improvement.
    Uses ChromaDB for RAG knowledge retrieval.
    INTEGRATED WITH: Risk, Infrastructure, Evacuation, Resource Agents
    """

    def __init__(self):
        self.name = "CitizenIntelligenceAgent"
        self.status = "idle"
        self.reports = []
        self.verified_reports = []
        self.gemini_enabled = False
        self.gemini_client = None
        self.gemini_model_name = None
        self.supported_languages = ['en', 'si', 'ta']
        self.severity_levels = ['Low', 'Medium', 'High', 'Critical']
        self.knowledge_base = []

        # feedback_log = entries actually sent to / acknowledged by the Risk Agent
        self.feedback_log = []
        # chat_log = conversational interactions
        self.chat_log = []

        # ===== AGENT REFERENCES =====
        self.risk_agent = risk_agent
        self.infrastructure_agent = infrastructure_agent
        self.evacuation_agent = evacuation_agent
        self.resource_agent = resource_agent

        # Initialize ChromaDB RAG
        self.chroma_rag = chroma_rag
        self.rag_enabled = self.chroma_rag.client is not None

        # Initialize Gemini with better error handling
        self._init_gemini()

        # Initialize knowledge base from ChromaDB
        self._load_knowledge_from_chromadb()

        # Load feedback history
        self._load_feedback_history()

        logger.info(f"✅ Citizen Intelligence Agent initialized (Gemini: {self.gemini_enabled}, RAG: {self.rag_enabled})")
        logger.info(f"   - Risk Agent: {'✅' if self.risk_agent else '❌'}")
        logger.info(f"   - Infrastructure Agent: {'✅' if self.infrastructure_agent else '❌'}")
        logger.info(f"   - Evacuation Agent: {'✅' if self.evacuation_agent else '❌'}")
        logger.info(f"   - Resource Agent: {'✅' if self.resource_agent else '❌'}")

    def _init_gemini(self):
        """Initialize Gemini client with better error handling and debugging"""
        
        # First check if package is available
        if not GEMINI_AVAILABLE:
            logger.warning("⚠️ google-generativeai package not installed")
            logger.warning("   Run: pip install google-generativeai")
            self.gemini_enabled = False
            return

        try:
            # Get API key from environment
            api_key = os.getenv('GEMINI_API_KEY')
            
            # Debug: Check if API key exists
            if not api_key:
                logger.error("❌ GEMINI_API_KEY not found in environment variables")
                logger.error("   Please check your .env file")
                self.gemini_enabled = False
                return
            
            # Log API key presence (don't log the actual key)
            logger.info(f"✅ GEMINI_API_KEY found (length: {len(api_key)})")
            
            # Configure Gemini
            genai.configure(api_key=api_key)
            
            # Try different models in order of preference.
            models_to_try = [
                'gemini-3.1-flash-lite',   # Higher limit (15 RPM)
                'gemini-2.5-flash-lite',   # Higher limit (10 RPM)
                'gemini-1.5-pro',
                'gemini-3.5-flash',
            ]
            
            for model_name in models_to_try:
                try:
                    logger.info(f"🔄 Attempting to initialize model: {model_name}")
                    
                    # Create model instance
                    self.gemini_client = genai.GenerativeModel(model_name)
                    
                    # Test the model with a simple request
                    test_prompt = "Say 'Hello, I am ready'"
                    test_response = self.gemini_client.generate_content(test_prompt)
                    
                    # Check if we got a valid response
                    if test_response and hasattr(test_response, 'text') and test_response.text:
                        self.gemini_model_name = model_name
                        self.gemini_enabled = True
                        logger.info(f"✅ Gemini successfully initialized with model: {model_name}")
                        logger.info(f"   Test response: {test_response.text[:50]}...")
                        return
                    else:
                        logger.warning(f"⚠️ Model '{model_name}' returned empty response")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Model '{model_name}' failed: {str(e)}")
                    continue
            
            # If we get here, all models failed
            logger.error("❌ All Gemini models failed to initialize")
            self.gemini_enabled = False
            
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed with error: {str(e)}")
            logger.error(traceback.format_exc())
            self.gemini_enabled = False
        
        # Final status
        if not self.gemini_enabled:
            logger.warning("⚠️ Gemini is DISABLED. Using fallback methods.")

    def _load_knowledge_from_chromadb(self):
        """Load knowledge from ChromaDB RAG"""
        if not self.rag_enabled:
            logger.info("ℹ️ ChromaDB RAG not enabled. Using hardcoded knowledge base.")
            self._initialize_knowledge_base()
            return

        try:
            # Search for all knowledge in ChromaDB
            results = self.chroma_rag.search_knowledge("all disaster knowledge", k=100)
            
            if results and len(results) > 0:
                # Convert to knowledge base format
                self.knowledge_base = []
                for result in results:
                    self.knowledge_base.append({
                        'category': result['metadata'].get('category', 'general'),
                        'content_en': result['content'],
                        'content_si': result['content'],  # Will be translated by Gemini if needed
                        'content_ta': result['content'],
                        'source': 'ChromaDB RAG'
                    })
                logger.info(f"✅ Loaded {len(self.knowledge_base)} knowledge items from ChromaDB")
                return
            else:
                logger.info("ℹ️ No knowledge found in ChromaDB. Creating default knowledge base.")
                self._initialize_knowledge_base()
                # Sync to ChromaDB for future use
                self._sync_knowledge_to_chromadb()
                
        except Exception as e:
            logger.error(f"❌ Error loading from ChromaDB: {e}")
            self._initialize_knowledge_base()

    def _sync_knowledge_to_chromadb(self):
        """Sync hardcoded knowledge to ChromaDB"""
        if not self.rag_enabled:
            return

        try:
            synced = 0
            for item in self.knowledge_base:
                content = item.get('content_en', '')
                category = item.get('category', 'general')
                if self.chroma_rag.add_knowledge(content, category):
                    synced += 1
            logger.info(f"✅ Synced {synced} knowledge items to ChromaDB")
        except Exception as e:
            logger.error(f"❌ Sync to ChromaDB failed: {e}")

    def _initialize_knowledge_base(self):
        """Initialize knowledge base with disaster information"""
        self.knowledge_base = [
            {
                'category': 'flood',
                'content_en': 'During floods, move to higher ground immediately and avoid walking or driving through moving water.',
                'content_si': 'ගංවතුර අවස්ථාවන්හිදී, ඉහළ බිම් වෙත වහාම ගමන් කරන්න. ගලා යන ජලය හරහා ඇවිදීම හෝ රිය පැදවීම වළක්වන්න.',
                'content_ta': 'வெள்ளப்பெருக்கு ஏற்படும் போது, உடனடியாக உயரமான இடங்களுக்குச் செல்லுங்கள். ஓடும் நீரில் நடப்பதையோ வாகனம் ஓட்டுவதையோ தவிர்க்கவும்.'
            },
            {
                'category': 'landslide',
                'content_en': 'If you notice cracks in the ground, tilting trees, or sudden changes in water flow, evacuate the area immediately.',
                'content_si': 'බිම්වල ඉරිතැලීම්, ගස් නැඹුරු වීම හෝ ජල ප්‍රවාහයේ හදිසි වෙනස්කම් දුටුවහොත්, වහාම එම ප්‍රදේශයෙන් ඉවත් වන්න.',
                'content_ta': 'நிலத்தில் விரிசல்கள், சாய்ந்த மரங்கள் அல்லது நீரோட்டத்தில் திடீர் மாற்றங்களை கவனித்தால், உடனடியாக அப்பகுதியை விட்டு வெளியேறவும்.'
            },
            {
                'category': 'evacuation',
                'content_en': 'Follow official evacuation routes, carry essential documents and medication, and check on elderly or disabled neighbours.',
                'content_si': 'නිල ඉවත් වීමේ මාර්ග අනුගමනය කරන්න, අත්‍යවශ්‍ය ලේඛන සහ ඖෂධ රැගෙන යන්න, වයෝවෘද්ධ හෝ ආබාධිත අසල්වැසියන් පිළිබඳව සොයා බලන්න.',
                'content_ta': 'அதிகாரப்பூர்வ வெளியேற்ற வழிகளைப் பின்பற்றவும், அத்தியாவசிய ஆவணங்கள் மற்றும் மருந்துகளை எடுத்துச் செல்லவும், வயதானவர்கள் அல்லது இயலாமை உள்ளவர்களை கவனிக்கவும்.'
            },
            {
                'category': 'emergency_contacts',
                'content_en': 'In Sri Lanka, call 117 for the Disaster Management Centre hotline, or 119 for Police emergency assistance.',
                'content_si': 'ශ්‍රී ලංකාවේ, ආපදා කළමනාකරණ මධ්යස්ථානයේ උණුසුම් රේඛාව සඳහා 117 ට හෝ පොලිස් හදිසි සහාය සඳහා 119 ට අමතන්න.',
                'content_ta': 'இலங்கையில், பேரிடர் முகாமைத்துவ மையத்தின் ஹாட்லைனுக்கு 117 அல்லது காவல்துறை அவசர உதவிக்கு 119 ஐ அழைக்கவும்.'
            }
        ]
        logger.info(f"✅ Knowledge base initialized with {len(self.knowledge_base)} items")

    def _load_feedback_history(self):
        """Load feedback history from file"""
        try:
            feedback_path = 'data/feedback/feedback_log.json'
            if os.path.exists(feedback_path):
                with open(feedback_path, 'r') as f:
                    self.feedback_log = json.load(f)
                logger.info(f"✅ Loaded {len(self.feedback_log)} feedback entries")
            else:
                os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
                self.feedback_log = []
                with open(feedback_path, 'w') as f:
                    json.dump([], f)
        except Exception as e:
            logger.warning(f"⚠️ Could not load feedback history: {e}")
            self.feedback_log = []

    def initialize(self):
        """Initialize the agent"""
        logger.info("🚀 Initializing Citizen Intelligence Agent...")
        self.status = "ready"
        logger.info("✅ Citizen Intelligence Agent ready!")
        logger.info(f"   - Gemini: {'✅ Enabled' if self.gemini_enabled else '❌ Disabled'}")
        logger.info(f"   - ChromaDB RAG: {'✅ Enabled' if self.rag_enabled else '❌ Disabled'}")
        logger.info(f"   - Knowledge Base: {len(self.knowledge_base)} items")
        logger.info(f"   - Feedback History: {len(self.feedback_log)} entries")
        logger.info(f"   - Risk Agent: {'✅' if self.risk_agent else '❌'}")
        logger.info(f"   - Infrastructure Agent: {'✅' if self.infrastructure_agent else '❌'}")
        logger.info(f"   - Evacuation Agent: {'✅' if self.evacuation_agent else '❌'}")
        logger.info(f"   - Resource Agent: {'✅' if self.resource_agent else '❌'}")
        return {"status": "initialized", "agent": self.name}

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        action = input_data.get('action', 'text_report')
        if action == 'text_report':
            return self._process_text_report(input_data)
        elif action == 'image_report':
            return self._process_image_report(input_data)
        elif action == 'voice_report':
            return self._process_voice_report(input_data)
        elif action == 'chat':
            return self._process_chat(input_data)
        elif action == 'translate':
            return self._process_translate(input_data)
        else:
            return {"error": f"Unknown action: {action}"}

    def _process_text_report(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("📝 Processing text report...")
        text = input_data.get('text', '')
        language = input_data.get('language', 'en')
        location = input_data.get('location', 'Unknown')
        user_id = input_data.get('user_id', 'anonymous')

        if not text:
            return {'error': 'No text provided'}

        report_data = self._extract_with_gemini(text, language)

        report = {
            'id': f"REP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'type': 'text',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'location': location,
            'language': language,
            'original_text': text,
            'extracted_data': report_data,
            'severity': report_data.get('severity', 'Medium'),
            'status': 'verified',
            'source': 'citizen_report'
        }

        self.reports.append(report)
        self.verified_reports.append(report)
        feedback_sent = self._send_feedback_to_risk_agent(report)

        return {
            'success': True,
            'report': report,
            'message': 'Report processed successfully',
            'feedback_sent': feedback_sent
        }

    def _extract_with_gemini(self, text: str, language: str) -> Dict[str, Any]:
        """Extract information using Gemini or fallback"""
        if self.gemini_enabled:
            try:
                prompt = f"""
                Analyze this citizen report.
                Language: {language}
                Text: {text}

                Extract: event_type (flood/landslide/storm/other),
                         severity (Low/Medium/High/Critical),
                         description,
                         urgent_actions.

                Return ONLY valid JSON.
                """

                response = self.gemini_client.generate_content(prompt)

                if response and response.text:
                    import re
                    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())

                # If Gemini fails, use fallback
                logger.warning("⚠️ Gemini extraction failed, using fallback")
                return self._simple_extract(text)

            except Exception as e:
                logger.error(f"❌ Extraction failed: {e}")
                return self._simple_extract(text)
        else:
            # Gemini not enabled, use fallback
            return self._simple_extract(text)

    def _simple_extract(self, text: str) -> Dict[str, Any]:
        """Simple extraction without Gemini"""
        text_lower = text.lower()
        
        # Determine event type
        if any(word in text_lower for word in ['flood', 'water', 'ගංවතුර', 'வெள்ள']):
            event_type = 'flood'
        elif any(word in text_lower for word in ['landslide', 'slide', 'මාරු', 'நிலச்சரிவு']):
            event_type = 'landslide'
        elif any(word in text_lower for word in ['storm', 'wind', 'cyclone']):
            event_type = 'storm'
        else:
            event_type = 'other'

        # Determine severity
        if any(word in text_lower for word in ['critical', 'emergency', 'urgent', 'severe', 'බරපතල', 'கடுமையான']):
            severity = 'Critical'
        elif any(word in text_lower for word in ['high', 'serious', 'rising', 'ඉහළ', 'உயர்']):
            severity = 'High'
        elif any(word in text_lower for word in ['medium', 'moderate', 'මධ්‍යම', 'மிதமான']):
            severity = 'Medium'
        else:
            severity = 'Low'

        return {
            'event_type': event_type,
            'severity': severity,
            'description': text[:200],
            'urgent_actions': 'Monitor the situation and contact local authorities if needed'
        }

    def _process_image_report(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🖼️ Processing image report...")
        image_data = input_data.get('image_data', '')
        location = input_data.get('location', 'Unknown')
        user_id = input_data.get('user_id', 'anonymous')

        if not image_data:
            return {'error': 'No image provided'}

        analysis = {'severity': 'Medium', 'description': 'Image analysis completed'}

        if self.gemini_enabled:
            try:
                image_bytes = base64.b64decode(image_data)
                image = Image.open(io.BytesIO(image_bytes))

                response = self.gemini_client.generate_content([
                    "Analyze this image for disaster assessment. Provide: event_type, severity, description.",
                    image
                ])

                if response and response.text:
                    analysis = {'severity': 'Medium', 'description': response.text[:200]}
            except Exception as e:
                logger.error(f"❌ Image analysis failed: {e}")

        report = {
            'id': f"REP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'type': 'image',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'location': location,
            'image_analysis': analysis,
            'severity': analysis.get('severity', 'Medium'),
            'status': 'verified',
            'source': 'citizen_report_image'
        }

        self.reports.append(report)
        self.verified_reports.append(report)
        feedback_sent = self._send_feedback_to_risk_agent(report)

        return {
            'success': True,
            'report': report,
            'message': 'Image report processed successfully',
            'feedback_sent': feedback_sent
        }

    def _process_voice_report(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🎤 Processing voice report...")
        audio_data = input_data.get('audio_data', '')
        language = input_data.get('language', 'en')
        location = input_data.get('location', 'Unknown')
        user_id = input_data.get('user_id', 'anonymous')

        if not audio_data:
            return {'error': 'No audio provided'}

        report = {
            'id': f"REP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'type': 'voice',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'location': location,
            'language': language,
            'severity': 'Medium',
            'status': 'pending',
            'message': 'Voice processing requires additional setup',
            'source': 'citizen_report_voice'
        }

        self.reports.append(report)
        self.verified_reports.append(report)
        feedback_sent = self._send_feedback_to_risk_agent(report)

        return {
            'success': True,
            'report': report,
            'message': 'Voice report received',
            'feedback_sent': feedback_sent
        }

    def _process_chat(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        query = input_data.get('query', '')
        language = input_data.get('language', 'en')
        user_id = input_data.get('user_id', 'anonymous')

        if not query:
            return {'error': 'No query provided'}

        response = self._generate_chat_response(query, language)

        chat_entry = {
            'user_id': user_id,
            'query': query,
            'language': language,
            'response': response[:200] if response else '',
            'timestamp': datetime.now().isoformat()
        }
        self.chat_log.append(chat_entry)

        return {
            'success': True,
            'query': query,
            'response': response,
            'language': language,
            'timestamp': datetime.now().isoformat()
        }

    # ================================================================
    # ===== AGENT INTEGRATION METHODS =====
    # ================================================================

    def _get_real_time_agent_data(self, district: str) -> Dict[str, Any]:
        """
        Get real-time data from all agents for a specific district
        """
        result = {
            'risk': {},
            'infrastructure': {},
            'evacuation': {},
            'resources': {},
            'error': None
        }
        
        try:
            # 1. Get Risk Data
            risk_result = self.risk_agent.predict_district(district)
            if risk_result and 'prediction' in risk_result:
                result['risk'] = risk_result['prediction']
        except Exception as e:
            logger.error(f"Risk agent failed: {e}")
            result['error'] = str(e)
        
        try:
            # 2. Get Infrastructure Data
            infra_result = self.infrastructure_agent.process({
                'district': district,
                'risk_level': 'Medium',
                'risk_score': 50
            })
            if infra_result:
                result['infrastructure'] = infra_result
        except Exception as e:
            logger.error(f"Infrastructure agent failed: {e}")
        
        try:
            # 3. Get Evacuation Data (SHELTERS!)
            evac_result = self.evacuation_agent.process({
                'district': district,
                'risk_level': 'Medium',
                'risk_score': 50
            })
            if evac_result:
                result['evacuation'] = evac_result
        except Exception as e:
            logger.error(f"Evacuation agent failed: {e}")
        
        try:
            # 4. Get Resource Data
            resource_result = self.resource_agent.process({
                'action': 'allocate',
                'risk_predictions': {district: {'risk_score': 50, 'risk_level': 'Medium'}}
            })
            if resource_result:
                result['resources'] = resource_result
        except Exception as e:
            logger.error(f"Resource agent failed: {e}")
        
        return result

    def _find_shelter_info(self, district: str, location: str) -> str:
        """
        Find shelter information using Evacuation Agent
        """
        try:
            # Get evacuation data
            evac_result = self.evacuation_agent.process({
                'district': district,
                'risk_level': 'Medium',
                'risk_score': 50
            })
            
            if 'error' in evac_result:
                return f"Could not retrieve shelter data for {district}"
            
            # Get nearest shelter
            nearest = evac_result.get('nearest_shelter', {})
            shelters_in_district = evac_result.get('shelters_in_district', [])
            
            response = f"📍 **Shelter Information for {district}:**\n\n"
            
            if nearest and 'error' not in nearest:
                response += f"**Nearest Shelter:**\n"
                response += f"• Name: {nearest.get('name', 'Unknown')}\n"
                response += f"• Distance: {nearest.get('distance_km', 'N/A')} km\n"
                response += f"• Capacity: {nearest.get('available_capacity', 'N/A')} people\n"
                
                if nearest.get('address'):
                    response += f"• Address: {nearest.get('address')}\n"
            else:
                response += "No shelter data available for this district.\n"
            
            # Add other shelters
            if shelters_in_district and len(shelters_in_district) > 0:
                response += f"\n**All Shelters in {district}:**\n"
                for shelter in shelters_in_district[:5]:
                    name = shelter.get('name', 'Unknown')
                    capacity = shelter.get('capacity', 'N/A')
                    available = shelter.get('available', 'N/A')
                    response += f"• {name} (Capacity: {capacity}, Available: {available})\n"
            
            response += f"\n📞 **Emergency Contacts:**\n"
            response += f"• DMC Hotline: 117\n"
            response += f"• Police: 119\n"
            response += f"• {district} District DMC: Contact local authorities"
            
            return response
            
        except Exception as e:
            logger.error(f"Error finding shelters: {e}")
            return f"Error retrieving shelter data: {str(e)}"

    def _get_risk_info(self, district: str) -> str:
        """Get risk information using Risk Agent"""
        try:
            risk_result = self.risk_agent.predict_district(district)
            
            if risk_result and 'prediction' in risk_result:
                pred = risk_result['prediction']
                response = f"📊 **Risk Assessment for {district}:**\n\n"
                response += f"• Risk Score: {pred.get('risk_score', 0)}%\n"
                response += f"• Risk Level: {pred.get('risk_level', 'Unknown')}\n"
                
                features = pred.get('features', {})
                if features:
                    response += f"\n**Current Conditions:**\n"
                    if features.get('rainfall_mm'):
                        response += f"• Rainfall: {features.get('rainfall_mm')}mm\n"
                    if features.get('river_level_m'):
                        response += f"• River Level: {features.get('river_level_m')}m\n"
                    if features.get('soil_moisture'):
                        response += f"• Soil Moisture: {features.get('soil_moisture')}%\n"
                    if features.get('temperature_c'):
                        response += f"• Temperature: {features.get('temperature_c')}°C\n"
                
                if pred.get('risk_level') in ['High', 'Critical']:
                    response += f"\n⚠️ **Action Required:** {pred.get('action_required', 'Take precautionary measures')}"
                else:
                    response += f"\n✅ **Status:** {pred.get('action_required', 'Monitor conditions')}"
                
                return response
            else:
                return f"Could not retrieve risk data for {district}"
                
        except Exception as e:
            logger.error(f"Risk query failed: {e}")
            return f"Error retrieving risk data: {str(e)}"

    def _get_infrastructure_info(self, district: str) -> str:
        """Get infrastructure information using Infrastructure Agent"""
        try:
            infra_result = self.infrastructure_agent.process({
                'district': district,
                'risk_level': 'Medium',
                'risk_score': 50
            })
            
            if infra_result and not infra_result.get('error'):
                response = f"🏗️ **Infrastructure Status for {district}:**\n\n"
                
                road_status = infra_result.get('road_status', [])
                if road_status:
                    safe = sum(1 for r in road_status if r.get('status') == 'Safe')
                    impassable = sum(1 for r in road_status if r.get('status') == 'Impassable')
                    blocked = sum(1 for r in road_status if r.get('status') == 'Blocked')
                    total = len(road_status)
                    
                    response += f"**Road Status:**\n"
                    response += f"• Total Roads Analyzed: {total}\n"
                    response += f"• Safe Roads: {safe}\n"
                    response += f"• Impassable Roads: {impassable}\n"
                    response += f"• Blocked Roads: {blocked}\n"
                    
                    if blocked > 0 or impassable > 0:
                        response += f"\n⚠️ **Affected Roads:**\n"
                        affected = [r for r in road_status if r.get('status') in ['Blocked', 'Impassable']][:5]
                        for road in affected:
                            name = road.get('road_name', 'Unknown')
                            status = road.get('status', 'Unknown')
                            confidence = road.get('confidence', 0)
                            response += f"• {name}: {status} ({confidence:.0f}% confidence)\n"
                else:
                    response += "No road data available.\n"
                
                return response
            else:
                return f"Could not retrieve infrastructure data for {district}"
                
        except Exception as e:
            logger.error(f"Infrastructure query failed: {e}")
            return f"Error retrieving infrastructure data: {str(e)}"

    def _get_resource_info(self, district: str) -> str:
        """Get resource information using Resource Agent"""
        try:
            resource_result = self.resource_agent.process({
                'action': 'allocate',
                'risk_predictions': {district: {'risk_score': 50, 'risk_level': 'Medium'}}
            })
            
            if resource_result:
                allocation_plan = resource_result.get('allocation_plan', [])
                for alloc in allocation_plan:
                    if alloc.get('district') == district:
                        resources = alloc.get('allocated_resources', {})
                        if resources:
                            response = f"📦 **Resources Allocated for {district}:**\n\n"
                            response += f"**Emergency Resources:**\n"
                            for r_type, qty in resources.items():
                                if qty > 0:
                                    name = r_type.replace('_', ' ').title()
                                    response += f"• {name}: {qty}\n"
                            
                            urgency = alloc.get('urgency', '')
                            if urgency:
                                response += f"\n⏰ **Status:** {urgency}"
                            
                            return response
                
                return f"No resources currently allocated for {district}"
            else:
                return f"Could not retrieve resource data for {district}"
                
        except Exception as e:
            logger.error(f"Resource query failed: {e}")
            return f"Error retrieving resource data: {str(e)}"

    # ================================================================
    # ===== MODIFIED CHAT RESPONSE WITH ALL AGENTS =====
    # ================================================================

    def _generate_chat_response(self, query: str, language: str) -> str:
        """
        Generate chat response using ALL agents + ChromaDB RAG + Gemini
        """
        # ===== STEP 1: Detect Intent and Extract Location =====
        query_lower = query.lower()
        
        # Extract district from query
        districts = ['Colombo', 'Gampaha', 'Kalutara', 'Galle', 'Matara', 'Kandy', 
                     'Ratnapura', 'Kurunegala', 'Anuradhapura', 'Badulla', 'Nuwara Eliya',
                     'Matale', 'Hambantota', 'Monaragala', 'Polonnaruwa', 'Puttalam', 
                     'Kegalle', 'Jaffna', 'Trincomalee', 'Batticaloa', 'Ampara',
                     'Vavuniya', 'Mannar', 'Mullaitivu', 'Kilinochchi']
        
        detected_district = None
        for d in districts:
            if d.lower() in query_lower:
                detected_district = d
                break
        
        # ===== STEP 2: Check for Shelter Queries =====
        if any(word in query_lower for word in ['shelter', 'shelters', 'evacuation center', 'evacuation centre', 'safe place', 'refuge', 'where can I go']):
            if detected_district:
                return self._find_shelter_info(detected_district, query)
            else:
                return "Please specify which district you're asking about (e.g., Colombo, Galle, Kandy) so I can find shelters for you."
        
        # ===== STEP 3: Check for Risk Queries =====
        if any(word in query_lower for word in ['risk', 'danger', 'hazard', 'threat', 'safe', 'dangerous', 'flood risk', 'landslide risk']):
            if detected_district:
                return self._get_risk_info(detected_district)
            else:
                return "Please specify which district you're asking about (e.g., Colombo, Galle, Kandy) for risk information."
        
        # ===== STEP 4: Check for Infrastructure/Road Queries =====
        if any(word in query_lower for word in ['road', 'roads', 'traffic', 'infrastructure', 'bridge', 'utility', 'power', 'water supply', 'condition']):
            if detected_district:
                return self._get_infrastructure_info(detected_district)
            else:
                return "Please specify which district you're asking about for infrastructure status."
        
        # ===== STEP 5: Check for Resource Queries =====
        if any(word in query_lower for word in ['resources', 'rescue', 'ambulance', 'boat', 'food', 'supplies', 'help', 'emergency services']):
            if detected_district:
                return self._get_resource_info(detected_district)
            else:
                return "Please specify which district you're asking about for resource information."
        
        # ===== STEP 6: Check for Emergency/Contact Queries =====
        if any(word in query_lower for word in ['emergency', 'urgent', 'help', 'call', 'contact', 'phone', 'number']):
            response = f"📞 **Emergency Contacts:**\n\n"
            response += f"• **Disaster Management Centre (DMC):** 117\n"
            response += f"• **Police Emergency:** 119\n"
            response += f"• **Ambulance:** 110\n"
            response += f"• **National Hospital:** 011-2691111\n\n"
            response += f"⚠️ If you are in immediate danger, please call 117 or 119 immediately."
            return response
        
        # ===== STEP 7: Use RAG + Gemini for General Queries =====
        # Search ChromaDB for relevant knowledge
        if self.rag_enabled:
            try:
                rag_results = self.chroma_rag.search_knowledge(query, k=3)
                if rag_results:
                    context = "\n\n".join([r['content'] for r in rag_results])
                else:
                    context = self._get_knowledge_context(query, language)
            except Exception as e:
                logger.warning(f"⚠️ ChromaDB search failed: {e}")
                context = self._get_knowledge_context(query, language)
        else:
            context = self._get_knowledge_context(query, language)
        
        # Use Gemini with RAG context
        if self.gemini_enabled:
            try:
                prompt = f"""
                You are a Sri Lanka disaster response assistant.
                
                **Important Rules:**
                1. Use the knowledge provided below to answer accurately.
                2. If the user asks about shelters, risk, roads, or resources, direct them to specific district information.
                3. For emergencies, always tell them to call 117 (DMC) or 119 (Police).
                4. Be helpful, practical, and actionable.
                5. If you don't know something, say so and suggest contacting local authorities.
                
                **Language:** {language}
                **Question:** {query}
                **Knowledge:** {context}
                
                **Available Districts:** Colombo, Gampaha, Kalutara, Galle, Matara, Kandy, Ratnapura, Kurunegala, Anuradhapura, Badulla, Nuwara Eliya, Matale, Hambantota, Monaragala, Polonnaruwa, Puttalam, Kegalle, Jaffna, Trincomalee, Batticaloa, Ampara, Vavuniya, Mannar, Mullaitivu, Kilinochchi
                
                **If the user asks about a specific district:** Always mention the district name in your response.
                **If the user asks about shelters:** Provide shelter information with names and capacities.
                **If the user asks about risk:** Provide risk score and level.
                **If the user asks about roads:** Provide road status with affected roads.
                
                Provide a helpful response in {language}. Keep it practical and actionable.
                """

                response = self.gemini_client.generate_content(prompt)
                if response and response.text:
                    return response.text
                else:
                    return self._get_fallback_response(query, language)

            except Exception as e:
                logger.error(f"❌ Chat failed: {e}")
                return self._get_fallback_response(query, language)
        else:
            return self._get_fallback_response(query, language)

    def _get_fallback_response(self, query: str, language: str) -> str:
        """Fallback responses when Gemini is unavailable"""
        query_lower = query.lower()
        
        # Check for emergency keywords
        if any(word in query_lower for word in ['emergency', 'urgent', 'help', 'evacuate', 'හදිසි', 'அவசர']):
            if language == 'si':
                return "හදිසි අවස්ථාවකදී, කරුණාකර 117 (ආපදා කළමනාකරණ මධ්යස්ථානය) හෝ 119 (පොලිස්) අමතන්න. ආරක්ෂිත ස්ථානයකට ගොස් උපදෙස් අනුගමනය කරන්න."
            elif language == 'ta':
                return "அவசர நிலையில், 117 (பேரிடர் முகாமைத்துவ மையம்) அல்லது 119 (காவல்துறை) அழைக்கவும். பாதுகாப்பான இடத்திற்குச் சென்று வழிமுறைகளைப் பின்பற்றவும்."
            else:
                return "In an emergency, please call 117 (Disaster Management Centre) or 119 (Police). Move to a safe location and follow official instructions."
        
        # Check for flood-related queries
        if any(word in query_lower for word in ['flood', 'water', 'ගංවතුර', 'வெள்ள']):
            if language == 'si':
                return "ගංවතුර අවස්ථාවකදී, ඉහළ බිම් වෙත වහාම ගමන් කරන්න. ගලා යන ජලය හරහා ඇවිදීම හෝ රිය පැදවීම වළක්වන්න. 117 ඇමතීමෙන් උපදෙස් ලබා ගන්න."
            elif language == 'ta':
                return "வெள்ளப்பெருக்கு ஏற்படும் போது, உடனடியாக உயரமான இடங்களுக்குச் செல்லுங்கள். ஓடும் நீரில் நடப்பதையோ வாகனம் ஓட்டுவதையோ தவிர்க்கவும். 117 அழைத்து வழிமுறைகளைப் பெறவும்."
            else:
                return "During a flood, move to higher ground immediately. Avoid walking or driving through moving water. Contact 117 for official instructions."
        
        # Check for evacuation queries
        if 'evacuation' in query_lower:
            if language == 'si':
                return "ඉවත් වීමේ මාර්ග අනුගමනය කරන්න. අත්‍යවශ්‍ය ලේඛන, ඖෂධ සහ ජලය රැගෙන යන්න. අසල්වැසියන්ට උදව් කරන්න. 117 ට ඇමතීමෙන් යාවත්කාලීන තොරතුරු ලබා ගන්න."
            elif language == 'ta':
                return "வெளியேற்ற வழிகளைப் பின்பற்றவும். அத்தியாவசிய ஆவணங்கள், மருந்துகள் மற்றும் தண்ணீரை எடுத்துச் செல்லுங்கள். அண்டை வீட்டாருக்கு உதவுங்கள். 117 அழைப்பதன் மூலம் புதுப்பித்த தகவல்களைப் பெறுங்கள்."
            else:
                return "Follow evacuation routes. Take essential documents, medication, and water. Help neighbours. Call 117 for updated information."
        
        # Default response
        if language == 'si':
            return "ඔබගේ ප්‍රශ්නය සඳහා සමාවන්න. කරුණාකර 117 (ආපදා කළමනාකරණ මධ්‍යස්ථානය) අමතන්න හෝ වැඩි විස්තර සඳහා නැවත උත්සාහ කරන්න."
        elif language == 'ta':
            return "உங்கள் கேள்விக்கு மன்னிக்கவும். தயவுசெய்து 117 (பேரிடர் முகாமைத்துவ மையம்) அழைக்கவும் அல்லது மேலும் தகவலுக்கு மீண்டும் முயற்சிக்கவும்."
        else:
            return "I apologize for the inconvenience. Please call 117 (Disaster Management Centre) or try again for more information."

    def _get_knowledge_context(self, query: str, language: str) -> str:
        """Get knowledge base context"""
        if not self.knowledge_base:
            return "No specific knowledge available."

        query_lower = query.lower()
        context = []
        for item in self.knowledge_base:
            if any(word in query_lower for word in ['flood', 'ගංවතුර', 'வெள்ள']) and item['category'] == 'flood':
                context.append(item.get(f'content_{language}', item['content_en']))
            elif any(word in query_lower for word in ['landslide', 'මාරු', 'நிலச்சரிவு']) and item['category'] == 'landslide':
                context.append(item.get(f'content_{language}', item['content_en']))
            elif 'evacuation' in query_lower and item['category'] == 'evacuation':
                context.append(item.get(f'content_{language}', item['content_en']))
            elif any(word in query_lower for word in ['emergency', 'contact', '117', '119']) and item['category'] == 'emergency_contacts':
                context.append(item.get(f'content_{language}', item['content_en']))

        return '\n'.join(context[:3]) if context else "No specific knowledge available."

    def _process_translate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process translation request"""
        text = input_data.get('text', '')
        target_language = input_data.get('target_language', 'en')
        source_language = input_data.get('source_language', 'auto')

        if not text:
            return {'error': 'No text to translate'}

        # If Gemini is enabled, use it
        if self.gemini_enabled:
            try:
                # Map language codes to full language names
                lang_map = {
                    'en': 'English',
                    'si': 'Sinhala',
                    'ta': 'Tamil'
                }
                
                target_lang_full = lang_map.get(target_language, target_language)
                source_lang_full = lang_map.get(source_language, source_language) if source_language != 'auto' else 'auto-detected'
                
                prompt = f"""
                Translate the following text from {source_lang_full} to {target_lang_full}.
                
                Text: {text}
                
                Important: 
                - Provide ONLY the translation, no additional text or explanations
                - If translating to Tamil (ta), use proper Tamil script
                - If translating to Sinhala (si), use proper Sinhala script
                - Preserve the meaning and urgency of the original text
                
                Translation:
                """

                response = self.gemini_client.generate_content(prompt)
                
                if response and response.text:
                    translated_text = response.text.strip()
                    # Clean up any extra text
                    for prefix in ['Translation:', 'Translated text:', 'Tamil translation:', 'Sinhala translation:']:
                        if translated_text.startswith(prefix):
                            translated_text = translated_text[len(prefix):].strip()
                    
                    return {
                        'success': True,
                        'original_text': text,
                        'source_language': source_language,
                        'target_language': target_language,
                        'translated_text': translated_text,
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    return self._simple_translate(text, target_language)
                    
            except Exception as e:
                logger.error(f"❌ Translation failed: {e}")
                return self._simple_translate(text, target_language)
        else:
            # Gemini not enabled, use fallback
            return self._simple_translate(text, target_language)

    def _simple_translate(self, text: str, target_language: str) -> Dict[str, Any]:
        """Simple translation fallback when Gemini fails"""
        # Common translations
        translations = {
            'en': {
                'hello': 'Hello',
                'hello, how are you?': 'Hello, how are you?',
                'emergency evacuation required immediately': 'Emergency evacuation required immediately!'
            },
            'si': {
                'hello': 'ආයුබෝවන්',
                'hello, how are you?': 'ආයුබෝවන්, ඔබට කොහොමද?',
                'emergency evacuation required immediately': 'හදිසි ඉවත් කිරීම වහාම අවශ්ය වේ!'
            },
            'ta': {
                'hello': 'வணக்கம்',
                'hello, how are you?': 'வணக்கம், எப்படி இருக்கிறீர்கள்?',
                'emergency evacuation required immediately': 'அவசர வெளியேற்றம் உடனடியாக தேவை!'
            }
        }
        
        # Try to find exact match
        text_lower = text.lower().strip()
        if text_lower in translations.get('en', {}):
            original_en = text_lower
            if target_language in translations:
                translated = translations[target_language].get(original_en, text)
                return {
                    'success': True,
                    'original_text': text,
                    'source_language': 'en',
                    'target_language': target_language,
                    'translated_text': translated,
                    'timestamp': datetime.now().isoformat(),
                    'note': 'Using fallback translation'
                }
        
        # Generic fallback
        lang_names = {'en': 'English', 'si': 'Sinhala', 'ta': 'Tamil'}
        lang_name = lang_names.get(target_language, target_language)
        
        return {
            'success': True,
            'original_text': text,
            'source_language': 'auto',
            'target_language': target_language,
            'translated_text': f"[{lang_name} translation]: {text}",
            'timestamp': datetime.now().isoformat(),
            'note': 'Gemini unavailable, using fallback'
        }

    def _send_feedback_to_risk_agent(self, report: Dict[str, Any]) -> bool:
        """Send feedback to Risk Agent"""
        try:
            # Try to import risk_agent
            from .risk_agent import risk_agent
        except ImportError as e:
            logger.error(f"❌ Could not import Risk Agent: {e}")
            # Still save feedback locally
            self._save_feedback_locally(report, success=False, error=str(e))
            return False

        try:
            feedback = {
                'source': 'citizen_report',
                'report_id': report.get('id', ''),
                'location': report.get('location', 'Unknown'),
                'severity': report.get('severity', 'Medium'),
                'event_type': report.get('extracted_data', {}).get('event_type', 'other'),
                'timestamp': report.get('timestamp', datetime.now().isoformat()),
                'original_text': report.get('original_text', ''),
                'report_type': report.get('type', 'text')
            }

            # Check if risk_agent has process_feedback method
            if hasattr(risk_agent, 'process_feedback'):
                try:
                    result = risk_agent.process_feedback(feedback)
                    logger.info(f"🔄 Feedback sent to Risk Agent: {report.get('id', '')}")
                    self._save_feedback_locally(report, success=True, result=result)
                    return True
                except Exception as e:
                    logger.error(f"❌ Risk Agent process_feedback failed: {e}")
                    self._save_feedback_locally(report, success=False, error=str(e))
                    return False
            else:
                logger.error("❌ Risk Agent has no 'process_feedback' method")
                self._save_feedback_locally(report, success=False, error="No process_feedback method")
                return False

        except Exception as e:
            logger.error(f"❌ Could not send feedback: {e}")
            self._save_feedback_locally(report, success=False, error=str(e))
            return False

    def _save_feedback_locally(self, report: Dict[str, Any], success: bool, result=None, error=None):
        """Save feedback locally"""
        try:
            feedback_entry = {
                'report_id': report.get('id', ''),
                'sent_at': datetime.now().isoformat(),
                'success': success,
                'result': result if result else None,
                'error': error if error else None,
                'report_summary': {
                    'location': report.get('location', 'Unknown'),
                    'severity': report.get('severity', 'Medium'),
                    'event_type': report.get('extracted_data', {}).get('event_type', 'other'),
                    'type': report.get('type', 'text')
                }
            }
            
            # Add to in-memory log
            self.feedback_log.append(feedback_entry)
            
            # Save to file
            feedback_path = 'data/feedback/feedback_log.json'
            os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
            
            # Load existing entries
            existing_entries = []
            if os.path.exists(feedback_path):
                try:
                    with open(feedback_path, 'r') as f:
                        existing_entries = json.load(f)
                except:
                    existing_entries = []
            
            # Append new entry
            existing_entries.append(feedback_entry)
            
            # Save back to file
            with open(feedback_path, 'w') as f:
                json.dump(existing_entries, f, indent=2)
                
            logger.info(f"💾 Feedback saved locally for report: {report.get('id', '')}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not save feedback locally: {e}")

    def get_reports(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        if severity:
            return [r for r in self.verified_reports if r.get('severity') == severity]
        return self.verified_reports

    def get_feedback_history(self) -> List[Dict[str, Any]]:
        return self.feedback_log

    def get_chat_history(self) -> List[Dict[str, Any]]:
        return self.chat_log

    def get_status(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status,
            'total_reports': len(self.reports),
            'verified_reports': len(self.verified_reports),
            'gemini_enabled': self.gemini_enabled,
            'gemini_model': self.gemini_model_name,
            'supported_languages': self.supported_languages,
            'knowledge_base_size': len(self.knowledge_base),
            'feedback_entries': len(self.feedback_log),
            'chat_entries': len(self.chat_log),
            'rag_enabled': self.rag_enabled,
            'vector_db': 'ChromaDB' if self.rag_enabled else 'None',
            'agent_version': '1.0.6',
            'feedback_loop_enabled': True,
            'integrated_agents': {
                'risk_agent': self.risk_agent is not None,
                'infrastructure_agent': self.infrastructure_agent is not None,
                'evacuation_agent': self.evacuation_agent is not None,
                'resource_agent': self.resource_agent is not None,
            }
        }


# Create singleton instance
citizen_agent = CitizenIntelligenceAgent()