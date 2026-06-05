from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    role = Column(String, default="student")  # admin, teacher, student
    google_id = Column(String, unique=True, index=True, nullable=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    # Password-reset flow
    password_reset_token = Column(String, nullable=True, index=True)
    password_reset_expires = Column(DateTime, nullable=True)

    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    history = relationship("UserHistory", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    # Registration step-2 fields
    age = Column(Integer, nullable=True)
    grade = Column(String, nullable=True)          # e.g. "10th", "freshman", "bachelor"
    interests = Column(JSON, nullable=True)        # list of subjects: ["math", "physics", ...]
    gender = Column(String, nullable=True)         # "male" | "female" | "other"

    user = relationship("User", back_populates="profile")


class UserHistory(Base):
    __tablename__ = "user_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question = Column(String, nullable=True)
    data = Column(JSON, nullable=True)  # Stores array of HTML strings/elements (1-5 or more)
    answer = Column(String, nullable=True)
    correct_answer = Column(String, nullable=True)
    favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="history")
    reviews = relationship("HistoryReview", back_populates="history", cascade="all, delete-orphan")


class HistoryReview(Base):
    """Star rating (1-5) + optional comment on a public history record."""
    __tablename__ = "history_reviews"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("user_histories.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)       # 1-5
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    history = relationship("UserHistory", back_populates="reviews")
    reviewer = relationship("User", backref="history_reviews")


class ComicBook(Base):
    __tablename__ = "comic_books"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    images = Column(JSON, nullable=False)  # List of image URLs or base64 strings
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_public = Column(Boolean, default=True)

    author = relationship("User", backref="comics")


class ComicReview(Base):
    __tablename__ = "comic_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    comic_id = Column(Integer, ForeignKey("comic_books.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1 to 5
    review_text = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    comic = relationship("ComicBook", backref="reviews")
    user = relationship("User", backref="comic_reviews")

