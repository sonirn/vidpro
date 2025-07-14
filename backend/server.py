from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import asyncio
import aiofiles
import json
import tempfile
import shutil
from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
import random
import mimetypes

# Import MongoDB configuration and authentication
from database.mongodb_config import initialize_database, get_db
from auth.supabase_auth import get_auth, verify_token, SupabaseAuthUser

# Import video processing services
from services.video_analyzer import video_analyzer
from services.plan_generator import plan_generator
from services.wan21_service import wan21_video_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MongoDB database
initialize_database()

# Create the main app
app = FastAPI(title="Video Generation API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication middleware
security = HTTPBearer()

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> SupabaseAuthUser:
    """Get current authenticated user from Supabase"""
    try:
        user = await verify_token(token.credentials)
        return user
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

# Pydantic models for API requests
class VideoUploadRequest(BaseModel):
    filename: str
    context: Optional[str] = None

class VideoUploadResponse(BaseModel):
    video_id: str
    status: str
    message: str
    
class VideoAnalysisRequest(BaseModel):
    video_id: str
    
class PlanGenerationRequest(BaseModel):
    video_id: str
    user_prompt: Optional[str] = ""
    
class PlanModificationRequest(BaseModel):
    video_id: str
    modification_request: str

class ChatMessageRequest(BaseModel):
    message: str
    video_id: str

class VideoGenerationRequest(BaseModel):
    video_id: str
    model_preference: Optional[str] = "auto"  # "t2v-1.3b", "i2v-14b", "flf2v-14b", "auto"

class SignUpRequest(BaseModel):
    email: str
    password: str

class SignInRequest(BaseModel):
    email: str
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Video upload endpoint with multiple files
@api_router.post("/upload-video")
async def upload_video_files(
    video_file: UploadFile = File(...),
    character_image: Optional[UploadFile] = File(None),
    audio_file: Optional[UploadFile] = File(None),
    user_prompt: Optional[str] = "",
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Upload video, character image, and audio files"""
    try:
        # Validate video file
        if not video_file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="Invalid video file type")
        
        # Create video ID
        video_id = str(uuid.uuid4())
        
        # Create uploads directory
        uploads_dir = Path("/app/backend/uploads")
        uploads_dir.mkdir(exist_ok=True)
        
        # Save video file
        video_path = uploads_dir / f"{video_id}_video.mp4"
        async with aiofiles.open(video_path, 'wb') as f:
            content = await video_file.read()
            await f.write(content)
        
        # Save character image if provided
        character_image_path = None
        if character_image:
            if not character_image.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="Invalid image file type")
            
            character_image_path = uploads_dir / f"{video_id}_character.jpg"
            async with aiofiles.open(character_image_path, 'wb') as f:
                content = await character_image.read()
                await f.write(content)
        
        # Save audio file if provided
        audio_path = None
        if audio_file:
            if not audio_file.content_type.startswith('audio/'):
                raise HTTPException(status_code=400, detail="Invalid audio file type")
            
            audio_path = uploads_dir / f"{video_id}_audio.mp3"
            async with aiofiles.open(audio_path, 'wb') as f:
                content = await audio_file.read()
                await f.write(content)
        
        # Save to database
        db = get_db()
        video_doc = {
            "video_id": video_id,
            "user_id": current_user.id,
            "sample_video_path": str(video_path),
            "character_image_path": str(character_image_path) if character_image_path else None,
            "audio_file_path": str(audio_path) if audio_path else None,
            "user_prompt": user_prompt or "",
            "upload_timestamp": datetime.utcnow(),
            "file_size": video_file.size,
            "duration": 0,  # Will be updated after analysis
            "analysis_status": "pending",
            "analysis_result": {},
            "plan_status": "pending",
            "generation_plan": {},
            "generation_status": "pending",
            "generated_video_path": "",
            "cloudflare_url": "",
            "expiry_date": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.videos.insert_one(video_doc)
        
        return VideoUploadResponse(
            video_id=video_id,
            status="uploaded",
            message="Video uploaded successfully. Analysis will begin shortly."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# Video analysis endpoint
@api_router.post("/analyze-video")
async def analyze_video(
    request: VideoAnalysisRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Analyze uploaded video using Gemini AI"""
    try:
        db = get_db()
        
        # Get video from database
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Update status to processing
        await db.videos.update_one(
            {"video_id": request.video_id},
            {"$set": {"analysis_status": "processing", "updated_at": datetime.utcnow()}}
        )
        
        # Analyze video
        analysis_result = await video_analyzer.analyze_video(
            video_path=video["sample_video_path"],
            character_image_path=video.get("character_image_path"),
            audio_path=video.get("audio_file_path"),
            user_prompt=video.get("user_prompt", "")
        )
        
        # Update database with analysis results
        await db.videos.update_one(
            {"video_id": request.video_id},
            {
                "$set": {
                    "analysis_status": "complete",
                    "analysis_result": analysis_result,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "video_id": request.video_id,
            "status": "analysis_complete",
            "analysis_result": analysis_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video analysis error: {e}")
        # Update status to failed
        db = get_db()
        await db.videos.update_one(
            {"video_id": request.video_id},
            {"$set": {"analysis_status": "failed", "updated_at": datetime.utcnow()}}
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# Plan generation endpoint
@api_router.post("/generate-plan")
async def generate_plan(
    request: PlanGenerationRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Generate video generation plan based on analysis"""
    try:
        db = get_db()
        
        # Get video from database
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        if video.get("analysis_status") != "complete":
            raise HTTPException(status_code=400, detail="Video analysis not complete")
        
        # Update status to processing
        await db.videos.update_one(
            {"video_id": request.video_id},
            {"$set": {"plan_status": "processing", "updated_at": datetime.utcnow()}}
        )
        
        # Generate plan
        plan_result = await plan_generator.generate_plan(
            analysis_result=video["analysis_result"],
            user_prompt=request.user_prompt
        )
        
        # Update database with plan
        await db.videos.update_one(
            {"video_id": request.video_id},
            {
                "$set": {
                    "plan_status": "complete",
                    "generation_plan": plan_result,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "video_id": request.video_id,
            "status": "plan_generated",
            "plan": plan_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plan generation error: {e}")
        # Update status to failed
        db = get_db()
        await db.videos.update_one(
            {"video_id": request.video_id},
            {"$set": {"plan_status": "failed", "updated_at": datetime.utcnow()}}
        )
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {str(e)}")

# Plan modification endpoint
@api_router.post("/modify-plan")
async def modify_plan(
    request: PlanModificationRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Modify existing plan based on user feedback"""
    try:
        db = get_db()
        
        # Get video from database
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        if video.get("plan_status") not in ["complete", "modified"]:
            raise HTTPException(status_code=400, detail="No plan available to modify")
        
        # Modify plan
        modified_plan = await plan_generator.modify_plan(
            current_plan=video["generation_plan"],
            modification_request=request.modification_request
        )
        
        # Update database with modified plan
        await db.videos.update_one(
            {"video_id": request.video_id},
            {
                "$set": {
                    "plan_status": "modified",
                    "generation_plan": modified_plan,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "video_id": request.video_id,
            "status": "plan_modified",
            "modified_plan": modified_plan
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plan modification error: {e}")
        raise HTTPException(status_code=500, detail=f"Plan modification failed: {str(e)}")

# Get video info endpoint
@api_router.get("/video/{video_id}")
async def get_video_info(
    video_id: str,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get video information and status"""
    try:
        db = get_db()
        video = await db.videos.find_one({
            "video_id": video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {
            "video_id": video_id,
            "upload_timestamp": video.get("upload_timestamp"),
            "analysis_status": video.get("analysis_status"),
            "plan_status": video.get("plan_status"),
            "generation_status": video.get("generation_status"),
            "expiry_date": video.get("expiry_date"),
            "has_character_image": bool(video.get("character_image_path")),
            "has_audio_file": bool(video.get("audio_file_path")),
            "user_prompt": video.get("user_prompt", "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video info error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get video info: {str(e)}")

# User videos endpoint
@api_router.get("/user/videos")
async def get_user_videos(
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get all videos for current user"""
    try:
        db = get_db()
        videos = await db.videos.find({
            "user_id": current_user.id
        }).sort("created_at", -1).to_list(None)
        
        # Convert ObjectId to string and format response
        formatted_videos = []
        for video in videos:
            formatted_videos.append({
                "video_id": video["video_id"],
                "upload_timestamp": video.get("upload_timestamp"),
                "analysis_status": video.get("analysis_status"),
                "plan_status": video.get("plan_status"),
                "generation_status": video.get("generation_status"),
                "expiry_date": video.get("expiry_date"),
                "created_at": video.get("created_at")
            })
        
        return {"videos": formatted_videos}
        
    except Exception as e:
        logger.error(f"User videos error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user videos: {str(e)}")

# Authentication endpoints
@api_router.post("/auth/signup")
async def sign_up(request: SignUpRequest):
    """Sign up new user with Supabase"""
    auth = await get_auth()
    return await auth.sign_up(request.email, request.password)

@api_router.post("/auth/signin")
async def sign_in(request: SignInRequest):
    """Sign in user with Supabase"""
    auth = await get_auth()
    return await auth.sign_in(request.email, request.password)

@api_router.post("/auth/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token"""
    auth = await get_auth()
    return await auth.refresh_token(request.refresh_token)

@api_router.post("/auth/signout")
async def sign_out(current_user: SupabaseAuthUser = Depends(get_current_user)):
    """Sign out user"""
    auth = await get_auth()
    return await auth.sign_out("")

@api_router.get("/auth/user")
async def get_current_user_info(current_user: SupabaseAuthUser = Depends(get_current_user)):
    """Get current user information"""
    return {"user": current_user}

# Video upload endpoint
@api_router.post("/upload")
async def upload_video(
    video_file: UploadFile = File(...),
    context: Optional[str] = None,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Upload video file for analysis"""
    try:
        # Validate file type
        if not video_file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video")
        
        # Generate unique video ID
        video_id = str(uuid.uuid4())
        
        # Create temporary file path
        temp_dir = Path("/tmp/video_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / f"{video_id}_{video_file.filename}"
        
        # Save uploaded file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await video_file.read()
            await f.write(content)
        
        # Store video metadata in MongoDB
        db = get_db()
        video_doc = {
            "video_id": video_id,
            "user_id": current_user.id,
            "filename": video_file.filename,
            "file_path": str(file_path),
            "file_size": len(content),
            "content_type": video_file.content_type,
            "context": context,
            "status": "uploaded",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.videos.insert_one(video_doc)
        
        # Start background analysis
        # TODO: Implement Gemini analysis in background task
        
        return {
            "video_id": video_id,
            "message": "Video uploaded successfully",
            "status": "uploaded"
        }
        
    except Exception as e:
        logger.error(f"Video upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# Video status endpoint
@api_router.get("/video/{video_id}/status")
async def get_video_status(
    video_id: str,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get video processing status"""
    try:
        db = get_db()
        video = await db.videos.find_one({
            "video_id": video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {
            "video_id": video_id,
            "status": video.get("status", "unknown"),
            "progress": video.get("progress", 0),
            "message": video.get("message", ""),
            "created_at": video.get("created_at"),
            "updated_at": video.get("updated_at")
        }
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

# Chat endpoint for plan modifications
@api_router.post("/chat")
async def chat_with_plan(
    request: ChatMessageRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Chat interface for modifying video generation plans"""
    try:
        db = get_db()
        
        # Verify video exists and belongs to user
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Store chat message
        chat_doc = {
            "video_id": request.video_id,
            "user_id": current_user.id,
            "message": request.message,
            "timestamp": datetime.utcnow(),
            "type": "user"
        }
        
        await db.chat_sessions.insert_one(chat_doc)
        
        # TODO: Implement AI response generation
        ai_response = "Thank you for your message. AI chat integration coming soon!"
        
        # Store AI response
        ai_chat_doc = {
            "video_id": request.video_id,
            "user_id": current_user.id,
            "message": ai_response,
            "timestamp": datetime.utcnow(),
            "type": "ai"
        }
        
        await db.chat_sessions.insert_one(ai_chat_doc)
        
        return {
            "response": ai_response,
            "video_id": request.video_id
        }
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

# Video generation endpoint
@api_router.post("/generate")
async def generate_video(
    request: VideoGenerationRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Start video generation using Wan 2.1"""
    try:
        db = get_db()
        
        # Verify video exists and belongs to user
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Start Wan 2.1 video generation
        result = await wan21_video_service.generate_video_clips(
            video_id=request.video_id,
            plan=video.get("generation_plan", {}),
            sample_video_path=video.get("sample_video_path", ""),
            character_image_path=video.get("character_image_path"),
            audio_path=video.get("audio_file_path")
        )
        
        if result.get("success"):
            generation_id = str(uuid.uuid4())
            generation_doc = {
                "generation_id": generation_id,
                "video_id": request.video_id,
                "user_id": current_user.id,
                "model_preference": request.model_preference,
                "status": "processing",
                "model_used": result.get("model_used", ""),
                "video_path": result.get("video_path"),
                "clips_generated": result.get("clips_generated", 0),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await db.generation_tasks.insert_one(generation_doc)
            
            return {
                "generation_id": generation_id,
                "video_id": request.video_id,
                "status": "processing",
                "message": "Video generation started with Wan 2.1",
                "model_used": result.get("model_used"),
                "clips_generated": result.get("clips_generated", 0)
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

# Wan 2.1 model recommendations endpoint
@api_router.get("/wan21/models")
async def get_wan21_models():
    """Get available Wan 2.1 models"""
    try:
        from integrations.wan21 import wan21_service
        return {"models": wan21_service.get_available_models()}
    except Exception as e:
        logger.error(f"Error getting Wan 2.1 models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")

# Wan 2.1 generation progress endpoint
@api_router.get("/wan21/generation/{generation_id}/progress")
async def get_wan21_generation_progress(
    generation_id: str,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get Wan 2.1 generation progress"""
    try:
        db = get_db()
        
        # Get generation task
        generation_task = await db.generation_tasks.find_one({
            "generation_id": generation_id,
            "user_id": current_user.id
        })
        
        if not generation_task:
            raise HTTPException(status_code=404, detail="Generation task not found")
        
        # Get detailed progress from video document
        video_progress = await wan21_video_service.get_generation_progress(
            generation_task["video_id"]
        )
        
        return {
            "generation_id": generation_id,
            "video_id": generation_task["video_id"],
            "status": generation_task.get("status", "pending"),
            "model_used": generation_task.get("model_used", ""),
            "clips_generated": generation_task.get("clips_generated", 0),
            "video_path": generation_task.get("video_path"),
            "detailed_progress": video_progress,
            "created_at": generation_task.get("created_at"),
            "updated_at": generation_task.get("updated_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting generation progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")

# Wan 2.1 model recommendations endpoint
@api_router.get("/wan21/recommendations/{video_id}")
async def get_wan21_recommendations(
    video_id: str,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get Wan 2.1 model recommendations for a video"""
    try:
        db = get_db()
        
        # Get video from database
        video = await db.videos.find_one({
            "video_id": video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Get recommendations
        analysis_result = video.get("analysis_result", {})
        recommendations = wan21_video_service.get_model_recommendations(analysis_result)
        
        return {
            "video_id": video_id,
            "recommendations": recommendations,
            "analysis_used": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")

# Cancel Wan 2.1 generation endpoint
@api_router.post("/wan21/generation/{generation_id}/cancel")
async def cancel_wan21_generation(
    generation_id: str,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Cancel Wan 2.1 generation"""
    try:
        db = get_db()
        
        # Get generation task
        generation_task = await db.generation_tasks.find_one({
            "generation_id": generation_id,
            "user_id": current_user.id
        })
        
        if not generation_task:
            raise HTTPException(status_code=404, detail="Generation task not found")
        
        # Cancel generation
        result = await wan21_video_service.cancel_generation(generation_task["video_id"])
        
        if result.get("success"):
            # Update generation task
            await db.generation_tasks.update_one(
                {"generation_id": generation_id},
                {
                    "$set": {
                        "status": "cancelled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return {
                "generation_id": generation_id,
                "status": "cancelled",
                "message": "Generation cancelled successfully"
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to cancel"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling generation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel: {str(e)}")

# Get user's generations
@api_router.get("/wan21/generations")
async def get_user_generations(
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get all Wan 2.1 generations for the current user"""
    try:
        db = get_db()
        generations = await db.generation_tasks.find({
            "user_id": current_user.id
        }).sort("created_at", -1).to_list(length=50)
        
        return {
            "generations": generations,
            "count": len(generations)
        }
        
    except Exception as e:
        logger.error(f"Get generations error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get generations: {str(e)}")

# Update the existing generate endpoint to use Wan 2.1 by default
@api_router.post("/generate-video")
async def generate_video_new(
    request: VideoGenerationRequest,
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Start video generation using Wan 2.1 (updated endpoint)"""
    try:
        db = get_db()
        
        # Verify video exists and belongs to user
        video = await db.videos.find_one({
            "video_id": request.video_id,
            "user_id": current_user.id
        })
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Ensure we have a plan
        if not video.get("generation_plan"):
            raise HTTPException(status_code=400, detail="No generation plan found. Please generate a plan first.")
        
        # Start background generation with Wan 2.1
        asyncio.create_task(
            wan21_video_service.generate_video_clips(
                video_id=request.video_id,
                plan=video.get("generation_plan", {}),
                sample_video_path=video.get("sample_video_path", ""),
                character_image_path=video.get("character_image_path"),
                audio_path=video.get("audio_file_path")
            )
        )
        
        # Create generation task record
        generation_id = str(uuid.uuid4())
        generation_doc = {
            "generation_id": generation_id,
            "video_id": request.video_id,
            "user_id": current_user.id,
            "model_preference": request.model_preference,
            "status": "queued",
            "provider": "wan21",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.generation_tasks.insert_one(generation_doc)
        
        return {
            "generation_id": generation_id,
            "video_id": request.video_id,
            "status": "queued",
            "message": "Video generation started with Wan 2.1",
            "provider": "wan21"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

# Get user's videos
@api_router.get("/videos")
async def get_user_videos(
    current_user: SupabaseAuthUser = Depends(get_current_user)
):
    """Get all videos for the current user"""
    try:
        db = get_db()
        videos = await db.videos.find({
            "user_id": current_user.id
        }).sort("created_at", -1).to_list(length=100)
        
        return {
            "videos": videos,
            "count": len(videos)
        }
        
    except Exception as e:
        logger.error(f"Get videos error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get videos: {str(e)}")

# Include API router
app.include_router(api_router)

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Video Generation API with Wan 2.1", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)