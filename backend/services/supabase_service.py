"""
Supabase service for database operations and authentication
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from supabase import create_client, Client
from pydantic import BaseModel, Field
import asyncpg
import asyncio
from contextlib import asynccontextmanager
import uuid

logger = logging.getLogger(__name__)

class SupabaseService:
    """Service for handling Supabase database operations"""
    
    def __init__(self):
        self.supabase_url = os.environ.get('SUPABASE_URL')
        self.supabase_anon_key = os.environ.get('SUPABASE_ANON_KEY')
        self.supabase_service_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        self.postgres_url = os.environ.get('POSTGRES_URL')
        
        # Initialize Supabase client
        self.supabase: Client = create_client(self.supabase_url, self.supabase_anon_key)
        self.admin_client: Client = create_client(self.supabase_url, self.supabase_service_key)
        
        # Connection pool for direct PostgreSQL operations
        self.pool = None
        
    async def init_connection_pool(self):
        """Initialize async connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.postgres_url,
                min_size=5,
                max_size=20,
                command_timeout=10
            )
            logger.info("✅ Supabase connection pool initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize connection pool: {e}")
            raise

    async def close_connection_pool(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Connection pool closed")

    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool"""
        if not self.pool:
            await self.init_connection_pool()
        
        async with self.pool.acquire() as connection:
            yield connection

    async def create_tables(self):
        """Create all necessary tables"""
        try:
            async with self.get_connection() as conn:
                # Create users table (extends Supabase auth.users)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS public.users (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        email TEXT UNIQUE NOT NULL,
                        name TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                
                # Create videos table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS public.videos (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
                        filename TEXT NOT NULL,
                        original_filename TEXT,
                        file_path TEXT,
                        file_size INTEGER,
                        mime_type TEXT,
                        duration FLOAT,
                        status TEXT NOT NULL DEFAULT 'uploaded',
                        analysis JSONB,
                        plan TEXT,
                        final_video_url TEXT,
                        progress INTEGER DEFAULT 0,
                        error_message TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '7 days'),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                
                # Create chat_sessions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS public.chat_sessions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
                        video_id UUID REFERENCES public.videos(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        messages JSONB DEFAULT '[]',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                
                # Create video_generations table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS public.video_generations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
                        video_id UUID REFERENCES public.videos(id) ON DELETE CASCADE,
                        generation_id TEXT UNIQUE NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        result_url TEXT,
                        error_message TEXT,
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                
                # Create indexes
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_user_id ON public.videos(user_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON public.videos(status);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_expires_at ON public.videos(expires_at);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_video_id ON public.chat_sessions(video_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_video_generations_user_id ON public.video_generations(user_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_video_generations_video_id ON public.video_generations(video_id);")
                
                logger.info("✅ All tables created successfully")
                
        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            raise

    async def create_user(self, email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new user with Supabase Auth"""
        try:
            # Create user with Supabase Auth
            auth_response = self.admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,  # Skip email confirmation
                "user_metadata": {"name": name} if name else {}
            })
            
            if auth_response.user:
                # Create user record in our users table
                async with self.get_connection() as conn:
                    await conn.execute("""
                        INSERT INTO public.users (id, email, name, created_at, updated_at)
                        VALUES ($1, $2, $3, NOW(), NOW())
                        ON CONFLICT (email) DO UPDATE SET
                        name = EXCLUDED.name,
                        updated_at = NOW()
                    """, str(auth_response.user.id), email, name)
                
                logger.info(f"✅ User created successfully: {email}")
                return {
                    "user": auth_response.user,
                    "session": None,
                    "success": True
                }
            else:
                logger.error(f"❌ Failed to create user: {email}")
                return {"success": False, "error": "Failed to create user"}
                
        except Exception as e:
            logger.error(f"❌ Error creating user: {e}")
            return {"success": False, "error": str(e)}

    async def sign_in_user(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in user with email and password"""
        try:
            auth_response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if auth_response.user and auth_response.session:
                logger.info(f"✅ User signed in successfully: {email}")
                return {
                    "user": auth_response.user,
                    "session": auth_response.session,
                    "success": True
                }
            else:
                logger.error(f"❌ Failed to sign in user: {email}")
                return {"success": False, "error": "Invalid credentials"}
                
        except Exception as e:
            logger.error(f"❌ Error signing in user: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get user from JWT token"""
        try:
            # Verify the token with Supabase
            user_response = self.supabase.auth.get_user(token)
            
            if user_response.user:
                return {
                    "id": user_response.user.id,
                    "email": user_response.user.email,
                    "user_metadata": user_response.user.user_metadata
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error verifying token: {e}")
            return None

    async def create_video(self, user_id: str, filename: str, original_filename: str, 
                          file_path: str, file_size: int, mime_type: str) -> str:
        """Create a new video record"""
        try:
            video_id = str(uuid.uuid4())
            
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO public.videos (id, user_id, filename, original_filename, file_path, file_size, mime_type, status, created_at, expires_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'uploaded', NOW(), NOW() + INTERVAL '7 days', NOW())
                """, video_id, user_id, filename, original_filename, file_path, file_size, mime_type)
            
            logger.info(f"✅ Video created successfully: {video_id}")
            return video_id
            
        except Exception as e:
            logger.error(f"❌ Error creating video: {e}")
            raise

    async def get_video(self, video_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get video by ID, optionally filtered by user"""
        try:
            async with self.get_connection() as conn:
                if user_id:
                    row = await conn.fetchrow("""
                        SELECT * FROM public.videos 
                        WHERE id = $1 AND user_id = $2
                    """, video_id, user_id)
                else:
                    row = await conn.fetchrow("""
                        SELECT * FROM public.videos 
                        WHERE id = $1
                    """, video_id)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting video: {e}")
            return None

    async def update_video_status(self, video_id: str, status: str, progress: int = None, 
                                 error_message: str = None, analysis: Dict = None, 
                                 plan: str = None, final_video_url: str = None):
        """Update video status and related fields"""
        try:
            async with self.get_connection() as conn:
                # Build dynamic query
                set_clauses = ["status = $2", "updated_at = NOW()"]
                params = [video_id, status]
                param_count = 2
                
                if progress is not None:
                    param_count += 1
                    set_clauses.append(f"progress = ${param_count}")
                    params.append(progress)
                
                if error_message is not None:
                    param_count += 1
                    set_clauses.append(f"error_message = ${param_count}")
                    params.append(error_message)
                
                if analysis is not None:
                    param_count += 1
                    set_clauses.append(f"analysis = ${param_count}")
                    params.append(analysis)
                
                if plan is not None:
                    param_count += 1
                    set_clauses.append(f"plan = ${param_count}")
                    params.append(plan)
                
                if final_video_url is not None:
                    param_count += 1
                    set_clauses.append(f"final_video_url = ${param_count}")
                    params.append(final_video_url)
                
                query = f"""
                    UPDATE public.videos 
                    SET {', '.join(set_clauses)}
                    WHERE id = $1
                """
                
                await conn.execute(query, *params)
                
            logger.info(f"✅ Video status updated: {video_id} -> {status}")
            
        except Exception as e:
            logger.error(f"❌ Error updating video status: {e}")
            raise

    async def get_user_videos(self, user_id: str, include_expired: bool = False) -> List[Dict[str, Any]]:
        """Get all videos for a user"""
        try:
            async with self.get_connection() as conn:
                if include_expired:
                    rows = await conn.fetch("""
                        SELECT * FROM public.videos 
                        WHERE user_id = $1
                        ORDER BY created_at DESC
                    """, user_id)
                else:
                    rows = await conn.fetch("""
                        SELECT * FROM public.videos 
                        WHERE user_id = $1 AND expires_at > NOW()
                        ORDER BY created_at DESC
                    """, user_id)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"❌ Error getting user videos: {e}")
            return []

    async def cleanup_expired_videos(self):
        """Clean up expired videos"""
        try:
            async with self.get_connection() as conn:
                # Mark expired videos
                await conn.execute("""
                    UPDATE public.videos 
                    SET status = 'expired', updated_at = NOW()
                    WHERE expires_at < NOW() AND status != 'expired'
                """)
                
                # Get count of expired videos
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM public.videos 
                    WHERE expires_at < NOW()
                """)
                
                logger.info(f"✅ Cleaned up {count} expired videos")
                return count
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up expired videos: {e}")
            return 0

    async def save_chat_message(self, user_id: str, video_id: str, session_id: str, 
                               message: str, response: str):
        """Save chat message and response"""
        try:
            async with self.get_connection() as conn:
                # Get or create chat session
                session_row = await conn.fetchrow("""
                    SELECT id, messages FROM public.chat_sessions 
                    WHERE video_id = $1 AND session_id = $2
                """, video_id, session_id)
                
                if session_row:
                    # Update existing session
                    messages = session_row['messages'] or []
                    messages.extend([
                        {"role": "user", "content": message, "timestamp": datetime.utcnow().isoformat()},
                        {"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()}
                    ])
                    
                    await conn.execute("""
                        UPDATE public.chat_sessions 
                        SET messages = $1, updated_at = NOW()
                        WHERE id = $2
                    """, messages, session_row['id'])
                else:
                    # Create new session
                    messages = [
                        {"role": "user", "content": message, "timestamp": datetime.utcnow().isoformat()},
                        {"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()}
                    ]
                    
                    await conn.execute("""
                        INSERT INTO public.chat_sessions (user_id, video_id, session_id, messages, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, NOW(), NOW())
                    """, user_id, video_id, session_id, messages)
                
                logger.info(f"✅ Chat message saved for video: {video_id}")
                
        except Exception as e:
            logger.error(f"❌ Error saving chat message: {e}")
            raise

    async def get_chat_history(self, video_id: str, session_id: str) -> List[Dict[str, Any]]:
        """Get chat history for a session"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT messages FROM public.chat_sessions 
                    WHERE video_id = $1 AND session_id = $2
                """, video_id, session_id)
                
                if row and row['messages']:
                    return row['messages']
                return []
                
        except Exception as e:
            logger.error(f"❌ Error getting chat history: {e}")
            return []

# Global instance
supabase_service = SupabaseService()