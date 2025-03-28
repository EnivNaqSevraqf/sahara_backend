from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
import base64
import uuid
import os
from datetime import datetime

from app.db.session import get_db
from app.models.chat import Channel, Message
from app.models.user import User, RoleType
from app.models.team import Team_TA
from app.core.security.auth import get_current_user

router = APIRouter(prefix="/discussions", tags=["chat"])

class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel_id: int, user_id: int):
        await websocket.accept()
        room_name = f"channel_{channel_id}"
        
        if room_name not in self.rooms:
            self.rooms[room_name] = []
        
        self.rooms[room_name].append(websocket)
        websocket.user_id = user_id
    
    def disconnect(self, websocket: WebSocket, channel_id: int):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            self.rooms[room_name].remove(websocket)
            if not self.rooms[room_name]:
                del self.rooms[room_name]
    
    async def broadcast(self, message: str, channel_id: int):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            dead_connections = []
            for connection in self.rooms[room_name]:
                try:
                    await connection.send_text(message)
                except WebSocketDisconnect:
                    dead_connections.append(connection)
            
            for conn in dead_connections:
                self.rooms[room_name].remove(conn)

manager = ConnectionManager()

def validate_channel_access(user: User, channel_id: int, db: Session) -> bool:
    """Validates whether a user has access to a specific channel."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return False
        
    if channel.type == 'global':
        return True
        
    if channel.type == 'team':
        return user.team_id == channel.team_id
        
    if channel.type == 'ta-team':
        if user.role.role == RoleType.TA:
            ta_assignment = db.query("Team_TA").filter(
                Team_TA.team_id == channel.team_id,
                Team_TA.ta_id == user.id
            ).first()
            return ta_assignment is not None
        if user.role.role == RoleType.STUDENT:
            return user.team_id == channel.team_id
            
    return False

@router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user["user"]
    
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(status_code=403, detail="You do not have access to this channel")
    
    messages = db.query(Message).filter(
        Message.channel_id == channel_id
    ).order_by(Message.created_at).all()
    
    return [
        {
            "id": message.id,
            "content": message.content,
            "sender_id": message.sender_id,
            "sender_name": message.sender.name,
            "channel_id": message.channel_id,
            "created_at": message.created_at.isoformat(),
            "message_type": message.message_type,
            "file_name": message.file_name
        } for message in messages
    ]

@router.websocket("/ws/{channel_id}/{token}")
async def websocket_endpoint(
    websocket: WebSocket, 
    channel_id: int, 
    token: str,
    db: Session = Depends(get_db)
):
    current_user_data = get_current_user(token, db)
    if not current_user_data:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    user = current_user_data["user"]
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(status_code=403, detail="You do not have access to this channel")

    await manager.connect(websocket, channel_id, user.id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)

@router.post("/messages")
async def send_message(
    content: str,
    channel_id: int,
    message_type: str = "text",
    file_data: str = None,
    file_name: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
): 
    user = current_user["user"]
    
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(status_code=403, detail="You do not have access to this channel")

    try:
        file_path = None
        if message_type == 'file' and file_data:
            file_data = base64.b64decode(file_data)
            file_name = f"{uuid.uuid4()}_{file_name}"
            file_path = os.path.join("forums_uploads", file_name)
            with open(file_path, "wb") as f:
                f.write(file_data)
            content = file_name

        new_message = Message(
            content=content,
            sender_id=user.id,
            channel_id=channel_id,
            message_type=message_type,
            file_name=file_name if message_type == 'file' else None
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        # Format message for broadcasting
        message_data = {
            "id": new_message.id,
            "content": new_message.content,
            "sender_id": new_message.sender_id,
            "sender_name": new_message.sender.name,
            "channel_id": new_message.channel_id,
            "created_at": new_message.created_at.isoformat(),
            "message_type": new_message.message_type,
            "file_name": new_message.file_name
        }

        await manager.broadcast(json.dumps(message_data), channel_id)
        return message_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))