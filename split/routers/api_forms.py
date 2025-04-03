from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from ..database.db import get_db
from ..models.form import Form
from ..models.form_response import FormResponse
from ..dependencies.auth import get_current_user
from pydantic import BaseModel
from datetime import datetime, timezone
from ..schemas.form_schemas import FormCreateRequest, FormResponseSubmit
from ..schemas.auth_schemas import UserIdRequest
from ..models.user import User
from ..crud.forms import create_form_db, store_form_response_db, get_form_by_id_db, get_all_forms_db, get_user_response_db
router = APIRouter(
    prefix="/api/forms",
    tags=["Forms"]
)


@router.post("/create")
async def api_create_form(form_data: FormCreateRequest, db: Session = Depends(get_db)):
    """Create a new form"""
    result = create_form_db(form_data, db)
    return JSONResponse(status_code=201, content=result)

@router.post("/submit")
async def api_submit_response(form_response: FormResponseSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Submit a response to a form"""
    result = store_form_response_db(form_response, user["user"].id, db)
    return JSONResponse(status_code=201, content=result)

@router.get("/{form_id}")
async def api_get_form(form_id: int, db: Session = Depends(get_db)):
    """Get a form by ID"""
    form = get_form_by_id_db(form_id, db)
    return JSONResponse(status_code=200, content=form["form_json"])

@router.get("/{form_id}/check-deadline") 
async def api_check_deadline(form_id: int, db: Session = Depends(get_db)):
    """Check if a form's deadline has passed"""
    form = get_form_by_id_db(form_id, db)
    deadline_passed = is_deadline_passed(form.get("deadline", ""))
    return JSONResponse(
        status_code=200, 
        content={
            "form_id": form_id,
            "form_name": form.get("title", ""),
            "deadline": form.get("deadline", ""),
            "deadline_passed": deadline_passed
        }
    )

@router.post("/get_forms")
async def api_get_forms(user: UserIdRequest, db: Session = Depends(get_db)):
    """Get all forms with info about whether the user has submitted a response"""
    forms = get_all_forms_db(user.user_id, db)
    return JSONResponse(status_code=200, content=forms)

@router.get("/{form_id}/user/{user_id}")
async def api_get_user_response(form_id: int, user_id: int, db: Session = Depends(get_db)):
    """Get a user's response to a form"""
    response = get_user_response_db(form_id, user_id, db)
    return JSONResponse(status_code=200, content=response)


def is_deadline_passed(deadline: str) -> bool:
    """
    Check if the form deadline has passed
    """
    deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
    current_dt = datetime.now(timezone.utc)
    return current_dt > deadline_dt 