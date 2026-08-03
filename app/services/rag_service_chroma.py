"""
RAG Service with ChromaDB
Lightweight, easy-to-use vector database for Disaster-ShieldAI
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
from chromadb.api.types import Documents, Embeddings, EmbeddingFunction

# Import Gemini for embeddings
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Same fallback list as rag_service.py — try the primary model first,
# fall back if the account/API version doesn't support it.
EMBEDDING_MODELS_TO_TRY = [
    "models/gemini-embedding-001",
    "models/text-embedding-004",
]


class GeminiEmbeddingFunction(EmbeddingFunction):
    """
    Calls google.generativeai.embed_content() directly instead of going
    through chromadb.utils.embedding_functions.GoogleGenerativeAiEmbeddingFunction.
    That built-in wrapper currently raises "ClientOptions does not accept an
    option 'headers'" against this project's installed SDK version — this
    class avoids the broken wrapper entirely.
    """

    def __init__(self, api_key: str, model_name: str = "models/gemini-embedding-001",
                 task_type: str = "retrieval_document"):
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.task_type = task_type

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            try:
                result = genai.embed_content(
                    model=self.model_name,
                    content=text,
                    task_type=self.task_type
                )
                embeddings.append(result['embedding'])
            except Exception as e:
                logger.error(f"❌ Embedding failed for one document: {e}")
                raise
        return embeddings


class ChromaRAGService:
    """
    RAG Service using ChromaDB
    Easy to use, no PostgreSQL required!
    Persistent storage in data/chromadb/
    """

    def __init__(self):
        self.client = None
        self.knowledge_collection = None
        self.shelter_collection = None
        self.gemini_enabled = False
        self.embedding_function = None
        self.embedding_model_name = None

        # Initialize
        self._init_chromadb()
        self._init_embeddings()
        self._init_collections()

        logger.info("✅ ChromaDB RAG Service initialized")

    def _init_chromadb(self):
        """Initialize ChromaDB client with persistence"""
        try:
            # Create data directory
            os.makedirs("data/chromadb", exist_ok=True)

            # Initialize client with persistence
            self.client = chromadb.PersistentClient(
                path="data/chromadb",
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info("✅ ChromaDB client initialized")
            logger.info(f"   Data path: data/chromadb/")
        except Exception as e:
            logger.error(f"❌ ChromaDB initialization failed: {e}")
            self.client = None

    def _init_embeddings(self):
        """
        Initialize Gemini embeddings for ChromaDB. Tries each model in
        EMBEDDING_MODELS_TO_TRY in order (same fallback pattern as
        rag_service.py) and commits to the first one that actually works,
        rather than assuming a single hardcoded model name is available.
        """
        api_key = os.getenv('GEMINI_API_KEY', '')

        if not api_key:
            logger.warning("⚠️ No Gemini API key found for embeddings")
            self.gemini_enabled = False
            return

        if not GEMINI_AVAILABLE:
            logger.warning("⚠️ google-generativeai not installed — embeddings disabled")
            self.gemini_enabled = False
            return

        for model_name in EMBEDDING_MODELS_TO_TRY:
            try:
                candidate = GeminiEmbeddingFunction(api_key=api_key, model_name=model_name)

                # Fail fast and loud here rather than silently falling back to
                # ChromaDB's default local embedder, which was happening before.
                candidate(["connectivity check"])

                self.embedding_function = candidate
                self.embedding_model_name = model_name
                self.gemini_enabled = True
                logger.info(f"✅ Gemini embeddings enabled (direct embed_content, model: '{model_name}')")
                return

            except Exception as e:
                logger.warning(f"⚠️ Embedding model '{model_name}' failed: {e}")
                continue

        logger.error("❌ All embedding models failed")
        self.gemini_enabled = False
        self.embedding_function = None

    def _init_collections(self):
        """Initialize or get collections"""
        if not self.client:
            return

        try:
            # Knowledge collection
            self.knowledge_collection = self.client.get_or_create_collection(
                name="knowledge_base",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            count = self.knowledge_collection.count()
            logger.info(f"✅ Knowledge collection: {count} documents")

            # Shelter collection
            self.shelter_collection = self.client.get_or_create_collection(
                name="shelters",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            count = self.shelter_collection.count()
            logger.info(f"✅ Shelter collection: {count} documents")

        except Exception as e:
            logger.error(f"❌ Collection initialization failed: {e}")

    # ============================================================
    # KNOWLEDGE METHODS
    # ============================================================

    def add_knowledge(self, content: str, category: str = "general", metadata: Dict = None) -> bool:
        """
        Add knowledge document to vector store
        """
        if not self.knowledge_collection:
            logger.warning("⚠️ Knowledge collection not available")
            return False

        try:
            doc_id = f"knowledge_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

            metadata = metadata or {}
            metadata.update({
                "category": category,
                "source": "user_added",
                "timestamp": datetime.now().isoformat()
            })

            self.knowledge_collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )

            logger.info(f"✅ Added knowledge: {content[:50]}...")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to add knowledge: {e}")
            return False

    def add_knowledge_bulk(self, knowledge_items: List[Dict]) -> int:
        """
        Add multiple knowledge items
        """
        success_count = 0
        for item in knowledge_items:
            content = item.get('content', '')
            category = item.get('category', 'general')
            if self.add_knowledge(content, category):
                success_count += 1

        logger.info(f"✅ Added {success_count}/{len(knowledge_items)} knowledge items")
        return success_count

    def search_knowledge(self, query: str, k: int = 5, category: str = None) -> List[Dict]:
        """
        Search knowledge using vector similarity
        """
        if not self.knowledge_collection:
            logger.warning("⚠️ Knowledge collection not available")
            return []

        try:
            # Build filter
            where = {}
            if category:
                where["category"] = category

            results = self.knowledge_collection.query(
                query_texts=[query],
                n_results=k,
                where=where if where else None,
                include=["documents", "metadatas", "distances"]
            )

            formatted_results = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    formatted_results.append({
                        'content': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else 0,
                        'relevance_score': 1 - results['distances'][0][i] if results['distances'] else 0
                    })

            return formatted_results

        except Exception as e:
            logger.error(f"❌ Knowledge search failed: {e}")
            return []

    # ============================================================
    # SHELTER METHODS
    # ============================================================

    def add_shelter(self, shelter_data: Dict) -> bool:
        """
        Add shelter to vector store
        """
        if not self.shelter_collection:
            logger.warning("⚠️ Shelter collection not available")
            return False

        try:
            # Create text representation for embedding
            text = f"""
            Shelter: {shelter_data.get('name', 'Unknown')}
            Type: {shelter_data.get('type', 'Unknown')}
            District: {shelter_data.get('district', 'Unknown')}
            Capacity: {shelter_data.get('capacity', 0)}
            Available: {shelter_data.get('available', 0)}
            Location: {shelter_data.get('lat', 0)}, {shelter_data.get('lon', 0)}
            """

            doc_id = shelter_data.get('shelter_id', f"shelter_{uuid.uuid4().hex[:8]}")

            metadata = {
                "shelter_id": doc_id,
                "name": shelter_data.get('name', 'Unknown'),
                "type": shelter_data.get('type', 'Unknown'),
                "district": shelter_data.get('district', 'Unknown'),
                "lat": shelter_data.get('lat', 0),
                "lon": shelter_data.get('lon', 0),
                "capacity": shelter_data.get('capacity', 0),
                "available": shelter_data.get('available', 0),
                "source": shelter_data.get('source', 'Unknown')
            }

            self.shelter_collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id]
            )

            logger.debug(f"✅ Added shelter: {shelter_data.get('name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to add shelter: {e}")
            return False

    def add_shelters_bulk(self, shelters: List[Dict]) -> int:
        """
        Add multiple shelters to vector store
        """
        success_count = 0
        for shelter in shelters:
            if self.add_shelter(shelter):
                success_count += 1

        logger.info(f"✅ Added {success_count}/{len(shelters)} shelters to ChromaDB")
        return success_count

    def search_shelters(self, query: str, district: str = None, k: int = 10) -> List[Dict]:
        """
        Search shelters using vector similarity
        """
        if not self.shelter_collection:
            logger.warning("⚠️ Shelter collection not available")
            return []

        try:
            # Build filter
            where = {}
            if district:
                where["district"] = district

            results = self.shelter_collection.query(
                query_texts=[query],
                n_results=k,
                where=where if where else None,
                include=["documents", "metadatas", "distances"]
            )

            formatted_results = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    formatted_results.append({
                        'shelter_id': metadata.get('shelter_id', 'unknown'),
                        'name': metadata.get('name', 'Unknown'),
                        'type': metadata.get('type', 'Unknown'),
                        'district': metadata.get('district', 'Unknown'),
                        'lat': metadata.get('lat', 0),
                        'lon': metadata.get('lon', 0),
                        'capacity': metadata.get('capacity', 0),
                        'available': metadata.get('available', 0),
                        'source': metadata.get('source', 'Unknown'),
                        'relevance_score': 1 - results['distances'][0][i] if results['distances'] else 0
                    })

            return formatted_results

        except Exception as e:
            logger.error(f"❌ Shelter search failed: {e}")
            return []

    def get_shelter_by_id(self, shelter_id: str) -> Optional[Dict]:
        """
        Get shelter by ID
        """
        if not self.shelter_collection:
            return None

        try:
            results = self.shelter_collection.get(
                ids=[shelter_id],
                include=["documents", "metadatas"]
            )

            if results and results['documents']:
                metadata = results['metadatas'][0] if results['metadatas'] else {}
                return {
                    'shelter_id': shelter_id,
                    'name': metadata.get('name', 'Unknown'),
                    'type': metadata.get('type', 'Unknown'),
                    'district': metadata.get('district', 'Unknown'),
                    'lat': metadata.get('lat', 0),
                    'lon': metadata.get('lon', 0),
                    'capacity': metadata.get('capacity', 0),
                    'available': metadata.get('available', 0)
                }
            return None

        except Exception as e:
            logger.error(f"❌ Error getting shelter: {e}")
            return None

    def delete_shelter(self, shelter_id: str) -> bool:
        """
        Delete shelter from vector store
        """
        if not self.shelter_collection:
            return False

        try:
            self.shelter_collection.delete(ids=[shelter_id])
            logger.info(f"✅ Deleted shelter: {shelter_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete shelter: {e}")
            return False

    # ============================================================
    # UTILITY METHODS
    # ============================================================

    def get_status(self) -> Dict:
        """Get ChromaDB service status"""
        knowledge_count = self.knowledge_collection.count() if self.knowledge_collection else 0
        shelter_count = self.shelter_collection.count() if self.shelter_collection else 0

        return {
            'enabled': self.client is not None,
            'chromadb_available': self.client is not None,
            'gemini_enabled': self.gemini_enabled,
            'embedding_model': self.embedding_model_name,
            'knowledge_collection': {
                'exists': self.knowledge_collection is not None,
                'count': knowledge_count
            },
            'shelter_collection': {
                'exists': self.shelter_collection is not None,
                'count': shelter_count
            },
            'data_path': 'data/chromadb',
            'vector_db_type': 'ChromaDB',
            'total_vectors': knowledge_count + shelter_count
        }

    def reset_collections(self):
        """
        Reset all collections (use with caution!)
        """
        if not self.client:
            return

        try:
            # Delete collections
            self.client.delete_collection("knowledge_base")
            self.client.delete_collection("shelters")

            # Recreate
            self._init_collections()
            logger.info("✅ Collections reset")

        except Exception as e:
            logger.error(f"❌ Reset failed: {e}")

    def get_collection_stats(self) -> Dict:
        """Get detailed collection statistics"""
        stats = {
            'knowledge': {},
            'shelters': {}
        }

        if self.knowledge_collection:
            try:
                # Get sample documents
                sample = self.knowledge_collection.get(limit=3)
                stats['knowledge'] = {
                    'count': self.knowledge_collection.count(),
                    'sample_ids': sample['ids'] if sample else []
                }
            except:
                pass

        if self.shelter_collection:
            try:
                sample = self.shelter_collection.get(limit=3)
                stats['shelters'] = {
                    'count': self.shelter_collection.count(),
                    'sample_ids': sample['ids'] if sample else []
                }
            except:
                pass

        return stats


# Singleton instance
chroma_rag = ChromaRAGService()