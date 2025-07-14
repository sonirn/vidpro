"""
Video processing service for MongoDB-based video generation website
"""
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import uuid
import logging
from database.mongodb_config import get_db
from pathlib import Path
import aiofiles
import asyncio

logger = logging.getLogger(__name__)

class VideoService:
    def __init__(self):
        self.db = get_db()
        self.upload_dir = Path("/app/backend/uploads")
        self.upload_dir.mkdir(exist_ok=True)
        
    def create_video_record(self, user_id: str, video_id: str, file_path: str, 
                           character_image_path: str = "", audio_file_path: str = "",
                           user_prompt: str = "", file_size: int = 0) -> bool:
        """Create a new video record in database"""
        try:
            video_data = {
                "video_id": video_id,
                "user_id": user_id,
                "sample_video_path": file_path,
                "character_image_path": character_image_path,
                "audio_file_path": audio_file_path,
                "user_prompt": user_prompt,
                "upload_timestamp": datetime.utcnow(),
                "file_size": file_size,
                "duration": 0.0,  # Will be updated during analysis
                "analysis_status": "pending",
                "analysis_result": {},
                "plan_status": "pending",
                "generation_plan": {},
                "generation_status": "pending",
                "generated_video_path": "",
                "cloudflare_url": "",
                "expiry_date": datetime.utcnow() + timedelta(days=7),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "processing_started": False,
                "processing_progress": 0,
                "error_message": "",
                "clips_generated": [],
                "final_video_ready": False
            }
            
            result = self.db.videos.insert_one(video_data)
            return result.inserted_id is not None
            
        except Exception as e:
            logger.error(f"Failed to create video record: {e}")
            return False
    
    def update_video_status(self, video_id: str, updates: Dict[str, Any]) -> bool:
        """Update video status and progress"""
        try:
            updates["updated_at"] = datetime.utcnow()
            result = self.db.videos.update_one(
                {"video_id": video_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update video status: {e}")
            return False
    
    def get_video_by_id(self, video_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get video by ID for specific user"""
        try:
            video = self.db.videos.find_one(
                {"video_id": video_id, "user_id": user_id},
                {"_id": 0}  # Exclude MongoDB ObjectId
            )
            return video
        except Exception as e:
            logger.error(f"Failed to get video: {e}")
            return None
    
    def get_user_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get user's videos with pagination"""
        try:
            videos = list(self.db.videos.find(
                {"user_id": user_id},
                {"_id": 0}  # Exclude MongoDB ObjectId
            ).sort("created_at", -1).limit(limit))
            return videos
        except Exception as e:
            logger.error(f"Failed to get user videos: {e}")
            return []
    
    def check_video_expiry(self, video_id: str) -> Dict[str, Any]:
        """Check if video has expired (7-day access)"""
        try:
            video = self.db.videos.find_one({"video_id": video_id})
            if not video:
                return {"exists": False, "expired": True}
            
            expiry_date = video.get("expiry_date")
            if not expiry_date:
                return {"exists": True, "expired": True}
            
            is_expired = datetime.utcnow() > expiry_date
            days_remaining = (expiry_date - datetime.utcnow()).days if not is_expired else 0
            
            return {
                "exists": True,
                "expired": is_expired,
                "expiry_date": expiry_date,
                "days_remaining": max(0, days_remaining)
            }
        except Exception as e:
            logger.error(f"Failed to check video expiry: {e}")
            return {"exists": False, "expired": True}
    
    def extend_video_access(self, video_id: str, user_id: str, days: int = 7) -> bool:
        """Extend video access period"""
        try:
            new_expiry = datetime.utcnow() + timedelta(days=days)
            result = self.db.videos.update_one(
                {"video_id": video_id, "user_id": user_id},
                {"$set": {"expiry_date": new_expiry, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to extend video access: {e}")
            return False
    
    def cleanup_expired_videos(self) -> int:
        """Clean up expired videos and files"""
        try:
            expired_videos = list(self.db.videos.find({
                "expiry_date": {"$lt": datetime.utcnow()}
            }))
            
            cleanup_count = 0
            for video in expired_videos:
                try:
                    # Delete physical files
                    if video.get("sample_video_path"):
                        if os.path.exists(video["sample_video_path"]):
                            os.remove(video["sample_video_path"])
                    
                    if video.get("generated_video_path"):
                        if os.path.exists(video["generated_video_path"]):
                            os.remove(video["generated_video_path"])
                    
                    # Delete database record
                    self.db.videos.delete_one({"video_id": video["video_id"]})
                    cleanup_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup video {video['video_id']}: {e}")
            
            return cleanup_count
        except Exception as e:
            logger.error(f"Failed to cleanup expired videos: {e}")
            return 0

class PlanService:
    def __init__(self):
        self.db = get_db()
    
    def create_plan(self, video_id: str, user_id: str, plan_data: Dict[str, Any]) -> str:
        """Create a new video generation plan"""
        try:
            plan_id = str(uuid.uuid4())
            plan_record = {
                "plan_id": plan_id,
                "video_id": video_id,
                "user_id": user_id,
                "original_plan": plan_data,
                "current_plan": plan_data,
                "plan_version": 1,
                "modification_history": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "approved": False,
                "generation_started": False
            }
            
            result = self.db.plans.insert_one(plan_record)
            return plan_id if result.inserted_id else None
            
        except Exception as e:
            logger.error(f"Failed to create plan: {e}")
            return None
    
    def update_plan(self, plan_id: str, updated_plan: Dict[str, Any], 
                   modification_note: str = "") -> bool:
        """Update existing plan with user modifications"""
        try:
            plan = self.db.plans.find_one({"plan_id": plan_id})
            if not plan:
                return False
            
            # Create modification history entry
            modification_entry = {
                "timestamp": datetime.utcnow(),
                "previous_version": plan["plan_version"],
                "note": modification_note,
                "changes": updated_plan
            }
            
            # Update plan
            new_version = plan["plan_version"] + 1
            result = self.db.plans.update_one(
                {"plan_id": plan_id},
                {"$set": {
                    "current_plan": updated_plan,
                    "plan_version": new_version,
                    "updated_at": datetime.utcnow()
                },
                "$push": {"modification_history": modification_entry}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to update plan: {e}")
            return False
    
    def get_plan_by_video(self, video_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get plan for specific video"""
        try:
            plan = self.db.plans.find_one(
                {"video_id": video_id, "user_id": user_id},
                {"_id": 0}
            )
            return plan
        except Exception as e:
            logger.error(f"Failed to get plan: {e}")
            return None
    
    def approve_plan(self, plan_id: str, user_id: str) -> bool:
        """Approve plan for video generation"""
        try:
            result = self.db.plans.update_one(
                {"plan_id": plan_id, "user_id": user_id},
                {"$set": {
                    "approved": True,
                    "approved_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to approve plan: {e}")
            return False

class ChatService:
    def __init__(self):
        self.db = get_db()
    
    def create_chat_session(self, video_id: str, user_id: str) -> str:
        """Create new chat session for video plan modification"""
        try:
            session_id = str(uuid.uuid4())
            session_data = {
                "session_id": session_id,
                "video_id": video_id,
                "user_id": user_id,
                "messages": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "active": True
            }
            
            result = self.db.chat_sessions.insert_one(session_data)
            return session_id if result.inserted_id else None
            
        except Exception as e:
            logger.error(f"Failed to create chat session: {e}")
            return None
    
    def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Add message to chat session"""
        try:
            message["timestamp"] = datetime.utcnow()
            message["message_id"] = str(uuid.uuid4())
            
            result = self.db.chat_sessions.update_one(
                {"session_id": session_id},
                {"$push": {"messages": message},
                 "$set": {"updated_at": datetime.utcnow()}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False
    
    def get_chat_history(self, video_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get chat history for video"""
        try:
            session = self.db.chat_sessions.find_one(
                {"video_id": video_id, "user_id": user_id},
                {"_id": 0}
            )
            return session.get("messages", []) if session else []
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

class TaskService:
    def __init__(self):
        self.db = get_db()
    
    def create_task(self, video_id: str, user_id: str, task_type: str, 
                   estimated_duration: int = 300) -> str:
        """Create background processing task"""
        try:
            task_id = str(uuid.uuid4())
            task_data = {
                "task_id": task_id,
                "video_id": video_id,
                "user_id": user_id,
                "task_type": task_type,  # 'analysis', 'planning', 'generation', 'processing'
                "status": "pending",
                "progress": 0,
                "current_step": "Initializing",
                "estimated_completion": datetime.utcnow() + timedelta(seconds=estimated_duration),
                "actual_completion": None,
                "error_message": "",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "retry_count": 0,
                "max_retries": 3
            }
            
            result = self.db.generation_tasks.insert_one(task_data)
            return task_id if result.inserted_id else None
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return None
    
    def update_task_progress(self, task_id: str, progress: int, 
                            current_step: str = "", status: str = "processing") -> bool:
        """Update task progress"""
        try:
            updates = {
                "progress": min(100, max(0, progress)),
                "current_step": current_step,
                "status": status,
                "updated_at": datetime.utcnow()
            }
            
            if progress >= 100:
                updates["status"] = "complete"
                updates["actual_completion"] = datetime.utcnow()
            
            result = self.db.generation_tasks.update_one(
                {"task_id": task_id},
                {"$set": updates}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to update task progress: {e}")
            return False
    
    def fail_task(self, task_id: str, error_message: str) -> bool:
        """Mark task as failed"""
        try:
            result = self.db.generation_tasks.update_one(
                {"task_id": task_id},
                {"$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "actual_completion": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                "$inc": {"retry_count": 1}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to fail task: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        try:
            task = self.db.generation_tasks.find_one(
                {"task_id": task_id},
                {"_id": 0}
            )
            return task
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return None
    
    def get_user_tasks(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent tasks"""
        try:
            tasks = list(self.db.generation_tasks.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit))
            return tasks
        except Exception as e:
            logger.error(f"Failed to get user tasks: {e}")
            return []

# Global service instances
video_service = VideoService()
plan_service = PlanService()
chat_service = ChatService()
task_service = TaskService()

def get_video_service():
    return video_service

def get_plan_service():
    return plan_service

def get_chat_service():
    return chat_service

def get_task_service():
    return task_service