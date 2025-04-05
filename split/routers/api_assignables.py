from fastapi import APIRouter, Depends, HTTPException, status, Form as FastAPIForm
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from ..database.db import get_db
from ..models.user import User
from ..dependencies.auth import prof_or_ta_required, prof_required, get_current_user
from ..models.assignment import Assignment
from ..models.assignable import Assignable
from fastapi import  File, UploadFile
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import os
import uuid
from ..models.roles import RoleType
from typing import Optional
import shutil

router = APIRouter(
    prefix="",
    tags=["Assignables"]
)

# this is to submit file for an assignable, done by students
@router.post("/assignables/{assignable_id}/submit")
async def submit_file(
    assignable_id: int,
    file: UploadFile = File(...),  # Now accepts a single file
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a file for an assignable.
    Only one assignment per submittable per user is allowed.
    """
    # Get the submittable
    assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
    if not assignable:
        raise HTTPException(status_code=404, detail="Assignable not found")

    # Check if user already has a submission
    user = db.query(User).filter(User.id == current_user["user"].id).first()
    existing_assignment = db.query(Assignment).filter(
        Assignment.user_id == user.id,
        Assignment.assignable_id == assignable_id
    ).first()

    if existing_assignment:
        raise HTTPException(
            status_code=400, 
            detail="Your team has already submitted a file for this submittable. Please delete the existing submission first."
        )

    # Check if submission is allowed based on opens_at and deadline
    now = datetime.now(timezone.utc)
    opens_at = datetime.fromisoformat(assignable.opens_at) if assignable.opens_at else None
    deadline = datetime.fromisoformat(assignable.deadline)

    if opens_at and now < opens_at:
        raise HTTPException(status_code=400, detail="Submission period has not started yet")
    if now > deadline:
        raise HTTPException(status_code=400, detail="Submission deadline has passed")

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"assignment_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create submission record
    assignment = Assignment(
        user_id=user.id,
        file_url=file_path,
        original_filename=file.filename,
        assignable_id=assignable_id,
        score=None  # Initialize score as None since it hasn't been graded yet
    )

    try:
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return {
            "message": "File submitted successfully",
            "assignment_id": assignment.id,
            "original_filename": assignment.original_filename,
            "max_score": assignable.max_score,  # Include max_score in response
            "score": assignment.score  # Include current score (will be None for new submissions)
        }
    except Exception as e:
        # If database operation fails, delete the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create assignment record: {str(e)}")

@router.post("/assignables/{assignable_id}/submit")
async def submit_file(
    assignable_id: int,
    file: UploadFile = File(...),  # Now accepts a single file
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a file for an assignable.
    Only one assignment per submittable per user is allowed.
    """
    # Get the submittable
    assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
    if not assignable:
        raise HTTPException(status_code=404, detail="Assignable not found")

    # Check if user already has a submission
    user = db.query(User).filter(User.id == current_user["user"].id).first()
    existing_assignment = db.query(Assignment).filter(
        Assignment.user_id == user.id,
        Assignment.assignable_id == assignable_id
    ).first()

    if existing_assignment:
        raise HTTPException(
            status_code=400, 
            detail="Your team has already submitted a file for this submittable. Please delete the existing submission first."
        )

    # Check if submission is allowed based on opens_at and deadline
    now = datetime.now(timezone.utc)
    opens_at = datetime.fromisoformat(assignable.opens_at) if assignable.opens_at else None
    deadline = datetime.fromisoformat(assignable.deadline)

    if opens_at and now < opens_at:
        raise HTTPException(status_code=400, detail="Submission period has not started yet")
    if now > deadline:
        raise HTTPException(status_code=400, detail="Submission deadline has passed")

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"assignment_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create submission record
    assignment = Assignment(
        user_id=user.id,
        file_url=file_path,
        original_filename=file.filename,
        assignable_id=assignable_id,
        score=None  # Initialize score as None since it hasn't been graded yet
    )

    try:
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return {
            "message": "File submitted successfully",
            "assignment_id": assignment.id,
            "original_filename": assignment.original_filename,
            "max_score": assignable.max_score,  # Include max_score in response
            "score": assignment.score  # Include current score (will be None for new submissions)
        }
    except Exception as e:
        # If database operation fails, delete the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Failed to create assignment record: {str(e)}")
    



@router.get("/assignables/")
async def get_assignables(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all assignables categorized by status"""
    try:
        # Get all submittables
        assignables = db.query(Assignable).all()
        
        # Get user's team submissions
        user = current_user["user"]
        user_assignments = {}
        if user.id:
            assignments = db.query(Assignment).filter(Assignment.user_id == user.id).all()
            user_assignments = {s.assignable_id: s for s in assignments}
        
        # Helper function to format submittable
        def format_assignable(s):
            assignment = user_assignments.get(s.id)
            return {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "opens_at": s.opens_at,
                "deadline": s.deadline,
                "max_score": s.max_score,  # Add max_score from submittable
                "reference_files": [{
                    "original_filename": s.original_filename
                }] if s.file_url else [],
                "submission_status": {
                    "has_submitted": bool(assignment),
                    "submission_id": assignment.id if assignment else None,
                    "submitted_on": assignment.submitted_on if assignment else None,
                    "original_filename": assignment.original_filename if assignment else None,
                    "score": assignment.score if assignment else None  # Add score from submission
                }
            }

        # Categorize submittables
        now = datetime.now(timezone.utc)
        upcoming = []
        open_assignables = []
        closed = []

        for s in assignables:
            formatted = format_assignable(s)
            opens_at = datetime.fromisoformat(s.opens_at) if s.opens_at else None
            deadline = datetime.fromisoformat(s.deadline)

            if opens_at and now < opens_at:
                upcoming.append(formatted)
            elif now > deadline:
                closed.append(formatted)
            else:
                open_assignables.append(formatted)

        return {
            "upcoming": upcoming,
            "open": open_assignables,
            "closed": closed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignables: {str(e)}")
    
# this is to download the reference file for an assignable, done by students and profs
@router.get("/assignables/{assignable_id}/reference-files/download")
async def download_reference_file(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download a reference file for a submittable"""
    try:
        # Get the submittable
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")

        if not assignable.file_url:
            raise HTTPException(status_code=404, detail="No reference file found")

        # Check if file exists
        if not os.path.exists(assignable.file_url):
            raise HTTPException(status_code=404, detail="File not found on server")

        # Return the file
        return FileResponse(
            assignable.file_url,
            media_type='application/octet-stream',
            filename=assignable.original_filename
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")
    
# this is to create a new submittable, done by profs
@router.post("/assignables/create")
async def create_assignable(
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    max_score: int = FastAPIForm(...),  # Add max_score parameter
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Create a new assignable with an optional reference file"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
        # Validate max_score
        if max_score <= 0:
            raise HTTPException(status_code=400, detail="Maximum score must be greater than zero")
            
        # Get the creator (professor) from token
        payload = token  # The token is already decoded by prof_required dependency
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Create submittable object
        assignable = Assignable(
            title=title,
            deadline=deadline,
            description=description,
            max_score=max_score,  # Add max_score to submittable creation
            opens_at=opens_at,
            creator_id=user.id,
            file_url="",  # Default empty string
            original_filename=""  # Default empty string
        )

        # Handle file upload if provided
        if file:
            # Create uploads directory if it doesn't exist
            upload_dir = "uploads"
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)

            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            # Update submittable with file information
            assignable.file_url = file_path
            assignable.original_filename = file.filename

        # Add to database
        db.add(assignable)
        db.commit()
        db.refresh(assignable)

        # Return JSON response with proper structure
        return JSONResponse(
            status_code=201,
            content={
                "message": "Submittable created successfully",
                "submittable": {
                    "id": assignable.id,
                    "title": assignable.title,
                    "opens_at": assignable.opens_at,
                    "deadline": assignable.deadline,
                    "description": assignable.description,
                    "max_score": assignable.max_score,  # Include max_score in response
                    "created_at": assignable.created_at,
                    "reference_files": [{
                        "original_filename": assignable.original_filename
                    }] if assignable.file_url else [],
                    "submission_status": {
                        "has_submitted": False,
                        "submission_id": None,
                        "submitted_on": None,
                        "original_filename": None,
                        "score": None  # Include score field in submission status
                    }
                }
            }
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating assignable: {str(e)}")

# this is to get details of a specific assignable, done by students and profs
@router.get("/assignables/{assignable_id}")
async def get_assignable(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific assignanle"""
    try:
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        return JSONResponse(status_code=200, content={
            "id": assignable.id,
            "title": assignable.title,
            "opens_at": assignable.opens_at,
            "deadline": assignable.deadline,
            "description": assignable.description,
            "max_score": assignable.max_score,
            "created_at": assignable.created_at,
            "reference_file": {
                "file_url": assignable.file_url,
                "original_filename": assignable.original_filename
            } if assignable.file_url else None
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignable: {str(e)}")

# this is to get all assignments for an assignable, done by profs
@router.get("/assignables/{assignable_id}/assignments")
async def get_assignable_assignments(
    assignable_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all assignments for a assignable (professors only)"""
    try:
        if current_user["role"] == RoleType.STUDENT:
            raise HTTPException(status_code=403, detail="Only professors or TA can view all assignments")
        
        # Get the assignable
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        assignments = db.query(Assignment).filter(Assignment.assignable_id == assignable_id).all()
        
        result = []
        for assignment in assignments:
            assignment_data = {
                "id": assignment.id,
                "user_id": assignment.user_id,
                "submitted_on": assignment.submitted_on,
                "score": assignment.score,
                "max_score": assignable.max_score,
                "file": {
                    "file_url": assignment.file_url,
                    "original_filename": assignment.original_filename
                },
                "user": {
                    "id": assignment.user.id,
                    "name": assignment.user.name,
                    "email": assignment.user.email
                } if assignment.user else None
            }
            result.append(assignment_data)
        
        return JSONResponse(status_code=200, content=result)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assignments: {str(e)}")

# this is to delete a assignable and all its assignments, done by profs
@router.delete("/assignables/{assignable_id}")
async def delete_assignable(
    assignable_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Delete a assignable and all its assignments (professors only)"""
    try:
        assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Delete the reference file if it exists
        if assignable.file_url:
            local_path = assignable.file_url.lstrip('/')
            if os.path.exists(local_path):
                os.remove(local_path)
        
        # Delete all submission files
        assignments = db.query(Assignment).filter(Assignment.assignable_id == assignable_id).all()
        for assignment in assignments:
            if assignment.file_url:
                local_path = assignment.file_url.lstrip('/')
                if os.path.exists(local_path):
                    os.remove(local_path)
        
        # Delete all submissions
        db.query(Assignment).filter(Assignment.assignable_id == assignable_id).delete()
        
        # Delete the submittable
        db.delete(assignable)
        db.commit()
        
        return JSONResponse(status_code=200, content={"message": "Assignable deleted successfully"})
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting assignable: {str(e)}")
    
# this is to update a assignable, done by profs
@router.put("/assignables/{assignable_id}")
async def update_assignable(
    assignable_id: int,
    title: str = FastAPIForm(...),
    deadline: str = FastAPIForm(...),
    description: str = FastAPIForm(...),
    opens_at: Optional[str] = FastAPIForm(None),
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    token: str = Depends(prof_or_ta_required)
):
    """Update a assignable (professors only)"""
    try:
        # Basic validation
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if opens_at:
                opens_at_dt = datetime.fromisoformat(opens_at.replace('Z', '+00:00'))
                # Validate that opens_at is before deadline
                if opens_at_dt >= deadline_dt:
                    raise HTTPException(
                        status_code=400, 
                        detail="opens_at must be before deadline"
                    )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
            
        existing_assignable = db.query(Assignable).filter(Assignable.id == assignable_id).first()
        if not existing_assignable:
            raise HTTPException(status_code=404, detail="Assignable not found")
        
        # Update basic information
        existing_assignable.title = title
        existing_assignable.opens_at = opens_at
        existing_assignable.deadline = deadline
        existing_assignable.description = description
        
        # Handle file update if provided
        if file:
            # Delete old file if it exists
            if existing_assignable.file_url:
                old_file_path = existing_assignable.file_url.lstrip('/')
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            # Save new file
            file_extension = file.filename.split('.')[-1]
            file_name = f"ref_{uuid.uuid4()}.{file_extension}"
            file_path = f"uploads/{file_name}"
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            existing_assignable.file_url = f"uploads/{file_name}"
            existing_assignable.original_filename = file.filename
        
        db.commit()
        db.refresh(existing_assignable)
        
        return JSONResponse(status_code=200, content={
            "message": "Submittable updated successfully",
            "submittable_id": existing_assignable.id
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)  # Clean up file if something went wrong
        raise HTTPException(status_code=500, detail=f"Error updating assignable: {str(e)}")
