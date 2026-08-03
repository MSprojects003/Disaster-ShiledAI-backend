"""
Routes for LangChain Agent Orchestrator
"""

from flask import Blueprint, request, jsonify
from ..services.agent_orchestrator import orchestrator
from ..services.rag_service import rag_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

orchestrator_bp = Blueprint('orchestrator', __name__)

@orchestrator_bp.route('/chat', methods=['POST'])
def chat():
    """
    Chat with the multi-agent orchestrator
    Body: {"query": "What's the risk in Colombo?", "language": "en"}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        query = data.get('query', '')
        language = data.get('language', 'en')
        user_id = data.get('user_id', 'anonymous')
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        # Process through orchestrator
        result = orchestrator.process(query, language, user_id)
        
        return jsonify({
            'success': result.get('success', False),
            'response': result.get('response', ''),
            'language': language,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Orchestrator chat error: {e}")
        return jsonify({'error': str(e)}), 500

@orchestrator_bp.route('/chat-rag', methods=['POST'])
def chat_with_rag():
    """
    Chat with RAG-enhanced responses
    Body: {"query": "What should I do during a flood?", "language": "en"}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        query = data.get('query', '')
        language = data.get('language', 'en')
        user_id = data.get('user_id', 'anonymous')
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        # Process with RAG
        result = orchestrator.process_with_rag(query, language)
        
        return jsonify({
            'success': result.get('success', False),
            'response': result.get('response', ''),
            'language': language,
            'rag_used': True,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ RAG chat error: {e}")
        return jsonify({'error': str(e)}), 500

@orchestrator_bp.route('/knowledge/add', methods=['POST'])
def add_knowledge():
    """
    Add knowledge to RAG vector store
    Body: {"documents": [{"content": "...", "category": "flood"}]}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        documents = data.get('documents', [])
        
        if not documents:
            return jsonify({'error': 'No documents provided'}), 400
        
        rag_service.add_documents(documents)
        
        return jsonify({
            'success': True,
            'message': f'Added {len(documents)} documents to knowledge base',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Add knowledge error: {e}")
        return jsonify({'error': str(e)}), 500

@orchestrator_bp.route('/knowledge/search', methods=['POST'])
def search_knowledge():
    """
    Search knowledge base
    Body: {"query": "flood safety", "k": 5}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        query = data.get('query', '')
        k = data.get('k', 5)
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        results = rag_service.retrieve(query, k=k)
        
        return jsonify({
            'success': True,
            'query': query,
            'num_results': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Search knowledge error: {e}")
        return jsonify({'error': str(e)}), 500

@orchestrator_bp.route('/status', methods=['GET'])
def get_orchestrator_status():
    """Get orchestrator status"""
    return jsonify({
        'status': orchestrator.get_status(),
        'rag_status': rag_service.get_status(),
        'timestamp': datetime.now().isoformat()
    })