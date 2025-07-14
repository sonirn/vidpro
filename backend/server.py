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
from auth.mongodb_auth import get_auth

# Import new video services
from services.video_service import get_video_service, get_plan_service, get_chat_service, get_task_service

# Import background worker
from workers.background_worker import get_background_worker, start_background_worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
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

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check and auth endpoints
        if request.url.path in ["/health", "/api/health", "/api/auth/login", "/api/auth/register"]:
            response = await call_next(request)
            return response
        
        # For other endpoints, check authorization
        if request.url.path.startswith("/api/"):
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                auth = get_auth()
                user = auth.get_user_by_token(token)
                if user:
                    request.state.user = user
                else:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or expired token"}
                    )
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authorization header required"}
                )
        
        response = await call_next(request)
        return response

app.add_middleware(AuthMiddleware)

# Pydantic models for requests/responses
class UserRegistration(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")

class UserLogin(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

class AuthResponse(BaseModel):
    success: bool
    user: Optional[Dict[str, Any]] = None
    token: Optional[str] = None
    error: Optional[str] = None

class VideoUploadResponse(BaseModel):
    video_id: str
    message: str
    analysis_started: bool

class VideoStatusResponse(BaseModel):
    video_id: str
    status: str
    progress: int
    message: str
    analysis_result: Optional[Dict[str, Any]] = None
    generation_plan: Optional[Dict[str, Any]] = None

class ChatMessage(BaseModel):
    message: str
    video_id: str

class ChatResponse(BaseModel):
    response: str
    updated_plan: Optional[Dict[str, Any]] = None

# Helper function to get current user
def get_current_user(request: Request):
    return getattr(request.state, 'user', None)

# Gemini API key rotation
GEMINI_API_KEYS = [
    os.getenv('GEMINI_API_KEY_1'),
    os.getenv('GEMINI_API_KEY_2'),
    os.getenv('GEMINI_API_KEY_3')
]

def get_gemini_api_key():
    """Get a random Gemini API key for load balancing"""
    return random.choice([key for key in GEMINI_API_KEYS if key])

# Background task for video analysis
async def analyze_video_task(video_id: str, user_id: str, file_path: str, user_prompt: str = ""):
    """Background task to analyze video using Gemini"""
    db = get_db()
    
    try:
        # Update status to processing
        db.videos.update_one(
            {"video_id": video_id},
            {"$set": {
                "analysis_status": "processing",
                "updated_at": datetime.utcnow()
            }}
        )
        
        # Initialize Gemini chat
        api_key = get_gemini_api_key()
        chat = LlmChat(
            llm_model="gemini-2.0-flash",
            api_key=api_key
        )
        
        # Create analysis prompt
        analysis_prompt = f"""
        Please analyze this video file in detail for video generation planning:

        1. **Visual Analysis**:
           - Scene composition and framing
           - Color palette and lighting
           - Camera movements and angles
           - Visual style and aesthetics
           - Key objects and subjects

        2. **Content Analysis**:
           - Main theme and concept
           - Narrative structure
           - Key moments and transitions
           - Emotional tone and mood
           - Target audience appeal

        3. **Technical Analysis**:
           - Video quality and resolution
           - Frame rate and motion
           - Audio quality and sync
           - Duration and pacing
           - Technical requirements

        4. **Generation Planning**:
           - Suggest 3-5 short clips (5-10 seconds each)
           - Describe scene compositions for 9:16 format
           - Recommend visual style and effects
           - Suggest transition types
           - Overall video structure plan

        Additional context from user: {user_prompt}

        Please provide a comprehensive analysis that will help create a similar but not identical video.
        """
        
        # Read video file
        with open(file_path, 'rb') as video_file:
            video_content = video_file.read()
        
        # Send to Gemini for analysis
        file_content = FileContentWithMimeType(
            content=video_content,
            mime_type="video/mp4"
        )
        
        messages = [
            UserMessage(content=analysis_prompt, files=[file_content])
        ]
        
        response = await chat.send_message(messages)
        analysis_result = response.content
        
        # Generate initial plan based on analysis
        plan_prompt = f"""
        Based on the video analysis below, create a detailed video generation plan:

        {analysis_result}

        Create a structured plan with:
        1. **Video Concept**: Overall theme and style
        2. **Clip Breakdown**: 3-5 clips with detailed descriptions
        3. **Visual Requirements**: Style, colors, composition for 9:16 format
        4. **Audio Requirements**: Voice, music, sound effects needs
        5. **Technical Specs**: Resolution, duration, effects
        6. **Timeline**: Sequence and timing of clips

        Format the plan as a JSON structure for easy parsing.
        """
        
        plan_response = await chat.send_message([UserMessage(content=plan_prompt)])
        
        # Try to parse JSON, fallback to text if needed
        try:
            generation_plan = json.loads(plan_response.content)
        except:
            generation_plan = {"plan_text": plan_response.content}
        
        # Update database with results
        db.videos.update_one(
            {"video_id": video_id},
            {"$set": {
                "analysis_status": "complete",
                "analysis_result": {
                    "analysis": analysis_result,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "plan_status": "generated",
                "generation_plan": generation_plan,
                "updated_at": datetime.utcnow()
            }}
        )
        
        logger.info(f"Video analysis completed for video_id: {video_id}")
        
    except Exception as e:
        logger.error(f"Video analysis failed for video_id {video_id}: {str(e)}")
        
        # Update status to failed
        db.videos.update_one(
            {"video_id": video_id},
            {"$set": {
                "analysis_status": "failed",
                "updated_at": datetime.utcnow()
            }}
        )

# API Endpoints

@api_router.post("/auth/register", response_model=AuthResponse)
async def register(user_data: UserRegistration):
    """Register a new user"""
    auth = get_auth()
    result = auth.register_user(user_data.email, user_data.password)
    return AuthResponse(**result)

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(user_data: UserLogin):
    """Login user"""
    auth = get_auth()
    result = auth.login_user(user_data.email, user_data.password)
    return AuthResponse(**result)

@api_router.post("/auth/logout")
async def logout(request: Request):
    """Logout user"""
    user = get_current_user(request)
    if user:
        auth = get_auth()
        auth.logout_user(user['user_id'])
    return {"message": "Logged out successfully"}

@api_router.get("/user/profile")
async def get_user_profile(request: Request):
    """Get current user profile"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    auth = get_auth()
    quota_info = auth.check_user_quota(user['user_id'])
    
    return {
        "user": user,
        "quota": quota_info
    }

@api_router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_prompt: str = ""
):
    """Upload video file for analysis"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check user quota
    auth = get_auth()
    quota_info = auth.check_user_quota(user['user_id'])
    if not quota_info['has_quota']:
        raise HTTPException(status_code=403, detail="Video quota exceeded")
    
    # Validate file type
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    # Generate video ID
    video_id = str(uuid.uuid4())
    
    # Create upload directory
    upload_dir = Path("/app/backend/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Save file
    file_path = upload_dir / f"{video_id}.mp4"
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    # Create video record in database
    db = get_db()
    video_data = {
        "video_id": video_id,
        "user_id": user['user_id'],
        "sample_video_path": str(file_path),
        "character_image_path": "",
        "audio_file_path": "",
        "user_prompt": user_prompt,
        "upload_timestamp": datetime.utcnow(),
        "file_size": len(content),
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
        "updated_at": datetime.utcnow()
    }
    
    db.videos.insert_one(video_data)
    
    # Start background analysis
    background_tasks.add_task(
        analyze_video_task,
        video_id=video_id,
        user_id=user['user_id'],
        file_path=str(file_path),
        user_prompt=user_prompt
    )
    
    return VideoUploadResponse(
        video_id=video_id,
        message="Video uploaded successfully. Analysis started.",
        analysis_started=True
    )

@api_router.get("/status/{video_id}", response_model=VideoStatusResponse)
async def get_video_status(video_id: str, request: Request):
    """Get video processing status"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    db = get_db()
    video = db.videos.find_one({"video_id": video_id, "user_id": user['user_id']})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Calculate progress based on status
    progress = 0
    if video['analysis_status'] == 'complete':
        progress = 30
    if video['plan_status'] == 'generated':
        progress = 50
    if video['generation_status'] == 'complete':
        progress = 100
    
    return VideoStatusResponse(
        video_id=video_id,
        status=video['analysis_status'],
        progress=progress,
        message=f"Analysis: {video['analysis_status']}, Plan: {video['plan_status']}",
        analysis_result=video.get('analysis_result'),
        generation_plan=video.get('generation_plan')
    )

@api_router.post("/chat/{video_id}", response_model=ChatResponse)
async def chat_with_plan(video_id: str, chat_message: ChatMessage, request: Request):
    """Chat to modify video generation plan"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    db = get_db()
    video = db.videos.find_one({"video_id": video_id, "user_id": user['user_id']})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if video['plan_status'] != 'generated':
        raise HTTPException(status_code=400, detail="Video plan not ready for modification")
    
    # Get current plan
    current_plan = video.get('generation_plan', {})
    
    # Create modification prompt
    modification_prompt = f"""
    Current video generation plan: {json.dumps(current_plan, indent=2)}
    
    User request: {chat_message.message}
    
    Please modify the plan according to the user's request while maintaining the overall structure.
    Return the updated plan as JSON and explain what changes were made.
    """
    
    # Send to Gemini for plan modification
    api_key = get_gemini_api_key()
    chat = LlmChat(
        llm_model="gemini-2.0-flash",
        api_key=api_key
    )
    
    response = await chat.send_message([UserMessage(content=modification_prompt)])
    
    # Try to extract JSON from response
    try:
        # Look for JSON in the response
        response_text = response.content
        if "{" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            json_str = response_text[start:end]
            updated_plan = json.loads(json_str)
            
            # Update plan in database
            db.videos.update_one(
                {"video_id": video_id},
                {"$set": {
                    "generation_plan": updated_plan,
                    "plan_status": "modified",
                    "updated_at": datetime.utcnow()
                }}
            )
            
            return ChatResponse(
                response=response_text,
                updated_plan=updated_plan
            )
        else:
            return ChatResponse(
                response=response_text,
                updated_plan=current_plan
            )
    except Exception as e:
        logger.error(f"Failed to parse plan modification: {e}")
        return ChatResponse(
            response=response.content,
            updated_plan=current_plan
        )

@api_router.get("/videos")
async def get_user_videos(request: Request):
    """Get user's video history"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    db = get_db()
    videos = list(db.videos.find(
        {"user_id": user['user_id']},
        {"_id": 0}  # Exclude MongoDB ObjectId
    ).sort("created_at", -1))
    
    return {"videos": videos}

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# Include the API router
app.include_router(api_router)

# Health check endpoint (without /api prefix)
@app.get("/health")
async def health_check_root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)