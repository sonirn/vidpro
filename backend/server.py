from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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

class VideoStatus(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    status: str  # "uploaded", "analyzing", "analyzed", "planning", "generating", "completed", "error"
    analysis: Optional[Dict[str, Any]] = None
    plan: Optional[str] = None
    final_video_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(days=7))
    progress: int = 0
    error_message: Optional[str] = None

class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Utility functions
def get_next_gemini_key():
    """Rotate between Gemini API keys for rate limiting"""
    global CURRENT_GEMINI_KEY_INDEX
    key = GEMINI_API_KEYS[CURRENT_GEMINI_KEY_INDEX]
    CURRENT_GEMINI_KEY_INDEX = (CURRENT_GEMINI_KEY_INDEX + 1) % len(GEMINI_API_KEYS)
    return key

async def save_uploaded_file(file: UploadFile, video_id: str) -> str:
    """Save uploaded file to temporary location"""
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / f"{video_id}_{file.filename}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    return str(file_path)

async def analyze_video_with_gemini(video_path: str, user_prompt: str = None) -> Dict[str, Any]:
    """Analyze video using Gemini API"""
    try:
        api_key = get_next_gemini_key()
        
        # Create Gemini chat instance
        chat = LlmChat(
            api_key=api_key,
            session_id=f"video_analysis_{uuid.uuid4()}",
            system_message="""You are an expert video analyst. Analyze the provided video in extreme detail including:
            1. Visual elements (objects, people, actions, scenes, colors, lighting)
            2. Audio elements (speech, music, sound effects, ambient sounds)
            3. Overall narrative and story structure
            4. Style and mood
            5. Technical aspects (camera movements, transitions, effects)
            6. Duration and pacing
            
            Provide a comprehensive analysis that will help create a similar video."""
        ).with_model("gemini", "gemini-2.0-flash")
        
        # Prepare video file
        video_file = FileContentWithMimeType(
            file_path=video_path,
            mime_type="video/mp4"
        )
        
        # Create analysis prompt
        analysis_prompt = f"""Please analyze this video in extreme detail. I need to understand:
        1. What exactly happens in this video from start to finish
        2. All visual elements, objects, people, and actions
        3. Audio analysis including speech, music, and sound effects
        4. The overall style, mood, and narrative structure
        5. Technical aspects like camera work and transitions
        
        {f'Additional context: {user_prompt}' if user_prompt else ''}
        
        Provide a comprehensive analysis in JSON format with these sections:
        - visual_analysis
        - audio_analysis
        - narrative_structure
        - style_and_mood
        - technical_aspects
        - duration_and_pacing
        - key_moments
        """
        
        user_message = UserMessage(
            text=analysis_prompt,
            file_contents=[video_file]
        )
        
        response = await chat.send_message(user_message)
        
        # Try to parse as JSON, fallback to text
        try:
            analysis = json.loads(response)
        except:
            analysis = {"raw_analysis": response}
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {str(e)}")

async def generate_video_plan(analysis: Dict[str, Any]) -> str:
    """Generate video creation plan based on analysis"""
    try:
        api_key = get_next_gemini_key()
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"plan_generation_{uuid.uuid4()}",
            system_message="""You are a professional video production planner. Based on the video analysis provided, create a detailed step-by-step plan to recreate a similar video. 

The plan should include:
1. Scene breakdown with timing
2. Visual elements needed for each scene
3. Audio requirements (music, effects, voiceover)
4. Transitions and effects
5. Technical specifications (aspect ratio 9:16, max 60 seconds)
6. Specific prompts for AI video generation

Make the plan actionable and detailed enough for AI video generation tools."""
        ).with_model("gemini", "gemini-2.0-flash")
        
        plan_prompt = f"""Based on this video analysis, create a detailed video production plan:

        Analysis: {json.dumps(analysis, indent=2)}
        
        Create a comprehensive plan that includes:
        1. Scene-by-scene breakdown with timing
        2. Visual elements and composition for each scene
        3. Audio strategy (background music, sound effects, voiceover)
        4. Transitions and visual effects
        5. Technical specifications (9:16 aspect ratio, under 60 seconds)
        6. Specific AI generation prompts for each scene
        7. Post-production steps for combining scenes
        
        Make sure the final video will be similar to the original but not an exact copy.
        """
        
        user_message = UserMessage(text=plan_prompt)
        response = await chat.send_message(user_message)
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating plan: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {str(e)}")

# API Routes
@api_router.post("/upload-video", response_model=VideoStatus)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_prompt: Optional[str] = None
):
    """Upload video file for analysis"""
    try:
        # Validate file
        if not file.filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            raise HTTPException(status_code=400, detail="Only video files are allowed")
        
        # Create video record
        video_id = str(uuid.uuid4())
        video_status = VideoStatus(
            id=video_id,
            filename=file.filename,
            status="uploaded",
            progress=10
        )
        
        # Save to database
        await db.videos.insert_one(video_status.dict())
        
        # Save file and start analysis in background
        file_path = await save_uploaded_file(file, video_id)
        background_tasks.add_task(process_video_analysis, video_id, file_path, user_prompt)
        
        return video_status
        
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

async def process_video_analysis(video_id: str, file_path: str, user_prompt: str = None):
    """Background task to analyze video and generate plan"""
    try:
        # Update status to analyzing
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {"status": "analyzing", "progress": 20}}
        )
        
        # Analyze video
        analysis = await analyze_video_with_gemini(file_path, user_prompt)
        
        # Update status to planning
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {"status": "planning", "progress": 60, "analysis": analysis}}
        )
        
        # Generate plan
        plan = await generate_video_plan(analysis)
        
        # Update status to analyzed
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {"status": "analyzed", "progress": 80, "plan": plan}}
        )
        
        # Clean up temporary file
        try:
            os.remove(file_path)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Error processing video {video_id}: {str(e)}")
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {"status": "error", "error_message": str(e)}}
        )

@api_router.get("/video-status/{video_id}", response_model=VideoStatus)
async def get_video_status(video_id: str):
    """Get video processing status"""
    video = await db.videos.find_one({"id": video_id})
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return VideoStatus(**video)

@api_router.post("/chat", response_model=ChatResponse)
async def chat_with_plan(request: ChatMessage):
    """Chat to modify video plan"""
    try:
        # Get video from database
        video = await db.videos.find_one({"id": request.video_id})
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        if not video.get("plan"):
            raise HTTPException(status_code=400, detail="Video plan not ready yet")
        
        api_key = get_next_gemini_key()
        
        chat = LlmChat(
            api_key=api_key,
            session_id=request.session_id,
            system_message=f"""You are a video production assistant. The user has a video plan and wants to make changes to it. 

Current plan: {video['plan']}

Help the user modify the plan based on their requests. Always respond with:
1. A conversational response to their request
2. If they want changes, provide the updated plan

Keep the conversation natural and helpful."""
        ).with_model("gemini", "gemini-2.0-flash")
        
        user_message = UserMessage(
            text=f"Current plan: {video['plan']}\n\nUser message: {request.message}"
        )
        
        response = await chat.send_message(user_message)
        
        return ChatResponse(response=response)
        
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@api_router.post("/generate-video")
async def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks
):
    """Start video generation process"""
    try:
        # Get video data for analysis
        video = await db.videos.find_one({"id": request.video_id})
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Update video status
        await db.videos.update_one(
            {"id": request.video_id},
            {"$set": {"status": "generating", "progress": 90, "plan": request.final_plan}}
        )
        
        # Start video generation in background with our new service
        background_tasks.add_task(
            process_video_generation_new, 
            request.video_id, 
            video.get("analysis", {}),
            request.final_plan
        )
        
        return {"message": "Video generation started", "video_id": request.video_id}
        
    except Exception as e:
        logger.error(f"Error starting video generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")

async def process_video_generation_new(video_id: str, video_analysis: Dict[str, Any], plan: Dict[str, Any]):
    """Background task for video generation using our new service"""
    try:
        logger.info(f"Starting video generation for {video_id}")
        
        # Use our video generation service
        generation_result = await video_generation_service.generate_video(
            video_id=video_id,
            video_analysis=video_analysis,
            video_plan=plan
        )
        
        # Update video with generation tracking info
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {
                "generation_id": generation_result["generation_id"],
                "generation_provider": generation_result["provider"],
                "generation_model": generation_result["model"],
                "generation_prompt": generation_result["prompt"],
                "status": "generating",
                "progress": 95
            }}
        )
        
        # Monitor generation progress
        generation_id = generation_result["generation_id"]
        max_wait_time = 600  # 10 minutes
        poll_interval = 15   # 15 seconds
        start_time = datetime.utcnow()
        
        while True:
            # Check generation status
            status = await video_generation_service.get_generation_status(generation_id)
            
            # Update video progress
            progress = 95 + (status.get("progress", 0) * 0.05)  # Scale to 95-100%
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"progress": progress}}
            )
            
            if status["status"] == "COMPLETED":
                # Video generation completed successfully
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {
                        "status": "completed",
                        "progress": 100,
                        "final_video_url": status.get("video_url"),
                        "generation_completed_at": datetime.utcnow().isoformat()
                    }}
                )
                logger.info(f"Video generation completed for {video_id}")
                break
                
            elif status["status"] == "FAILED":
                # Generation failed
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {
                        "status": "error",
                        "error_message": status.get("error", "Video generation failed"),
                        "generation_failed_at": datetime.utcnow().isoformat()
                    }}
                )
                logger.error(f"Video generation failed for {video_id}: {status.get('error')}")
                break
                
            # Check timeout
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > max_wait_time:
                await db.videos.update_one(
                    {"id": video_id},
                    {"$set": {
                        "status": "error",
                        "error_message": "Video generation timeout",
                        "generation_failed_at": datetime.utcnow().isoformat()
                    }}
                )
                logger.error(f"Video generation timeout for {video_id}")
                break
            
            # Wait before next check
            await asyncio.sleep(poll_interval)
        
    except VideoGenerationError as e:
        logger.error(f"Video generation service error for {video_id}: {str(e)}")
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {
                "status": "error", 
                "error_message": f"Generation service error: {str(e)}",
                "generation_failed_at": datetime.utcnow().isoformat()
            }}
        )
    except Exception as e:
        logger.error(f"Unexpected error in video generation {video_id}: {str(e)}")
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {
                "status": "error",
                "error_message": f"Unexpected error: {str(e)}",
                "generation_failed_at": datetime.utcnow().isoformat()
            }}
        )

@api_router.get("/user-videos")
async def get_user_videos():
    """Get all user videos (simplified for MVP)"""
    videos = await db.videos.find().to_list(100)
    return [VideoStatus(**video) for video in videos]

@api_router.get("/generation-status/{generation_id}")
async def get_generation_status(generation_id: str):
    """Get detailed status of a video generation"""
    try:
        status = await video_generation_service.get_generation_status(generation_id)
        return status
    except Exception as e:
        logger.error(f"Error getting generation status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/cancel-generation/{generation_id}")
async def cancel_generation(generation_id: str):
    """Cancel an ongoing video generation"""
    try:
        result = await video_generation_service.cancel_generation(generation_id)
        return result
    except Exception as e:
        logger.error(f"Error cancelling generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/model-recommendations/{video_id}")
async def get_model_recommendations(video_id: str):
    """Get AI model recommendations for a video"""
    try:
        # Get video data
        video = await db.videos.find_one({"id": video_id})
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Analyze requirements and get recommendations
        requirements = model_selector.analyze_video_requirements(
            video.get("analysis", {}),
            video.get("plan", {})
        )
        
        recommendations = model_selector.get_model_recommendations(requirements)
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error getting model recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/")
async def root():
    return {"message": "Video Generation API is running"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)