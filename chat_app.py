from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os
from datetime import datetime
import uvicorn

# Create app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Database configuration
DB_CONFIG = {
    "dbname": "chat_db",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost"
}

def init_db():
    """Initialize the database with required tables"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Create teams table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS teams (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL
    )
    ''')
    
    # Create students table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        password VARCHAR(50) NOT NULL,
        roll_no VARCHAR(50) UNIQUE NOT NULL,
        team_id INTEGER REFERENCES teams(id)
    )
    ''')
    
    # Create channels table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        type VARCHAR(10) NOT NULL CHECK (type IN ('global', 'team')),
        team_id INTEGER REFERENCES teams(id)
    )
    ''')
    
    # Create messages table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        content TEXT NOT NULL,
        sender_id INTEGER REFERENCES students(id),
        channel_id INTEGER REFERENCES channels(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert dummy data if not exists
    cur.execute("SELECT COUNT(*) FROM teams")
    if cur.fetchone()[0] == 0:
        # Insert teams
        cur.execute('''
        INSERT INTO teams (name) VALUES 
        ('Team A'), ('Team B'), ('Team C')
        ''')
        
        # Insert students (5 students per team)
        for team_id in range(1, 4):
            for i in range(5):
                student_num = (team_id - 1) * 5 + i + 1
                cur.execute('''
                INSERT INTO students (name, password, roll_no, team_id)
                VALUES (%s, %s, %s, %s)
                ''', (f'Student {student_num}', 'password', f'ROLL{student_num}', team_id))
        
        # Create global channel
        cur.execute('''
        INSERT INTO channels (name, type, team_id)
        VALUES ('Global Chat', 'global', NULL)
        ''')
        
        # Create team channels
        for team_id in range(1, 4):
            cur.execute('''
            INSERT INTO channels (name, type, team_id)
            VALUES (%s, 'team', %s)
            ''', (f'Team {team_id} Chat', team_id))
    
    conn.commit()
    cur.close()
    conn.close()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    os.makedirs("templates", exist_ok=True)
    init_db()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[int, WebSocket]] = {
            'global': {},
            'team': {}
        }
    
    async def connect(self, websocket: WebSocket, channel_id: int, user_id: int):
        await websocket.accept()
        channel_type = self.get_channel_type(channel_id)
        if channel_type not in self.active_connections:
            self.active_connections[channel_type] = {}
        self.active_connections[channel_type][user_id] = websocket
    
    def disconnect(self, channel_id: int, user_id: int):
        channel_type = self.get_channel_type(channel_id)
        if channel_type in self.active_connections and user_id in self.active_connections[channel_type]:
            del self.active_connections[channel_type][user_id]
    
    async def broadcast(self, message: str, channel_id: int, exclude_user: Optional[int] = None):
        channel_type = self.get_channel_type(channel_id)
        if channel_type == 'global':
            connections = self.active_connections['global']
        else:
            team_id = self.get_team_id(channel_id)
            connections = {uid: ws for uid, ws in self.active_connections['team'].items()
                         if self.get_user_team(uid) == team_id}
        
        for user_id, connection in connections.items():
            if user_id != exclude_user:
                await connection.send_text(message)
    
    def get_channel_type(self, channel_id: int) -> str:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT type FROM channels WHERE id = %s", (channel_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result['type'] if result else 'global'
    
    def get_team_id(self, channel_id: int) -> Optional[int]:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT team_id FROM channels WHERE id = %s", (channel_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result['team_id'] if result else None
    
    def get_user_team(self, user_id: int) -> Optional[int]:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT team_id FROM students WHERE id = %s", (user_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result['team_id'] if result else None

manager = ConnectionManager()

# Pydantic models
class User(BaseModel):
    name: str

class Message(BaseModel):
    content: str
    channel_id: int
    sender_id: int

# Database helper functions
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def get_user_by_name(name: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE name = %s", (name,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def get_channels_for_user(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get user's team_id
    cur.execute("SELECT team_id FROM students WHERE id = %s", (user_id,))
    user = cur.fetchone()
    team_id = user['team_id'] if user else None
    
    # Get available channels
    cur.execute("""
        SELECT * FROM channels 
        WHERE type = 'global' 
        OR (type = 'team' AND team_id = %s)
    """, (team_id,))
    
    channels = cur.fetchall()
    cur.close()
    conn.close()
    return channels

def save_message(sender_id: int, channel_id: int, content: str):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO messages (sender_id, channel_id, content)
        VALUES (%s, %s, %s)
        RETURNING id, created_at
    """, (sender_id, channel_id, content))
    
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return result

def get_recent_messages(channel_id: int, limit: int = 50):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT m.*, s.name as sender_name
        FROM messages m
        JOIN students s ON m.sender_id = s.id
        WHERE m.channel_id = %s
        ORDER BY m.created_at DESC
        LIMIT %s
    """, (channel_id, limit))
    
    messages = cur.fetchall()
    cur.close()
    conn.close()
    
    # Convert to list and reverse to show oldest first
    messages = list(messages)
    messages.reverse()
    return messages

# API Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/login")
async def login(user: User):
    db_user = get_user_by_name(user.name)
    if db_user:
        channels = get_channels_for_user(db_user['id'])
        return {
            "id": db_user['id'],
            "name": db_user['name'],
            "team_id": db_user['team_id'],
            "channels": channels
        }
    raise HTTPException(status_code=404, detail="User not found")

@app.get("/api/channels/{channel_id}/messages")
async def get_messages(channel_id: int):
    try:
        messages = get_recent_messages(channel_id)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messages")
async def send_message(message: Message):
    try:
        result = save_message(message.sender_id, message.channel_id, message.content)
        
        # Get sender info
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM students WHERE id = %s", (message.sender_id,))
        sender = cur.fetchone()
        cur.close()
        conn.close()
        
        # Format message for broadcasting
        message_data = {
            "id": result['id'],
            "content": message.content,
            "sender_id": message.sender_id,
            "sender_name": sender['name'],
            "channel_id": message.channel_id,
            "created_at": result['created_at'].isoformat()
        }
        
        # Broadcast to channel members excluding sender (since frontend already shows the message)
        await manager.broadcast(
            json.dumps(message_data),
            message.channel_id,
            message.sender_id  # Exclude sender to avoid duplicate messages
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
            # Keep connection alive, messages handled through HTTP endpoints
    except WebSocketDisconnect:
        manager.disconnect(channel_id, user_id)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)