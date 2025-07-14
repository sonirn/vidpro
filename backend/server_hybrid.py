from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging
from pathlib import Path
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import MongoDB configuration and authentication
from database.mongodb_config import initialize_database, get_db
from auth.supabase_auth import get_auth, verify_token, SupabaseAuthUser

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

class ChatMessageRequest(BaseModel):
    message: str
    video_id: str

class VideoGenerationRequest(BaseModel):
    video_id: str
    model_preference: Optional[str] = "auto"  # "t2v-1.3b", "i2v-14b", "flf2v-14b", "auto"

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

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
        
        # Create generation task
        generation_id = str(uuid.uuid4())
        generation_doc = {
            "generation_id": generation_id,
            "video_id": request.video_id,
            "user_id": current_user.id,
            "model_preference": request.model_preference,
            "status": "queued",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.generation_tasks.insert_one(generation_doc)
        
        # TODO: Start background Wan 2.1 generation
        
        return {
            "generation_id": generation_id,
            "video_id": request.video_id,
            "status": "queued",
            "message": "Video generation started"
        }
        
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