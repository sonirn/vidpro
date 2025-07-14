from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
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

# Import our video generation services
from services.video_generator import video_generation_service, VideoGenerationError
from services.model_selector import model_selector
# Import storage and processing services
from services.storage import storage_manager
from services.video_processor import video_processor
from services.audio_generator import audio_generator

# Import Supabase services
from services.supabase_service import supabase_service
from services.auth_service import (
    auth_service, get_current_user, get_current_user_optional, auth_middleware,
    SignupRequest, LoginRequest, AuthResponse, UserResponse, AuthUser
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Create the main app without a prefix
app = FastAPI(title="Video Generation API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables for API key rotation
GEMINI_API_KEYS = [
    os.environ.get('GEMINI_API_KEY_1'),
    os.environ.get('GEMINI_API_KEY_2'),
    os.environ.get('GEMINI_API_KEY_3')
]
CURRENT_GEMINI_KEY_INDEX = 0

# Models
class VideoAnalysisRequest(BaseModel):
    video_id: str
    user_prompt: Optional[str] = None

class VideoAnalysisResponse(BaseModel):
    video_id: str
    analysis: Dict[str, Any]
    plan: str
    status: str

class ChatMessage(BaseModel):
    message: str
    video_id: str
    session_id: str

class ChatResponse(BaseModel):
    response: str
    updated_plan: Optional[str] = None

class VideoGenerationRequest(BaseModel):
    video_id: str
    final_plan: str
    session_id: str

class VideoStatusResponse(BaseModel):
    id: str
    filename: str
    status: str
    analysis: Optional[Dict[str, Any]] = None
    plan: Optional[str] = None
    final_video_url: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    progress: int = 0
    error_message: Optional[str] = None

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database connection and create tables"""
    try:
        logger.info("🚀 Starting Video Generation API...")
        
        # Initialize Supabase connection
        await supabase_service.init_connection_pool()
        
        # Create tables if they don't exist
        await supabase_service.create_tables()
        
        logger.info("✅ Database initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up database connections"""
    try:
        await supabase_service.close_connection_pool()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")

# Add auth middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper functions
def get_next_gemini_key():
    """Get next Gemini API key for rotation"""
    global CURRENT_GEMINI_KEY_INDEX
    key = GEMINI_API_KEYS[CURRENT_GEMINI_KEY_INDEX]
    CURRENT_GEMINI_KEY_INDEX = (CURRENT_GEMINI_KEY_INDEX + 1) % len(GEMINI_API_KEYS)
    return key

async def process_video_analysis(video_id: str, user_prompt: Optional[str] = None):
    """Background task to analyze video using Gemini"""
    try:
        # Update status to analyzing
        await supabase_service.update_video_status(video_id, "analyzing", progress=10)
        
        # Get video details
        video = await supabase_service.get_video(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Load video file
        video_path = Path(video['file_path'])
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Analyze video with Gemini
        gemini_key = get_next_gemini_key()
        
        with open(video_path, 'rb') as video_file:
            video_content = video_file.read()
        
        # Create Gemini chat client
        chat_client = LlmChat(api_key=gemini_key, model="gemini-2.0-flash-exp")
        
        # Create analysis prompt
        analysis_prompt = f"""
        Analyze this video and provide:
        1. Visual style and aesthetics
        2. Content themes and narrative
        3. Technical aspects (lighting, composition, movement)
        4. Emotional tone and mood
        5. Key visual elements and patterns
        
        User context: {user_prompt if user_prompt else "No specific context provided"}
        
        Provide a detailed analysis in JSON format with the following structure:
        {{
            "visual_style": "description",
            "content_themes": ["theme1", "theme2"],
            "technical_aspects": {{"lighting": "description", "composition": "description", "movement": "description"}},
            "emotional_tone": "description",
            "key_elements": ["element1", "element2"],
            "duration": "detected_duration",
            "aspect_ratio": "detected_ratio"
        }}
        """
        
        # Send video to Gemini for analysis
        file_content = FileContentWithMimeType(
            content=video_content,
            mime_type=video['mime_type']
        )
        
        response = chat_client.chat([
            UserMessage(content=analysis_prompt, files=[file_content])
        ])
        
        # Parse analysis response
        analysis_text = response.text
        
        # Try to extract JSON from response
        try:
            import re
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis_json = json.loads(json_match.group())
            else:
                analysis_json = {"raw_analysis": analysis_text}
        except:
            analysis_json = {"raw_analysis": analysis_text}
        
        # Update video with analysis
        await supabase_service.update_video_status(
            video_id, "analyzed", progress=50, analysis=analysis_json
        )
        
        # Generate video plan
        await generate_video_plan(video_id, analysis_json)
        
    except Exception as e:
        logger.error(f"❌ Video analysis failed: {e}")
        await supabase_service.update_video_status(
            video_id, "error", error_message=str(e)
        )

async def generate_video_plan(video_id: str, analysis: Dict[str, Any]):
    """Generate video creation plan based on analysis"""
    try:
        # Update status to planning
        await supabase_service.update_video_status(video_id, "planning", progress=70)
        
        # Create plan generation prompt
        plan_prompt = f"""
        Based on this video analysis, create a detailed plan for generating a similar video:
        
        Analysis: {json.dumps(analysis, indent=2)}
        
        Create a comprehensive video generation plan including:
        1. Visual style guidelines
        2. Content structure and narrative flow
        3. Technical specifications
        4. Key scenes and transitions
        5. Specific prompts for AI video generation
        
        Format the plan as a detailed text that can be used to generate similar videos.
        """
        
        # Get Gemini key and create chat client
        gemini_key = get_next_gemini_key()
        chat_client = LlmChat(api_key=gemini_key, model="gemini-2.0-flash-exp")
        
        # Generate plan
        response = chat_client.chat([UserMessage(content=plan_prompt)])
        plan_text = response.text
        
        # Update video with plan
        await supabase_service.update_video_status(
            video_id, "planned", progress=90, plan=plan_text
        )
        
        logger.info(f"✅ Video plan generated successfully: {video_id}")
        
    except Exception as e:
        logger.error(f"❌ Plan generation failed: {e}")
        await supabase_service.update_video_status(
            video_id, "error", error_message=str(e)
        )

# Authentication endpoints
@api_router.post("/auth/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """User registration endpoint"""
    try:
        # Create user with Supabase
        auth_result = await supabase_service.create_user(
            request.email, request.password, request.name
        )
        
        if not auth_result.get('success'):
            raise HTTPException(
                status_code=400, 
                detail=auth_result.get('error', 'Failed to create user')
            )
        
        # Create access token
        user = auth_result['user']
        access_token = auth_service.create_access_token(
            user.id, request.email, request.name
        )
        
        return AuthResponse(
            access_token=access_token,
            user=AuthUser(id=user.id, email=request.email, name=request.name)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Signup error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """User login endpoint"""
    try:
        # Sign in user with Supabase
        auth_result = await supabase_service.sign_in_user(request.email, request.password)
        
        if not auth_result.get('success'):
            raise HTTPException(
                status_code=401, 
                detail=auth_result.get('error', 'Invalid credentials')
            )
        
        # Create access token
        user = auth_result['user']
        access_token = auth_service.create_access_token(
            user.id, request.email, user.user_metadata.get('name')
        )
        
        return AuthResponse(
            access_token=access_token,
            user=AuthUser(
                id=user.id, 
                email=request.email, 
                name=user.user_metadata.get('name')
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: AuthUser = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse.from_auth_user(current_user)

# Video endpoints
@api_router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    context: Optional[str] = None,
    current_user: AuthUser = Depends(get_current_user)
):
    """Upload video file with authentication"""
    try:
        # Validate file
        if not file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video")
        
        # Check file size (max 100MB)
        file_size = 0
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        
        try:
            async with aiofiles.open(temp_file.name, 'wb') as f:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    file_size += len(chunk)
                    if file_size > 100 * 1024 * 1024:  # 100MB limit
                        raise HTTPException(status_code=413, detail="File too large")
                    await f.write(chunk)
        finally:
            await file.seek(0)
        
        # Generate unique filename
        video_id = str(uuid.uuid4())
        file_extension = Path(file.filename).suffix
        filename = f"{video_id}{file_extension}"
        
        # Save to uploads directory
        uploads_dir = ROOT_DIR / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        file_path = uploads_dir / filename
        
        # Move temp file to permanent location
        shutil.move(temp_file.name, file_path)
        
        # Create video record in database
        video_id = await supabase_service.create_video(
            user_id=current_user.id,
            filename=filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=file.content_type
        )
        
        logger.info(f"✅ Video uploaded successfully: {video_id}")
        
        return {
            "video_id": video_id,
            "filename": filename,
            "message": "Video uploaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Video upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

@api_router.post("/analyze/{video_id}")
async def analyze_video(
    video_id: str,
    request: VideoAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user)
):
    """Start video analysis"""
    try:
        # Verify video belongs to user
        video = await supabase_service.get_video(video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Start background analysis
        background_tasks.add_task(
            process_video_analysis, 
            video_id, 
            request.user_prompt
        )
        
        return {"message": "Video analysis started", "video_id": video_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Analysis start failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to start analysis")

@api_router.get("/status/{video_id}", response_model=VideoStatusResponse)
async def get_video_status(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Get video processing status"""
    try:
        # Get video from database
        video = await supabase_service.get_video(video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return VideoStatusResponse(
            id=video['id'],
            filename=video['filename'],
            status=video['status'],
            analysis=video['analysis'],
            plan=video['plan'],
            final_video_url=video['final_video_url'],
            created_at=video['created_at'],
            expires_at=video['expires_at'],
            progress=video['progress'],
            error_message=video['error_message']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")

@api_router.get("/videos", response_model=List[VideoStatusResponse])
async def get_user_videos(current_user: AuthUser = Depends(get_current_user)):
    """Get all videos for authenticated user"""
    try:
        videos = await supabase_service.get_user_videos(current_user.id)
        
        return [
            VideoStatusResponse(
                id=video['id'],
                filename=video['filename'],
                status=video['status'],
                analysis=video['analysis'],
                plan=video['plan'],
                final_video_url=video['final_video_url'],
                created_at=video['created_at'],
                expires_at=video['expires_at'],
                progress=video['progress'],
                error_message=video['error_message']
            )
            for video in videos
        ]
        
    except Exception as e:
        logger.error(f"❌ Get videos failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get videos")

@api_router.post("/chat/{video_id}")
async def chat_with_video(
    video_id: str,
    request: ChatMessage,
    current_user: AuthUser = Depends(get_current_user)
):
    """Chat to modify video plan"""
    try:
        # Verify video belongs to user
        video = await supabase_service.get_video(video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        if not video['plan']:
            raise HTTPException(status_code=400, detail="Video plan not ready")
        
        # Create chat prompt
        chat_prompt = f"""
        Current video plan: {video['plan']}
        
        User message: {request.message}
        
        Based on the user's message, modify the video plan accordingly. 
        Provide a helpful response and the updated plan if changes are needed.
        
        Respond in the format:
        RESPONSE: [your response to the user]
        UPDATED_PLAN: [updated plan if changed, or "NO_CHANGE" if no updates needed]
        """
        
        # Get Gemini key and create chat client
        gemini_key = get_next_gemini_key()
        chat_client = LlmChat(api_key=gemini_key, model="gemini-2.0-flash-exp")
        
        # Get chat response
        response = chat_client.chat([UserMessage(content=chat_prompt)])
        response_text = response.text
        
        # Parse response
        response_parts = response_text.split("UPDATED_PLAN:")
        chat_response = response_parts[0].replace("RESPONSE:", "").strip()
        
        updated_plan = None
        if len(response_parts) > 1:
            plan_text = response_parts[1].strip()
            if plan_text != "NO_CHANGE":
                updated_plan = plan_text
                # Update video plan in database
                await supabase_service.update_video_status(
                    video_id, video['status'], plan=updated_plan
                )
        
        # Save chat message
        await supabase_service.save_chat_message(
            current_user.id, video_id, request.session_id, 
            request.message, chat_response
        )
        
        return ChatResponse(
            response=chat_response,
            updated_plan=updated_plan
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Chat failed: {e}")
        raise HTTPException(status_code=500, detail="Chat failed")

# Video generation endpoints (keeping existing functionality)
@api_router.post("/generate-video")
async def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user)
):
    """Generate video using AI models"""
    try:
        # Verify video belongs to user
        video = await supabase_service.get_video(request.video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Start video generation
        generation_id = await video_generation_service.start_generation(
            video_id=request.video_id,
            plan=request.final_plan,
            user_id=current_user.id
        )
        
        return {
            "generation_id": generation_id,
            "message": "Video generation started",
            "video_id": request.video_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Video generation failed: {e}")
        raise HTTPException(status_code=500, detail="Video generation failed")

@api_router.get("/generation-status/{generation_id}")
async def get_generation_status(
    generation_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Get video generation status"""
    try:
        status = await video_generation_service.get_generation_status(
            generation_id, current_user.id
        )
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Generation status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")

@api_router.get("/model-recommendations/{video_id}")
async def get_model_recommendations(
    video_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Get AI model recommendations for video"""
    try:
        # Verify video belongs to user
        video = await supabase_service.get_video(video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        recommendations = await model_selector.get_recommendations(video_id)
        return recommendations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Model recommendations failed: {e}")
        raise HTTPException(status_code=500, detail="Recommendations failed")

@api_router.delete("/cancel-generation/{generation_id}")
async def cancel_generation(
    generation_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Cancel video generation"""
    try:
        result = await video_generation_service.cancel_generation(
            generation_id, current_user.id
        )
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Cancel generation failed: {e}")
        raise HTTPException(status_code=500, detail="Cancel failed")

# Admin endpoints
@api_router.post("/admin/cleanup-expired")
async def cleanup_expired_videos(current_user: AuthUser = Depends(get_current_user)):
    """Clean up expired videos (admin only)"""
    try:
        # Simple admin check - in production, implement proper role-based access
        if not current_user.email.endswith('@admin.com'):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        count = await supabase_service.cleanup_expired_videos()
        return {"message": f"Cleaned up {count} expired videos"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Add router to app
app.include_router(api_router)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Video Generation API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)