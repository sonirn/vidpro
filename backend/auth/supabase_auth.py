"""
Supabase authentication service - handles user authentication only
All data storage is done through MongoDB
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from supabase import create_client, Client
from pydantic import BaseModel
import jwt
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class SupabaseAuthUser(BaseModel):
    """User model for Supabase authentication"""
    id: str
    email: str
    email_confirmed_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class SupabaseAuth:
    """Supabase authentication service"""
    
    def __init__(self):
        self.supabase_url = os.environ.get('SUPABASE_URL')
        self.supabase_anon_key = os.environ.get('SUPABASE_ANON_KEY')
        self.supabase_service_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        
        if not all([self.supabase_url, self.supabase_anon_key]):
            raise ValueError("Missing required Supabase configuration")
        
        # Initialize Supabase client for authentication only
        self.supabase: Client = create_client(self.supabase_url, self.supabase_anon_key)
        
        if self.supabase_service_key:
            self.admin_client: Client = create_client(self.supabase_url, self.supabase_service_key)
        else:
            self.admin_client = None
        
        logger.info("✅ Supabase authentication service initialized")
    
    async def sign_up(self, email: str, password: str) -> Dict[str, Any]:
        """Sign up new user"""
        try:
            response = self.supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            
            if response.user:
                return {
                    "user": response.user,
                    "session": response.session,
                    "message": "User created successfully"
                }
            else:
                raise HTTPException(status_code=400, detail="Failed to create user")
        
        except Exception as e:
            logger.error(f"Sign up error: {e}")
            raise HTTPException(status_code=400, detail=f"Sign up failed: {str(e)}")
    
    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in user"""
        try:
            response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user and response.session:
                return {
                    "user": response.user,
                    "session": response.session,
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "message": "Login successful"
                }
            else:
                raise HTTPException(status_code=401, detail="Invalid credentials")
        
        except Exception as e:
            logger.error(f"Sign in error: {e}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
    
    async def verify_token(self, token: str) -> SupabaseAuthUser:
        """Verify JWT token and return user info"""
        try:
            # Get user info from token
            user_response = self.supabase.auth.get_user(token)
            
            if not user_response.user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            user = user_response.user
            
            return SupabaseAuthUser(
                id=user.id,
                email=user.email,
                email_confirmed_at=user.email_confirmed_at,
                last_sign_in_at=user.last_sign_in_at,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
        
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token"""
        try:
            response = self.supabase.auth.refresh_session(refresh_token)
            
            if response.session:
                return {
                    "session": response.session,
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "message": "Token refreshed successfully"
                }
            else:
                raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    async def sign_out(self, token: str) -> Dict[str, Any]:
        """Sign out user"""
        try:
            # Note: Supabase doesn't have a direct sign out with token method
            # The client should just discard the token
            return {"message": "Signed out successfully"}
        
        except Exception as e:
            logger.error(f"Sign out error: {e}")
            raise HTTPException(status_code=400, detail="Sign out failed")

# Global authentication instance
auth_service = SupabaseAuth()

# Convenience functions for FastAPI dependencies
async def get_auth():
    """Get auth service instance"""
    return auth_service

async def verify_token(token: str) -> SupabaseAuthUser:
    """Verify token and return user"""
    return await auth_service.verify_token(token)