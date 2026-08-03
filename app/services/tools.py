"""
LangChain Tools for Multi-Agent Orchestration
Each tool wraps an agent's functionality
"""

import json
import logging
from typing import Type, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

# Import all agents
from ..agents.risk_agent import risk_agent
from ..agents.infrastructure_agent import infrastructure_agent
from ..agents.evacuation_agent import evacuation_agent
from ..agents.resource_agent import resource_agent
from ..agents.citizen_agent import citizen_agent
from .rag_service import rag_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Input Schemas for Tools
# ============================================================

class RiskPredictionInput(BaseModel):
    district: str = Field(description="The district name in Sri Lanka (e.g., Colombo, Gampaha, Kandy)")

class InfrastructureInput(BaseModel):
    district: str = Field(description="The district name to analyze infrastructure")

class EvacuationInput(BaseModel):
    district: str = Field(description="The district to plan evacuation for")
    lat: Optional[float] = Field(default=None, description="Latitude of the user's location")
    lon: Optional[float] = Field(default=None, description="Longitude of the user's location")

class ResourceAllocationInput(BaseModel):
    district: Optional[str] = Field(default=None, description="Specific district or leave empty for all")

class ChatInput(BaseModel):
    query: str = Field(description="The user's question or query")
    language: str = Field(default="en", description="Language code: en, si, ta")

class RagQueryInput(BaseModel):
    query: str = Field(description="The question to search for in the knowledge base")
    k: int = Field(default=5, description="Number of documents to retrieve")

# ============================================================
# Tools Definition
# ============================================================

class RiskPredictionTool(BaseTool):
    """Tool to predict flood/landslide risk for a district"""
    
    name: str = "risk_prediction"
    description: str = "Predicts flood and landslide risk scores (0-100) for a given district in Sri Lanka."
    args_schema: Type[BaseModel] = RiskPredictionInput
    
    def _run(self, district: str) -> str:
        try:
            result = risk_agent.predict_district(district)
            if 'error' in result:
                return f"Error: {result['error']}"
            
            prediction = result.get('prediction', {})
            return json.dumps({
                'district': district,
                'risk_score': prediction.get('risk_score', 0),
                'risk_level': prediction.get('risk_level', 'Unknown'),
                'alert_triggered': prediction.get('risk_level') in ['High', 'Critical']
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, district: str) -> str:
        return self._run(district)


class InfrastructureTool(BaseTool):
    """Tool to analyze infrastructure and road conditions"""
    
    name: str = "infrastructure_analysis"
    description: str = "Analyzes road and bridge conditions in a district based on risk predictions."
    args_schema: Type[BaseModel] = InfrastructureInput
    
    def _run(self, district: str) -> str:
        try:
            result = infrastructure_agent.process({
                'district': district,
                'risk_level': 'Medium'  # Default, will be updated by orchestrator
            })
            
            return json.dumps({
                'district': district,
                'total_roads': result.get('total_roads_analyzed', 0),
                'blocked_roads': result.get('blocked_roads', 0),
                'impassable_roads': result.get('impassable_roads', 0),
                'safe_roads': result.get('safe_roads', 0),
                'alert_triggered': result.get('alert_triggered', False)
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, district: str) -> str:
        return self._run(district)


class EvacuationTool(BaseTool):
    """Tool to plan evacuation routes"""
    
    name: str = "evacuation_planning"
    description: str = "Plans the safest evacuation route to the nearest shelter for a district."
    args_schema: Type[BaseModel] = EvacuationInput
    
    def _run(self, district: str, lat: float = None, lon: float = None) -> str:
        try:
            # Get risk prediction first
            risk_result = risk_agent.predict_district(district)
            risk_level = risk_result.get('prediction', {}).get('risk_level', 'Low')
            
            result = evacuation_agent.process({
                'district': district,
                'risk_level': risk_level,
                'origin_lat': lat,
                'origin_lon': lon
            })
            
            nearest = result.get('nearest_shelter', {})
            return json.dumps({
                'district': district,
                'nearest_shelter': nearest.get('name', 'Not found') if 'error' not in nearest else 'No shelter found',
                'distance_km': nearest.get('distance_km', 0) if 'error' not in nearest else 0,
                'estimated_time': result.get('evacuation_route', {}).get('estimated_time', 'Unknown'),
                'safety_level': result.get('evacuation_route', {}).get('safety_level', 'Unknown')
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, district: str, lat: float = None, lon: float = None) -> str:
        return self._run(district, lat, lon)


class ResourceAllocationTool(BaseTool):
    """Tool to allocate emergency resources"""
    
    name: str = "resource_allocation"
    description: str = "Optimizes allocation of rescue teams, ambulances, boats, and supplies."
    args_schema: Type[BaseModel] = ResourceAllocationInput
    
    def _run(self, district: str = None) -> str:
        try:
            if district:
                result = resource_agent.process({
                    'action': 'deployment_plan',
                    'district': district
                })
                return json.dumps({
                    'district': district,
                    'deployment_plan': result.get('deployment_plan', {}),
                    'timestamp': result.get('timestamp', '')
                }, indent=2)
            else:
                result = resource_agent.process({'action': 'allocate'})
                return json.dumps({
                    'total_districts': result.get('total_districts', 0),
                    'resources_used': result.get('resources_used', {}),
                    'resources_remaining': result.get('resources_remaining', {})
                }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, district: str = None) -> str:
        return self._run(district)


class CitizenChatTool(BaseTool):
    """Tool for citizen interaction"""
    
    name: str = "citizen_assistant"
    description: str = "Provides disaster information, answers questions, and processes citizen reports."
    args_schema: Type[BaseModel] = ChatInput
    
    def _run(self, query: str, language: str = "en") -> str:
        try:
            result = citizen_agent.process({
                'action': 'chat',
                'query': query,
                'language': language
            })
            
            return json.dumps({
                'query': query,
                'response': result.get('response', 'No response'),
                'language': language
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, query: str, language: str = "en") -> str:
        return self._run(query, language)


class RAGTool(BaseTool):
    """Tool for knowledge retrieval"""
    
    name: str = "knowledge_retrieval"
    description: str = "Retrieves relevant disaster knowledge from the RAG vector database."
    args_schema: Type[BaseModel] = RagQueryInput
    
    def _run(self, query: str, k: int = 5) -> str:
        try:
            documents = rag_service.retrieve(query, k=k)
            
            if not documents:
                return "No relevant information found in the knowledge base."
            
            # Format results
            results = []
            for doc in documents:
                results.append({
                    'content': doc['content'],
                    'category': doc['metadata'].get('category', 'general')
                })
            
            return json.dumps({
                'query': query,
                'num_results': len(results),
                'results': results
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _arun(self, query: str, k: int = 5) -> str:
        return self._run(query, k)