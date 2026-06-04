"""
User model for authentication
"""
from datetime import datetime
from typing import Optional

class User:
    """User model for MongoDB"""
    
    def __init__(self, email: str, name: str, password_hash: str, 
                 _id: Optional[str] = None, created_at: Optional[datetime] = None,
                 last_login: Optional[datetime] = None):
        self.email = email
        self.name = name
        self.password_hash = password_hash
        self._id = _id
        self.created_at = created_at or datetime.utcnow()
        self.last_login = last_login
    
    def to_dict(self):
        """Convert user to dictionary (exclude password)"""
        return {
            "id": str(self._id) if self._id else None,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
    
    @staticmethod
    def from_dict(data: dict):
        """Create User from dictionary"""
        return User(
            email=data.get('email'),
            name=data.get('name'),
            password_hash=data.get('password_hash'),
            _id=data.get('_id'),
            created_at=data.get('created_at'),
            last_login=data.get('last_login')
        )
