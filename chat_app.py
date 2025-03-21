from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from pydantic import BaseModel
import redis
import json
import os
from datetime import datetime
import uvicorn
import shutil
from pathlib import Path

# Define upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

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

# Redis configuration
REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "decode_responses": True  # This ensures Redis returns strings instead of bytes
}

# Redis connection
redis_client = redis.Redis(**REDIS_CONFIG)

def init_db():
    """Initialize the database with required data structures and dummy data"""
    try:
        print("Checking Redis connection...")
        if not redis_client.ping():
            print("Redis connection failed!")
            return
        print("Redis connection successful")
        
        print("Current Redis keys:", redis_client.keys("*"))
        
        # Only initialize if the database is empty
        if not redis_client.exists("team:counter"):
            print("Initializing database with dummy data...")
            try:
                # Initialize counters
                print("Setting up counters...")
                redis_client.set("team:counter", "0")
                redis_client.set("student:counter", "0")
                redis_client.set("channel:counter", "0")
                redis_client.set("message:counter", "0")
                
                print("Creating teams...")
                # Create teams and TAs
                for team_name in ["Team A", "Team B", "Team C"]:
                    try:
                        team_id = redis_client.incr("team:counter")
                        print(f"Creating team {team_name} with ID {team_id}")
                        team_key = f"team:{team_id}"
                        
                        # Store team data
                        redis_client.hset(team_key, "id", str(team_id))
                        redis_client.hset(team_key, "name", team_name)
                        redis_client.sadd("teams", team_id)
                        print(f"Team {team_name} created successfully")
                        
                        # Create TA for the team (using IDs 16-18)
                        ta_id = 15 + team_id  # This will give us TAs with IDs 16, 17, 18
                        ta_key = f"ta:{ta_id}"
                        redis_client.hset(ta_key, "id", str(ta_id))
                        redis_client.hset(ta_key, "name", f"TA {team_id}")
                        redis_client.hset(ta_key, "team_id", str(team_id))
                        redis_client.sadd("tas", ta_id)
                        redis_client.hset(team_key, "ta_id", str(ta_id))
                        print(f"TA created for {team_name}")
                        
                        try:
                            # Create team channel
                            channel_id = redis_client.incr("channel:counter")
                            print(f"Creating channel for team {team_name}")
                            channel_key = f"channel:{channel_id}"
                            redis_client.hset(channel_key, "id", str(channel_id))
                            redis_client.hset(channel_key, "name", f"{team_name} Chat")
                            redis_client.hset(channel_key, "type", "team")
                            redis_client.hset(channel_key, "team_id", str(team_id))
                            redis_client.sadd("channels", channel_id)
                            print(f"Channel for team {team_name} created successfully")
                            
                            # Create TA channel for the team
                            ta_channel_id = redis_client.incr("channel:counter")
                            print(f"Creating TA channel for team {team_name}")
                            ta_channel_key = f"channel:{ta_channel_id}"
                            redis_client.hset(ta_channel_key, "id", str(ta_channel_id))
                            redis_client.hset(ta_channel_key, "name", f"{team_name} TA Chat")
                            redis_client.hset(ta_channel_key, "type", "ta")
                            redis_client.hset(ta_channel_key, "team_id", str(team_id))
                            redis_client.sadd("channels", ta_channel_id)
                            print(f"TA Channel for team {team_name} created successfully")
                        except Exception as channel_error:
                            print(f"Error creating channels for team {team_name}: {channel_error}")
                            raise
                        
                        try:
                            # Create students for each team
                            print(f"Creating students for team {team_name}")
                            for i in range(5):
                                student_id = redis_client.incr("student:counter")
                                student_num = (team_id - 1) * 5 + i + 1
                                print(f"Creating student {student_num}")
                                student_key = f"student:{student_id}"
                                redis_client.hset(student_key, "id", str(student_id))
                                redis_client.hset(student_key, "name", f"Student {student_num}")
                                redis_client.hset(student_key, "password", "password")
                                redis_client.hset(student_key, "roll_no", f"ROLL{student_num}")
                                redis_client.hset(student_key, "team_id", str(team_id))
                                redis_client.sadd("students", student_id)
                                redis_client.sadd(f"team:{team_id}:students", student_id)
                                print(f"Student {student_num} created successfully")
                        except Exception as student_error:
                            print(f"Error creating students for team {team_name}: {student_error}")
                            raise
                            
                    except Exception as team_error:
                        print(f"Error processing team {team_name}: {team_error}")
                        raise

                try:
                    # Create global channel
                    print("Creating global channel...")
                    global_channel_id = redis_client.incr("channel:counter")
                    redis_client.hset(f"channel:{global_channel_id}", "id", str(global_channel_id))
                    redis_client.hset(f"channel:{global_channel_id}", "name", "Global Chat")
                    redis_client.hset(f"channel:{global_channel_id}", "type", "global")
                    redis_client.hset(f"channel:{global_channel_id}", "team_id", "")
                    redis_client.sadd("channels", global_channel_id)
                    print("Global channel created successfully")
                except Exception as global_channel_error:
                    print(f"Error creating global channel: {global_channel_error}")
                    raise

            except Exception as init_error:
                print(f"Error during initialization: {init_error}")
                raise
                
            print("\nVerifying created data:")
            print("Teams:", redis_client.smembers("teams"))
            print("TAs:", redis_client.smembers("tas"))
            print("Channels:", redis_client.smembers("channels"))
            print("Students:", redis_client.smembers("students"))
            print("All keys:", redis_client.keys("*"))
            
        else:
            print("Database already initialized")
            print("Current keys:", redis_client.keys("*"))
            print("Teams:", redis_client.smembers("teams"))
            print("TAs:", redis_client.smembers("tas"))
            print("Channels:", redis_client.smembers("channels"))
            print("Students:", redis_client.smembers("students"))

    except redis.RedisError as e:
        print(f"Redis error during initialization: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error during initialization: {e}")
        print(f"Error type: {type(e)}")
        raise

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
        websocket.user_id = user_id
    
    def disconnect(self, websocket: WebSocket, channel_id: int):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            self.rooms[room_name].remove(websocket)
            if not self.rooms[room_name]:
                del self.rooms[room_name]
    
    async def broadcast(self, message: str, channel_id: int, exclude_user: Optional[int] = None):
        room_name = f"channel_{channel_id}"
        if room_name in self.rooms:
            for connection in self.rooms[room_name]:
                if not exclude_user or getattr(connection, 'user_id', None) != exclude_user:
                    try:
                        await connection.send_text(message)
                    except Exception:
                        self.rooms[room_name].remove(connection)

manager = ConnectionManager()

# Pydantic models
class User(BaseModel):
    name: str

class Message(BaseModel):
    content: str
    channel_id: int
    sender_id: int
    is_file: bool = False

# Database helper functions
def get_user_by_name(name: str):
    print(f"Searching for user with name: '{name}'")
    # First check students
    for student_id in redis_client.smembers("students"):
        student_data = redis_client.hgetall(f"student:{student_id}")
        if student_data.get("name") == name:
            student_data["user_type"] = "student"
            print(f"Found matching student: {student_data}")
            return student_data
            
    # Then check TAs
    for ta_id in redis_client.smembers("tas"):
        ta_data = redis_client.hgetall(f"ta:{ta_id}")
        if ta_data.get("name") == name:
            ta_data["user_type"] = "ta"
            print(f"Found matching TA: {ta_data}")
            return ta_data
            
    print("No matching user found")
    return None

def get_channels_for_user(user_id: int, user_type: str):
    channels = []
    team_id = None
    
    if user_type == "student":
        student_data = redis_client.hgetall(f"student:{user_id}")
        team_id = student_data.get("team_id")
    else:  # TA
        ta_data = redis_client.hgetall(f"ta:{user_id}")
        team_id = ta_data.get("team_id")

    # Get all channels
    for channel_id in redis_client.smembers("channels"):
        channel_data = redis_client.hgetall(f"channel:{channel_id}")
        channel_type = channel_data.get("type")
        channel_team_id = channel_data.get("team_id")
        
        if user_type == "ta":
            # TAs can access only TA channel of their team and global channel
            if (channel_type == "global" or 
                (channel_type == "ta" and channel_team_id == team_id)):
                channels.append(channel_data)
        else:  # student
            # Students can access team channel, team's TA channel, and global channel
            if (channel_type == "global" or 
                (channel_type in ["team", "ta"] and channel_team_id == team_id)):
                channels.append(channel_data)

    return channels

def save_message(sender_id: int, channel_id: int, content: str, user_type: str = None):
    try:
        print(f"Debug - save_message: sender_id={sender_id}, checking if TA...")
        # Explicitly check if the sender_id matches any TA ids (16-18)
        is_ta = 16 <= int(sender_id) <= 18
        user_type = "ta" if is_ta else "student"
        print(f"Debug - determined user_type: {user_type}")

        message_id = redis_client.incr("message:counter")
        timestamp = datetime.now().isoformat()
        
        # Get sender info from correct set based on user type
        if user_type == "ta":
            sender = redis_client.hgetall(f"ta:{sender_id}")
        else:
            sender = redis_client.hgetall(f"student:{sender_id}")
            
        print(f"Debug - Found sender info: {sender}")
        
        message_data = {
            "id": str(message_id),
            "content": content,
            "sender_id": str(sender_id),
            "sender_name": sender.get("name", "Unknown"),
            "channel_id": str(channel_id),
            "created_at": timestamp,
            "user_type": user_type
        }
        
        print(f"Debug - Final message data: {message_data}")
        redis_client.hmset(f"message:{message_id}", message_data)
        redis_client.zadd(f"channel:{channel_id}:messages", {message_id: message_id})
        
        return message_data
    except Exception as e:
        print(f"Error in save_message: {str(e)}")
        raise

def get_recent_messages(channel_id: int, limit: int = 50):
    messages = []
    message_ids = redis_client.zrange(f"channel:{channel_id}:messages", 0, limit-1)
    
    for msg_id in message_ids:
        message_data = redis_client.hgetall(f"message:{msg_id}")
        if message_data:
            # Get sender info based on user type
            user_type = message_data.get("user_type", "student")
            if user_type == "ta":
                sender_data = redis_client.hgetall(f"ta:{message_data['sender_id']}")
            else:
                sender_data = redis_client.hgetall(f"student:{message_data['sender_id']}")
            
            message_data["sender_name"] = sender_data.get("name", "Unknown")
            messages.append(message_data)
    
    return messages

# API Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/login")
async def login(user: User):
    print(f"Login attempt for user: '{user.name}'")
    db_user = get_user_by_name(user.name)
    if db_user:
        user_type = db_user.get("user_type", "student")
        channels = get_channels_for_user(int(db_user["id"]), user_type)
        return {
            "id": int(db_user["id"]),
            "name": db_user["name"],
            "team_id": db_user["team_id"],
            "user_type": user_type,
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
        print(f"Debug - Received message from sender_id: {message.sender_id}")
        # Determine user type by ID range
        user_type = "ta" if 16 <= message.sender_id <= 18 else "student"
        print(f"Debug - Determined user_type: {user_type}")
        
        result = save_message(message.sender_id, message.channel_id, message.content, user_type)
        
        await manager.broadcast(
            json.dumps(result),
            message.channel_id,
            message.sender_id
        )
        
        return result
    except Exception as e:
        print(f"Error in send_message endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_file(file: UploadFile, channel_id: int, sender_id: int):
    try:
        # Create channel directory if it doesn't exist
        channel_dir = UPLOAD_DIR / str(channel_id)
        channel_dir.mkdir(exist_ok=True)
        
        # Save file with timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        file_path = channel_dir / f"{timestamp}{file.filename}"
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "filename": file_path.name,
            "original_name": file.filename,
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download/{channel_id}/{filename}")
async def download_file(channel_id: int, filename: str):
    try:
        file_path = UPLOAD_DIR / str(channel_id) / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(
            path=file_path,
            filename=filename.split("_", 2)[2]  # Remove timestamp prefix
        )
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)