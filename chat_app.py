from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from pydantic import BaseModel, validator
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os
from datetime import datetime
import uvicorn
import base64
import uuid
from fastapi.staticfiles import StaticFiles

# Create required directories
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

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

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Database configuration
DB_CONFIG = {
    "dbname": "chat_db",
    "user": "ashik",
    "password": "ashik",
    "host": "localhost"
}

# Add file upload directory configuration
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def init_db():
    """Initialize the database with required tables"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Drop all tables with dependencies in correct order
    cur.execute('DROP TABLE IF EXISTS messages')
    cur.execute('DROP TABLE IF EXISTS shared_files')
    cur.execute('DROP TABLE IF EXISTS channels')
    cur.execute('DROP TABLE IF EXISTS students')
    cur.execute('DROP TABLE IF EXISTS teams')
    
    # Create teams table
    cur.execute('''
    CREATE TABLE teams (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL
    )
    ''')
    
    # Create students table with is_ta
    cur.execute('''
    CREATE TABLE students (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        password VARCHAR(50) NOT NULL,
        roll_no VARCHAR(50) UNIQUE NOT NULL,
        team_id INTEGER REFERENCES teams(id),
        is_ta BOOLEAN DEFAULT FALSE
    )
    ''')
    
    # Create channels table
    cur.execute('''
    CREATE TABLE channels (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        type VARCHAR(10) NOT NULL CHECK (type IN ('global', 'team', 'ta-team')),
        team_id INTEGER REFERENCES teams(id)
    )
    ''')
    
    # Create messages table
    cur.execute('''
    CREATE TABLE messages (
        id SERIAL PRIMARY KEY,
        content TEXT NOT NULL,
        sender_id INTEGER REFERENCES students(id),
        channel_id INTEGER REFERENCES channels(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        message_type VARCHAR(10) DEFAULT 'text',
        file_name VARCHAR(255)
    )
    ''')
    
    # Create shared_files table
    cur.execute('''
    CREATE TABLE shared_files (
        id SERIAL PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        filepath VARCHAR(255) NOT NULL,
        channel_id INTEGER REFERENCES channels(id),
        uploader_id INTEGER REFERENCES students(id),
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        # Reset student id sequence to start TAs from ID 16
        cur.execute("ALTER SEQUENCE students_id_seq RESTART WITH 16")
        
        # Insert TAs
        for i in range(3):
            cur.execute('''
            INSERT INTO students (name, password, roll_no, team_id, is_ta)
            VALUES (%s, %s, %s, %s, TRUE)
            ''', (f'TA {i+1}', 'password', f'TA{i+1}', i+1))
        
        # Reset sequence for regular students
        cur.execute("ALTER SEQUENCE students_id_seq RESTART WITH 1")
        
        # Insert regular students (5 per team)
        for team_id in range(1, 4):
            for i in range(5):
                student_num = (team_id - 1) * 5 + i + 1
                cur.execute('''
                INSERT INTO students (name, password, roll_no, team_id, is_ta)
                VALUES (%s, %s, %s, %s, FALSE)
                ''', (f'Student {student_num}', 'password', f'ROLL{student_num}', team_id))
        
        # Create channels
        cur.execute('''
        INSERT INTO channels (name, type, team_id)
        VALUES ('Global Chat', 'global', NULL)
        ''')
        
        # Create team and TA channels
        for team_id in range(1, 4):
            cur.execute('''
            INSERT INTO channels (name, type, team_id)
            VALUES 
                (%s, 'team', %s),
                (%s, 'ta-team', %s)
            ''', (
                f'Team {team_id} Chat', team_id,
                f'Team {team_id} TA Channel', team_id
            ))
    
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
        self.rooms: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel_id: int, user_id: int):
        await websocket.accept()
        room_name = f"channel_{channel_id}"
        
        if room_name not in self.rooms:
            self.rooms[room_name] = []
        
        self.rooms[room_name].append(websocket)
        # Store user_id in websocket state for later use
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
            
            # Remove dead connections
            for conn in dead_connections:
                self.rooms[room_name].remove(conn)

manager = ConnectionManager()

# Pydantic models
class User(BaseModel):
    name: str

    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Username cannot be empty')
        return v.strip()

class Message(BaseModel):
    content: str
    channel_id: int
    sender_id: int
    message_type: str = 'text'
    file_data: Optional[str] = None
    file_name: Optional[str] = None

# Database helper functions
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def get_user_by_name(name: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                s.id, 
                s.name, 
                s.team_id, 
                s.is_ta,
                t.name as team_name
            FROM students s
            LEFT JOIN teams t ON s.team_id = t.id
            WHERE s.name = %s
        """, (name,))
        user = cur.fetchone()
        cur.close()
        return user
    except Exception as e:
        print(f"Database error: {str(e)}")  # Debug log
        raise
    finally:
        if conn:
            conn.close()

def get_channels_for_user(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get user's team_id and check if they're a TA
    cur.execute("""
        SELECT team_id, is_ta 
        FROM students 
        WHERE id = %s
    """, (user_id,))
    user = cur.fetchone()
    
    if not user:
        return []
        
    team_id = user['team_id']
    is_ta = user['is_ta']
    
    # Get available channels
    if is_ta:
        cur.execute("""
            SELECT c.*, t.name as team_name 
            FROM channels c
            LEFT JOIN teams t ON c.team_id = t.id
            WHERE type = 'global' 
            OR (team_id = %s)
        """, (team_id,))
    else:
        cur.execute("""
            SELECT c.*, t.name as team_name 
            FROM channels c
            LEFT JOIN teams t ON c.team_id = t.id
            WHERE type = 'global' 
            OR (team_id = %s AND (type = 'team' OR type = 'ta-team'))
        """, (team_id,))
    
    channels = cur.fetchall()
    cur.close()
    conn.close()
    return channels

def save_message(sender_id: int, channel_id: int, content: str, message_type: str = 'text', file_name: Optional[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO messages (sender_id, channel_id, content, message_type, file_name)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, created_at
    """, (sender_id, channel_id, content, message_type, file_name))
    
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
    print(f"Login attempt for user: {user.name}")  # Debug log
    try:
        db_user = get_user_by_name(user.name)
        if not db_user:
            raise HTTPException(status_code=404, detail=f"User not found: {user.name}")

        channels = get_channels_for_user(db_user['id'])
        print(f"Found channels for user: {channels}")  # Debug log

        return {
            "id": db_user['id'],
            "name": db_user['name'],
            "team_id": db_user['team_id'],
            "team_name": db_user.get('team_name', 'No Team'),
            "is_ta": db_user.get('is_ta', False),
            "channels": channels
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=str(e))

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
        file_path = None
        if message.message_type == 'file' and message.file_data:
            # Decode base64 file data
            file_data = base64.b64decode(message.file_data)
            # Generate unique filename
            file_name = f"{uuid.uuid4()}_{message.file_name}"
            file_path = os.path.join(UPLOAD_DIR, file_name)
            # Save file
            with open(file_path, "wb") as f:
                f.write(file_data)
            # Update content to be the file path
            message.content = file_path

        result = save_message(
            message.sender_id,
            message.channel_id,
            message.content,
            message_type=message.message_type,
            file_name=message.file_name
        )
        
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
            "created_at": result['created_at'].isoformat(),
            "message_type": message.message_type,
            "file_name": message.file_name if message.message_type == 'file' else None
        }

        # Broadcast to all channel members including sender
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
            # Keep connection alive, messages handled through HTTP endpoints
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)

# Add new routes for file handling
@app.post("/api/channels/{channel_id}/upload")
async def upload_file(channel_id: int, file: UploadFile = File(...)):
    try:
        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        # Save file
        with open(filepath, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Save file info to database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO shared_files (filename, filepath, channel_id, uploader_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (file.filename, filepath, channel_id, user_id))
        
        file_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        
        return {"filename": file.filename, "id": file_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/channels/{channel_id}/files")
async def get_channel_files(channel_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, uploaded_at, uploader_id
        FROM shared_files
        WHERE channel_id = %s
        ORDER BY uploaded_at DESC
    """, (channel_id,))
    files = cur.fetchall()
    cur.close()
    conn.close()
    return files

@app.get("/api/files/{file_id}")
async def download_file(file_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT filepath, filename FROM shared_files WHERE id = %s", (file_id,))
    file_info = cur.fetchone()
    cur.close()
    conn.close()
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        file_info['filepath'], 
        filename=file_info['filename'],
        media_type='application/octet-stream'
    )

@app.get("/api/messages/{message_id}/file")
async def get_message_file(message_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT content, file_name 
        FROM messages 
        WHERE id = %s AND message_type = 'file'
    """, (message_id,))
    file_info = cur.fetchone()
    cur.close()
    conn.close()
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        file_info['content'],
        filename=file_info['file_name'],
        media_type='application/octet-stream'
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)