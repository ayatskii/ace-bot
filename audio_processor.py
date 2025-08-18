"""
Audio processing module for handling voice messages and transcription
"""
import os
import logging
import tempfile
import requests
from typing import Optional, Tuple
import config

try:
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logging.warning("⚠️ ElevenLabs not installed. Voice features will be disabled.")

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Handle audio transcription using Eleven Labs API"""
    
    def __init__(self):
        """Initialize Eleven Labs client"""
        if not ELEVENLABS_AVAILABLE:
            logger.warning("⚠️ ElevenLabs not available. Voice transcription disabled.")
            self.client = None
            return
            
        if not config.ELEVEN_LABS_API_KEY:
            logger.error("🔥 ELEVEN_LABS_API_KEY not found in environment variables")
            self.client = None
            return
        
        try:
            self.client = ElevenLabs(api_key=config.ELEVEN_LABS_API_KEY)
            logger.info("✅ Eleven Labs client initialized successfully")
        except Exception as e:
            logger.error(f"🔥 Failed to initialize Eleven Labs client: {e}")
            self.client = None
    
    async def download_voice_file(self, file_url: str, file_path: str) -> bool:
        """Download voice file from Telegram servers"""
        try:
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            file_size = os.path.getsize(file_path)
            logger.info(f"✅ Voice file downloaded successfully. Size: {file_size} bytes")
            return True
            
        except requests.RequestException as e:
            logger.error(f"🔥 Failed to download voice file: {e}")
            return False
        except Exception as e:
            logger.error(f"🔥 Unexpected error downloading voice file: {e}")
            return False
    
    def transcribe_audio(self, audio_file_path: str) -> Optional[str]:
        """Transcribe audio file using Eleven Labs Speech-to-Text"""
        if not self.client:
            logger.error("🔥 Eleven Labs client not available for transcription")
            return None
            
        try:
            logger.info(f"🎤 Starting transcription for file: {audio_file_path}")
            
            # Check if file exists and has content
            if not os.path.exists(audio_file_path):
                logger.error(f"🔥 Audio file not found: {audio_file_path}")
                return None
            
            file_size = os.path.getsize(audio_file_path)
            if file_size == 0:
                logger.error(f"🔥 Audio file is empty: {audio_file_path}")
                return None
            
            logger.info(f"📁 File size: {file_size} bytes")
            
            # Use Eleven Labs Speech-to-Text with correct API format
            try:
                # Correct ElevenLabs API format from documentation
                with open(audio_file_path, 'rb') as audio_file:
                    result = self.client.speech_to_text.convert(
                        model_id='scribe_v1',
                        file=audio_file
                    )
                
                # Log the raw response for debugging
                logger.info(f"🔍 Raw ElevenLabs response type: {type(result)}")
                logger.info(f"🔍 Raw ElevenLabs response content: {result}")
                
                # Handle ElevenLabs SpeechToTextChunkResponseModel
                transcription = None
                
                # Check for text attribute first (ElevenLabs response object)
                if hasattr(result, 'text') and result.text:
                    transcription = result.text
                    logger.info(f"🎯 Extracted text from result.text: '{transcription[:100]}...'")
                elif isinstance(result, dict):
                    transcription = result.get('text', '')
                    if not transcription:
                        # Try alternative keys
                        transcription = result.get('transcript', '') or result.get('transcription', '')
                    logger.info(f"🎯 Extracted text from dict: '{transcription[:100]}...'")
                else:
                    # Try to access as string representation
                    result_str = str(result)
                    # Look for text=" pattern in the string
                    import re
                    text_match = re.search(r'text="([^"]*)"', result_str)
                    if text_match:
                        transcription = text_match.group(1)
                        logger.info(f"🎯 Extracted text from regex: '{transcription[:100]}...'")
                
                if transcription:
                    transcription = transcription.strip()
                    if transcription:  # Make sure it's not empty after stripping
                        logger.info(f"✅ Transcription successful with scribe_v1. Length: {len(transcription)} characters")
                        logger.info(f"📝 Transcription preview: {transcription[:100]}...")
                        return transcription
                    
            except Exception as e1:
                logger.warning(f"⚠️ scribe_v1 model failed: {e1}, trying alternative models...")
                try:
                    # Try alternative model
                    with open(audio_file_path, 'rb') as audio_file:
                        result = self.client.speech_to_text.convert(
                            model_id='eleven_english_sts_v2',
                            file=audio_file
                        )
                    
                    # Log the fallback response for debugging
                    logger.info(f"🔍 Fallback response type: {type(result)}")
                    logger.info(f"🔍 Fallback response content: {result}")
                    
                    if isinstance(result, dict):
                        transcription = result.get('text', '')
                        if not transcription:
                            transcription = result.get('transcript', '') or result.get('transcription', '')
                    elif hasattr(result, 'text'):
                        transcription = result.text
                    elif hasattr(result, 'transcript'):
                        transcription = result.transcript
                    else:
                        transcription = str(result)
                    
                    if transcription:
                        transcription = transcription.strip()
                        if transcription:  # Make sure it's not empty after stripping
                            logger.info(f"✅ Transcription successful with fallback model. Length: {len(transcription)} characters")
                            logger.info(f"📝 Transcription preview: {transcription[:100]}...")
                            return transcription
                            
                except Exception as e2:
                    logger.error(f"🔥 All ElevenLabs models failed. Error 1: {e1}, Error 2: {e2}")
                    logger.info("💡 Check ElevenLabs API key and model availability")
                    return None
            
            # If we get here, all attempts failed
            logger.warning("⚠️ Failed to transcribe voice message")
            return None
                    
        except Exception as e:
            logger.error(f"🔥 Transcription failed: {e}")
            return None
    
    async def process_voice_message(self, file_url: str) -> Optional[str]:
        """Complete voice message processing pipeline"""
        if not self.client:
            logger.error("🔥 Eleven Labs client not available for voice processing")
            return None
            
        temp_file = None
        try:
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                temp_file_path = temp_file.name
            
            logger.info(f"📥 Processing voice message from URL: {file_url}")
            
            # Download voice file
            if not await self.download_voice_file(file_url, temp_file_path):
                return None
            
            # Transcribe audio
            transcription = self.transcribe_audio(temp_file_path)
            
            if transcription:
                logger.info(f"✅ Voice message processed successfully")
                return transcription
            else:
                logger.warning("⚠️ Failed to transcribe voice message")
                return None
                
        except Exception as e:
            logger.error(f"🔥 Voice message processing failed: {e}")
            return None
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info("🧹 Temporary audio file cleaned up")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clean up temporary file: {e}")

# Global instance
audio_processor = AudioProcessor()
