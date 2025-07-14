"""
Video Analysis Service using Gemini 2.5 Pro/Flash for detailed video analysis
"""
import os
import logging
import json
import base64
import asyncio
import aiofiles
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)

class VideoAnalyzer:
    def __init__(self):
        self.api_keys = [
            os.getenv('GEMINI_API_KEY_1'),
            os.getenv('GEMINI_API_KEY_2'),
            os.getenv('GEMINI_API_KEY_3')
        ]
        self.current_key_index = 0
        self.models = {
            'pro': 'gemini-2.5-pro',
            'flash': 'gemini-2.5-flash'
        }
        self.configure_gemini()
        
    def configure_gemini(self):
        """Configure Gemini API with current key"""
        if self.api_keys[self.current_key_index]:
            genai.configure(api_key=self.api_keys[self.current_key_index])
            logger.info(f"Configured Gemini API with key index {self.current_key_index}")
        else:
            logger.error("No valid Gemini API key found")
            
    def rotate_api_key(self):
        """Rotate to next API key if current one fails"""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.configure_gemini()
        logger.info(f"Rotated to API key index {self.current_key_index}")
        
    async def analyze_video(self, video_path: str, character_image_path: Optional[str] = None, 
                          audio_path: Optional[str] = None, user_prompt: str = "") -> Dict[str, Any]:
        """
        Comprehensive video analysis using Gemini 2.5 Pro/Flash
        
        Args:
            video_path: Path to the sample video file
            character_image_path: Optional path to character image
            audio_path: Optional path to audio file
            user_prompt: Additional user context
            
        Returns:
            Dictionary containing detailed analysis results
        """
        try:
            # Start with Gemini 2.5 Pro for detailed analysis
            model = genai.GenerativeModel(self.models['pro'])
            
            # Prepare video file
            video_file = await self._upload_video_to_gemini(video_path)
            
            # Prepare character image if provided
            image_file = None
            if character_image_path and os.path.exists(character_image_path):
                image_file = await self._upload_image_to_gemini(character_image_path)
            
            # Create comprehensive analysis prompt
            analysis_prompt = self._create_analysis_prompt(user_prompt, bool(image_file))
            
            # Prepare input for Gemini
            input_parts = [analysis_prompt, video_file]
            if image_file:
                input_parts.append(image_file)
            
            # Generate analysis
            response = await self._generate_with_retry(model, input_parts)
            
            # Parse and structure the response
            analysis_result = self._parse_analysis_response(response.text)
            
            # Add metadata
            analysis_result['metadata'] = {
                'analyzed_at': datetime.utcnow().isoformat(),
                'model_used': self.models['pro'],
                'api_key_index': self.current_key_index,
                'has_character_image': bool(image_file),
                'has_audio_file': bool(audio_path),
                'user_prompt': user_prompt
            }
            
            logger.info(f"Video analysis completed for {video_path}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Video analysis failed: {str(e)}")
            # Try with Flash model as fallback
            try:
                return await self._fallback_analysis(video_path, character_image_path, user_prompt)
            except Exception as fallback_error:
                logger.error(f"Fallback analysis also failed: {str(fallback_error)}")
                return self._create_error_response(str(e))
    
    async def _upload_video_to_gemini(self, video_path: str) -> Any:
        """Upload video file to Gemini API"""
        try:
            video_file = genai.upload_file(
                path=video_path,
                mime_type="video/mp4"
            )
            
            # Wait for processing
            while video_file.state.name == "PROCESSING":
                await asyncio.sleep(1)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED":
                raise Exception("Video processing failed")
                
            return video_file
            
        except Exception as e:
            logger.error(f"Failed to upload video to Gemini: {str(e)}")
            raise
    
    async def _upload_image_to_gemini(self, image_path: str) -> Any:
        """Upload image file to Gemini API"""
        try:
            image_file = genai.upload_file(
                path=image_path,
                mime_type="image/jpeg"
            )
            return image_file
            
        except Exception as e:
            logger.error(f"Failed to upload image to Gemini: {str(e)}")
            raise
    
    def _create_analysis_prompt(self, user_prompt: str, has_character_image: bool) -> str:
        """Create comprehensive analysis prompt for Gemini"""
        prompt = f"""
        You are an expert video analyst. Analyze this video in extreme detail and provide a comprehensive analysis in JSON format.
        
        {f"User Context: {user_prompt}" if user_prompt else ""}
        {f"A character reference image is provided - use it to understand the character style and appearance." if has_character_image else ""}
        
        Provide analysis in this exact JSON structure:
        {{
            "video_overview": {{
                "title": "Brief descriptive title",
                "duration": "estimated duration in seconds",
                "genre": "video genre/style",
                "mood": "overall mood/tone",
                "target_audience": "intended audience"
            }},
            "visual_analysis": {{
                "scenes": [
                    {{
                        "scene_number": 1,
                        "timestamp": "00:00-00:10",
                        "description": "detailed scene description",
                        "characters": ["character descriptions"],
                        "setting": "environment/location",
                        "camera_angle": "camera movement/angle",
                        "lighting": "lighting conditions",
                        "colors": "dominant colors",
                        "objects": ["key objects/props"],
                        "actions": ["main actions/movements"]
                    }}
                ],
                "visual_style": "overall visual style",
                "aspect_ratio": "current aspect ratio",
                "quality": "video quality assessment"
            }},
            "audio_analysis": {{
                "speech": {{
                    "has_speech": true/false,
                    "language": "detected language",
                    "tone": "speaking tone",
                    "pace": "speaking pace",
                    "transcript": "approximate transcript if speech detected"
                }},
                "music": {{
                    "has_music": true/false,
                    "genre": "music genre",
                    "tempo": "tempo description",
                    "mood": "musical mood"
                }},
                "sound_effects": {{
                    "has_effects": true/false,
                    "types": ["types of sound effects"]
                }}
            }},
            "character_analysis": {{
                "main_characters": [
                    {{
                        "name": "character identifier",
                        "description": "physical description",
                        "clothing": "clothing description",
                        "expressions": ["facial expressions"],
                        "personality": "perceived personality traits",
                        "role": "role in video"
                    }}
                ],
                "character_consistency": "assessment of character consistency"
            }},
            "story_structure": {{
                "narrative_type": "story type",
                "beginning": "opening description",
                "middle": "development description", 
                "end": "conclusion description",
                "theme": "main themes",
                "message": "key message/purpose"
            }},
            "technical_details": {{
                "transitions": ["types of transitions used"],
                "effects": ["visual effects used"],
                "text_overlays": ["text content if any"],
                "animation_style": "animation type if applicable",
                "editing_pace": "editing rhythm"
            }},
            "similarity_requirements": {{
                "key_elements_to_replicate": ["most important elements to keep"],
                "style_requirements": ["style elements to maintain"],
                "mood_requirements": ["mood elements to preserve"],
                "character_requirements": ["character elements to replicate"],
                "story_requirements": ["story elements to maintain"]
            }}
        }}
        
        Be extremely detailed and thorough. This analysis will be used to create a similar video, so accuracy is crucial.
        Focus on elements that can be replicated while avoiding direct copying.
        """
        return prompt
    
    async def _generate_with_retry(self, model: Any, input_parts: List[Any], max_retries: int = 3) -> Any:
        """Generate content with retry logic and API key rotation"""
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    model.generate_content,
                    input_parts,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                )
                return response
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    if "quota" in str(e).lower() or "rate" in str(e).lower():
                        self.rotate_api_key()
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
    
    async def _fallback_analysis(self, video_path: str, character_image_path: Optional[str], 
                                user_prompt: str) -> Dict[str, Any]:
        """Fallback analysis using Gemini 2.5 Flash"""
        try:
            model = genai.GenerativeModel(self.models['flash'])
            
            # Simpler prompt for Flash model
            simple_prompt = f"""
            Analyze this video briefly and provide basic information in JSON format:
            {{
                "video_overview": {{
                    "title": "video title",
                    "duration": "duration",
                    "genre": "genre",
                    "mood": "mood"
                }},
                "key_scenes": ["scene 1", "scene 2", "scene 3"],
                "characters": ["character descriptions"],
                "story": "basic story description",
                "style": "visual style",
                "audio": "audio description"
            }}
            """
            
            video_file = await self._upload_video_to_gemini(video_path)
            input_parts = [simple_prompt, video_file]
            
            response = await self._generate_with_retry(model, input_parts)
            
            # Parse basic response
            basic_analysis = self._parse_basic_analysis(response.text)
            basic_analysis['metadata'] = {
                'analyzed_at': datetime.utcnow().isoformat(),
                'model_used': self.models['flash'],
                'fallback_analysis': True
            }
            
            return basic_analysis
            
        except Exception as e:
            logger.error(f"Fallback analysis failed: {str(e)}")
            raise
    
    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate the analysis response"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_text = response_text[json_start:json_end]
            
            analysis = json.loads(json_text)
            
            # Validate required fields
            required_fields = ['video_overview', 'visual_analysis', 'audio_analysis', 
                             'character_analysis', 'story_structure', 'technical_details', 
                             'similarity_requirements']
            
            for field in required_fields:
                if field not in analysis:
                    logger.warning(f"Missing required field: {field}")
                    analysis[field] = {}
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            return self._create_basic_analysis_from_text(response_text)
        except Exception as e:
            logger.error(f"Error parsing analysis response: {str(e)}")
            return self._create_basic_analysis_from_text(response_text)
    
    def _parse_basic_analysis(self, response_text: str) -> Dict[str, Any]:
        """Parse basic analysis from Flash model"""
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_text = response_text[json_start:json_end]
            
            return json.loads(json_text)
            
        except Exception as e:
            logger.error(f"Failed to parse basic analysis: {str(e)}")
            return self._create_basic_analysis_from_text(response_text)
    
    def _create_basic_analysis_from_text(self, text: str) -> Dict[str, Any]:
        """Create basic analysis structure from text when JSON parsing fails"""
        return {
            "video_overview": {
                "title": "Video Analysis",
                "duration": "unknown",
                "genre": "unknown",
                "mood": "unknown"
            },
            "raw_analysis": text,
            "parsing_error": True,
            "visual_analysis": {"scenes": []},
            "audio_analysis": {"speech": {"has_speech": False}},
            "character_analysis": {"main_characters": []},
            "story_structure": {"narrative_type": "unknown"},
            "technical_details": {"transitions": []},
            "similarity_requirements": {"key_elements_to_replicate": []}
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response structure"""
        return {
            "error": True,
            "error_message": error_message,
            "video_overview": {
                "title": "Analysis Failed",
                "duration": "unknown",
                "genre": "unknown",
                "mood": "unknown"
            },
            "visual_analysis": {"scenes": []},
            "audio_analysis": {"speech": {"has_speech": False}},
            "character_analysis": {"main_characters": []},
            "story_structure": {"narrative_type": "unknown"},
            "technical_details": {"transitions": []},
            "similarity_requirements": {"key_elements_to_replicate": []}
        }

# Global instance
video_analyzer = VideoAnalyzer()