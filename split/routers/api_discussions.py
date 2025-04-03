from fastapi import APIRouter, Depends, HTTPException, status, WebSocket
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.user import User
from ..models.roles import RoleType
from ..models.team import Team
from ..models.team_ta import Team_TA
from ..models.channel import Channel
from ..models.message import Message
from ..schemas.discussion_schemas import MessageModel
from ..dependencies.auth import prof_or_ta_required, prof_required, get_current_user, get_current_user_from_string, validate_channel_access
from fastapi.responses import JSONResponse
import os
import uuid
import json
from base64 import b64decode, b64encode

router = APIRouter(
    prefix="/api/discussions",
    tags=["API Discussions"]
)

@router.post("/discussions")
async def get_discussions_page(
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user_data["user"]
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user.name}")

    channels = []
    
    # Add global channel for all users
    global_channel = db.query(Channel).filter(Channel.type == 'global').first()
    if not global_channel:
        global_channel = Channel(
            name='Global Chat',
            type='global'
        )
        db.add(global_channel)
        db.commit()
        db.refresh(global_channel)
    
    channels.append(global_channel)
    
    # For students: add their team channel and team-TA channel if they exist
    if user.role.role == RoleType.STUDENT and user.teams:
        team = user.teams[0]  # Get the student's team
        
        # Get or create team channel
        team_channel = db.query(Channel).filter(
            Channel.type == 'team',
            Channel.team_id == team.id
        ).first()
        
        if not team_channel:
            team_channel = Channel(
                name=f'Team {team.name} Chat',
                type='team',
                team_id=team.id
            )
            db.add(team_channel)
            db.commit()
        
        channels.append(team_channel)
        
        # Check if team has TA(s) and add team-TA channel if it exists
        team_ta = db.query(Team_TA).filter(Team_TA.team_id == team.id).first()
        if team_ta:
            ta_channel = db.query(Channel).filter(
                Channel.type == 'ta-team',
                Channel.team_id == team.id
            ).first()
            
            if not ta_channel:
                ta_channel = Channel(
                    name=f'Team {team.name} TA Channel',
                    type='ta-team',
                    team_id=team.id
                )
                db.add(ta_channel)
                db.commit()
            
            channels.append(ta_channel)
    
    # For TAs and Profs: add all their team-TA channels
    elif user.role.role in [RoleType.TA, RoleType.PROF]:
        # Get all teams this TA/Prof is assigned to
        team_tas = db.query(Team_TA).filter(Team_TA.ta_id == user.id).all()
        for team_ta in team_tas:
            ta_channel = db.query(Channel).filter(
                Channel.type == 'ta-team',
                Channel.team_id == team_ta.team_id
            ).first()
            
            if not ta_channel:
                team = db.query(Team).filter(Team.id == team_ta.team_id).first()
                ta_channel = Channel(
                    name=f'Team {team.name} TA Channel',
                    type='ta-team',
                    team_id=team.id
                )
                db.add(ta_channel)
                db.commit()
            
            channels.append(ta_channel)

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "team_id": user.team_id,
        "team_name": user.teams[0].name if user.teams else 'No Team',
        "is_ta": user.role.role in [RoleType.TA, RoleType.PROF],
        "channels": channels,
        "role": user.role.role.value
    }


@router.get("/discussions/channels/{channel_id}/messages")
async def get_messages(
    channel_id: int,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user_data["user"]
    
    # Validate user's access to the channel
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )
    
    messages = db.query(Message).filter(
        Message.channel_id == channel_id
    ).order_by(Message.created_at).all()
    
    # Convert messages to dictionary with sender information
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

@router.post("/discussions/messages")
async def send_message(
    message: MessageModel,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
): 
    user = current_user_data["user"]

    if(message.sender_id != user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot send messages on behalf of another user"
        )
    
    # Validate user's access to the channel
    if not validate_channel_access(user, message.channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )

    try:
        file_path = None
        if message.message_type == 'file' and message.file_data:
            file_data = b64decode(message.file_data)
            file_name = f"{uuid.uuid4()}_{message.file_name}"
            file_path = os.path.join("forums_uploads", file_name)
            with open(file_path, "wb") as f:
                f.write(file_data)
            message.content = file_name  # Store just the filename, not the full path

        new_message = Message(
            content=message.content,
            sender_id=user.id,
            channel_id=message.channel_id,
            message_type=message.message_type,
            file_name=message.content if message.message_type == 'file' else None  # Use content as file_name for files
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
            "file_name": new_message.content if message.message_type == 'file' else None  # Use content as file_name for files
        }

        await manager.broadcast(
            json.dumps(message_data),
            message.channel_id
        )

        return message_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/discussions/ws/{channel_id}/{token}")
async def websocket_endpoint(
    websocket: WebSocket, 
    channel_id: int, 
    #user_id: int,
    token: str,
    # current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # print("In here")
    current_user_data = get_current_user_from_string(token , db)
    if not current_user_data:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    user = current_user_data["user"]
    
    # Validate user's access to the channel
    print(f"User: {user.username}, Channel ID: {channel_id}")
    if not validate_channel_access(user, channel_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this channel"
        )

    #await manager.connect(websocket, channel_id, int(token))
    

    await manager.connect(websocket, channel_id, user.id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)

@router.get("/discussions/download/{file_name}")
async def download_file(
    file_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a file and return it as base64 encoded data"""
    try:
        # Get the file record from the database
        file_record = db.query(Message).filter(Message.file_name == file_name).first()
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if the user has access to the file
        user = current_user["user"]
        if not validate_channel_access(user, file_record.channel_id, db):
            raise HTTPException(status_code=403, detail="Not authorized to download this file")
        # Check if the file is a reference file
        if file_record.message_type != 'file':
            raise HTTPException(status_code=400, detail="Not a reference file")
        
        # Convert URL path to local path
        local_path = file_record.file_name.lstrip('/')
        local_path = os.path.join("forums_uploads", local_path)
        # Check if the file exists locally
        if not os.path.exists(local_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read the file and encode it in base64
        with open(local_path, "rb") as file:
            file_data = file.read()
            encoded_file_data = b64encode(file_data).decode('utf-8')
        
        return JSONResponse(status_code=200, content={
            "file_id": file_record.id,
            "original_filename": file_record.file_name,
            "file_data": encoded_file_data
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

from sqlalchemy.orm import Session