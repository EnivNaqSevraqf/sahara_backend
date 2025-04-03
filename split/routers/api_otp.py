from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database.db import get_db
from ..models.user import User
from ..schemas.auth_schemas import RequestOTPModel, VerifyOTPModel, ResetPasswordWithOTPModel
from ..utils.otp import generate_secure_otp, hash_otp, verify_otp
from datetime import datetime, timezone, timedelta
from ..models.user_otp import UserOTP
import traceback
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from email.mime.text import MIMEText
import smtplib
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(
    
    tags=["OTP"]
)

# Email configuration - you should store these in environment variables in production
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "saharaai.noreply@gmail.com"  # Replace with your email
EMAIL_HOST_PASSWORD = "zfrr wwru xeru rbhf"  # Replace with your app password
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "Sahara Team <saharaai.noreply@gmail.com>"  # Fixed to use the actual email account

# Function to send emails
def send_email(to_email, subject, html_content):
    """
    Send an HTML email using SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML body of the email
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = DEFAULT_FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        
        # Attach HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        print(f"Attempting to send email to {to_email}")
        
        # Connect to SMTP server with more detailed error handling
        try:
            # Enable debug output
            server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
            server.set_debuglevel(1)  # Add this line to enable verbose debug output
            print(f"Connected to SMTP server: {EMAIL_HOST}:{EMAIL_PORT}")
            
            if EMAIL_USE_TLS:
                server.starttls()
                print("TLS encryption enabled")
            
            print(f"Logging in with user: {EMAIL_HOST_USER}")
            server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
            print("Login successful")
            
            # Send email - more detailed debugging
            print(f"Sending mail from {EMAIL_HOST_USER} to {to_email}")
            result = server.sendmail(EMAIL_HOST_USER, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}")
            print(f"Server response: {result if result else 'No response (success)'}")
            server.quit()
            
            return True
        except smtplib.SMTPAuthenticationError as auth_err:
            print(f"SMTP Authentication Error: {str(auth_err)}")
            return False
        except smtplib.SMTPRecipientsRefused as ref_err:
            print(f"Recipients refused: {str(ref_err)}")
            return False
        except smtplib.SMTPSenderRefused as send_err:
            print(f"Sender refused: {str(send_err)}")
            return False
        except smtplib.SMTPDataError as data_err:
            print(f"SMTP data error: {str(data_err)}")
            return False
        except smtplib.SMTPException as smtp_e:
            print(f"SMTP Error: {str(smtp_e)}")
            return False
        except Exception as conn_e:
            print(f"Connection error: {str(conn_e)}")
            print(f"Error type: {type(conn_e).__name__}")
            print(f"Traceback: {traceback.format_exc()}")
            return False
    except Exception as e:
        print(f"Failed to prepare email: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

# Create HTML email template for OTP
def create_otp_email(otp, expiry_minutes=10):
    """
    Create HTML email content for OTP verification
    
    Args:
        otp: The one-time password
        expiry_minutes: Validity period in minutes
    
    Returns:
        HTML content as string
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Password Reset Code</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .code {{ font-size: 24px; font-weight: bold; text-align: center; 
                    padding: 15px; background-color: #e9e9e9; margin: 20px 0; letter-spacing: 5px; }}
            .footer {{ font-size: 12px; text-align: center; margin-top: 20px; color: #1f2e6a; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Reset Verification</h2>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>You've requested to reset your password for your Sahara account.</p>
                <p>Please use the following verification code to complete the process:</p>
                
                <div class="code">{otp}</div>
                
                <p>This code is valid for {expiry_minutes} minutes and can only be used once.</p>
                <p>If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
            </div>
            <div class="footer">
                <p>This is an automated message, please do not reply directly to this email.</p>
                <p>&copy; {datetime.now().year} Sahara Team</p>
            </div>
        </div>
    </body>
    </html>
    """
def create_hashed_password(password: str):
    return pwd_context.hash(password)

@router.post("/request-otp")
async def request_otp(request: RequestOTPModel, db: Session = Depends(get_db)):
    """
    Request OTP for password reset and send it via email
    """
    try:
        # Check if user with email exists
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            # For security, we return a similar message but with a special status code
            # that the frontend can use to show a helpful message
            print(f"OTP request for non-existent email: {request.email}")
            return {
                "message": "If the email exists in our system, a verification code has been sent. Please check your spam folder if you don't see it in your inbox.",
                "status": "user_not_found"  # Changed this to be more semantic
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
@router.post("/verify-otp")
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
@router.post("/reset-password-with-otp")
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