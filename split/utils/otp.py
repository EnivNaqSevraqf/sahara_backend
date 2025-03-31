
from fastapi import HTTPException
import secrets
import string
from passlib.context import CryptContext

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