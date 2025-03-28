from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.session import get_db
from app.core.security.auth import (
    get_current_user,
    create_hashed_password,
    verify_password,
    generate_token,
    generate_random_string
)
from app.models.user import User, Role, RoleType
from app.services.email import send_email, create_otp_email
from app.schemas.user import (
    UserBase,
    CreateProfRequest,
    RequestOTPModel,
    VerifyOTPModel,
    ResetPasswordWithOTPModel
)

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = current_user["user"]
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "role": user.role.role.value,
        "team_id": user.team_id
    }

@router.post("/prof")
async def create_prof(
    request: CreateProfRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] != RoleType.PROF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can create other professors"
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {request.email} is already registered"
        )

    # Generate temporary password
    temp_password = generate_random_string(12)
    
    # Get professor role
    prof_role = db.query(Role).filter(Role.role == RoleType.PROF).first()
    if not prof_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Professor role not found in database"
        )

    # Create new professor user
    new_prof = User(
        name=request.name,
        email=request.email,
        username=request.email.split('@')[0],
        hashed_password=create_hashed_password(temp_password),
        role_id=prof_role.id
    )
    
    try:
        # Add to database
        db.add(new_prof)
        db.commit()
        db.refresh(new_prof)
        
        # Send email with temporary password
        email_content = f"""
        <h2>Welcome to Sahara!</h2>
        <p>Your account has been created with the following credentials:</p>
        <p>Username: {new_prof.username}</p>
        <p>Temporary Password: {temp_password}</p>
        <p>Please change your password after logging in.</p>
        """
        
        email_sent = send_email(
            to_email=request.email,
            subject="Welcome to Sahara - Your Account Details",
            html_content=email_content
        )
        
        if not email_sent:
            # If email fails, still return success but with a warning
            return {
                "message": "Professor account created successfully, but failed to send email",
                "username": new_prof.username
            }
            
        return {
            "message": "Professor account created successfully",
            "username": new_prof.username
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/reset-password/request")
async def request_password_reset(
    request: RequestOTPModel,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Generate OTP
    otp = generate_random_string(6)
    expiry = datetime.utcnow() + timedelta(minutes=10)
    
    # Store OTP in database
    user.reset_otp = otp
    user.reset_otp_expiry = expiry
    db.commit()
    
    # Send OTP email
    email_content = create_otp_email(otp)
    email_sent = send_email(
        to_email=request.email,
        subject="Password Reset Code",
        html_content=email_content
    )
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reset code email"
        )
        
    return {"message": "Password reset code sent to your email"}

@router.post("/reset-password/verify")
async def verify_reset_otp(
    request: VerifyOTPModel,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not user.reset_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request"
        )

    if user.reset_otp != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code"
        )

    if datetime.utcnow() > user.reset_otp_expiry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code has expired"
        )

    return {"message": "Reset code verified successfully"}

@router.post("/reset-password/complete")
async def complete_password_reset(
    request: ResetPasswordWithOTPModel,
    db: Session = Depends(get_db)
):
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )

    user = db.query(User).filter(User.email == request.email).first()
    if not user or not user.reset_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request"
        )

    if user.reset_otp != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code"
        )

    if datetime.utcnow() > user.reset_otp_expiry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code has expired"
        )

    # Update password
    user.hashed_password = create_hashed_password(request.new_password)
    user.reset_otp = None
    user.reset_otp_expiry = None
    db.commit()

    return {"message": "Password reset successfully"}