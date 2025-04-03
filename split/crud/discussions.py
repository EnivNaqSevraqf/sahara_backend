from sqlalchemy.orm import Session
from ..models.channel import Channel
from ..models.message import Message

def get_discussions_page(current_user_data: dict, db: Session):
    channels = db.query(Channel).all()
    return channels

def get_messages(channel_id: int, current_user_data: dict, db: Session):
    messages = db.query(Message).filter(Message.channel_id == channel_id).all()
    return messages 