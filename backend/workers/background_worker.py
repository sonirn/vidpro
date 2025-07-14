"""
Background task worker system for video processing
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from services.video_service import get_video_service, get_task_service
from database.mongodb_config import get_db

logger = logging.getLogger(__name__)

class BackgroundTaskWorker:
    def __init__(self):
        self.db = get_db()
        self.video_service = get_video_service()
        self.task_service = get_task_service()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.running = False
        self.worker_thread = None
        
    def start(self):
        """Start the background worker"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._run_worker, daemon=True)
            self.worker_thread.start()
            logger.info("Background task worker started")
    
    def stop(self):
        """Stop the background worker"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
        logger.info("Background task worker stopped")
    
    def _run_worker(self):
        """Main worker loop"""
        while self.running:
            try:
                # Get pending tasks
                pending_tasks = list(self.db.generation_tasks.find({
                    "status": "pending",
                    "retry_count": {"$lt": 3}
                }).sort("created_at", 1).limit(5))
                
                if pending_tasks:
                    # Process tasks concurrently
                    futures = []
                    for task in pending_tasks:
                        future = self.executor.submit(self._process_task, task)
                        futures.append(future)
                    
                    # Wait for completion (with timeout)
                    for future in futures:
                        try:
                            future.result(timeout=30)  # 30 second timeout per task
                        except Exception as e:
                            logger.error(f"Task processing failed: {e}")
                
                # Sleep before next check
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(10)  # Longer sleep on error
    
    def _process_task(self, task: Dict[str, Any]):
        """Process a single task"""
        task_id = task["task_id"]
        task_type = task["task_type"]
        
        logger.info(f"Processing task {task_id} of type {task_type}")
        
        try:
            # Update task status to processing
            self.task_service.update_task_progress(
                task_id, 0, "Starting processing", "processing"
            )
            
            # Route to appropriate processor
            if task_type == "analysis":
                self._process_analysis_task(task)
            elif task_type == "planning":
                self._process_planning_task(task)
            elif task_type == "generation":
                self._process_generation_task(task)
            elif task_type == "processing":
                self._process_video_processing_task(task)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            # Mark as complete
            self.task_service.update_task_progress(task_id, 100, "Completed", "complete")
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.task_service.fail_task(task_id, str(e))
    
    def _process_analysis_task(self, task: Dict[str, Any]):
        """Process video analysis task"""
        video_id = task["video_id"]
        user_id = task["user_id"]
        
        # Get video details
        video = self.video_service.get_video_by_id(video_id, user_id)
        if not video:
            raise ValueError("Video not found")
        
        # Update progress
        self.task_service.update_task_progress(
            task["task_id"], 10, "Loading video file"
        )
        
        # Simulate analysis process (replace with actual Gemini integration)
        import time
        time.sleep(2)  # Simulate processing time
        
        self.task_service.update_task_progress(
            task["task_id"], 30, "Analyzing video content"
        )
        
        # Mock analysis result
        analysis_result = {
            "visual_analysis": {
                "scenes": ["Opening scene", "Main content", "Closing scene"],
                "color_palette": ["#FF6B6B", "#4ECDC4", "#45B7D1"],
                "composition": "Vertical 9:16 format",
                "lighting": "Natural daylight"
            },
            "content_analysis": {
                "theme": "Educational content",
                "mood": "Informative and engaging",
                "target_audience": "General audience",
                "key_moments": ["Introduction", "Main points", "Conclusion"]
            },
            "technical_analysis": {
                "resolution": "1080x1920",
                "frame_rate": 30,
                "duration": 45.5,
                "quality": "High"
            }
        }
        
        self.task_service.update_task_progress(
            task["task_id"], 80, "Generating analysis report"
        )
        
        # Update video with analysis result
        self.video_service.update_video_status(video_id, {
            "analysis_status": "complete",
            "analysis_result": analysis_result,
            "duration": 45.5
        })
        
        # Create follow-up planning task
        planning_task_id = self.task_service.create_task(
            video_id, user_id, "planning", 120
        )
        
        logger.info(f"Analysis complete for video {video_id}, planning task {planning_task_id} created")
    
    def _process_planning_task(self, task: Dict[str, Any]):
        """Process video planning task"""
        video_id = task["video_id"]
        user_id = task["user_id"]
        
        # Get video with analysis
        video = self.video_service.get_video_by_id(video_id, user_id)
        if not video or video.get("analysis_status") != "complete":
            raise ValueError("Video analysis not complete")
        
        self.task_service.update_task_progress(
            task["task_id"], 20, "Creating generation plan"
        )
        
        # Mock plan generation (replace with actual Gemini integration)
        generation_plan = {
            "video_concept": "Similar video with new content",
            "clip_breakdown": [
                {
                    "clip_id": "clip_001",
                    "description": "Opening scene with introduction",
                    "duration": 8,
                    "style": "Clean and modern",
                    "text_overlay": "Welcome message"
                },
                {
                    "clip_id": "clip_002", 
                    "description": "Main content demonstration",
                    "duration": 30,
                    "style": "Educational focus",
                    "text_overlay": "Key points"
                },
                {
                    "clip_id": "clip_003",
                    "description": "Closing with call to action",
                    "duration": 12,
                    "style": "Engaging conclusion",
                    "text_overlay": "Thank you message"
                }
            ],
            "visual_requirements": {
                "aspect_ratio": "9:16",
                "resolution": "1080x1920",
                "style": "Modern and clean",
                "colors": ["#FF6B6B", "#4ECDC4", "#45B7D1"]
            },
            "audio_requirements": {
                "voiceover": "Professional narrator",
                "background_music": "Upbeat and modern",
                "sound_effects": "Minimal and clean"
            },
            "technical_specs": {
                "total_duration": 50,
                "frame_rate": 30,
                "quality": "High"
            }
        }
        
        self.task_service.update_task_progress(
            task["task_id"], 80, "Finalizing plan"
        )
        
        # Update video with plan
        self.video_service.update_video_status(video_id, {
            "plan_status": "generated",
            "generation_plan": generation_plan
        })
        
        logger.info(f"Planning complete for video {video_id}")
    
    def _process_generation_task(self, task: Dict[str, Any]):
        """Process video generation task"""
        video_id = task["video_id"]
        user_id = task["user_id"]
        
        # Get video with plan
        video = self.video_service.get_video_by_id(video_id, user_id)
        if not video or video.get("plan_status") not in ["generated", "modified", "approved"]:
            raise ValueError("Video plan not ready")
        
        self.task_service.update_task_progress(
            task["task_id"], 10, "Initializing video generation"
        )
        
        # Mock generation process (replace with actual Wan 2.1 integration)
        plan = video.get("generation_plan", {})
        clips = plan.get("clip_breakdown", [])
        
        generated_clips = []
        for i, clip in enumerate(clips):
            progress = 20 + (i * 50 // len(clips))
            self.task_service.update_task_progress(
                task["task_id"], progress, f"Generating clip {i+1}/{len(clips)}"
            )
            
            # Simulate clip generation
            time.sleep(3)  # Simulate processing time
            
            generated_clips.append({
                "clip_id": clip["clip_id"],
                "path": f"/app/backend/output/wan21/{video_id}_clip_{i+1}.mp4",
                "duration": clip["duration"],
                "status": "generated"
            })
        
        self.task_service.update_task_progress(
            task["task_id"], 80, "Combining clips"
        )
        
        # Update video with generation progress
        self.video_service.update_video_status(video_id, {
            "generation_status": "processing",
            "clips_generated": generated_clips
        })
        
        # Create video processing task
        processing_task_id = self.task_service.create_task(
            video_id, user_id, "processing", 180
        )
        
        logger.info(f"Generation complete for video {video_id}, processing task {processing_task_id} created")
    
    def _process_video_processing_task(self, task: Dict[str, Any]):
        """Process final video assembly task"""
        video_id = task["video_id"]
        user_id = task["user_id"]
        
        # Get video with generated clips
        video = self.video_service.get_video_by_id(video_id, user_id)
        if not video or video.get("generation_status") != "processing":
            raise ValueError("Video generation not complete")
        
        self.task_service.update_task_progress(
            task["task_id"], 20, "Assembling final video"
        )
        
        # Mock video processing (replace with actual FFmpeg integration)
        time.sleep(5)  # Simulate processing time
        
        final_video_path = f"/app/backend/output/wan21/{video_id}_final.mp4"
        
        self.task_service.update_task_progress(
            task["task_id"], 60, "Applying effects and transitions"
        )
        
        time.sleep(3)  # Simulate processing time
        
        self.task_service.update_task_progress(
            task["task_id"], 80, "Uploading to storage"
        )
        
        # Mock upload to Cloudflare R2
        cloudflare_url = f"https://r2.cloudflare.com/video-generation-bucket/{video_id}_final.mp4"
        
        # Update video with final result
        self.video_service.update_video_status(video_id, {
            "generation_status": "complete",
            "generated_video_path": final_video_path,
            "cloudflare_url": cloudflare_url,
            "final_video_ready": True,
            "processing_progress": 100
        })
        
        logger.info(f"Video processing complete for video {video_id}")

# Global worker instance
background_worker = BackgroundTaskWorker()

def get_background_worker():
    return background_worker

def start_background_worker():
    background_worker.start()

def stop_background_worker():
    background_worker.stop()