"""
Authentication service for JWT token handling and user management
"""

import os
import jwt
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from services.supabase_service import supabase_service

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# HTTP Bearer token scheme
security = HTTPBearer()

class AuthUser(BaseModel):
    """User model for authentication"""
    id: str
    email: str
    name: Optional[str] = None

class AuthService:
    """Service for handling authentication and JWT tokens"""
    
    def __init__(self):
        self.jwt_secret = JWT_SECRET
        self.jwt_algorithm = JWT_ALGORITHM
        
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return pwd_context.hash(password)
    
    def create_access_token(self, user_id: str, email: str, name: Optional[str] = None) -> str:
        """Create JWT access token"""
        try:
            payload = {
                "sub": user_id,
                "email": email,
                "name": name,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
            }
            
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            logger.info(f"✅ Access token created for user: {email}")
            return token
            
        except Exception as e:
            logger.error(f"❌ Error creating access token: {e}")
            raise HTTPException(status_code=500, detail="Could not create access token")
    
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and verify JWT token"""
        try:
            payload = jwt.decode(
                token, 
                self.jwt_secret, 
                algorithms=[self.jwt_algorithm]
            )
            
            # Check if token is expired
            if datetime.utcnow() > datetime.fromtimestamp(payload.get("exp", 0)):
                logger.warning("Token has expired")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error decoding token: {e}")
            return None
    
    async def get_current_user(self, token: str) -> Optional[AuthUser]:
        """Get current user from JWT token"""
        try:
            payload = self.decode_token(token)
            if not payload:
                return None
            
            user_id = payload.get("sub")
            email = payload.get("email")
            name = payload.get("name")
            
            if not user_id or not email:
                logger.warning("Invalid token payload")
                return None
            
            return AuthUser(id=user_id, email=email, name=name)
            
        except Exception as e:
            logger.error(f"❌ Error getting current user: {e}")
            return None

# Global auth service instance
auth_service = AuthService()

# Dependency for getting current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> AuthUser:
    """FastAPI dependency to get current authenticated user"""
    if not credentials:
        raise HTTPException(status_code=401, detail="No authentication token provided")
    
    token = credentials.credentials
    user = await auth_service.get_current_user(token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user

# Optional dependency for getting current user (doesn't raise exception)
async def get_current_user_optional(request: Request) -> Optional[AuthUser]:
    """Optional dependency to get current user without raising exception"""
    try:
        # Try to get authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        
        token = auth_header.split(" ")[1]
        user = await auth_service.get_current_user(token)
        return user
        
    except Exception:
        return None

# Middleware for extracting user from token
async def auth_middleware(request: Request, call_next):
    """Middleware to extract user info from token"""
    try:
        # Get user if token exists
        user = await get_current_user_optional(request)
        
        # Add user to request state
        request.state.user = user
        
        # Continue with request
        response = await call_next(request)
        return response
        
    except Exception as e:
        logger.error(f"❌ Error in auth middleware: {e}")
        # Continue without user
        request.state.user = None
        response = await call_next(request)
        return response

# Authentication models
class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser

class UserResponse(BaseModel):
    user: AuthUser
    
    @classmethod
    def from_auth_user(cls, user: AuthUser):
        return cls(user=user)