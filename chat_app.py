from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text, Boolean, Enum, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import JSONB
import json
import os
from datetime import datetime
import uvicorn
import base64
import uuid
from fastapi.staticfiles import StaticFiles
import enum

# Database configuration - using main.py's database
DATABASE_URL = "postgresql://avnadmin:AVNS_DkrVvzHCnOiMVJwagav@pg-8b6fabf-sahara-team-8.f.aivencloud.com:17950/defaultdb"
Base = declarative_base()

# Create required directories
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# Role enum from main.py
class RoleType(enum.Enum):
    PROF = "prof"
    STUDENT = "student"
    TA = "ta"

# SQLAlchemy Models
class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    role = Column(Enum(RoleType), nullable=False, unique=True)
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=False, unique=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    hashed_password = Column(String, nullable=False)

    role = relationship("Role", back_populates="users")
    teams = relationship("Team", secondary="team_members", back_populates="members")
    messages = relationship("Message", back_populates="sender")

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    members = relationship("User", secondary="team_members", back_populates="teams")

team_members = Table(
    "team_members", Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
)

# Chat-specific models
class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    type = Column(String(10), nullable=False)  # global, team, or ta-team
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    messages = relationship("Message", back_populates="channel")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(Integer, ForeignKey("channels.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    message_type = Column(String(10), default='text')
    file_name = Column(String(255))

    sender = relationship("User", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")

# Create engine and sessionmaker
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create app
app = FastAPI()

# Add CORS middleware and static files mount
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database with required tables"""
    Base.metadata.create_all(bind=engine)
    
    # Only insert initial data if the tables are empty
    db = SessionLocal()
    try:
        if db.query(Channel).count() == 0:
            # Create only global channel
            global_channel = Channel(name='Global Chat', type='global')
            db.add(global_channel)
            db.commit()

        # Comment out team initialization for now
        # if db.query(Team).count() == 0:
        #     # Insert teams
        #     teams = [
        #         Team(name='Team A'),
        #         Team(name='Team B'),
        #         Team(name='Team C')
        #     ]
        #     db.add_all(teams)
        #     db.commit()

        #     # Insert TAs
        #     for i, team in enumerate(teams):
        #         ta = User(
        #             name=f'TA {i+1}',
        #             email=f'ta{i+1}@example.com',
        #             username=f'ta{i+1}',
        #             hashed_password='password',
        #             role_id=3,  # Assuming role_id 3 is for TA
        #             team_id=team.id
        #         )
        #         db.add(ta)
            
        #     # Insert regular students
        #     for team in teams:
        #         for i in range(5):
        #             student = User(
        #                 name=f'Student {i+1} of {team.name}',
        #                 email=f'student{i+1}@example.com',
        #                 username=f'student{i+1}',
        #                 hashed_password='password',
        #                 role_id=2,  # Assuming role_id 2 is for Student
        #                 team_id=team.id
        #             )
        #             db.add(student)
            
        #     # Create team channels
        #     for team in teams:
        #         team_channel = Channel(
        #             name=f'Team {team.name} Chat',
        #             type='team',
        #             team_id=team.id
        #         )
        #         ta_channel = Channel(
        #             name=f'Team {team.name} TA Channel',
        #             type='ta-team',
        #             team_id=team.id
        #         )
        #         db.add_all([team_channel, ta_channel])
            
        #     db.commit()
    finally:
        db.close()

# WebSocket connection manager
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

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# Pydantic models for request/response
class MessageModel(BaseModel):
    content: str
    channel_id: int
    sender_id: int
    message_type: str = 'text'
    file_data: Optional[str] = None
    file_name: Optional[str] = None

# Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/login")
async def login(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {username}")

    # Only get global channel
    channels = db.query(Channel).filter(Channel.type == 'global').all()

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "team_id": user.team_id,
        "team_name": user.teams[0].name if user.teams else 'No Team',
        "is_ta": user.role.role == RoleType.TA,
        "channels": channels
    }

@app.get("/api/channels/{channel_id}/messages")
async def get_messages(channel_id: int, db: Session = Depends(get_db)):
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

@app.post("/api/messages")
async def send_message(message: MessageModel, db: Session = Depends(get_db)):
    try:
        file_path = None
        if message.message_type == 'file' and message.file_data:
            file_data = base64.b64decode(message.file_data)
            file_name = f"{uuid.uuid4()}_{message.file_name}"
            file_path = os.path.join("uploads", file_name)
            with open(file_path, "wb") as f:
                f.write(file_data)
            message.content = file_name  # Store just the filename, not the full path

        new_message = Message(
            content=message.content,
            sender_id=message.sender_id,
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

@app.websocket("/ws/{channel_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: int, user_id: int):
    await manager.connect(websocket, channel_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)