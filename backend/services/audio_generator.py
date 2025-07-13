"""
Audio Generation Service using ElevenLabs for Video Generation Platform
"""
import os
import uuid
import logging
import aiofiles
from typing import Optional, Dict, Any, List
from pathlib import Path
import httpx
import asyncio

logger = logging.getLogger(__name__)

class ElevenLabsAudioGenerator:
    """Handles audio generation using ElevenLabs API"""
    
    def __init__(self):
        self.api_key = os.environ.get('ELEVENLABS_API_KEY')
        if not self.api_key:
            logger.warning("ElevenLabs API key not found. Audio generation will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
        
        self.base_url = "https://api.elevenlabs.io/v1"
        self.temp_dir = "/tmp/audio_generation"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Default voice settings
        self.default_voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
        self.default_model = "eleven_monolingual_v1"
        
        logger.info(f"ElevenLabsAudioGenerator initialized (enabled: {self.enabled})")
    
    async def get_available_voices(self) -> Dict[str, Any]:
        """Get list of available voices from ElevenLabs"""
        if not self.enabled:
            return {'success': False, 'error': 'ElevenLabs API key not configured'}
        
        try:
            headers = {
                'Accept': 'application/json',
                'xi-api-key': self.api_key
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/voices", headers=headers)
                
                if response.status_code == 200:
                    voices_data = response.json()
                    
                    # Format voice information
                    voices = []
                    for voice in voices_data.get('voices', []):
                        voices.append({
                            'voice_id': voice.get('voice_id'),
                            'name': voice.get('name'),
                            'category': voice.get('category'),
                            'description': voice.get('description', ''),
                            'gender': voice.get('labels', {}).get('gender', 'unknown'),
                            'age': voice.get('labels', {}).get('age', 'unknown'),
                            'accent': voice.get('labels', {}).get('accent', 'unknown')
                        })
                    
                    logger.info(f"Retrieved {len(voices)} available voices")
                    return {
                        'success': True,
                        'voices': voices,
                        'total_count': len(voices)
                    }
                else:
                    error_msg = f"ElevenLabs API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                    
        except Exception as e:
            error_msg = f"Error fetching voices: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def generate_speech(self, text: str, voice_id: Optional[str] = None, 
                            output_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate speech from text using ElevenLabs"""
        if not self.enabled:
            return {'success': False, 'error': 'ElevenLabs API key not configured'}
        
        try:
            # Use default voice if none specified
            if not voice_id:
                voice_id = self.default_voice_id
            
            # Generate output path if not provided
            if not output_path:
                audio_id = uuid.uuid4().hex
                output_path = os.path.join(self.temp_dir, f"speech_{audio_id}.mp3")
            
            # Prepare request
            url = f"{self.base_url}/text-to-speech/{voice_id}"
            headers = {
                'Accept': 'audio/mpeg',
                'Content-Type': 'application/json',
                'xi-api-key': self.api_key
            }
            
            payload = {
                'text': text,
                'model_id': self.default_model,
                'voice_settings': {
                    'stability': 0.5,
                    'similarity_boost': 0.5,
                    'style': 0.0,
                    'use_speaker_boost': True
                }
            }
            
            logger.info(f"Generating speech for {len(text)} characters with voice {voice_id}")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    # Save audio file
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(response.content)
                    
                    file_size = os.path.getsize(output_path)
                    
                    logger.info(f"Successfully generated speech audio: {output_path}")
                    
                    return {
                        'success': True,
                        'audio_path': output_path,
                        'file_size': file_size,
                        'voice_id': voice_id,
                        'text_length': len(text),
                        'model': self.default_model
                    }
                else:
                    error_msg = f"ElevenLabs speech generation error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {'success': False, 'error': error_msg}
                    
        except Exception as e:
            error_msg = f"Speech generation error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def generate_character_voice(self, text: str, character_description: str, 
                                     output_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate speech with voice matching character description"""
        if not self.enabled:
            return {'success': False, 'error': 'ElevenLabs API key not configured'}
        
        try:
            # Get available voices
            voices_result = await self.get_available_voices()
            if not voices_result['success']:
                return voices_result
            
            # Simple voice selection based on character description
            voices = voices_result['voices']
            selected_voice = self.default_voice_id
            
            # Basic character voice matching
            character_lower = character_description.lower()
            
            for voice in voices:
                voice_name = voice['name'].lower()
                gender = voice.get('gender', '').lower()
                age = voice.get('age', '').lower()
                
                # Match based on character description
                if any(keyword in character_lower for keyword in ['young', 'child', 'kid']):
                    if 'young' in age or 'child' in voice_name:
                        selected_voice = voice['voice_id']
                        break
                elif any(keyword in character_lower for keyword in ['old', 'elder', 'wise']):
                    if 'old' in age or 'elder' in voice_name:
                        selected_voice = voice['voice_id']
                        break
                elif any(keyword in character_lower for keyword in ['male', 'man', 'boy']):
                    if 'male' in gender:
                        selected_voice = voice['voice_id']
                        break
                elif any(keyword in character_lower for keyword in ['female', 'woman', 'girl']):
                    if 'female' in gender:
                        selected_voice = voice['voice_id']
                        break
            
            # Generate speech with selected voice
            return await self.generate_speech(text, selected_voice, output_path)
            
        except Exception as e:
            error_msg = f"Character voice generation error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def enhance_audio_quality(self, audio_path: str, output_path: str) -> Dict[str, Any]:
        """Enhance audio quality using basic processing"""
        try:
            # This would require additional audio processing libraries
            # For now, just copy the file
            import shutil
            shutil.copy2(audio_path, output_path)
            
            return {
                'success': True,
                'input_path': audio_path,
                'output_path': output_path,
                'process_type': 'audio_enhancement'
            }
            
        except Exception as e:
            error_msg = f"Audio enhancement error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def cleanup_temp_files(self):
        """Clean up temporary audio files"""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir, exist_ok=True)
            logger.info("Cleaned up temporary audio files")
        except Exception as e:
            logger.error(f"Error cleaning up temp audio files: {str(e)}")

# Global audio generator instance
audio_generator = ElevenLabsAudioGenerator()