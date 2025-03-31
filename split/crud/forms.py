from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from ..models.form import Form
from ..models.form_response import FormResponse
from ..schemas.form_schemas import FormCreateRequest, FormResponseSubmit
from fastapi import HTTPException, Depends
from datetime import datetime, timezone
import json
from ..database import get_db

def create_form_db(form_data: FormCreateRequest, db: Session) -> Dict[str, Any]:
    """
    Create a new form in the database
    
    Parameters:
    - form_data: FormCreateRequest object
    - db: Database session
    
    Returns:
    - Dictionary with form details including the generated ID
    """
    try:
        # Create form object
        new_form = Form(
            title=form_data.title,
            # description=form_data.description,
            description = "Form description",
            # target_type=form_data.target_type,
            # target_id=form_data.target_id,
            # target_type= RoleType.STUDENT,
            created_at=datetime.now(timezone.utc).isoformat(),
            form_json=json.dumps(form_data.form_json),
            deadline=form_data.deadline
        )
        
        # Add to database
        db.add(new_form)
        db.commit()
        db.refresh(new_form)
        
        return {
            "id": new_form.id,
            "title": new_form.title,
            "created_at": new_form.created_at,
            "deadline": form_data.deadline
        }
    except Exception as e:
        db.rollback()
        print(f"error creating form: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating form: {str(e)}")

def store_form_response_db(response_data: FormResponseSubmit, 
                            user_id: int,  # Current user information
                           db: Session = Depends(get_db)):
    """
    Store a user's response to a form
    
    Parameters:
    - response_data: FormResponseSubmit object
    - user_id: Current user information
    - db: Database session
    
    Returns:
    - Dictionary with operation result
    """
    try:
        # Check if form exists
        form = db.query(Form).filter(Form.id == response_data.form_id).first()
        
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Check deadline
        if is_deadline_passed(form.deadline):
            raise HTTPException(status_code=400, detail="Form submission deadline has passed")
        
        # Check if user has already responded
        existing_response = db.query(FormResponse).filter(
            FormResponse.form_id == response_data.form_id,
            FormResponse.user_id == user_id
        ).first()
        
        if existing_response:
            # Update existing response
            existing_response.response_data = response_data.response_data
            existing_response.submitted_at = datetime.now(timezone.utc).isoformat()
            message = "Response updated successfully"
        else:
            # Add new response
            new_response = FormResponse(
                form_id=response_data.form_id,
                user_id=user_id,
                response_data=response_data.response_data,
                submitted_at=datetime.now(timezone.utc).isoformat()
            )
            db.add(new_response)
            message = "Response submitted successfully"
        
        db.commit()
        
        return {
            "message": message,
            "form_id": response_data.form_id,
        }
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error storing form response: {str(e)}")

def get_form_by_id_db(form_id: int, db: Session) -> Dict[str, Any]:
    """
    Retrieve a form by its ID
    
    Parameters:
    - form_id: The ID of the form to retrieve
    - db: Database session
    
    Returns:
    - Dictionary with form details
    """
    try:
        form = db.query(Form).filter(Form.id == form_id).first()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Return form data
        return {
            "id": form.id,
            "title": form.title,
            "description": form.description,
            "created_at": form.created_at,
            "deadline": form.deadline,
            "form_json": json.loads(form.form_json) if hasattr(form, "form_json") else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving form: {str(e)}")

def get_user_response_db(form_id: int, user_id: int, db: Session) -> Dict[str, Any]:
    """
    Get a specific user's response to a form
    
    Parameters:
    - form_id: ID of the form
    - user_id: ID of the user
    - db: Database session
    
    Returns:
    - Dictionary with user's response data or None if not found
    """
    try:
        form = db.query(Form).filter(Form.id == form_id).first()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        user_response = db.query(FormResponse).filter(
            FormResponse.form_id == form_id,
            FormResponse.user_id == user_id
        ).first()
        
        return {
            "found": user_response is not None,
            "form_id": form_id,
            "user_id": user_id,
            "response_data": json.loads(user_response.response_data) if user_response else None,
            "submitted_at": user_response.submitted_at if user_response else None
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

def get_all_forms_db(user_id: Optional[int] = None, db: Session = None) -> List[Dict[str, Any]]:
    """
    Get all forms in the database
    
    Parameters:
    - user_id: Optional user ID to check if the user has submitted the form
    - db: Database session
    
    Returns:
    - List of form documents with data relevant for listing
    """
    try:
        # Get all forms
        forms = db.query(Form).all()
        result = []
        
        for form in forms:
            form_data = {
                "id": form.id,
                "title": form.title,
                "description": form.description,
                "created_at": form.created_at,
                "deadline": form.deadline,
                # "target_type": form.target_type.value,
                # "target_id": form.target_id,
                "score": "-/-",  # Placeholder for score
                "deadline_passed": is_deadline_passed(form.deadline)
            }
            
            if user_id:
                # Check if user has submitted a response
                response = db.query(FormResponse).filter(
                    FormResponse.form_id == form.id,
                    FormResponse.user_id == user_id
                ).first()
                form_data["attempt"] = response is None
            else:
                form_data["attempt"] = False
            
            result.append(form_data)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving forms: {str(e)}")