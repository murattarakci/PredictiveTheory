import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path # <--- IMPORT PATH HERE
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Enum,
    UniqueConstraint # For composite unique constraints if needed later
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum

# logging.getLogger().setLevel(logging.ERROR) # Keep this or adjust for more SQL logs

Base = declarative_base()

class VisibilityEnum(enum.Enum):
    PRIVATE = "private"
    EMBARGOED = "embargoed"
    PUBLIC = "public"

class SplitRatioEnum(enum.Enum): # Not directly used in Repository model for storing selection, but defined
    RATIO_60_20_20 = "60-20-20"
    RATIO_70_15_15 = "70-15-15"
    RATIO_80_10_10 = "80-10-10"

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True) # For POC; use proper hashing in production
    role = Column(String, nullable=False)  # 'peer' or 'scholar'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    repositories = relationship('Repository', back_populates='owner')
    access_logs = relationship('AccessLog', back_populates='user')
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"

class Repository(Base):
    __tablename__ = 'repositories'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    repo_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    visibility = Column(Enum(VisibilityEnum), default=VisibilityEnum.PRIVATE)
    # Will store a comma-separated string of column names if multiple, or a single name, or None
    split_column = Column(String, nullable=True)
    # Storing the selected split ratio string (e.g., "0.7,0.15,0.15") directly
    split_ratio_selection = Column(String, nullable=True)
    permalink = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    owner = relationship('User', back_populates='repositories')
    datasets = relationship('Dataset', back_populates='repository', cascade="all, delete-orphan")
    access_logs = relationship('AccessLog', back_populates='repository', cascade="all, delete-orphan")
    # For databases that support it well with SQLAlchemy (not easily with SQLite for composite):
    # __table_args__ = (UniqueConstraint('user_id', 'repo_name', name='_user_repo_name_uc'),)
    def __repr__(self):
        return f"<Repository(id={self.id}, name='{self.repo_name}', owner_id={self.user_id})>"

class Dataset(Base):
    __tablename__ = 'datasets'
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('repositories.id', ondelete="CASCADE"), nullable=False)
    dataset_type = Column(String, nullable=False)  # 'train', 'test', 'validation', 'analysis'
    location = Column(String, nullable=False)  # file path relative to a base data directory
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    repository = relationship('Repository', back_populates='datasets')
    def __repr__(self):
        return f"<Dataset(id={self.id}, type='{self.dataset_type}', repo_id={self.repository_id})>"

class AccessLog(Base):
    __tablename__ = 'access_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True) # User can be deleted, log remains
    repository_id = Column(Integer, ForeignKey('repositories.id', ondelete="CASCADE"), nullable=False)
    accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    action = Column(String, nullable=False)  # 'upload', 'download', 'view'
    user = relationship('User', back_populates='access_logs')
    repository = relationship('Repository', back_populates='access_logs')
    def __repr__(self):
        return f"<AccessLog(id={self.id}, user_id={self.user_id}, repo_id={self.repository_id}, action='{self.action}')>"

DB_DIR = Path(__file__).resolve().parent # poc.db will be in the same directory as models.py (db/)
db_path = DB_DIR / 'poc.db'
engine = create_engine(f"sqlite:///{db_path}", echo=False) # Set echo=True for SQL debugging
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(engine)
    print(f"Database initialized at: {db_path}")