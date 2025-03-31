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