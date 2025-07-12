"""
Video Generation Service
Main orchestrator for video generation using RunwayML and Veo models
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import json

from integrations.runway import runway_client, RunwayMLError
from integrations.veo import veo_client, VeoError
from services.model_selector import model_selector

logger = logging.getLogger(__name__)

class VideoGenerationError(Exception):
    """Custom exception for video generation errors"""
    pass

class VideoGenerationService:
    def __init__(self):
        self.active_generations = {}  # Track ongoing generations
        
    async def generate_video(
        self,
        video_id: str,
        video_analysis: Dict[str, Any],
        video_plan: Dict[str, Any],
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a video based on analysis and plan
        
        Args:
            video_id: Original video ID for tracking
            video_analysis: Results from Gemini video analysis
            video_plan: Generated video plan from AI
            user_preferences: Optional user preferences for generation
            
        Returns:
            Generation task information
        """
        try:
            # Create unique generation ID
            generation_id = f"gen_{video_id}_{uuid.uuid4().hex[:8]}"
            
            logger.info(f"Starting video generation {generation_id} for video {video_id}")
            
            # Analyze requirements
            requirements = model_selector.analyze_video_requirements(video_analysis, video_plan)
            
            # Apply user preferences if provided
            if user_preferences:
                requirements.update(user_preferences)
            
            # Select best model
            provider, model, reasoning = model_selector.select_best_model(requirements)
            
            # Extract generation prompt from plan
            prompt = self._extract_generation_prompt(video_plan, video_analysis)
            
            # Enhance prompt based on selected model
            if provider == "veo":
                prompt = await veo_client.enhance_prompt_for_veo(prompt, video_analysis)
            
            # Track generation
            generation_info = {
                "generation_id": generation_id,
                "video_id": video_id,
                "status": "STARTING",
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "requirements": requirements,
                "reasoning": reasoning,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            self.active_generations[generation_id] = generation_info
            
            # Start generation based on provider
            if provider == "runway":
                result = await self._generate_with_runway(generation_id, model, prompt, requirements)
            elif provider == "veo":
                result = await self._generate_with_veo(generation_id, model, prompt, video_analysis, requirements)
            else:
                raise VideoGenerationError(f"Unknown provider: {provider}")
            
            # Update tracking info
            generation_info.update(result)
            generation_info["status"] = "PROCESSING"
            generation_info["updated_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Video generation {generation_id} started successfully with {provider}/{model}")
            
            return generation_info
            
        except Exception as e:
            logger.error(f"Video generation failed for {video_id}: {str(e)}")
            
            # Ensure generation_id is defined
            if 'generation_id' in locals() and generation_id in self.active_generations:
                self.active_generations[generation_id]["status"] = "FAILED"
                self.active_generations[generation_id]["error"] = str(e)
                self.active_generations[generation_id]["updated_at"] = datetime.utcnow().isoformat()
            
            raise VideoGenerationError(f"Video generation failed: {str(e)}")
    
    def _extract_generation_prompt(self, video_plan: Dict[str, Any], video_analysis: Dict[str, Any]) -> str:
        """Extract or construct the generation prompt from plan and analysis"""
        try:
            # Try to get prompt from plan first
            plan_text = str(video_plan)
            
            if isinstance(video_plan, dict):
                # Look for specific prompt fields
                for key in ["prompt", "generation_prompt", "description", "summary"]:
                    if key in video_plan and video_plan[key]:
                        return str(video_plan[key])
            
            # Fallback: construct from analysis
            if isinstance(video_analysis, dict):
                analysis_text = str(video_analysis)
                
                # Try to extract key elements
                prompt_parts = []
                
                # Add video description if available
                for key in ["description", "summary", "content", "visual_description"]:
                    if key in video_analysis and video_analysis[key]:
                        prompt_parts.append(str(video_analysis[key]))
                        break
                
                # Add style information
                for key in ["style", "visual_style", "mood", "tone"]:
                    if key in video_analysis and video_analysis[key]:
                        prompt_parts.append(f"Style: {video_analysis[key]}")
                        break
                
                if prompt_parts:
                    return ". ".join(prompt_parts)
            
            # Ultimate fallback
            return f"Create a professional video based on the provided analysis and plan. " \
                   f"Video should be in 9:16 aspect ratio, high quality, and visually engaging."
                   
        except Exception as e:
            logger.warning(f"Error extracting prompt, using fallback: {str(e)}")
            return "Create a high-quality video in 9:16 aspect ratio"
    
    async def _generate_with_runway(
        self, 
        generation_id: str,
        model: str, 
        prompt: str, 
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate video using RunwayML"""
        try:
            duration = min(requirements.get("duration", 8), 10)  # Cap at 10s for Runway
            
            result = await runway_client.generate_with_retry(
                prompt=prompt,
                model=model,
                aspect_ratio="9:16",
                duration=duration,
                max_retries=2
            )
            
            return {
                "runway_task_id": result["task_id"],
                "estimated_duration": duration,
                "api_provider": "runway"
            }
            
        except RunwayMLError as e:
            logger.error(f"RunwayML generation failed for {generation_id}: {str(e)}")
            raise VideoGenerationError(f"RunwayML generation failed: {str(e)}")
    
    async def _generate_with_veo(
        self,
        generation_id: str,
        model: str,
        prompt: str,
        video_analysis: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate video using Google Veo"""
        try:
            duration = min(requirements.get("duration", 8), 8 if "2" in model else 10)
            
            if "2" in model:
                result = await veo_client.generate_video_veo2(
                    prompt=prompt,
                    aspect_ratio="9:16",
                    duration=duration
                )
            else:
                result = await veo_client.generate_video_veo3(
                    prompt=prompt,
                    aspect_ratio="9:16", 
                    duration=duration
                )
            
            return {
                "veo_task_id": result["task_id"],
                "estimated_duration": duration,
                "api_provider": "veo",
                "gemini_response": result.get("gemini_response")
            }
            
        except VeoError as e:
            logger.error(f"Veo generation failed for {generation_id}: {str(e)}")
            raise VideoGenerationError(f"Veo generation failed: {str(e)}")
    
    async def get_generation_status(self, generation_id: str) -> Dict[str, Any]:
        """Get the status of a video generation"""
        try:
            if generation_id not in self.active_generations:
                return {
                    "generation_id": generation_id,
                    "status": "NOT_FOUND",
                    "error": "Generation ID not found"
                }
            
            generation_info = self.active_generations[generation_id]
            provider = generation_info.get("provider")
            
            # Check status with appropriate provider
            if provider == "runway" and "runway_task_id" in generation_info:
                runway_status = await runway_client.get_task_status(generation_info["runway_task_id"])
                
                # Update our tracking
                generation_info["status"] = runway_status["status"]
                generation_info["progress"] = runway_status.get("progress", 0)
                generation_info["video_url"] = runway_status.get("video_url")
                generation_info["error"] = runway_status.get("error")
                generation_info["updated_at"] = datetime.utcnow().isoformat()
                
            elif provider == "veo" and "veo_task_id" in generation_info:
                veo_status = await veo_client.get_generation_status(generation_info["veo_task_id"])
                
                # Update our tracking
                generation_info["status"] = veo_status["status"]
                generation_info["progress"] = veo_status.get("progress", 0)
                generation_info["video_url"] = veo_status.get("video_url")
                generation_info["error"] = veo_status.get("error")
                generation_info["updated_at"] = datetime.utcnow().isoformat()
            
            return generation_info
            
        except Exception as e:
            logger.error(f"Error checking generation status for {generation_id}: {str(e)}")
            return {
                "generation_id": generation_id,
                "status": "ERROR",
                "error": str(e)
            }
    
    async def cancel_generation(self, generation_id: str) -> Dict[str, Any]:
        """Cancel an ongoing video generation"""
        try:
            if generation_id not in self.active_generations:
                return {"success": False, "error": "Generation not found"}
            
            generation_info = self.active_generations[generation_id]
            
            # Mark as cancelled
            generation_info["status"] = "CANCELLED"
            generation_info["updated_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Generation {generation_id} cancelled")
            
            return {"success": True, "message": "Generation cancelled"}
            
        except Exception as e:
            logger.error(f"Error cancelling generation {generation_id}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_all_generations(self, video_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all generations, optionally filtered by video_id"""
        try:
            generations = list(self.active_generations.values())
            
            if video_id:
                generations = [g for g in generations if g.get("video_id") == video_id]
            
            # Sort by creation time (newest first)
            generations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            return generations
            
        except Exception as e:
            logger.error(f"Error getting generations: {str(e)}")
            return []
    
    def cleanup_completed_generations(self, max_age_hours: int = 24):
        """Clean up old completed generations to free memory"""
        try:
            current_time = datetime.utcnow()
            to_remove = []
            
            for generation_id, info in self.active_generations.items():
                if info.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                    created_at = datetime.fromisoformat(info.get("created_at", current_time.isoformat()))
                    age_hours = (current_time - created_at).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        to_remove.append(generation_id)
            
            for generation_id in to_remove:
                del self.active_generations[generation_id]
                logger.info(f"Cleaned up old generation {generation_id}")
            
            return len(to_remove)
            
        except Exception as e:
            logger.error(f"Error during generation cleanup: {str(e)}")
            return 0

# Global instance
video_generation_service = VideoGenerationService()