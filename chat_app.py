from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import sqlite3
import json
import os
from datetime import datetime
import uvicorn

# Create app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Database setup
DB_PATH = "chat.db"

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create messages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)
    init_db()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket
    
    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
    
    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

manager = ConnectionManager()

# Pydantic models
class User(BaseModel):
    username: str

class Message(BaseModel):
    sender_id: int
    content: str

# Helper functions for database operations
def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def create_user(username: str):
    """Create a new user in the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        # Username already exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user_id = cursor.fetchone()["id"]
    finally:
        conn.close()
    
    return user_id

def save_message(sender_id: int, content: str):
    """Save a message to the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO messages (sender_id, content) VALUES (?, ?)",
        (sender_id, content)
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    
    return message_id

def get_recent_messages(limit: int = 50):
    """Get recent messages from the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT m.id, m.content, m.created_at, u.id as user_id, u.username
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        ORDER BY m.created_at DESC
        LIMIT ?
    """, (limit,))
    
    messages = cursor.fetchall()
    conn.close()
    
    # Convert to list of dicts and reverse to show oldest first
    result = [dict(msg) for msg in messages]
    result.reverse()
    
    return result

def get_all_users():
    """Get all users from the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username FROM users ORDER BY username")
    users = cursor.fetchall()
    conn.close()
    
    return [dict(user) for user in users]

# API Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/users")
async def register_user(user: User):
    try:
        user_id = create_user(user.username)
        return {"id": user_id, "username": user.username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

@app.get("/api/users")
async def get_users():
    try:
        users = get_all_users()
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")

@app.get("/api/messages")
async def get_messages(limit: int = 50):
    try:
        messages = get_recent_messages(limit)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving messages: {str(e)}")

@app.post("/api/messages")
async def send_message(message: Message):
    try:
        message_id = save_message(message.sender_id, message.content)
        
        # Get the username for this sender
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (message.sender_id,))
        result = cursor.fetchone()
        conn.close()
        
        username = result["username"] if result else "Unknown"
        
        # Format message for broadcasting
        message_data = {
            "id": message_id,
            "content": message.content,
            "sender_id": message.sender_id,
            "username": username,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Broadcast to all connected clients
        await manager.broadcast(json.dumps(message_data))
        
        return {"id": message_id, **message_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Just keep the connection alive
            data = await websocket.receive_text()
            # We don't process messages here - they come through the HTTP API
    except WebSocketDisconnect:
        manager.disconnect(user_id)

# Run the application directly if this file is executed
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

#Hello