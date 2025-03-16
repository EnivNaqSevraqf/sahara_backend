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
forms_collection = db['forms']  # Add this collection for forms

async def get_timestamp_request(timestamp: str = Form(...)) -> TimestampRequest:
    return TimestampRequest(timestamp=timestamp)

@app.post("/createForm")
async def create_form_old(
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

class FormCreate(BaseModel):
    form_name: str
    form_json: Dict[str, Any]
    deadline: str
    
    @validator('deadline')
    def validate_deadline(cls, v):
        try:
            # Validate ISO 8601 format
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Invalid deadline format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")

class FormResponse(BaseModel):
    form_id: str
    user_id: str
    response_data: Dict[str, Any]

def create_form(form_data: FormCreate) -> Dict[str, Any]:
    """
    Create a new form in the database
    
    Parameters:
    - form_data: FormCreate object with form name, JSON structure, and deadline
    
    Returns:
    - Dictionary with form details including the generated ID
    """
    try:
        # Create form document
        form_doc = {
            "form_name": form_data.form_name,
            "form_json": form_data.form_json,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deadline": form_data.deadline,
            "responses": []
        }
        
        # Insert into MongoDB
        result = forms_collection.insert_one(form_doc)
        form_id = str(result.inserted_id)
        
        # # Update the document with the string ID
        # forms_collection.update_one(
        #     {"_id": result.inserted_id},
        #     {"$set": {"_id": form_id}}
        # )
        
        return {
            "_id": form_id,
            "form_name": form_data.form_name,
            "created_at": form_doc["created_at"],
            "deadline": form_data.deadline
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating form: {str(e)}")

def store_form_response(response_data: FormResponse) -> Dict[str, Any]:
    """
    Store a user's response to a form
    
    Parameters:
    - response_data: FormResponse object with form_id, user_id and response data
    
    Returns:
    - Dictionary with operation result
    """
    try:
        # Check if form exists and deadline hasn't passed
        form = forms_collection.find_one({"_id": response_data.form_id})
        
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Check deadline
        if is_deadline_passed(form["deadline"]):
            raise HTTPException(status_code=400, detail="Form submission deadline has passed")
        
        # Check if user has already responded
        existing_response = next(
            (resp for resp in form.get("responses", []) if resp.get("user_id") == response_data.user_id), 
            None
        )
        
        if existing_response:
            # Update existing response
            result = forms_collection.update_one(
                {"_id": response_data.form_id, "responses.user_id": response_data.user_id},
                {"$set": {"responses.$.response_data": response_data.response_data}}
            )
            message = "Response updated successfully"
        else:
            # Add new response
            result = forms_collection.update_one(
                {"_id": response_data.form_id},
                {"$push": {"responses": {
                    "user_id": response_data.user_id,
                    "response_data": response_data.response_data,
                    "submitted_at": datetime.utcnow().isoformat()
                }}}
            )
            message = "Response submitted successfully"
        
        return {
            "message": message,
            "form_id": response_data.form_id,
            "user_id": response_data.user_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error storing form response: {str(e)}")

def get_form_by_id(form_id: str) -> Dict[str, Any]:
    """
    Retrieve a form by its ID
    
    Parameters:
    - form_id: The ID of the form to retrieve
    
    Returns:
    - Dictionary with form details
    """
    print("Form ID I recieved:", form_id)
    try:
        form = forms_collection.find_one({"_id": ObjectId(form_id)})
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        return form
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving form: {str(e)}")

def get_user_response(form_id: str, user_id: str) -> Dict[str, Any]:
    """
    Get a specific user's response to a form
    
    Parameters:
    - form_id: ID of the form
    - user_id: ID of the user
    
    Returns:
    - Dictionary with user's response data or None if not found
    """
    try:
        form = forms_collection.find_one({"_id": form_id})
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        user_response = next(
            (resp for resp in form.get("responses", []) if resp.get("user_id") == user_id),
            None
        )
        
        return {
            "found": user_response is not None,
            "form_id": form_id,
            "user_id": user_id,
            "response_data": user_response["response_data"] if user_response else None,
            "submitted_at": user_response["submitted_at"] if user_response else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user response: {str(e)}")

def is_deadline_passed(deadline: str) -> bool:
    """
    Check if a form's deadline has passed
    
    Parameters:
    - deadline: ISO 8601 formatted deadline string
    
    Returns:
    - True if deadline has passed, False otherwise
    """
    try:
        # Parse deadline into datetime object
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        # Compare with current time
        return datetime.now(deadline_dt.tzinfo) > deadline_dt
    except Exception as e:
        # If there's any error parsing, default to assuming deadline has passed
        raise ValueError(f"Invalid deadline format: {str(e)}")

def get_all_forms() -> List[Dict[str, Any]]:
    """
    Get all forms in the database
    
    Returns:
    - List of form documents with data relevant for listing
    """
    try:
        forms = list(forms_collection.find({}))
        for i in forms:
            i["_id"] = str(i["_id"])
            i["score"] = "-/-"
            i["attempt"] = True
            del i["form_json"]
            del i["responses"]
        return forms
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving forms: {str(e)}")

# Example route implementations using these functions
@app.post("/api/forms/create")
async def api_create_form(form_data: FormCreate):
    result = create_form(form_data)
    print(result)
    return JSONResponse(status_code=201, content=result)

@app.post("/api/forms/{form_id}/submit")
async def api_submit_response(form_id: str, response: Dict[str, Any], user_id: str = Depends(resolveUserToken)):
    form_response = FormResponse(form_id=form_id, user_id=user_id, response_data=response)
    result = store_form_response(form_response)
    return JSONResponse(status_code=201, content=result)

@app.get("/api/forms/{form_id}")
async def api_get_form(form_id: str):
    form = get_form_by_id(form_id)
    form["_id"] = str(form["_id"])
    return JSONResponse(status_code=200, content=form["form_json"])

@app.get("/api/forms/{form_id}/check-deadline")
async def api_check_deadline(form_id: str):
    form = get_form_by_id(form_id)
    deadline_passed = is_deadline_passed(form["deadline"])
    return JSONResponse(
        status_code=200, 
        content={
            "form_id": form_id,
            "form_name": form["form_name"],
            "deadline": form["deadline"],
            "deadline_passed": deadline_passed
        }
    )



@app.get("/api/get_forms")
async def api_get_forms():
    forms = get_all_forms()
    return JSONResponse(status_code=200, content=forms)
