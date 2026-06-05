from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="User's email address")

class UserCreate(UserBase):
    password: str = Field(..., description="Strong password", min_length=8)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "hacker@example.com",
                "password": "supersecretpassword123"
            }
        }

class UserUpdate(BaseModel):
    password: Optional[str] = None
    is_active: Optional[bool] = None

class UserInDB(UserBase):
    id: int = Field(..., description="Unique user ID")
    is_active: bool = Field(..., description="Whether the user account is active")
    is_superuser: bool = Field(..., description="Admin flag")
    role: str = Field(..., description="User role, e.g. 'admin', 'teacher', 'user'")
    mfa_enabled: bool = Field(..., description="Is 2FA enabled for this user?")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "email": "hacker@example.com",
                "id": 1337,
                "is_active": True,
                "is_superuser": False,
                "role": "user",
                "mfa_enabled": False
            }
        }

class UserMFA(BaseModel):
    email: EmailStr
    code: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    refresh: bool = False

# Password reset schemas
class ForgotPassword(BaseModel):
    email: EmailStr = Field(..., description="Email address to send reset link to")

    class Config:
        json_schema_extra = {"example": {"email": "user@example.com"}}

class ResetPassword(BaseModel):
    token: str = Field(..., description="Reset token from the email link")
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars)")

    class Config:
        json_schema_extra = {
            "example": {
                "token": "abc123resettoken",
                "new_password": "mynewpassword99"
            }
        }

# ── 2-Step Registration Schemas ──────────────────────────────────────────────

class CheckEmail(BaseModel):
    """Step 1: check if email/username exists before full registration."""
    email: EmailStr = Field(..., description="Email to check availability")

class CheckEmailResponse(BaseModel):
    exists: bool
    message: str

class CompleteProfile(BaseModel):
    """Step 2 (new users only): supply extra info after email+password signup."""
    age: Optional[int] = Field(None, ge=5, le=120, description="User's age")
    grade: Optional[str] = Field(None, description="Grade/level e.g. '10th', 'freshman', 'bachelor'")
    interests: Optional[List[str]] = Field(None, description="Subjects of interest e.g. ['math','physics']")
    gender: Optional[str] = Field(None, description="'male' | 'female' | 'other'")
    avatar_url: Optional[str] = Field(None, description="Profile image URL or base64 data URI")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "age": 16,
                "grade": "10th",
                "interests": ["math", "physics", "chemistry"],
                "gender": "male",
                "avatar_url": "https://example.com/avatar.jpg",
                "first_name": "John",
                "last_name": "Doe"
            }
        }

# User Profile Schemas
class UserProfileBase(BaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    bio: Optional[str] = Field(None, description="User biography")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    age: Optional[int] = Field(None, ge=5, le=120)
    grade: Optional[str] = None
    interests: Optional[List[str]] = None
    gender: Optional[str] = None

class UserProfileUpdate(UserProfileBase):
    pass

class UserProfileInDB(UserProfileBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True


# User History Schemas
class UserHistoryCreate(BaseModel):
    question: Optional[str] = Field(None, description="The query/question asked by the user")
    data: Optional[List[str]] = Field(None, description="Array of HTML string responses (1-5 or more)")
    answer: Optional[str] = Field(None, description="The user's response to the question")
    correct_answer: Optional[str] = Field(None, description="The correct answer for the question")
    favorite: Optional[bool] = Field(False, description="Is this history item favorited")

class UserHistoryInDB(UserHistoryCreate):
    id: int
    user_id: int
    created_at: datetime
    is_correct: Optional[bool] = Field(None, description="Computed field if the answer was correct")

    class Config:
        from_attributes = True

# ── History Review Schemas ────────────────────────────────────────────────────

class HistoryReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    comment: Optional[str] = Field(None, description="Optional review comment")

class HistoryReviewerInfo(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True

class HistoryReviewInDB(HistoryReviewCreate):
    id: int
    history_id: int
    reviewer_id: int
    created_at: datetime
    reviewer: Optional[HistoryReviewerInfo] = None

    class Config:
        from_attributes = True

# ── Public History Response ───────────────────────────────────────────────────

class PublicHistoryCreator(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True

class PublicHistoryResponse(BaseModel):
    id: int
    question: Optional[str]
    data: Optional[List[str]]
    created_at: datetime
    favorite: Optional[bool]
    user: Optional[PublicHistoryCreator]
    avg_rating: Optional[float] = Field(None, description="Average star rating 1-5, None if no reviews")
    review_count: int = 0

    class Config:
        from_attributes = True

# Comic Book Schemas
class ComicBookCreate(BaseModel):
    title: str = Field(..., description="Title of the comic book")
    description: Optional[str] = Field(None, description="Description of the comic book")
    images: List[str] = Field(..., description="Array of image URLs or base64 strings")
    is_public: Optional[bool] = Field(True, description="Visible to everyone")

class ComicBookUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    images: Optional[List[str]] = None
    is_public: Optional[bool] = None

class ComicBookInDB(ComicBookCreate):
    id: int
    author_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Comic Review Schemas
class ComicReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating (1-5)")
    review_text: Optional[str] = Field(None, description="Optional review text")

class ComicReviewInDB(ComicReviewCreate):
    id: int
    comic_id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
