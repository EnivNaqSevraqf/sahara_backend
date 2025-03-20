from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Query, Header, Body, File
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import random
import string
from pydantic import BaseModel, EmailStr
import enum
import secrets
import os
import tempfile
import io
from read_csv import extract_student_data_from_content, extract_ta_data_from_content, CSVFormatError
from fastapi.middleware.cors import CORSMiddleware


# ----------------------------
# Database and ORM Setup
# ----------------------------
# Update with your PostgreSQL credentials - the default username is usually "postgres"
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:hello123@localhost/maindb"

# Add debug prints to diagnose database connection issues
try:
    print("Connecting to database...")
    engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=True)  # Add echo=True to see SQL commands
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # Test connection
    with engine.connect() as conn:
        print("Database connection successful!")
    
except Exception as e:
    print(f"ERROR CONNECTING TO DATABASE: {e}")
    import traceback
    traceback.print_exc()
    # Optionally, exit the application if database setup fails
    # import sys
    # sys.exit(1)

# ----------------------------
# Password Hashing Setup
# ----------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ----------------------------
# JWT (JSON Web Token) Configuration
# ----------------------------
SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ----------------------------
# Enum for User Roles
# ----------------------------
class UserRole(str, enum.Enum):
    prof = "prof"  # Now prof is the highest role (removed admin)
    student = "student"
    ta = "ta"

# ----------------------------
# Pydantic Models for Request Bodies
# ----------------------------
class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole

class UserInDB(UserBase):
    id: int
    username: str
    hashed_password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ExtendedLoginRequest(BaseModel):
    username: str
    password: str
    role: str

class ResetPasswordAfterOTPRequest(BaseModel):
    new_password: str
    confirm_password: str

class CreateProfRequest(BaseModel):
    name: str
    email: EmailStr

class OTPVerificationRequest(BaseModel):
    email: EmailStr
    role: UserRole
    otp: str

class TempRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    confirm_password: str
    role: UserRole

# ----------------------------
# Database Models (Tables)
# ----------------------------
class Prof(Base):
    __tablename__ = "profs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class TA(Base):
    __tablename__ = "tas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# Later in your code, before creating tables:
print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
# ----------------------------
# Create Default Admin/Prof Entry
# ----------------------------

# This code ensures that a default admin/prof record with username 'root123' and password 'root123'
# exists for testing purposes.
with SessionLocal() as db:
    existing_admin = db.query(Prof).filter(Prof.username == "root123").first()
    if not existing_admin:
        new_admin = Prof(
            name="Root Admin",
            email="root@example.com",
            username="root123",
            hashed_password=pwd_context.hash("root123")  # Alternatively: create_hashed_password("root123")
        )
        db.add(new_admin)
        db.commit()

# ----------------------------
# Dependency to Get DB Session
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Utility Functions
# ----------------------------
def create_hashed_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def generate_token(data: dict, expires_delta: timedelta):
    """Generate a JWT token that includes an expiration time."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_random_string(length=8):
    """Generate a random string of fixed length."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))

# ----------------------------
# FastAPI Application Initialization
# ----------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def get_verified_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        role = payload.get("role")
        if email is None or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return {"email": email, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Rename admin_required to prof_required and update logic
def prof_required(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role = payload.get("role")
        if role != "prof":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

# Replace the get_current_user function to handle all user types
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    # Query the appropriate table based on the role
    if role == "prof":  # Changed from ["prof", "admin"]
        user = db.query(Prof).filter(Prof.username == username).first()
    elif role == "student":
        user = db.query(Student).filter(Student.username == username).first()
    elif role == "ta":
        user = db.query(TA).filter(TA.username == username).first()
    else:
        raise credentials_exception
    
    if user is None:
        raise credentials_exception
    
    # Return both user object and role
    return {"user": user, "role": role}

# ----------------------------
# API Endpoints
# ----------------------------

@app.post("/login")
def login(request: ExtendedLoginRequest, db: Session = Depends(get_db)):
    role = request.role.lower()
    if role == "prof":  # Changed from role in ["prof", "admin"]
        user = db.query(Prof).filter(Prof.username == request.username).first()
    elif role == "student":
        user = db.query(Student).filter(Student.username == request.username).first()
    elif role == "ta":
        user = db.query(TA).filter(TA.username == request.username).first()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role provided")

    # Verify credentials.
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = generate_token({"sub": user.username, "role": role}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}

# Update the reset_password function
@app.post("/reset-password")
def reset_password(
    new_password: str = Body(..., embed=True),
    confirm_password: str = Body(..., embed=True),
    current_user_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords don't match"
        )
    
    # Get user object and role
    user = current_user_data["user"]
    
    # Hash the new password
    hashed_password = create_hashed_password(new_password)
    
    # Update the current authenticated user's password
    user.hashed_password = hashed_password
    db.commit()
    
    return {"message": "Password reset successfully"}

# Admin endpoint to create a new professor, now secured by prof_required.
@app.post("/create-prof")
def create_prof(
    request: CreateProfRequest,
    db: Session = Depends(get_db),
    prof_data: dict = Depends(prof_required)  # Changed from admin_required
):
    # Extract username from email (characters before @)
    username = request.email.split('@')[0]
    
    # Check if username already exists
    existing_user = db.query(Prof).filter(Prof.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Username {username} already exists"
        )
    
    # Generate a temporary password
    temporary_password = generate_random_string(10)
    hashed_password = create_hashed_password(temporary_password)
    
    new_prof = Prof(name=request.name, email=request.email, username=username, hashed_password=hashed_password)
    db.add(new_prof)
    db.commit()
    db.refresh(new_prof)
    
    return {
        "message": "Professor created successfully",
        "username": username,
        "temporary_password": temporary_password
    }

# Create a new dependency to check if user is prof
def prof_or_ta_required(current_user_data: dict = Depends(get_current_user)):
    role = current_user_data["role"]
    if role not in ["prof", "ta"]:  # Changed from ["prof", "admin"]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can perform this action"
        )
    return current_user_data

@app.post("/upload-students")
async def upload_students(
    file: UploadFile = File(...),
    current_user_data: dict = Depends(prof_or_ta_required),
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content directly
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Use the function to process content directly
        try:
            students = extract_student_data_from_content(content_str)
        except CSVFormatError as e:
            # Return a user-friendly error for CSV format issues
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
        
        created_students = []
        errors = []
        
        # Process each student
        for student in students:
            try:
                username = student['Username']
                
                # Check if username already exists
                existing_user = db.query(Student).filter(Student.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new student
                new_student = Student(
                    name=student['Name'],
                    email=student['Email'],
                    username=username,
                    hashed_password=hashed_password
                )
                
                # Add and commit the new student
                db.add(new_student)
                db.commit()
                db.refresh(new_student)
                
                # Add to successful creations list
                created_students.append({
                    "name": new_student.name,
                    "email": new_student.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing student {student}: {str(e)}")
        
        # Return result
        return {
            "message": f"Processed {len(created_students)} students",
            "created_students": created_students,
            "errors": errors
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )

@app.post("/upload-tas")
async def upload_tas(
    file: UploadFile = File(...),
    current_user_data: dict = Depends(prof_required),  # Changed from prof_or_ta_required to prof_required
    db: Session = Depends(get_db)
):
    # Ensure the file is a CSV
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content directly
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Use the function to process content directly
        try:
            tas = extract_ta_data_from_content(content_str)
        except CSVFormatError as e:
            # Return a user-friendly error for CSV format issues
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV format error: {str(e)}"
            )
            
        created_tas = []
        errors = []
        
        # Process each TA
        for ta in tas:
            try:
                username = ta['Username']
                
                # Check if username already exists
                existing_user = db.query(TA).filter(TA.username == username).first()
                if existing_user:
                    errors.append(f"Username {username} already exists")
                    continue
                
                # Generate random password
                temp_password = generate_random_string(10)
                hashed_password = create_hashed_password(temp_password)
                
                # Create new TA
                new_ta = TA(
                    name=ta['Name'],
                    email=ta['Email'],
                    username=username,
                    hashed_password=hashed_password
                )
                
                # Add and commit the new TA
                db.add(new_ta)
                db.commit()
                db.refresh(new_ta)
                
                # Add to successful creations list
                created_tas.append({
                    "name": new_ta.name,
                    "email": new_ta.email,
                    "username": username,
                    "temp_password": temp_password
                })
                
            except Exception as e:
                errors.append(f"Error processing TA {ta}: {str(e)}")
        
        # Return result
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

@app.post("/register-temp", include_in_schema=False)  # Hide from documentation
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
    
    # Check if username already exists in any role's table
    existing_prof = db.query(Prof).filter(Prof.username == username).first()
    existing_student = db.query(Student).filter(Student.username == username).first()
    existing_ta = db.query(TA).filter(TA.username == username).first()
    
    if existing_prof or existing_student or existing_ta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username {username} already exists"
        )
    
    # Check if email already exists for any role
    existing_email_prof = db.query(Prof).filter(Prof.email == request.email).first()
    existing_email_student = db.query(Student).filter(Student.email == request.email).first()
    existing_email_ta = db.query(TA).filter(TA.email == request.email).first()
    
    if existing_email_prof or existing_email_student or existing_email_ta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {request.email} is already registered"
        )
    
    # Hash the password
    hashed_password = create_hashed_password(request.password)
    
    # Create new user based on role
    if request.role == UserRole.prof:  # Changed from request.role == UserRole.prof or request.role == UserRole.admin
        new_user = Prof(
            name=request.name,
            email=request.email,
            username=username,
            hashed_password=hashed_password
        )
    elif request.role == UserRole.student:
        new_user = Student(
            name=request.name,
            email=request.email,
            username=username,
            hashed_password=hashed_password
        )
    elif request.role == UserRole.ta:
        new_user = TA(
            name=request.name,
            email=request.email,
            username=username,
            hashed_password=hashed_password
        )
    
    # Add user to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Return response without token - user needs to log in separately
    return {
        "message": f"User registered successfully as {request.role}",
        "username": username
    }

# ----------------------------
# Templates for Additional Endpoints
# ----------------------------

# TODO: Implement OTP generation (e.g., /forgot-password) and CSV extraction for bulk user creation.
# @app.post("/forgot-password")
# def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
#     """
#     Check if email exists, generate OTP, store it, and send OTP via email.
#     """
#     pass

# @app.post("/upload-csv")
# def upload_csv(file: UploadFile, role: UserRole, db: Session = Depends(get_db)):
#     """
#     Extract data from a CSV file and create multiple users (e.g., students or TAs).
#     and commit it in the database.
#     """
#     pass
