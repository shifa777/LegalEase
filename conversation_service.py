"""
Conversation Management Service
Handles user chat history storage and retrieval
"""
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from db import conversations_collection


class ConversationService:
    """Service for managing user conversations"""
    
    @staticmethod
    def create_conversation(user_email: str, title: str = "New Conversation") -> Dict[str, Any]:
        """
        Create a new conversation for a user
        
        Args:
            user_email: User's email address
            title: Conversation title (auto-generated from first message if not provided)
            
        Returns:
            Created conversation document
        """
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"
        
        conversation = {
            "conversation_id": conversation_id,
            "user_email": user_email,
            "title": title,
            "messages": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "preview": ""
        }
        
        try:
            conversations_collection.insert_one(conversation)
            print(f"Created conversation: {conversation_id} for {user_email}")
            
            # Return without MongoDB's _id
            return {
                "conversation_id": conversation_id,
                "title": title,
                "messages": [],
                "created_at": conversation["created_at"].isoformat(),
                "updated_at": conversation["updated_at"].isoformat(),
                "preview": ""
            }
        except Exception as e:
            print(f"Error creating conversation: {e}")
            raise
    
    @staticmethod
    def get_user_conversations(user_email: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get all conversations for a user (sorted by most recent)
        
        Args:
            user_email: User's email address
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversation summaries (without full messages)
        """
        try:
            conversations = conversations_collection.find(
                {"user_email": user_email}
            ).sort("updated_at", -1).limit(limit)
            
            result = []
            for conv in conversations:
                result.append({
                    "conversation_id": conv["conversation_id"],
                    "title": conv["title"],
                    "preview": conv.get("preview", ""),
                    "created_at": conv["created_at"].isoformat(),
                    "updated_at": conv["updated_at"].isoformat(),
                    "message_count": len(conv.get("messages", []))
                })
            
            return result
        except Exception as e:
            print(f"Error getting user conversations: {e}")
            return []
    
    @staticmethod
    def get_conversation(conversation_id: str, user_email: str) -> Optional[Dict[str, Any]]:
        """
        Get full conversation with all messages
        
        Args:
            conversation_id: Conversation ID
            user_email: User's email (for security - ensure user owns conversation)
            
        Returns:
            Full conversation with messages or None
        """
        try:
            conversation = conversations_collection.find_one({
                "conversation_id": conversation_id,
                "user_email": user_email
            })
            
            if not conversation:
                return None
            
            return {
                "conversation_id": conversation["conversation_id"],
                "title": conversation["title"],
                "messages": conversation.get("messages", []),
                "created_at": conversation["created_at"].isoformat(),
                "updated_at": conversation["updated_at"].isoformat(),
                "preview": conversation.get("preview", "")
            }
        except Exception as e:
            print(f"Error getting conversation: {e}")
            return None
    
    @staticmethod
    def add_message(conversation_id: str, user_email: str, role: str, content: str) -> bool:
        """
        Add a message to a conversation
        
        Args:
            conversation_id: Conversation ID
            user_email: User's email
            role: Message role (user or assistant)
            content: Message content
            
        Returns:
            True if successful
        """
        try:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Update conversation with new message
            update = {
                "$push": {"messages": message},
                "$set": {"updated_at": datetime.utcnow()}
            }
            
            # Update title from first user message
            conversation = conversations_collection.find_one({
                "conversation_id": conversation_id,
                "user_email": user_email
            })
            
            if conversation:
                # If title is still "New Conversation" and this is a user message, update it
                if conversation["title"] == "New Conversation" and role == "user":
                    title = content[:50] + "..." if len(content) > 50 else content
                    update["$set"]["title"] = title
                
                # Update preview (last assistant message or user message)
                if role == "assistant":
                    preview = content[:100] + "..." if len(content) > 100 else content
                    update["$set"]["preview"] = preview
            
            result = conversations_collection.update_one(
                {
                    "conversation_id": conversation_id,
                    "user_email": user_email
                },
                update
            )
            
            return result.modified_count > 0
        except Exception as e:
            print(f"Error adding message: {e}")
            return False
    
    @staticmethod
    def update_conversation_title(conversation_id: str, user_email: str, title: str) -> bool:
        """
        Update conversation title
        
        Args:
            conversation_id: Conversation ID
            user_email: User's email
            title: New title
            
        Returns:
            True if successful
        """
        try:
            result = conversations_collection.update_one(
                {
                    "conversation_id": conversation_id,
                    "user_email": user_email
                },
                {
                    "$set": {
                        "title": title,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating title: {e}")
            return False
    
    @staticmethod
    def delete_conversation(conversation_id: str, user_email: str) -> bool:
        """
        Delete a conversation
        
        Args:
            conversation_id: Conversation ID
            user_email: User's email
            
        Returns:
            True if successful
        """
        try:
            result = conversations_collection.delete_one({
                "conversation_id": conversation_id,
                "user_email": user_email
            })
            
            if result.deleted_count > 0:
                print(f"Deleted conversation: {conversation_id}")
                return True
            return False
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            return False


# Singleton instance
conversation_service = ConversationService()
