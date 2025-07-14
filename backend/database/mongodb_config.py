"""
MongoDB configuration and connection management for video generation website
"""
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class MongoDBConfig:
    def __init__(self):
        self.connection_string = os.getenv('MONGODB_CONNECTION_STRING')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'video_generation_db')
        self.client = None
        self.db = None
        
    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            logger.info(f"Connected to MongoDB database: {self.db_name}")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def get_database(self):
        """Get database instance"""
        if not self.db:
            self.connect()
        return self.db
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global database instance
db_config = MongoDBConfig()

def get_db():
    """Get database instance for use in other modules"""
    return db_config.get_database()

# Database schemas
USER_SCHEMA = {
    "user_id": str,  # Unique user identifier
    "email": str,
    "password_hash": str,
    "created_at": datetime,
    "last_login": datetime,
    "is_active": bool,
    "subscription_status": str,  # 'free', 'premium'
    "video_quota": int,  # Number of videos allowed
    "videos_used": int,  # Number of videos generated
}

VIDEO_SCHEMA = {
    "video_id": str,  # Unique video identifier
    "user_id": str,  # Reference to user
    "sample_video_path": str,  # Path to uploaded sample video
    "character_image_path": str,  # Optional character image
    "audio_file_path": str,  # Optional audio file
    "user_prompt": str,  # User's additional context
    "upload_timestamp": datetime,
    "file_size": int,  # Size in bytes
    "duration": float,  # Duration in seconds
    "analysis_status": str,  # 'pending', 'processing', 'complete', 'failed'
    "analysis_result": dict,  # Detailed analysis from Gemini
    "plan_status": str,  # 'pending', 'generated', 'modified', 'approved'
    "generation_plan": dict,  # AI-generated video plan
    "generation_status": str,  # 'pending', 'processing', 'complete', 'failed'
    "generated_video_path": str,  # Path to final generated video
    "cloudflare_url": str,  # Cloudflare R2 URL
    "expiry_date": datetime,  # 7-day access expiry
    "created_at": datetime,
    "updated_at": datetime,
}

PLAN_SCHEMA = {
    "plan_id": str,  # Unique plan identifier
    "video_id": str,  # Reference to video
    "user_id": str,  # Reference to user
    "original_plan": dict,  # Original AI-generated plan
    "current_plan": dict,  # Modified plan after user input
    "plan_version": int,  # Version number for plan iterations
    "modification_history": list,  # History of user modifications
    "created_at": datetime,
    "updated_at": datetime,
}

CHAT_SESSION_SCHEMA = {
    "session_id": str,  # Unique session identifier
    "video_id": str,  # Reference to video
    "user_id": str,  # Reference to user
    "messages": list,  # Chat messages array
    "created_at": datetime,
    "updated_at": datetime,
}

GENERATION_TASK_SCHEMA = {
    "task_id": str,  # Unique task identifier
    "video_id": str,  # Reference to video
    "user_id": str,  # Reference to user
    "task_type": str,  # 'analysis', 'planning', 'generation', 'processing'
    "status": str,  # 'pending', 'processing', 'complete', 'failed'
    "progress": int,  # Progress percentage 0-100
    "current_step": str,  # Current processing step
    "estimated_completion": datetime,  # Estimated completion time
    "actual_completion": datetime,  # Actual completion time
    "error_message": str,  # Error details if failed
    "created_at": datetime,
    "updated_at": datetime,
}

def create_indexes():
    """Create database indexes for optimal performance"""
    db = get_db()
    
    # User indexes
    db.users.create_index("user_id", unique=True)
    db.users.create_index("email", unique=True)
    
    # Video indexes
    db.videos.create_index("video_id", unique=True)
    db.videos.create_index("user_id")
    db.videos.create_index("created_at")
    db.videos.create_index("expiry_date")
    
    # Plan indexes
    db.plans.create_index("plan_id", unique=True)
    db.plans.create_index("video_id")
    db.plans.create_index("user_id")
    
    # Chat session indexes
    db.chat_sessions.create_index("session_id", unique=True)
    db.chat_sessions.create_index("video_id")
    db.chat_sessions.create_index("user_id")
    
    # Generation task indexes
    db.generation_tasks.create_index("task_id", unique=True)
    db.generation_tasks.create_index("video_id")
    db.generation_tasks.create_index("user_id")
    db.generation_tasks.create_index("status")
    db.generation_tasks.create_index("created_at")
    
    logger.info("Database indexes created successfully")

def initialize_database():
    """Initialize database with schemas and indexes"""
    try:
        db_config.connect()
        create_indexes()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False