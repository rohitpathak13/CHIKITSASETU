from pydantic import BaseModel, EmailStr
from typing import Optional
from core.models.user import RoleEnum

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserProfileResponse(BaseModel):
    id: int
    email: str
    role: RoleEnum
    first_name: str
    last_name: str
    phone: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
