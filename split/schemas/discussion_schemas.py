from pydantic import BaseModel
from typing import Optional

class MessageModel(BaseModel):
    content: str
    channel_id: int
    sender_id: int
    message_type: str = 'text'
    file_data: Optional[str] = None
    file_name: Optional[str] = None 