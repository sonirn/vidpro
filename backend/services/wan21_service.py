"""
Wan 2.1 Video Generation Service

This service handles video generation using Wan 2.1 models.
It provides intelligent model selection and generation orchestration.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
from datetime import datetime
import uuid
import os

from integrations.wan21 import wan21_service, Wan21Model, Wan21Task
from database.mongodb_config import get_db

logger = logging.getLogger(__name__)

class Wan21VideoService:
    """Service for managing Wan 2.1 video generation"""
    
    def __init__(self):
        self.service = wan21_service
        
    async def select_optimal_model(self, 
                                 video_analysis: Dict[str, Any],
                                 has_character_image: bool = False,
                                 has_audio: bool = False) -> Wan21Model:
        """
        Select the optimal Wan 2.1 model based on video analysis
        
        Args:
            video_analysis: Analysis results from Gemini
            has_character_image: Whether character image is provided
            has_audio: Whether audio file is provided
            
        Returns:
            Selected Wan21Model
        """
        
        # Extract key characteristics from analysis
        complexity = video_analysis.get("complexity", "medium")
        motion_type = video_analysis.get("motion_type", "normal")
        scene_changes = video_analysis.get("scene_changes", [])
        resolution_preference = video_analysis.get("resolution_preference", "480p")
        
        # Decision logic based on analysis
        if has_character_image:
            # Use Image-to-Video model when character image is provided
            logger.info("Selected I2V-14B model due to character image availability")
            return Wan21Model.I2V_14B
        
        elif len(scene_changes) > 0 and complexity == "high":
            # Use larger model for complex scenes
            logger.info("Selected T2V-14B model due to high complexity")
            return Wan21Model.T2V_14B
        
        elif resolution_preference == "720p":
            # Use 14B model for high resolution
            logger.info("Selected T2V-14B model for 720p resolution")
            return Wan21Model.T2V_14B
        
        else:
            # Use lightweight model for simpler scenarios
            logger.info("Selected T2V-1.3B model for standard generation")
            return Wan21Model.T2V_1_3B
    
    async def generate_video_clips(self, 
                                 video_id: str,
                                 plan: Dict[str, Any],
                                 sample_video_path: str,
                                 character_image_path: Optional[str] = None,
                                 audio_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate video clips based on the plan
        
        Args:
            video_id: Video project ID
            plan: Generation plan from AI
            sample_video_path: Path to sample video
            character_image_path: Path to character image (optional)
            audio_path: Path to audio file (optional)
            
        Returns:
            Generation results
        """
        
        try:
            db = get_db()
            
            # Get video document
            video_doc = await db.videos.find_one({"video_id": video_id})
            if not video_doc:
                raise ValueError(f"Video {video_id} not found")
            
            # Extract analysis results
            analysis_result = video_doc.get("analysis_result", {})
            
            # Select optimal model
            selected_model = await self.select_optimal_model(
                analysis_result,
                has_character_image=bool(character_image_path),
                has_audio=bool(audio_path)
            )
            
            # Extract clips from plan
            clips = plan.get("clips", [])
            if not clips:
                raise ValueError("No clips found in generation plan")
            
            # Generate each clip
            generated_clips = []
            total_clips = len(clips)
            
            for i, clip in enumerate(clips):
                # Update progress
                progress = (i / total_clips) * 100
                await db.videos.update_one(
                    {"video_id": video_id},
                    {
                        "$set": {
                            "generation_status": "processing",
                            "progress": progress,
                            "current_clip": i + 1,
                            "total_clips": total_clips,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                # Generate clip
                clip_result = await self._generate_single_clip(
                    clip=clip,
                    selected_model=selected_model,
                    character_image_path=character_image_path,
                    clip_index=i,
                    video_id=video_id
                )
                
                generated_clips.append(clip_result)
                
                # Log progress
                logger.info(f"Generated clip {i+1}/{total_clips} for video {video_id}")
            
            # Combine clips using FFmpeg
            final_video_path = await self._combine_clips(generated_clips, video_id)
            
            # Update final status
            await db.videos.update_one(
                {"video_id": video_id},
                {
                    "$set": {
                        "generation_status": "complete",
                        "progress": 100,
                        "generated_video_path": final_video_path,
                        "generated_clips": generated_clips,
                        "model_used": selected_model.value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return {
                "success": True,
                "video_path": final_video_path,
                "clips_generated": len(generated_clips),
                "model_used": selected_model.value,
                "clips": generated_clips
            }
            
        except Exception as e:
            logger.error(f"Error generating video clips: {e}")
            
            # Update error status
            db = get_db()
            await db.videos.update_one(
                {"video_id": video_id},
                {
                    "$set": {
                        "generation_status": "failed",
                        "error_message": str(e),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_single_clip(self, 
                                  clip: Dict[str, Any],
                                  selected_model: Wan21Model,
                                  character_image_path: Optional[str],
                                  clip_index: int,
                                  video_id: str) -> Dict[str, Any]:
        """Generate a single video clip"""
        
        prompt = clip.get("prompt", "")
        duration = clip.get("duration", 5)  # Default 5 seconds
        
        # Determine generation method
        if selected_model == Wan21Model.I2V_14B and character_image_path:
            # Image-to-Video generation
            result = await self.service.generate_image_to_video(
                prompt=prompt,
                image_path=character_image_path,
                model=selected_model,
                size="1280*720"
            )
        else:
            # Text-to-Video generation
            size = "832*480" if selected_model == Wan21Model.T2V_1_3B else "1280*720"
            result = await self.service.generate_text_to_video(
                prompt=prompt,
                model=selected_model,
                size=size
            )
        
        # Add clip metadata
        result.update({
            "clip_index": clip_index,
            "video_id": video_id,
            "duration": duration,
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return result
    
    async def _combine_clips(self, clips: List[Dict[str, Any]], video_id: str) -> str:
        """Combine generated clips into final video using FFmpeg"""
        
        try:
            # Create output directory
            output_dir = Path(f"/tmp/wan21_output/{video_id}")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create file list for FFmpeg
            file_list_path = output_dir / "clips.txt"
            
            with open(file_list_path, 'w') as f:
                for clip in clips:
                    if clip.get("success") and clip.get("video_path"):
                        f.write(f"file '{clip['video_path']}'\n")
            
            # Output path
            final_output = output_dir / f"final_video_{video_id}.mp4"
            
            # FFmpeg command to concatenate clips
            ffmpeg_cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0",
                "-i", str(file_list_path),
                "-c", "copy",
                "-aspect", "9:16",  # Ensure 9:16 aspect ratio
                str(final_output)
            ]
            
            # Execute FFmpeg
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Successfully combined clips for video {video_id}")
                return str(final_output)
            else:
                logger.error(f"FFmpeg error: {stderr.decode()}")
                raise RuntimeError(f"Failed to combine clips: {stderr.decode()}")
                
        except Exception as e:
            logger.error(f"Error combining clips: {e}")
            raise
    
    async def get_generation_progress(self, video_id: str) -> Dict[str, Any]:
        """Get generation progress for a video"""
        
        try:
            db = get_db()
            video_doc = await db.videos.find_one({"video_id": video_id})
            
            if not video_doc:
                return {"error": "Video not found"}
            
            return {
                "video_id": video_id,
                "status": video_doc.get("generation_status", "pending"),
                "progress": video_doc.get("progress", 0),
                "current_clip": video_doc.get("current_clip", 0),
                "total_clips": video_doc.get("total_clips", 0),
                "model_used": video_doc.get("model_used", ""),
                "error_message": video_doc.get("error_message", ""),
                "updated_at": video_doc.get("updated_at")
            }
            
        except Exception as e:
            logger.error(f"Error getting generation progress: {e}")
            return {"error": str(e)}
    
    async def cancel_generation(self, video_id: str) -> Dict[str, Any]:
        """Cancel video generation"""
        
        try:
            db = get_db()
            
            # Update status to cancelled
            result = await db.videos.update_one(
                {"video_id": video_id},
                {
                    "$set": {
                        "generation_status": "cancelled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Generation cancelled for video {video_id}")
                return {"success": True, "message": "Generation cancelled"}
            else:
                return {"success": False, "message": "Video not found or already finished"}
                
        except Exception as e:
            logger.error(f"Error cancelling generation: {e}")
            return {"success": False, "error": str(e)}
    
    def get_model_recommendations(self, video_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get model recommendations based on video analysis"""
        
        recommendations = []
        
        # Analyze video characteristics
        complexity = video_analysis.get("complexity", "medium")
        motion_type = video_analysis.get("motion_type", "normal")
        scene_changes = video_analysis.get("scene_changes", [])
        
        # T2V-1.3B recommendation
        t2v_1_3b_score = 80
        if complexity == "low":
            t2v_1_3b_score += 15
        elif complexity == "high":
            t2v_1_3b_score -= 20
        
        recommendations.append({
            "model": Wan21Model.T2V_1_3B.value,
            "name": "Wan 2.1 T2V-1.3B",
            "score": t2v_1_3b_score,
            "reasoning": "Lightweight model suitable for simple scenes and fast generation",
            "pros": ["Fast generation", "Low VRAM usage", "Good for simple scenes"],
            "cons": ["Limited resolution", "Less detail in complex scenes"],
            "vram_required": "8.19GB",
            "estimated_time": "4 minutes for 5s video"
        })
        
        # T2V-14B recommendation
        t2v_14b_score = 75
        if complexity == "high":
            t2v_14b_score += 20
        elif complexity == "low":
            t2v_14b_score -= 10
        
        recommendations.append({
            "model": Wan21Model.T2V_14B.value,
            "name": "Wan 2.1 T2V-14B",
            "score": t2v_14b_score,
            "reasoning": "High-quality model for complex scenes and high resolution",
            "pros": ["High quality", "720p support", "Complex scene handling"],
            "cons": ["High VRAM usage", "Slower generation"],
            "vram_required": "24GB+",
            "estimated_time": "8-12 minutes for 5s video"
        })
        
        # I2V-14B recommendation (if character image available)
        i2v_14b_score = 85
        recommendations.append({
            "model": Wan21Model.I2V_14B.value,
            "name": "Wan 2.1 I2V-14B",
            "score": i2v_14b_score,
            "reasoning": "Best for character consistency with provided image",
            "pros": ["Character consistency", "High quality", "720p support"],
            "cons": ["Requires character image", "High VRAM usage"],
            "vram_required": "24GB+",
            "estimated_time": "6-10 minutes for 5s video"
        })
        
        # Sort by score
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        return recommendations

# Global service instance
wan21_video_service = Wan21VideoService()