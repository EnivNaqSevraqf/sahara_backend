import csv
from datetime import datetime, timedelta
from typing import List, Optional
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..dependencies.auth import oauth2_scheme
from read_csv import CSVFormatError
from ..database.init import get_db
from ..models.user import User
from ..models.roles import RoleType
from ..config.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def generate_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_random_string(length=8):
    return "hello123"
    # return "".join(random.choices(string.ascii_letters + string.digits, k=length))

def resolve_token(token: str = Header(None)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
def create_hashed_password(password: str):
    return pwd_context.hash(password)

def extract_students(content: str) -> List[dict]:
    """
    Extracts student data from the CSV content.
    Returns a list of dictionaries with student data.
    """
    reader = csv.DictReader(content.splitlines())
    students = []
    expected_headers = ['RollNo','Name', 'Email']
    headers = reader.fieldnames
    try:
        for header in expected_headers:
            if header not in headers:
                raise CSVFormatError(f"Missing header: {header}")
        
        for row in reader:
            student = {
                'RollNo': row.get('RollNo'),
                'Name': row.get('Name'),
                'Email': row.get('Email'),
                
            }
            students.append(student)
        

        for student in students:
            if not student['RollNo'] or not student['Name'] or not student['Email']:
                print(student)
                raise CSVFormatError("All fields must be filled for each student.")
        
        return students
    except CSVFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
"""
CSV File Format for Student Upload:
Expected columns:
- Name: Full name of the student (e.g., "John Doe")
- Email: Valid email address (e.g., "john.doe@example.com")
- Username: Unique username for login (e.g., "jdoe" or "john.doe")

Example CSV format:
```
Name,Email,Username
John Doe,john.doe@example.com,jdoe
Jane Smith,jane.smith@example.com,jsmith
```

Notes:
- The first row must contain the column headers as shown above
- All three columns are required for each student
- Usernames must be unique across all users in the system
- Each row will create a new student account with a randomly generated temporary password
"""