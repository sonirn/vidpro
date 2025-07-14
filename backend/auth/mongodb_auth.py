"""
MongoDB-based authentication system for video generation website
"""
import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid
import logging
from database.mongodb_config import get_db

logger = logging.getLogger(__name__)

class MongoDBAuth:
    def __init__(self):
        self.db = get_db()
        self.jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key-here')
        self.jwt_algorithm = 'HS256'
        self.token_expiry_hours = 24 * 7  # 7 days
        
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def generate_token(self, user_id: str) -> str:
        """Generate JWT token for user"""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None
    
    def register_user(self, email: str, password: str) -> Dict[str, Any]:
        """Register new user"""
        try:
            # Check if user already exists
            existing_user = self.db.users.find_one({"email": email})
            if existing_user:
                return {"success": False, "error": "User already exists"}
            
            # Create new user
            user_id = str(uuid.uuid4())
            user_data = {
                "user_id": user_id,
                "email": email,
                "password_hash": self.hash_password(password),
                "created_at": datetime.utcnow(),
                "last_login": datetime.utcnow(),
                "is_active": True,
                "subscription_status": "free",
                "video_quota": 10,  # Free users get 10 videos
                "videos_used": 0,
            }
            
            # Insert user into database
            result = self.db.users.insert_one(user_data)
            if result.inserted_id:
                # Generate token
                token = self.generate_token(user_id)
                
                # Return user data without password hash and _id
                response_user = {k: v for k, v in user_data.items() if k != 'password_hash'}
                
                return {
                    "success": True,
                    "user": response_user,
                    "token": token
                }
            else:
                return {"success": False, "error": "Failed to create user"}
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return {"success": False, "error": "Registration failed"}
    
    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Login user and return token"""
        try:
            # Find user by email
            user = self.db.users.find_one({"email": email})
            if not user:
                return {"success": False, "error": "Invalid credentials"}
            
            # Verify password
            if not self.verify_password(password, user['password_hash']):
                return {"success": False, "error": "Invalid credentials"}
            
            # Check if user is active
            if not user.get('is_active', True):
                return {"success": False, "error": "Account deactivated"}
            
            # Update last login
            self.db.users.update_one(
                {"user_id": user['user_id']},
                {"$set": {"last_login": datetime.utcnow()}}
            )
            
            # Generate token
            token = self.generate_token(user['user_id'])
            
            # Return user data without password hash
            user.pop('password_hash')
            user.pop('_id')  # Remove MongoDB ObjectId
            
            return {
                "success": True,
                "user": user,
                "token": token
            }
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return {"success": False, "error": "Login failed"}
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            user = self.db.users.find_one({"user_id": user_id})
            if user:
                user.pop('password_hash', None)
                user.pop('_id', None)
                return user
            return None
        except Exception as e:
            logger.error(f"Get user error: {e}")
            return None
    
    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get user by JWT token"""
        payload = self.verify_token(token)
        if payload:
            return self.get_user_by_id(payload['user_id'])
        return None
    
    def update_user_quota(self, user_id: str, videos_used: int) -> bool:
        """Update user's video usage quota"""
        try:
            result = self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"videos_used": videos_used}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Update quota error: {e}")
            return False
    
    def check_user_quota(self, user_id: str) -> Dict[str, Any]:
        """Check if user has remaining quota"""
        try:
            user = self.db.users.find_one({"user_id": user_id})
            if not user:
                return {"has_quota": False, "remaining": 0}
            
            video_quota = user.get('video_quota', 0)
            videos_used = user.get('videos_used', 0)
            remaining = max(0, video_quota - videos_used)
            
            return {
                "has_quota": remaining > 0,
                "remaining": remaining,
                "total_quota": video_quota,
                "used": videos_used
            }
        except Exception as e:
            logger.error(f"Check quota error: {e}")
            return {"has_quota": False, "remaining": 0}
    
    def logout_user(self, user_id: str) -> bool:
        """Logout user (in this implementation, just return True as JWT is stateless)"""
        # In a more sophisticated implementation, you might maintain a blacklist of tokens
        # For now, we'll just return True as the client should discard the token
        return True

# Global auth instance
auth = MongoDBAuth()

def get_auth():
    """Get authentication instance"""
    return auth