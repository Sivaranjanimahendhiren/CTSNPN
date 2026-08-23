"""
Conversation Repository: Handles PostgreSQL persistence of patient chat messages.
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import PatientConversation


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_message(
        self,
        chat_id: str,
        role: str,
        message_text: str,
        patient_id: Optional[str] = "P001",
        channel: str = "TELEGRAM",
    ) -> PatientConversation:
        """Saves an incoming or outgoing conversation message."""
        conv = PatientConversation(
            chat_id=str(chat_id),
            patient_id=patient_id,
            role=role,
            message_text=message_text,
            channel=channel,
            created_at=datetime.utcnow(),
        )
        self.session.add(conv)
        self.session.flush()
        return conv

    def get_conversation_history(
        self,
        chat_id: str,
        limit: int = 20,
    ) -> List[PatientConversation]:
        """Retrieves recent conversation messages for a chat session in chronological order."""
        return (
            self.session.query(PatientConversation)
            .filter(PatientConversation.chat_id == str(chat_id))
            .order_by(PatientConversation.created_at.asc())
            .limit(limit)
            .all()
        )
