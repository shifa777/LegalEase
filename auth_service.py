"""
Authentication service for user management
"""
import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
from db import users_collection
from models import User

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

class AuthService:
    """Handle user authentication and management"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    
    @staticmethod
    def generate_token(user_id: str, email: str) -> str:
        """Generate JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    @staticmethod
    def signup(email: str, name: str, password: str) -> Dict:
        """Register a new user"""
        try:
            # Check if user already exists
            existing_user = users_collection.find_one({'email': email})
            if existing_user:
                return {
                    'success': False,
                    'error': 'User with this email already exists'
                }
            
            # Validate inputs
            if not email or not name or not password:
                return {
                    'success': False,
                    'error': 'All fields are required'
                }
            
            if len(password) < 6:
                return {
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                }
            
            # Hash password
            password_hash = AuthService.hash_password(password)
            
            # Create user
            user_data = {
                'email': email,
                'name': name,
                'password_hash': password_hash,
                'created_at': datetime.utcnow(),
                'last_login': None
            }
            
            result = users_collection.insert_one(user_data)
            user_id = str(result.inserted_id)
            
            # Generate token
            token = AuthService.generate_token(user_id, email)
            
            # Get user object
            user = User.from_dict({**user_data, '_id': result.inserted_id})
            
            return {
                'success': True,
                'token': token,
                'user': user.to_dict()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Signup failed: {str(e)}'
            }
    
    @staticmethod
    def login(email: str, password: str) -> Dict:
        """Authenticate user and return token"""
        try:
            # Find user
            user_data = users_collection.find_one({'email': email})
            if not user_data:
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }
            
            # Verify password
            if not AuthService.verify_password(password, user_data['password_hash']):
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }
            
            # Update last login
            users_collection.update_one(
                {'_id': user_data['_id']},
                {'$set': {'last_login': datetime.utcnow()}}
            )
            
            # Generate token
            user_id = str(user_data['_id'])
            token = AuthService.generate_token(user_id, email)
            
            # Get user object
            user = User.from_dict(user_data)
            
            return {
                'success': True,
                'token': token,
                'user': user.to_dict()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Login failed: {str(e)}'
            }
    
    @staticmethod
    def get_user_from_token(token: str) -> Optional[Dict]:
        """Get user information from token"""
        try:
            payload = AuthService.verify_token(token)
            if not payload:
                return None
            
            user_data = users_collection.find_one({'email': payload['email']})
            if not user_data:
                return None
            
            user = User.from_dict(user_data)
            return user.to_dict()
            
        except Exception:
            return None
    
    @staticmethod
    def forgot_password(email: str) -> Dict:
        """Initiate password reset (simplified version)"""
        try:
            user_data = users_collection.find_one({'email': email})
            if not user_data:
                # Don't reveal if user exists
                return {
                    'success': True,
                    'message': 'If the email exists, a reset link will be sent'
                }
            
            # In production, you would:
            # 1. Generate a reset token
            # 2. Send email with reset link
            # For now, we just acknowledge the request
            
            return {
                'success': True,
                'message': 'If the email exists, a reset link will be sent'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Password reset failed: {str(e)}'
            }

# Create singleton instance
auth_service = AuthService()
