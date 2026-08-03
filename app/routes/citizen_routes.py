from flask import Blueprint, request, jsonify, send_file
from ..agents.citizen_agent import citizen_agent
from ..utils.text_cleaning import clean_text_for_speech
from ..services.tts_service import synthesize_speech
from datetime import datetime
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

citizen_bp = Blueprint('citizen', __name__)

# Initialize agent
citizen_agent.initialize()


@citizen_bp.route('/report/text', methods=['POST'])
def submit_text_report():
    """
    Submit a text citizen report
    Body: {"text": "...", "language": "en", "location": "Colombo", "user_id": "..."}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = citizen_agent.process({
            'action': 'text_report',
            'text': data.get('text', ''),
            'language': data.get('language', 'en'),
            'location': data.get('location', 'Unknown'),
            'user_id': data.get('user_id', 'anonymous')
        })

        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Text report error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/report/image', methods=['POST'])
def submit_image_report():
    """
    Submit an image citizen report
    Body: {"image_data": "<base64>", "location": "Colombo", "user_id": "..."}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = citizen_agent.process({
            'action': 'image_report',
            'image_data': data.get('image_data', ''),
            'location': data.get('location', 'Unknown'),
            'user_id': data.get('user_id', 'anonymous')
        })

        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Image report error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/report/voice', methods=['POST'])
def submit_voice_report():
    """
    Submit a voice citizen report
    Body: {"audio_data": "<base64>", "audio_mime_type": "audio/wav",
           "language": "en", "location": "Colombo", "user_id": "..."}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = citizen_agent.process({
            'action': 'voice_report',
            'audio_data': data.get('audio_data', ''),
            'audio_mime_type': data.get('audio_mime_type', 'audio/wav'),
            'language': data.get('language', 'en'),
            'location': data.get('location', 'Unknown'),
            'user_id': data.get('user_id', 'anonymous')
        })

        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Voice report error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/chat', methods=['POST'])
def chat():
    """
    Chat with the disaster response assistant
    Body: {"query": "...", "language": "en", "user_id": "..."}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = citizen_agent.process({
            'action': 'chat',
            'query': data.get('query', ''),
            'language': data.get('language', 'en'),
            'user_id': data.get('user_id', 'anonymous')
        })

        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/translate', methods=['POST'])
def translate():
    """
    Translate text
    Body: {"text": "...", "source_language": "auto", "target_language": "si"}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = citizen_agent.process({
            'action': 'translate',
            'text': data.get('text', ''),
            'source_language': data.get('source_language', 'auto'),
            'target_language': data.get('target_language', 'en')
        })

        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Translation error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/tts', methods=['POST'])
def tts():
    """
    Text to speech. ElevenLabs for English/Tamil, free edge-tts for Sinhala
    (ElevenLabs does not support Sinhala natively).
    Body: {"text": "...", "language": "en|si|ta"}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        raw_text = (data.get('text') or '').strip()
        language = (data.get('language') or 'en').strip()

        if not raw_text:
            return jsonify({'error': 'Text is required'}), 400

        clean_text = clean_text_for_speech(raw_text)
        if not clean_text:
            return jsonify({'error': 'Nothing left to speak after cleaning'}), 400

        audio_bytes = synthesize_speech(clean_text, language)

        return send_file(
            BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="tts.mp3"
        )

    except Exception as e:
        logger.error(f"❌ TTS error: {e}")
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/reports', methods=['GET'])
def get_reports():
    """Get citizen reports, optionally filtered by severity"""
    try:
        severity = request.args.get('severity', None)
        reports = citizen_agent.get_reports(severity)
        return jsonify({
            'total': len(reports),
            'reports': reports
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@citizen_bp.route('/status', methods=['GET'])
def get_agent_status():
    """Get citizen agent status"""
    return jsonify(citizen_agent.get_status())


@citizen_bp.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify routes are working"""
    return jsonify({
        'message': 'Citizen routes are working!',
        'timestamp': datetime.now().isoformat()
    })