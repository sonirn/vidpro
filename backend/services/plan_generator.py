"""
Plan Generation Service using Gemini 2.5 Pro/Flash for video generation planning
"""
import os
import logging
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)

class PlanGenerator:
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
    
    async def generate_plan(self, analysis_result: Dict[str, Any], 
                          user_prompt: str = "") -> Dict[str, Any]:
        """
        Generate comprehensive video generation plan based on analysis
        
        Args:
            analysis_result: Video analysis from VideoAnalyzer
            user_prompt: Additional user requirements
            
        Returns:
            Dictionary containing detailed generation plan
        """
        try:
            model = genai.GenerativeModel(self.models['pro'])
            
            # Create plan generation prompt
            plan_prompt = self._create_plan_prompt(analysis_result, user_prompt)
            
            # Generate plan
            response = await self._generate_with_retry(model, [plan_prompt])
            
            # Parse and structure the response
            plan_result = self._parse_plan_response(response.text)
            
            # Add metadata
            plan_result['metadata'] = {
                'generated_at': datetime.utcnow().isoformat(),
                'model_used': self.models['pro'],
                'api_key_index': self.current_key_index,
                'user_prompt': user_prompt,
                'original_analysis': analysis_result.get('metadata', {})
            }
            
            logger.info("Video generation plan created successfully")
            return plan_result
            
        except Exception as e:
            logger.error(f"Plan generation failed: {str(e)}")
            # Try with Flash model as fallback
            try:
                return await self._fallback_plan_generation(analysis_result, user_prompt)
            except Exception as fallback_error:
                logger.error(f"Fallback plan generation also failed: {str(fallback_error)}")
                return self._create_error_response(str(e))
    
    async def modify_plan(self, current_plan: Dict[str, Any], 
                         modification_request: str) -> Dict[str, Any]:
        """
        Modify existing plan based on user feedback
        
        Args:
            current_plan: Current plan to modify
            modification_request: User's modification request
            
        Returns:
            Modified plan
        """
        try:
            model = genai.GenerativeModel(self.models['flash'])
            
            # Create modification prompt
            modification_prompt = self._create_modification_prompt(current_plan, modification_request)
            
            # Generate modified plan
            response = await self._generate_with_retry(model, [modification_prompt])
            
            # Parse response
            modified_plan = self._parse_plan_response(response.text)
            
            # Update metadata
            modified_plan['metadata'] = current_plan.get('metadata', {})
            modified_plan['metadata']['modified_at'] = datetime.utcnow().isoformat()
            modified_plan['metadata']['modification_request'] = modification_request
            
            # Track modification history
            if 'modification_history' not in modified_plan:
                modified_plan['modification_history'] = []
            
            modified_plan['modification_history'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'request': modification_request,
                'version': len(modified_plan['modification_history']) + 1
            })
            
            logger.info("Plan modification completed successfully")
            return modified_plan
            
        except Exception as e:
            logger.error(f"Plan modification failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def _create_plan_prompt(self, analysis_result: Dict[str, Any], user_prompt: str) -> str:
        """Create comprehensive plan generation prompt"""
        prompt = f"""
        You are an expert video generation planner. Based on the provided video analysis, create a detailed plan to generate a SIMILAR video (not a copy) that maintains the essence while being original.

        Original Video Analysis:
        {json.dumps(analysis_result, indent=2)}

        {f"User Requirements: {user_prompt}" if user_prompt else ""}

        Create a comprehensive video generation plan in this exact JSON structure:
        {{
            "project_overview": {{
                "title": "Generated video title",
                "concept": "Core concept/theme",
                "target_duration": "target duration in seconds (max 60)",
                "aspect_ratio": "9:16",
                "style": "visual style to achieve",
                "mood": "target mood/tone",
                "difficulty_level": "generation complexity (easy/medium/hard)"
            }},
            "script_outline": {{
                "theme": "main theme/message",
                "storyline": "story progression",
                "key_moments": [
                    {{
                        "moment": "key moment description",
                        "timing": "when it should happen",
                        "importance": "why it's important"
                    }}
                ],
                "dialogue_notes": "speech/dialogue requirements",
                "narrative_structure": "how story unfolds"
            }},
            "character_requirements": {{
                "main_characters": [
                    {{
                        "name": "character identifier",
                        "description": "physical description",
                        "clothing": "clothing style",
                        "personality": "personality traits",
                        "role": "role in video",
                        "consistency_notes": "how to maintain consistency"
                    }}
                ],
                "character_consistency": "overall consistency requirements"
            }},
            "visual_requirements": {{
                "scenes": [
                    {{
                        "scene_number": 1,
                        "description": "scene description",
                        "duration": "scene duration",
                        "setting": "location/environment",
                        "lighting": "lighting setup",
                        "camera_angle": "camera position/movement",
                        "colors": "color palette",
                        "props": ["required props/objects"],
                        "actions": ["main actions/movements"],
                        "visual_style": "specific visual style notes"
                    }}
                ],
                "transitions": [
                    {{
                        "from_scene": 1,
                        "to_scene": 2,
                        "type": "transition type",
                        "duration": "transition duration"
                    }}
                ],
                "effects": [
                    {{
                        "type": "effect type",
                        "application": "when/where to apply",
                        "intensity": "effect strength"
                    }}
                ]
            }},
            "audio_requirements": {{
                "speech": {{
                    "required": true/false,
                    "style": "speaking style",
                    "tone": "voice tone",
                    "pace": "speaking pace",
                    "script": "approximate script if needed"
                }},
                "music": {{
                    "required": true/false,
                    "genre": "music genre",
                    "mood": "musical mood",
                    "tempo": "tempo requirement",
                    "integration": "how to integrate with video"
                }},
                "sound_effects": {{
                    "required": true/false,
                    "types": ["sound effect types needed"],
                    "timing": "when to apply effects"
                }}
            }},
            "technical_specifications": {{
                "video_format": "MP4",
                "resolution": "720p minimum",
                "aspect_ratio": "9:16",
                "frame_rate": "30fps",
                "quality_settings": "high quality, no watermarks",
                "compression": "balanced quality/size"
            }},
            "generation_strategy": {{
                "approach": "generation approach (text-to-video, image-to-video, etc.)",
                "model_preference": "Wan 2.1 model type to use",
                "clip_breakdown": [
                    {{
                        "clip_id": "clip_1",
                        "description": "what to generate",
                        "duration": "clip duration",
                        "prompt": "generation prompt",
                        "style_notes": "style specifications",
                        "character_notes": "character requirements"
                    }}
                ],
                "quality_checkpoints": ["quality validation points"],
                "fallback_options": ["backup plans if generation fails"]
            }},
            "editing_requirements": {{
                "clip_sequencing": "how to arrange clips",
                "transitions": "transition requirements",
                "effects": "post-processing effects",
                "color_correction": "color adjustment needs",
                "audio_sync": "audio synchronization requirements",
                "final_polish": "final editing touches"
            }},
            "quality_assurance": {{
                "similarity_targets": ["elements that must be similar to original"],
                "originality_requirements": ["what must be different/original"],
                "quality_standards": ["quality benchmarks to meet"],
                "validation_checklist": ["final validation steps"]
            }}
        }}

        IMPORTANT REQUIREMENTS:
        1. Video must be 9:16 aspect ratio
        2. Duration must be under 60 seconds
        3. Must be similar to original but NOT a copy
        4. No watermarks or logos
        5. High quality output
        6. Consider using Wan 2.1 model capabilities
        7. Break down into manageable clips for generation
        8. Ensure character consistency if characters are present
        9. Match the mood and style while being original
        10. Plan for automated generation process
        """
        return prompt
    
    def _create_modification_prompt(self, current_plan: Dict[str, Any], 
                                  modification_request: str) -> str:
        """Create prompt for plan modification"""
        prompt = f"""
        You are modifying a video generation plan based on user feedback.
        
        Current Plan:
        {json.dumps(current_plan, indent=2)}
        
        User Modification Request:
        {modification_request}
        
        Modify the plan according to the user's request while maintaining the overall structure and feasibility.
        Return the complete modified plan in the same JSON format as the original.
        
        Ensure that:
        1. The modification is technically feasible
        2. The plan remains coherent and logical
        3. Quality standards are maintained
        4. The 9:16 aspect ratio and 60s duration limits are respected
        5. The modification enhances the overall video quality
        
        Return the complete modified plan in JSON format.
        """
        return prompt
    
    async def _generate_with_retry(self, model: Any, input_parts: List[str], 
                                 max_retries: int = 3) -> Any:
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
    
    async def _fallback_plan_generation(self, analysis_result: Dict[str, Any], 
                                      user_prompt: str) -> Dict[str, Any]:
        """Fallback plan generation using Flash model"""
        try:
            model = genai.GenerativeModel(self.models['flash'])
            
            # Simpler prompt for Flash model
            simple_prompt = f"""
            Create a basic video generation plan based on this analysis:
            {json.dumps(analysis_result.get('video_overview', {}), indent=2)}
            
            User requirements: {user_prompt}
            
            Provide a simple plan in JSON format with these sections:
            - project_overview
            - script_outline
            - visual_requirements
            - audio_requirements
            - generation_strategy
            
            Keep it simple but comprehensive.
            """
            
            response = await self._generate_with_retry(model, [simple_prompt])
            
            # Parse basic response
            basic_plan = self._parse_plan_response(response.text)
            basic_plan['metadata'] = {
                'generated_at': datetime.utcnow().isoformat(),
                'model_used': self.models['flash'],
                'fallback_plan': True
            }
            
            return basic_plan
            
        except Exception as e:
            logger.error(f"Fallback plan generation failed: {str(e)}")
            raise
    
    def _parse_plan_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate the plan response"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_text = response_text[json_start:json_end]
            
            plan = json.loads(json_text)
            
            # Validate required fields
            required_fields = ['project_overview', 'script_outline', 'visual_requirements', 
                             'audio_requirements', 'generation_strategy']
            
            for field in required_fields:
                if field not in plan:
                    logger.warning(f"Missing required field: {field}")
                    plan[field] = {}
            
            # Ensure clip breakdown exists
            if 'clip_breakdown' not in plan.get('generation_strategy', {}):
                plan['generation_strategy']['clip_breakdown'] = []
            
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            return self._create_basic_plan_from_text(response_text)
        except Exception as e:
            logger.error(f"Error parsing plan response: {str(e)}")
            return self._create_basic_plan_from_text(response_text)
    
    def _create_basic_plan_from_text(self, text: str) -> Dict[str, Any]:
        """Create basic plan structure from text when JSON parsing fails"""
        return {
            "project_overview": {
                "title": "Generated Video Plan",
                "concept": "Video generation plan",
                "target_duration": "60",
                "aspect_ratio": "9:16",
                "style": "similar to original",
                "mood": "engaging"
            },
            "script_outline": {
                "theme": "Similar to original video",
                "storyline": "Follow original structure"
            },
            "visual_requirements": {
                "scenes": [],
                "transitions": [],
                "effects": []
            },
            "audio_requirements": {
                "speech": {"required": False},
                "music": {"required": False},
                "sound_effects": {"required": False}
            },
            "generation_strategy": {
                "approach": "text-to-video",
                "model_preference": "Wan 2.1",
                "clip_breakdown": []
            },
            "raw_plan": text,
            "parsing_error": True
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response structure"""
        return {
            "error": True,
            "error_message": error_message,
            "project_overview": {
                "title": "Plan Generation Failed",
                "concept": "Error occurred",
                "target_duration": "60",
                "aspect_ratio": "9:16"
            },
            "script_outline": {"theme": "Error"},
            "visual_requirements": {"scenes": []},
            "audio_requirements": {"speech": {"required": False}},
            "generation_strategy": {"clip_breakdown": []}
        }

# Global instance
plan_generator = PlanGenerator()