from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import json
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, validator
import os
from pymongo import MongoClient
from bson.json_util import dumps, loads
from bson.objectid import ObjectId

app = FastAPI()
@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

def resolveUserToken(token):
    # for now, return the token as is
    # TODO: implement token resolution and figure out how you plan on storing the user related info in the page
    return token
''' resolve userid
teamid
role
'''
class EventBase(BaseModel):
    """Base model for event data matching react-scheduler format"""
    event_id: Optional[int] = None
    title: str
    start: str  # ISO string or date string in format "YYYY/M/D HH:MM"
    end: str    # ISO string or date string in format "YYYY/M/D HH:MM"
    type: Optional[str] = "personal"  # personal, global, etc.
    
    @validator('start', 'end')
    def validate_datetime(cls, v):
        """Validate datetime formats and convert to ISO if needed"""
        try:
            # Try ISO format first
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            try:
                # Try the format used in react-scheduler examples
                dt = datetime.strptime(v, "%Y/%m/%d %H:%M")
                return dt.isoformat()
            except ValueError:
                raise ValueError("Invalid datetime format. Use ISO 8601 or YYYY/M/D HH:MM")


class EventsUpdate(BaseModel):
    """Model for bulk updating events"""
    events_json: Dict[str, Any]
    user_id: str


class EventCreate(EventBase):
    """Model for creating a new event"""
    user_id: str


class EventResponse(BaseModel):
    """Model for event response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None




# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection setup
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['calendarData']
events_collection = db['events']


def create_event(event_data: EventCreate) -> Dict[str, Any]:
    """
    Create a new event in the database
    
    Parameters:
    - event_data: EventCreate object with event details matching react-scheduler format
    
    Returns:
    - Dictionary with event details including the generated ID
    """
    try:
        # Create event document
        event_doc = event_data.dict()

        if event_doc.get("type") == "global" and role != "prof":
            raise HTTPException(status_code=403, detail="Only professors can create global events")
        
        if "type" not in event_doc:
            event_doc["type"] = "personal"

        # Generate event_id if not provided
        if not event_doc.get("event_id"):
            # Get highest existing event_id and increment
            highest_event = events_collection.find_one(
                {"user_id": event_data.user_id},
                sort=[("event_id", -1)]
            )
            next_id = 1
            if highest_event and "event_id" in highest_event:
                next_id = highest_event["event_id"] + 1
                
            event_doc["event_id"] = next_id
        
        #event_doc["_id"]=str(event_doc["_id"])
        
        # Insert into MongoDB
        result = events_collection.insert_one(event_doc)
        
        return {
            "success": True,
            "message": "Event created successfully",
            "data": {
                "mongo_id": str(result.inserted_id)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating event: {str(e)}")


def update_event(event_id: int, user_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing event
    
    Parameters:
    - event_id: ID of the event to update
    - user_id: ID of the user who owns the event
    - event_data: Dictionary with updated event fields
    
    Returns:
    - Dictionary with operation status and updated event
    """
    try:
        # Remove any fields that are None
        update_data = {k: v for k, v in event_data.items() if v is not None}

        role = resolveUserToken(token)
        # Query condition: Allow update if user is a professor or if type is personal
        query = {
            "event_id": event_id,
            "$or": [{"type": "personal"}, {"role": "prof"}]
        }
        
        # Find and update the event
        result = events_collection.find_one_and_update(
            {"event_id": event_id, "user_id": user_id},
            {"$set": update_data},
            return_document=True  # Return the updated document
        )
        
        if not result:
            return {
                "success": False,
                "message": "Event not found or not authorized to update"
            }
            
        # Convert ObjectId to string
        result["_id"] = str(result["_id"])
        
        return {
            "success": True,
            "message": "Event updated successfully",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating event: {str(e)}")


def delete_event(event_id: int, user_id: str) -> Dict[str, Any]:
    """
    Delete an event
    
    Parameters:
    - event_id: ID of the event to delete
    - user_id: ID of the user who owns the event
    
    Returns:
    - Dictionary with operation status
    """
    try:
        # Find and delete the event
        result = events_collection.delete_one({"event_id": event_id, "user_id": user_id})
        
        if result.deleted_count == 0:
            return {
                "success": False,
                "message": "Event not found or not authorized to delete"
            }
            
        return {
            "success": True,
            "message": "Event deleted successfully",
            "data": {"event_id": event_id}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting event: {str(e)}")


def update_events(event_data: EventsUpdate) -> Dict[str, Any]:
    """
    Overwrites existing events for a user with new event data
    
    Parameters:
    - event_data: EventsUpdate object with events_json containing events array
    
    Returns:
    - Dictionary with operation status
    """
    try:
        user_id = event_data.user_id
        
        # First delete all existing events for this user
        events_collection.delete_many({"user_id": user_id})
        
        # Extract events array from the json
        events = event_data.events_json.get("events", [])
        
        if not events:
            return {
                "success": True,
                "message": "All events cleared for user",
                "data": {"count": 0}
            }
        
        # Process each event to ensure proper formatting
        processed_events = []
        for i, event in enumerate(events):
            # Ensure each event has the user_id
            event["user_id"] = user_id
            
            # Ensure event_id is an integer
            if "event_id" not in event:
                event["event_id"] = i + 1
                
            # Convert date strings if needed
            for field in ["start", "end"]:
                if field in event and isinstance(event[field], str):
                    try:
                        # Try ISO format first
                        datetime.fromisoformat(event[field].replace('Z', '+00:00'))
                    except ValueError:
                        try:
                            # Try the format used in react-scheduler examples
                            dt = datetime.strptime(event[field], "%Y/%m/%d %H:%M")
                            event[field] = dt.isoformat()
                        except ValueError:
                            # Leave as is if parsing fails
                            pass
                            
            processed_events.append(event)
            
        # Insert all events
        if processed_events:
            events_collection.insert_many(processed_events)
            
        return {
            "success": True,
            "message": f"Successfully updated calendar with {len(processed_events)} events",
            "data": {
                "count": len(processed_events)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating events: {str(e)}")


def get_events(user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None, event_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Get events for a user with optional date range and type filtering
    
    Parameters:
    - user_id: ID of the user
    - start_date: Optional start date for filtering (ISO format)
    - end_date: Optional end date for filtering (ISO format)
    - event_type: Optional event type for filtering
    
    Returns:
    - Dictionary with events matching the criteria
    """
    try:
        # Build query
        query = {"user_id": user_id}
        
        # Add date range if provided
        if start_date:
            query["start"] = {"$gte": start_date}
        if end_date:
            query["end"] = {"$lte": end_date}
            
        # Add event type if provided
        if event_type:
            query["type"] = event_type
            
        # Get events
        events = list(events_collection.find(query))
        
        # Convert ObjectId to string
        for event in events:
            event["_id"] = str(event["_id"])
            
        return {
            "success": True,
            "message": f"Found {len(events)} events",
            "data": events
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching events: {str(e)}")


# API Endpoints
@app.post("/api/calendar/events")
async def api_create_event(event: EventCreate):
    """API endpoint to create a new event"""
    result = create_event(event)
    print(result)
    return JSONResponse(status_code=201, content=result)


@app.put("/api/calendar/events/{event_id}")
async def api_update_event(event_id: int, event: EventCreate):
    """API endpoint to update an existing event"""
    # Exclude event_id from the update data (it's in the path)
    event_dict = event.dict(exclude={"event_id"})
    result = update_event(event_id, event.user_id, event_dict)
    return JSONResponse(status_code=200, content=result)


@app.delete("/api/calendar/events/{event_id}")
async def api_delete_event(event_id: int, user_id: str):
    """API endpoint to delete an event"""
    result = delete_event(event_id, user_id)
    return JSONResponse(status_code=200, content=result)


@app.post("/api/calendar/events/update")
async def api_update_events(events_update: EventsUpdate):
    """API endpoint to update all events for a user"""
    result = update_events(events_update)
    return JSONResponse(status_code=200, content=result)


@app.get("/api/calendar/events/{user_id}")
async def api_get_events(
    user_id: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    event_type: Optional[str] = None
):
    """API endpoint to get events for a user"""
    result = get_events(user_id, start_date, end_date, event_type)
    return JSONResponse(status_code=200, content=result)

