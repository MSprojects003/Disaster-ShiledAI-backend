"""
LangChain Agent Orchestrator
Coordinates all agents using tool calling and RAG

Rewritten for langchain>=1.0 / langchain-core>=1.5 / langchain-google-genai>=4.x
The old AgentExecutor + create_tool_calling_agent + ConversationBufferMemory
API no longer exists in modern langchain. It's replaced by:
  - langchain.agents.create_agent()  -> returns a compiled LangGraph graph
  - invoke with {"messages": [...]}  -> returns {"messages": [...]}
  - conversation memory via a checkpointer + thread_id, instead of a
    Memory object passed into the executor
"""

import os
import logging
import traceback
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv

try:
    from langchain.agents import create_agent
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.checkpoint.memory import InMemorySaver
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    print(f"⚠️ LangChain import error: {e}")

from .tools import (
    RiskPredictionTool,
    InfrastructureTool,
    EvacuationTool,
    ResourceAllocationTool,
    CitizenChatTool,
    RAGTool
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Disaster-Shield AI, a Sri Lanka disaster response coordinator.
You have access to multiple tools to help citizens and authorities.

Tools available:
- risk_prediction: Predict flood/landslide risk for a district
- infrastructure_analysis: Check road and bridge conditions
- evacuation_planning: Plan safest evacuation routes
- resource_allocation: Allocate emergency resources
- citizen_assistant: Answer disaster-related questions
- knowledge_retrieval: Search disaster knowledge base

When responding:
1. For general disaster knowledge, use knowledge_retrieval first
2. For specific district information, use the relevant tools
3. Combine tools when needed (e.g., risk + infrastructure + evacuation)
4. Always provide clear, actionable recommendations
5. If you don't know something, say so honestly
6. Keep responses concise and helpful
"""


class AgentOrchestrator:
    """
    LangChain Agent Orchestrator (langchain 1.x / LangGraph based)
    Coordinates multi-agent system with tool calling and RAG
    """

    def __init__(self):
        self.llm = None
        self.llm_model_name = None
        self.llm_is_thinking_model = False
        self.agent = None  # compiled LangGraph graph (replaces agent_executor)
        self.checkpointer = None
        self.tools = []
        self.initialized = False
        self.error_message = None

        if not LANGCHAIN_AVAILABLE:
            logger.warning("⚠️ LangChain not available. Orchestrator disabled.")
            self.error_message = "LangChain not installed"
            return

        try:
            self._init_memory()
            self._init_llm()
            self._init_tools()
            self._init_agent()
            self.initialized = self.agent is not None
            logger.info(f"✅ Agent Orchestrator initialized (status: {self.initialized})")
        except Exception as e:
            logger.error(f"❌ Orchestrator initialization failed: {e}", exc_info=True)
            self.error_message = str(e)
            self.initialized = False
            traceback.print_exc()

    def _init_memory(self):
        """Initialize conversation memory (checkpointer, replaces ConversationBufferMemory)"""
        try:
            self.checkpointer = InMemorySaver()
            logger.info("✅ Memory (checkpointer) initialized")
        except Exception as e:
            logger.warning(f"⚠️ Memory initialization failed: {e}")
            self.checkpointer = None

    def _init_llm(self):
        """Initialize Gemini LLM"""
        try:
            if not LANGCHAIN_AVAILABLE:
                return

            api_key = os.getenv('GEMINI_API_KEY', '')
            if not api_key:
                logger.warning("⚠️ No Gemini API key found")
                self.error_message = "No GEMINI_API_KEY set"
                return

            # Order matters: first match wins. Put known-good models first.
            models = [
                'gemini-3.1-flash-lite',   # Higher limit (15 RPM)
                'gemini-2.5-flash-lite',   # Higher limit (10 RPM)
                'gemini-3.5-flash',
                'gemini-1.5-pro',          # Last resort - verify this still exists for your key
            ]

            for model_name in models:
                try:
                    candidate = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.3,
                        max_retries=0,
                        disable_streaming=True,
                    )
                    test_response = candidate.invoke("Say hello")
                    if test_response:
                        self.llm = candidate
                        self.llm_model_name = model_name
                        self.llm_is_thinking_model = model_name.startswith('gemini-3')
                        logger.info(f"✅ LLM initialized with model: {model_name}")
                        return
                except Exception as e:
                    logger.warning(f"⚠️ Model '{model_name}' failed: {e}")
                    continue

            logger.error("❌ All LLM models failed")
            self.error_message = "All LLM models failed"

        except Exception as e:
            logger.error(f"❌ LLM initialization failed: {e}", exc_info=True)
            self.error_message = str(e)

    def _init_tools(self):
        """Initialize all LangChain tools"""
        try:
            self.tools = [
                RiskPredictionTool(),
                InfrastructureTool(),
                EvacuationTool(),
                ResourceAllocationTool(),
                CitizenChatTool(),
                RAGTool()
            ]
            logger.info(f"✅ Loaded {len(self.tools)} tools: {[t.name for t in self.tools]}")
        except Exception as e:
            logger.error(f"❌ Tool initialization failed: {e}", exc_info=True)
            self.tools = []
            self.error_message = f"Tools error: {e}"

    def _init_agent(self):
        """Initialize the LangGraph agent (replaces AgentExecutor)"""
        if not self.llm:
            logger.warning("⚠️ No LLM available. Agent disabled.")
            return

        if not self.tools:
            logger.warning("⚠️ No tools available. Agent disabled.")
            return

        try:
            self.agent = create_agent(
                model=self.llm,
                tools=self.tools,
                system_prompt=SYSTEM_PROMPT,
                checkpointer=self.checkpointer,
            )
            logger.info("✅ Agent initialized with tool calling (LangGraph)")

        except Exception as e:
            logger.error(f"❌ Agent initialization failed: {e}", exc_info=True)
            self.error_message = f"Agent error: {e}"
            traceback.print_exc()

    def process(self, query: str, language: str = "en", user_id: str = "anonymous") -> Dict[str, Any]:
        """
        Process user query through the orchestrator
        """
        if not self.initialized:
            return {
                'success': False,
                'error': self.error_message or 'Agent not initialized',
                'response': 'System is currently unavailable. Please try again later.',
                'details': {
                    'langchain_available': LANGCHAIN_AVAILABLE,
                    'llm_available': self.llm is not None,
                    'agent_available': self.agent is not None
                }
            }

        try:
            if language != 'en':
                query = f"[Language: {language}] {query}"

            logger.info(f"📝 Processing query: {query[:100]}...")

            # thread_id ties this call to a conversation for the checkpointer,
            # so the agent remembers prior turns for this user
            config = {"configurable": {"thread_id": user_id}}

            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": query}]},
                config=config,
            )

            messages = result.get("messages", [])
            final_text = messages[-1].content if messages else "No response"

            # Reconstruct a rough equivalent of "intermediate_steps" from the
            # message list (tool calls + tool results), for compatibility
            # with any code downstream that inspected agent_thoughts.
            agent_thoughts = [
                {
                    "type": type(m).__name__,
                    "content": getattr(m, "content", None),
                    "tool_calls": getattr(m, "tool_calls", None),
                }
                for m in messages
            ]

            return {
                'success': True,
                'response': final_text,
                'agent_thoughts': agent_thoughts,
                'language': language,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Processing error: {e}", exc_info=True)
            traceback.print_exc()

            error_str = str(e)
            if 'thought_signature' in error_str:
                return {
                    'success': False,
                    'error': error_str,
                    'error_type': type(e).__name__,
                    'known_issue': True,
                    'response': (
                        f"This query needed multiple tool calls in one reasoning step, "
                        f"which the current model ('{self.llm_model_name}') doesn't support "
                        f"reliably in this system yet. Try rephrasing as a simpler, single-part "
                        f"question, or try again — a different model may be selected on retry."
                    )
                }

            return {
                'success': False,
                'error': error_str,
                'error_type': type(e).__name__,
                'response': 'An error occurred while processing your request. Please try again.'
            }

    def process_with_rag(self, query: str, language: str = "en") -> Dict[str, Any]:
        """
        Process query with RAG-enhanced context
        """
        try:
            from .rag_service import rag_service

            if getattr(rag_service, 'enabled', False):
                rag_result = rag_service.retrieve(query, k=3)

                if rag_result:
                    context = "\n\n".join([doc['content'] for doc in rag_result])
                    enhanced_query = f"""
                    Context from disaster knowledge base:
                    {context}

                    Question: {query}

                    Please provide a response based on the context above and your knowledge.
                    """
                    return self.process(enhanced_query, language)

            return self.process(query, language)

        except Exception as e:
            logger.error(f"❌ RAG processing error: {e}", exc_info=True)
            return self.process(query, language)

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        try:
            from .rag_service import rag_service
            rag_available = bool(getattr(rag_service, 'enabled', False))
        except Exception as e:
            logger.warning(f"⚠️ Could not read rag_service status: {e}")
            rag_available = False

        return {
            'initialized': self.initialized,
            'langchain_available': LANGCHAIN_AVAILABLE,
            'llm_available': self.llm is not None,
            'llm_model': self.llm_model_name,
            'llm_is_thinking_model': self.llm_is_thinking_model,
            'agent_available': self.agent is not None,
            'rag_available': rag_available,
            'tools_count': len(self.tools),
            'tools': [tool.name for tool in self.tools] if self.tools else [],
            'error_message': self.error_message
        }

# Singleton instance
orchestrator = AgentOrchestrator()