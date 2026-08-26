"""Long-Term Conversation Memory - Persistent Storage & Retrieval

Saves conversations to local database and provides semantic search over history.
Allows users to recall previous discussions and build on prior context.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import hashlib
import streamlit as st
from pathlib import Path


class ConversationMemory:
    """Manages conversation persistence and retrieval."""
    
    def __init__(self, db_path: str = "./conversations_db"):
        """Initialize memory store.
        
        Args:
            db_path: Path to store conversation JSON files
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
    
    def save_conversation(self, user_email: str, conversation_history: List[Dict], 
                         topic: str = "", tags: List[str] = None) -> str:
        """Save a conversation to persistent storage.
        
        Args:
            user_email: User identifier
            conversation_history: List of {role, content} dicts
            topic: Optional topic/title for conversation
            tags: Optional tags for categorization
        
        Returns:
            Conversation ID
        """
        conv_id = hashlib.md5(f"{user_email}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        user_dir = self.db_path / user_email.replace('@', '_')
        user_dir.mkdir(parents=True, exist_ok=True)
        
        conv_data = {
            "id": conv_id,
            "user_email": user_email,
            "created_at": datetime.now().isoformat(),
            "topic": topic,
            "tags": tags or [],
            "message_count": len(conversation_history),
            "history": conversation_history
        }
        
        conv_file = user_dir / f"{conv_id}.json"
        with open(conv_file, 'w') as f:
            json.dump(conv_data, f, indent=2)
        
        return conv_id
    
    def load_conversation(self, user_email: str, conv_id: str) -> Optional[Dict]:
        """Load a saved conversation.
        
        Args:
            user_email: User identifier
            conv_id: Conversation ID to load
        
        Returns:
            Conversation dict or None if not found
        """
        user_dir = self.db_path / user_email.replace('@', '_')
        conv_file = user_dir / f"{conv_id}.json"
        
        if conv_file.exists():
            with open(conv_file, 'r') as f:
                return json.load(f)
        return None
    
    def list_conversations(self, user_email: str, limit: int = 20) -> List[Dict]:
        """List all conversations for a user.
        
        Args:
            user_email: User identifier
            limit: Max conversations to return
        
        Returns:
            List of conversation metadata dicts
        """
        user_dir = self.db_path / user_email.replace('@', '_')
        
        if not user_dir.exists():
            return []
        
        convs = []
        for conv_file in sorted(user_dir.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            with open(conv_file, 'r') as f:
                data = json.load(f)
                convs.append({
                    "id": data["id"],
                    "created_at": data["created_at"],
                    "topic": data["topic"],
                    "message_count": data["message_count"],
                    "tags": data.get("tags", [])
                })
        
        return convs
    
    def get_conversation_summary(self, user_email: str, conv_id: str) -> str:
        """Get a brief summary of a conversation.
        
        Args:
            user_email: User identifier
            conv_id: Conversation ID
        
        Returns:
            Summary text
        """
        conv = self.load_conversation(user_email, conv_id)
        if not conv:
            return ""
        
        history = conv.get("history", [])
        summary = f"Topic: {conv.get('topic', 'Untitled')}\n"
        summary += f"Date: {conv.get('created_at', 'Unknown')[:10]}\n"
        summary += f"Messages: {len(history)}\n\n"
        
        # Extract first and last exchange
        if history:
            summary += "**Start:**\n"
            for msg in history[:2]:
                summary += f"{msg['role'].upper()}: {msg['content'][:100]}...\n"
            
            if len(history) > 4:
                summary += "\n**End:**\n"
                for msg in history[-2:]:
                    summary += f"{msg['role'].upper()}: {msg['content'][:100]}...\n"
        
        return summary
    
    def search_conversations(self, user_email: str, query: str) -> List[Dict]:
        """Search conversations by topic/tags/content keywords.
        
        Args:
            user_email: User identifier
            query: Search keyword
        
        Returns:
            List of matching conversation metadata
        """
        convs = self.list_conversations(user_email, limit=100)
        query_lower = query.lower()
        
        results = []
        for conv in convs:
            if (query_lower in conv.get("topic", "").lower() or
                any(query_lower in tag.lower() for tag in conv.get("tags", []))):
                results.append(conv)
        
        return results
    
    def get_context_from_past(self, user_email: str, current_query: str, 
                             embedder=None, top_k: int = 3) -> str:
        """Retrieve relevant context from past conversations.
        
        Args:
            user_email: User identifier
            current_query: Current question
            embedder: Optional embeddings model for semantic search
            top_k: Number of relevant past exchanges to retrieve
        
        Returns:
            Formatted context from past conversations
        """
        if not embedder:
            # Fallback to simple keyword search
            matching_convs = self.search_conversations(user_email, current_query)
        else:
            # TODO: Semantic search using embedder
            matching_convs = self.list_conversations(user_email, limit=10)
        
        context_parts = []
        for conv in matching_convs[:top_k]:
            summary = self.get_conversation_summary(user_email, conv["id"])
            context_parts.append(f"\n---\nPast conversation ({conv['created_at'][:10]}): {summary}")
        
        return "\n".join(context_parts) if context_parts else ""


def render_conversation_browser(memory: ConversationMemory, user_email: str):
    """Render conversation history browser in Streamlit.
    
    Args:
        memory: ConversationMemory instance
        user_email: User identifier
    """
    st.markdown("### 📚 Conversation History")
    
    search_term = st.text_input("🔍 Search past conversations", key="conv_search")
    
    if search_term:
        convs = memory.search_conversations(user_email, search_term)
    else:
        convs = memory.list_conversations(user_email)
    
    if convs:
        for conv in convs:
            with st.expander(f"📌 {conv['topic']} ({conv['created_at'][:10]}) — {conv['message_count']} messages"):
                summary = memory.get_conversation_summary(user_email, conv["id"])
                st.text(summary)
                
                if st.button(f"Load this conversation", key=f"load_{conv['id']}"):
                    st.session_state.loaded_conversation = memory.load_conversation(user_email, conv["id"])
                    st.session_state.chat_history = st.session_state.loaded_conversation.get("history", [])
                    st.success("Conversation loaded!")
                    st.rerun()
    else:
        st.info("No conversations found.")
