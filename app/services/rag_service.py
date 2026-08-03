"""
RAG (Retrieval-Augmented Generation) Service
Uses FAISS + Gemini Embeddings for disaster knowledge retrieval
Now with Evacuation-specific methods
"""

import os
import json
import logging
import pickle
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Updated embedding models
EMBEDDING_MODELS_TO_TRY = [
    "models/gemini-embedding-001",
    "models/text-embedding-004",
]

class RAGService:
    """
    RAG Service for Disaster-ShieldAI
    Provides knowledge retrieval using FAISS + Gemini Embeddings
    Now supports Evacuation shelter data
    """

    def __init__(self):
        self.vector_store = None
        self.embeddings = None
        self.embedding_model_name = None
        self.documents = []
        self.enabled = True
        self.disabled_reason = None
        self.vector_store_path = "data/rag/vector_store/"
        self.knowledge_path = "data/rag/knowledge/"
        self.shelter_vector_store_path = "data/rag/shelter_vector_store/"

        # Create directories
        os.makedirs(self.vector_store_path, exist_ok=True)
        os.makedirs(self.knowledge_path, exist_ok=True)
        os.makedirs(self.shelter_vector_store_path, exist_ok=True)

        # Initialize embeddings
        self._init_embeddings()

        # Load or build vector store
        try:
            self._load_or_build_vector_store()
        except Exception as e:
            logger.error(f"❌ RAG vector store unavailable: {e}")
            self.vector_store = None
            self.enabled = False
            self.disabled_reason = str(e)

        # Initialize shelter vector store
        self.shelter_vector_store = None
        self._init_shelter_vector_store()

        logger.info(f"✅ RAG Service initialized (enabled={self.enabled})")

    def _init_embeddings(self):
        """Initialize Gemini embeddings"""
        api_key = os.getenv('GEMINI_API_KEY', '')
        if not api_key:
            logger.warning("⚠️ No Gemini API key found for embeddings")
            self.embeddings = None
            self.enabled = False
            self.disabled_reason = "No GEMINI_API_KEY set"
            return

        for model_name in EMBEDDING_MODELS_TO_TRY:
            try:
                candidate = GoogleGenerativeAIEmbeddings(
                    model=model_name,
                    google_api_key=api_key
                )
                candidate.embed_query("test")
                self.embeddings = candidate
                self.embedding_model_name = model_name
                logger.info(f"✅ Gemini embeddings initialized with model '{model_name}'")
                return
            except Exception as e:
                logger.warning(f"⚠️ Embedding model '{model_name}' failed: {e}")
                continue

        logger.error("❌ All embedding models failed")
        self.embeddings = None
        self.enabled = False
        self.disabled_reason = "All embedding models failed"

    def _load_or_build_vector_store(self):
        """Load existing vector store or build new one"""
        if not self.embeddings:
            return

        try:
            index_path = os.path.join(self.vector_store_path, "index.faiss")
            if os.path.exists(index_path):
                self.vector_store = FAISS.load_local(
                    self.vector_store_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("✅ Vector store loaded from disk")
            else:
                self._build_vector_store()
        except Exception as e:
            logger.error(f"❌ Error loading vector store: {e}")
            self._build_vector_store()

    def _build_vector_store(self):
        """Build vector store from knowledge documents"""
        logger.info("📚 Building vector store from knowledge documents...")

        documents = self._load_knowledge_documents()

        if not documents:
            logger.warning("⚠️ No knowledge documents found")
            return

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        chunks = text_splitter.split_documents(documents)
        logger.info(f"   Created {len(chunks)} chunks from {len(documents)} documents")

        self.vector_store = FAISS.from_documents(chunks, self.embeddings)
        self.vector_store.save_local(self.vector_store_path)
        logger.info(f"✅ Vector store saved to {self.vector_store_path}")

    def _load_knowledge_documents(self) -> List[Document]:
        """Load knowledge documents from knowledge directory"""
        documents = []

        # Check for JSON knowledge files
        json_files = [f for f in os.listdir(self.knowledge_path) if f.endswith('.json')]

        if json_files:
            for json_file in json_files:
                try:
                    with open(os.path.join(self.knowledge_path, json_file), 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                if 'content' in item:
                                    doc = Document(
                                        page_content=item['content'],
                                        metadata={
                                            'category': item.get('category', 'general'),
                                            'source': json_file,
                                            'language': item.get('language', 'en')
                                        }
                                    )
                                    documents.append(doc)
                except Exception as e:
                    logger.warning(f"⚠️ Could not load {json_file}: {e}")

        # If no documents found, create default knowledge
        if not documents:
            documents = self._create_default_knowledge()

        return documents

    def _create_default_knowledge(self) -> List[Document]:
        """Create default knowledge documents"""
        default_knowledge = [
            {
                'category': 'flood',
                'content': 'During floods, move to higher ground immediately. Do not walk or drive through flood waters. Listen to official warnings and evacuation orders.'
            },
            {
                'category': 'flood',
                'content': 'Sri Lanka experiences floods during monsoon seasons (May-August and October-December). Low-lying areas near rivers like Kelani, Mahaweli, and Kalu are most vulnerable.'
            },
            {
                'category': 'landslide',
                'content': 'Landslides occur in Sri Lanka during heavy rainfall, especially in hill country areas like Kandy, Nuwara Eliya, and Badulla. Look for signs like cracks in the ground or tilting trees.'
            },
            {
                'category': 'evacuation',
                'content': 'Sri Lanka has evacuation centers identified by the Disaster Management Centre (DMC). Follow official evacuation routes and instructions from local authorities.'
            },
            {
                'category': 'emergency',
                'content': 'In Sri Lanka, contact 117 for the Disaster Management Centre, 119 for Police emergency, and 110 for Fire and Ambulance services.'
            }
        ]

        documents = []
        for item in default_knowledge:
            doc = Document(
                page_content=item['content'],
                metadata={'category': item.get('category', 'general'), 'source': 'default_knowledge'}
            )
            documents.append(doc)

        with open(os.path.join(self.knowledge_path, 'default_knowledge.json'), 'w') as f:
            json.dump(default_knowledge, f, indent=2)

        logger.info(f"✅ Created {len(documents)} default knowledge documents")
        return documents

    # ================================================================
    # SHELTER-SPECIFIC RAG METHODS
    # ================================================================

    def _init_shelter_vector_store(self):
        """Initialize shelter-specific vector store"""
        if not self.embeddings:
            logger.warning("⚠️ No embeddings available for shelter vector store")
            return

        try:
            index_path = os.path.join(self.shelter_vector_store_path, "index.faiss")
            if os.path.exists(index_path):
                self.shelter_vector_store = FAISS.load_local(
                    self.shelter_vector_store_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("✅ Shelter vector store loaded from disk")
            else:
                logger.info("ℹ️ No shelter vector store found. Will build on first use.")
                self.shelter_vector_store = None
        except Exception as e:
            logger.error(f"❌ Error loading shelter vector store: {e}")
            self.shelter_vector_store = None

    def add_shelter_to_vector_store(self, shelter_data: Dict[str, Any]):
        """
        Add a shelter to the vector store for RAG retrieval
        """
        if not self.embeddings:
            logger.warning("⚠️ No embeddings available")
            return False

        try:
            # Create document from shelter data
            content = f"""
            Shelter Name: {shelter_data.get('name', 'Unknown')}
            Type: {shelter_data.get('type', 'Unknown')}
            District: {shelter_data.get('district', 'Unknown')}
            Address: {shelter_data.get('address', 'Unknown')}
            Capacity: {shelter_data.get('capacity', 0)} people
            Available: {shelter_data.get('available', 0)} people
            Coordinates: {shelter_data.get('lat', 0)}, {shelter_data.get('lon', 0)}
            Source: {shelter_data.get('source', 'Unknown')}
            """

            # IMPORTANT: 'name' (and 'address') were previously missing from
            # this metadata dict — they were only ever written into the
            # `content` string above, which is used purely for embedding
            # similarity, not for structured field lookups. Every read path
            # (find_shelters_rag, get_shelter_by_id) reads doc.metadata, not
            # doc.page_content, so shelters always came back with
            # name="Unknown" regardless of what was in the source CSV/data.
            metadata = {
                'shelter_id': shelter_data.get('shelter_id', 'unknown'),
                'name': shelter_data.get('name', 'Unknown Shelter'),
                'district': shelter_data.get('district', 'Unknown'),
                'type': shelter_data.get('type', 'Unknown'),
                'lat': shelter_data.get('lat', 0),
                'lon': shelter_data.get('lon', 0),
                'capacity': shelter_data.get('capacity', 0),
                'available': shelter_data.get('available', 0),
                'source': shelter_data.get('source', 'Unknown'),
                'address': shelter_data.get('address', None),
                'timestamp': datetime.now().isoformat()
            }

            doc = Document(page_content=content, metadata=metadata)

            if self.shelter_vector_store:
                self.shelter_vector_store.add_documents([doc])
            else:
                self.shelter_vector_store = FAISS.from_documents([doc], self.embeddings)

            self.shelter_vector_store.save_local(self.shelter_vector_store_path)
            logger.info(f"✅ Added shelter '{shelter_data.get('name')}' to vector store")
            return True

        except Exception as e:
            logger.error(f"❌ Error adding shelter to vector store: {e}")
            return False

    def find_shelters_rag(self, query: str, district: str = None, k: int = 10) -> List[Dict[str, Any]]:
        """
        Find shelters using RAG (semantic search)
        """
        if not self.shelter_vector_store:
            logger.warning("⚠️ Shelter vector store not initialized")
            return []

        try:
            # Build search query
            search_query = query
            if district:
                search_query = f"{query} in {district}, Sri Lanka"

            # Search with metadata filter
            filter_metadata = {}
            if district:
                filter_metadata['district'] = district

            results = self.shelter_vector_store.similarity_search_with_score(
                search_query,
                k=k,
                filter=filter_metadata if filter_metadata else None
            )

            shelters = []
            for doc, score in results:
                shelters.append({
                    'name': doc.metadata.get('name', 'Unknown Shelter'),
                    'shelter_id': doc.metadata.get('shelter_id', 'unknown'),
                    'district': doc.metadata.get('district', 'Unknown'),
                    'type': doc.metadata.get('type', 'Unknown'),
                    'lat': doc.metadata.get('lat', 0),
                    'lon': doc.metadata.get('lon', 0),
                    'capacity': doc.metadata.get('capacity', 0),
                    'available': doc.metadata.get('available', 0),
                    'source': doc.metadata.get('source', 'Unknown'),
                    'address': doc.metadata.get('address', None),
                    'relevance_score': float(score)
                })

            logger.info(f"✅ Found {len(shelters)} shelters via RAG")
            return shelters

        except Exception as e:
            logger.error(f"❌ RAG shelter search error: {e}")
            return []

    def get_shelter_by_id(self, shelter_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific shelter by ID from vector store"""
        if not self.shelter_vector_store:
            return None

        try:
            # Search with metadata filter for specific ID
            results = self.shelter_vector_store.similarity_search(
                shelter_id,
                k=1,
                filter={'shelter_id': shelter_id}
            )

            if results:
                doc = results[0]
                return {
                    'name': doc.metadata.get('name', 'Unknown Shelter'),
                    'shelter_id': doc.metadata.get('shelter_id', 'unknown'),
                    'district': doc.metadata.get('district', 'Unknown'),
                    'type': doc.metadata.get('type', 'Unknown'),
                    'lat': doc.metadata.get('lat', 0),
                    'lon': doc.metadata.get('lon', 0),
                    'capacity': doc.metadata.get('capacity', 0),
                    'available': doc.metadata.get('available', 0),
                    'source': doc.metadata.get('source', 'Unknown'),
                    'address': doc.metadata.get('address', None)
                }
            return None

        except Exception as e:
            logger.error(f"❌ Error retrieving shelter by ID: {e}")
            return None

    def sync_shelters_to_rag(self, shelters: List[Dict[str, Any]]):
        """
        Sync multiple shelters to the RAG vector store
        """
        logger.info(f"🔄 Syncing {len(shelters)} shelters to RAG vector store...")

        success_count = 0
        for shelter in shelters:
            if self.add_shelter_to_vector_store(shelter):
                success_count += 1

        logger.info(f"✅ Synced {success_count}/{len(shelters)} shelters to RAG")
        return success_count

    def retrieve(self, query: str, k: int = 5, filter_metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Retrieve relevant documents for a query"""
        if not self.vector_store:
            logger.warning("⚠️ Vector store not initialized")
            return []

        try:
            if filter_metadata:
                results = self.vector_store.similarity_search(
                    query,
                    k=k,
                    filter=filter_metadata
                )
            else:
                results = self.vector_store.similarity_search(query, k=k)

            documents = []
            for doc in results:
                documents.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'relevance': 1.0
                })

            return documents

        except Exception as e:
            logger.error(f"❌ Retrieval error: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        """Get RAG service status"""
        return {
            'enabled': self.enabled,
            'initialized': self.vector_store is not None,
            'shelter_vector_store_initialized': self.shelter_vector_store is not None,
            'embeddings_available': self.embeddings is not None,
            'embedding_model': self.embedding_model_name,
            'disabled_reason': self.disabled_reason,
            'knowledge_path': self.knowledge_path,
            'shelter_vector_store_path': self.shelter_vector_store_path,
            'document_count': len(self.documents) if self.documents else 0
        }

# Singleton instance
rag_service = RAGService()