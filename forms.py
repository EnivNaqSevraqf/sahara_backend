from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
from typing import Optional
from pydantic import BaseModel, validator
import os
from pymongo import MongoClient
from bson.json_util import dumps, loads


def resolveUserToken(token):
    # for now, return the token as is
    # TODO: implement token resolution and figure out how you plan on storing the user related info in the page
    return token



class TimestampRequest(BaseModel):
    timestamp: str
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        try:
            # Validate ISO 8601 format
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Invalid timestamp format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")

class SurveyResult(BaseModel):
    userId: str
    postId: str
    surveyResult: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "postId": "123e4567-e89b-12d3-a456-426614174000",
                "surveyResult": "{\"question1\":\"answer1\",\"question2\":\"answer2\"}"
            }
        }

class SurveyCheck(BaseModel):
    userId: str
    postId: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "userId": "user123",
                "postId": "123e4567-e89b-12d3-a456-426614174000"
            }
        }

app = FastAPI()

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
db = mongo_client['surveyData']
survey_collection = db['surveyResults']

async def get_timestamp_request(timestamp: str = Form(...)) -> TimestampRequest:
    return TimestampRequest(timestamp=timestamp)

@app.post("/createForm")
async def create_form(
    file: UploadFile = File(...),
    timestamp_request: TimestampRequest = Depends(get_timestamp_request)
):
    """
    Endpoint to create a form by uploading a JSON file along with a timestamp
    
    Parameters:
    - file: JSON file uploaded by user
    - timestamp_request: Timestamp in ISO 8601 format
    
    Returns:
    - JSON response with status of operation
    """
    # Validate file is JSON
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are accepted")
    
    # Read the JSON content
    try:
        contents = await file.read()
        json_data = json.loads(contents)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
    # Here you would typically save the form data to a database
    # For this example, we'll just return a success message
    
    # Reset file pointer for potential further processing
    await file.seek(0)
    
    return JSONResponse(
        status_code=201,
        content={
            "message": "Form created successfully",
            "filename": file.filename,
            "timestamp": timestamp_request.timestamp,
            "form_data": json_data
        }
    )

@app.post("/storeResult", status_code=201)
async def store_result(survey_result: SurveyResult):
    """
    Endpoint to store survey results
    
    Parameters:
    - survey_result: JSON object containing postId and survey results (as a string)
    
    Returns:
    - JSON response with status of operation
    """
    try:
        post_id = survey_result.postId
        
        # Parse the surveyResult string into a JSON object
        try:
            survey_data = json.loads(survey_result.surveyResult)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in surveyResult")
        
        # Assuming userId is part of the parsed survey data or using a default
        user_id = survey_result.userId
        
        # Store in MongoDB using postId as key and {userId: surveyResult} as value
        result = survey_collection.update_one(
            {"_id": post_id},
            {"$set": {user_id: survey_data}},
            upsert=True
        )
        
        return JSONResponse(
            status_code=201,
            content={
                "message": "Survey result stored successfully",
                "postId": post_id,
                "resultSummary": f"Received {len(survey_data.keys())} answers",
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error storing survey result: {str(e)}")

@app.post("/getResult")
async def get_result(survey_check: SurveyCheck):
    """
    Endpoint to get a survey result for a specific userId and postId
    
    Parameters:
    - survey_check: JSON object containing userId and postId
    
    Returns:
    - JSON response with the survey result data or null if not found
    """
    try:
        # Query MongoDB to find the document with the given postId
        result = survey_collection.find_one({"_id": survey_check.postId})
        
        # Check if document exists and contains the userId field
        if result is not None and survey_check.userId in result:
            return JSONResponse(
                status_code=200,
                content={
                    "found": True,
                    "userId": survey_check.userId,
                    "postId": survey_check.postId,
                    "surveyData": result[survey_check.userId]
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "found": False,
                    "userId": survey_check.userId,
                    "postId": survey_check.postId,
                    "surveyData": None
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving survey result: {str(e)}")

@app.post("/test-endpoint")
async def test_endpoint(request_data: Request):
    """
    Dummy endpoint that always succeeds
    
    Parameters:
    - request_data: Optional JSON data
    
    Returns:
    - JSON response with success message
    """
    # print("Received data:", request_data)
    body = await request_data.body()  # Read the raw request body as bytes
    body_str = body.decode("utf-8") 
    print("Received data:", body_str)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Request processed successfully",
            # "received_data": request_data.body()
        }
    )


