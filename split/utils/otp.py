
from fastapi import HTTPException
import secrets
import string
from passlib.context import CryptContext
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def generate_secure_otp(length=6):
    """Generate a cryptographically secure random OTP of specified length"""
    # Use secrets module for cryptographic security
    return ''.join(secrets.choice(string.digits) for _ in range(length))

# Hash an OTP for secure storage
def hash_otp(otp: str) -> str:
    """Hash an OTP using the same password hashing mechanism"""
    return pwd_context.hash(otp)

# Verify a provided OTP against its hash
def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify an OTP against its hashed value"""
    return pwd_context.verify(plain_otp, hashed_otp)

# Generate a secure random string for passwords
def generate_secure_string(length=10):
    """Generate a cryptographically secure random string for temporary passwords"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

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