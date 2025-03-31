from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.user import User
from ..dependencies.auth import create_access_token, get_current_user
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from ..utils.auth import verify_password, generate_token
from ..database.init import get_db
from ..models.roles import Role, RoleType
from ..schemas.auth_schemas import ResetPasswordRequest, CreateProfRequest
from ..dependencies.auth import prof_required, prof_or_ta_required
from ..utils.auth import create_hashed_password, generate_random_string, extract_students, extract_ta_data_from_content
from read_csv import CSVFormatError
import traceback
from ..schemas.auth_schemas import TempRegisterRequest

router = APIRouter(
    prefix="/api/auth",
    tags=["API Auth"]
)

@router.post("/login")
def login(request: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == request.username).first()
        
        # Verify credentials
        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid username or password"
            )

        # Get the role
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="User role not found"
            )
        
        # Generate token
        token = generate_token(
            {"sub": user.username}, 
            timedelta(days=1)
        )
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": role.role.value
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/reset-password")
def reset_password(
    request: ResetPasswordRequest,
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )
    
    # Get user object
    user = current_user_data["user"]
    
    # Hash the new password
    hashed_password = create_hashed_password(request.new_password)
    
    # Update password
    user.hashed_password = hashed_password
    db.commit()
    
    return {"message": "Password reset successfully"}

@router.post("/create-prof")
def create_prof(
    request: CreateProfRequest,
    token: str = Depends(prof_required),
    db: Session = Depends(get_db)
):
    # Extract username from email
    username = request.email.split('@')[0]
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Username {username} already exists"
        )
    
    # Get prof role id
    prof_role = db.query(Role).filter(Role.role == RoleType.PROF).first()
    if not prof_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Professor role not found"
        )
    
    # Generate temporary password
    temporary_password = generate_random_string(10)
    hashed_password = create_hashed_password(temporary_password)
    
    # Create new professor
    new_prof = User(
        name=request.name, 
        email=request.email, 
        username=username, 
        hashed_password=hashed_password,
        role_id=prof_role.id
    )
    
    db.add(new_prof)
    db.commit()
    db.refresh(new_prof)
    
    return {
        "message": "Professor created successfully",
        "username": username,
        "temporary_password": temporary_password
    }

@router.post("/upload-students")
async def upload_students(
    file: UploadFile = File(...),
    token: str = Depends(prof_or_ta_required),  # Updated dependency
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        try:
            students = extract_students(content_str)
        except CSVFormatError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
        
        created_students = []
        errors = []
        
        # Get student role
        student_role = db.query(Role).filter(Role.role == RoleType.STUDENT).first()
        if not student_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Student role not found"
            )
        
        # Process each student
        for student in students:
            try:
                # extract username from email
                username = student['Email'].split('@')[0]
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new student
                if 'RollNo' in student:
                    user_id = student['RollNo']
                else:
                    user_id = None
                new_student = User(
                    id=user_id,
                    name=student['Name'],
                    email=student['Email'],
                    username=username,
                    hashed_password=hashed_password,
                    role_id=student_role.id
                )
                
                # Add and commit
                db.add(new_student)
                db.commit()
                db.refresh(new_student)
                
                # Add to successful creations
                created_students.append({
                    "name": new_student.name,
                    "email": new_student.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing student {student}: {str(e)}")
        
        return {
            "message": f"Processed {len(created_students)} students",
            "created_students": created_students,
            "errors": errors
        }
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )

@router.post("/upload-tas")
async def upload_tas(
    file: UploadFile = File(...),
    token: str = Depends(prof_required),
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        try:
            tas = extract_ta_data_from_content(content_str)
        except CSVFormatError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
            
        created_tas = []
        errors = []
        
        # Get TA role
        ta_role = db.query(Role).filter(Role.role == RoleType.TA).first()
        if not ta_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TA role not found"
            )
        
        # Process each TA
        for ta in tas:
            try:
                username = ta['Username']
                
                # Check if username already exists
                existing_user = db.query(User).filter(User.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new TA
                new_ta = User(
                    name=ta['Name'],
                    email=ta['Email'],
                    username=username,
                    hashed_password=hashed_password,
                    role_id=ta_role.id
                )
                
                # Add and commit
                db.add(new_ta)
                db.commit()
                db.refresh(new_ta)
                
                # Add to successful creations
                created_tas.append({
                    "name": new_ta.name,
                    "email": new_ta.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing TA {ta}: {str(e)}")
        
        return {
            "message": f"Processed {len(created_tas)} TAs",
            "created_tas": created_tas,
            "errors": errors
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )

@router.post("/register-temp")
def register_temp(
    request: TempRegisterRequest,
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )
    
    # Generate username from email
    username = request.email.split('@')[0]
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username {username} already exists"
        ) 
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == request.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {request.email} is already registered"
        )
    
    # Get role ID
    role = db.query(Role).filter(Role.role == request.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role {request.role} does not exist"
        )
    
    # Hash the password
    hashed_password = create_hashed_password(request.password)
    
    # Create new user
    new_user = User(
        name=request.name,
        email=request.email,
        username=username,
        hashed_password=hashed_password,
        role_id=role.id
    )
    
    # Add user to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": f"User registered successfully as {request.role}",
        "username": username
    }
