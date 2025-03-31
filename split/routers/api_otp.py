@app.post("/request-otp")
async def request_otp(request: RequestOTPModel, db: Session = Depends(get_db)):
    """
    Request OTP for password reset and send it via email
    """
    try:
        # Check if user with email exists
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            # For security, we still return the same message
            # but we'll log this for debugging
            print(f"OTP request for non-existent email: {request.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "email_not_found"  # Add a status for debugging only
            }
        
        # Generate secure OTP
        plain_otp = generate_secure_otp(6)
        print(f"Generated OTP for {user.email}: {plain_otp}")  # Only log during development
        
        # Hash the OTP for secure storage
        hashed_otp = hash_otp(plain_otp)
        
        # Set expiration time (10 minutes from now)
        expiration_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        # Check if an OTP entry already exists for this user
        existing_otp = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        if existing_otp:
            # Update existing OTP record
            existing_otp.hashed_otp = hashed_otp
            existing_otp.expires_at = expiration_time.isoformat()
        else:
            # Create new OTP record
            new_otp_record = UserOTP(
                user_id=user.id,
                hashed_otp=hashed_otp,
                expires_at=expiration_time.isoformat()
            )
            db.add(new_otp_record)
        
        # Commit the changes
        db.commit()
        
        # Create email content
        email_subject = "Your Password Reset Code - Sahara"
        email_html = create_otp_email(plain_otp)
        
        # Send email with OTP
        try:
            print(f"Attempting to send email to {user.email} with OTP: {plain_otp}")
            email_sent = send_email(user.email, email_subject, email_html)
        except Exception as e:
            print(f"Exception during email sending: {str(e)}")
            print(traceback.format_exc())
            email_sent = False
        
        if not email_sent:
            print(f"Failed to send OTP email to {user.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "email_attempted" # For debugging purposes
            }
        
        # For security reasons, always return the same message whether email exists or not
        return {
            "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
            "status": "email_sent" # For debugging purposes
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in request_otp: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your request. Please try again."
        )

# Verify OTP endpoint
@app.post("/verify-otp")
async def verify_otp_endpoint(request: VerifyOTPModel, db: Session = Depends(get_db)):
    """
    Verify OTP provided by the user
    """
    try:
        # Find user by email
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get OTP record for user
        otp_record = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        # Check if OTP record exists
        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP request found for this email"
            )
        
        # Check if OTP has expired
        expiration_time = datetime.fromisoformat(otp_record.expires_at)
        if datetime.now(timezone.utc) > expiration_time:
            # Delete expired OTP
            db.delete(otp_record)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new one."
            )
        
        # Verify OTP
        if not verify_otp(request.otp, otp_record.hashed_otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        
        # OTP is valid - do not delete yet as we need it for reset_password_with_otp
        return {"message": "OTP verified successfully"}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in verify_otp: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP. Please try again."
        )

# Reset password with OTP endpoint
@app.post("/reset-password-with-otp")
async def reset_password_with_otp(request: ResetPasswordWithOTPModel, db: Session = Depends(get_db)):
    """
    Reset password after OTP verification
    """
    try:
        # Find user by email
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get OTP record for user
        otp_record = db.query(UserOTP).filter(UserOTP.user_id == user.id).first()
        
        # Check if OTP record exists
        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP request found for this email"
            )
        
        # Check if OTP has expired
        expiration_time = datetime.fromisoformat(otp_record.expires_at)
        if datetime.now(timezone.utc) > expiration_time:
            # Delete expired OTP
            db.delete(otp_record)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new one."
            )
        
        # Verify OTP
        if not verify_otp(request.otp, otp_record.hashed_otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP"
            )
        
        # Verify passwords match
        if request.new_password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        # Hash the new password
        hashed_password = create_hashed_password(request.new_password)
        
        # Update user's password
        user.hashed_password = hashed_password
        
        # Delete the OTP record after successful password reset
        db.delete(otp_record)
        
        # Commit changes
        db.commit()
        
        return {"message": "Password reset successfully"}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in reset_password_with_otp: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password. Please try again."
        )

# Email configuration - you should store these in environment variables in production
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "saharaai.noreply@gmail.com"  # Replace with your email
EMAIL_HOST_PASSWORD = "zfrr wwru xeru rbhf"  # Replace with your app password
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "Sahara Team <saharaai.noreply@gmail.com>"  # Fixed to use the actual email account