from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import os

# base class
Base = declarative_base()

# User table
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)
    role = Column(String, nullable=False)  # 'peer' or 'scholar'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # One-to-many relationship with repositories
    repositories = relationship('Repository', back_populates='owner')

    # One-to-many relationship with access logs
    access_logs = relationship('AccessLog', back_populates='user')

# Repository table
class Repository(Base):
    __tablename__ = 'repositories'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    repo_name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Many-to-one relationship with user
    owner = relationship('User', back_populates='repositories')

    # One-to-many relationship with datasets
    datasets = relationship('Dataset', back_populates='repository')

    # One-to-many relationship with access logs
    access_logs = relationship('AccessLog', back_populates='repository')

# Dataset table
class Dataset(Base):
    __tablename__ = 'datasets'

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('repositories.id'), nullable=False)
    dataset_type = Column(String, nullable=False)  # 'train', 'test', 'validation', 'analysis'
    location = Column(String, nullable=False)  # file path
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Many-to-one relationship with repository
    repository = relationship('Repository', back_populates='datasets')

class AccessLog(Base):
    __tablename__ = 'access_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    repository_id = Column(Integer, ForeignKey('repositories.id'), nullable=False)
    accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    action = Column(String, nullable=False)  # 'upload', 'download'

    # Many-to-one relationship with user
    user = relationship('User', back_populates='access_logs')

    # Many-to-one relationship with repository
    repository = relationship('Repository', back_populates='access_logs')

db_path = os.path.join(os.path.dirname(__file__), 'poc.db')
engine = create_engine(f"sqlite:///{db_path}", echo=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
