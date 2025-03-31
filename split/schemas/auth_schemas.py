from pydantic import BaseModel, EmailStr
from typing import Optional
from ..models.roles import RoleType

class QueryBaseModel(BaseModel):
    token: str = None

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: RoleType

class LoginRequest(BaseModel):
    username: str
    password: str

class ResetPasswordRequest(BaseModel):
    new_password: str
    confirm_password: str

class CreateProfRequest(BaseModel):
    name: str
    email: EmailStr

class TempRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    confirm_password: str
    role: RoleType

class RequestOTPModel(BaseModel):
    email: EmailStr

class VerifyOTPModel(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordWithOTPModel(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    confirm_password: str 

class UserIdRequest(BaseModel):
    user_id: int 

