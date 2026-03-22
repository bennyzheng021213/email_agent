from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from src.config.settings import settings

# Create database engine
engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Email(Base):
    """Email model for storing processed emails"""
    __tablename__ = "emails"

    id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, index=True)
    from_email = Column(String, index=True)
    to_email = Column(String)
    subject = Column(String)
    content = Column(Text)
    received_at = Column(DateTime)
    is_processed = Column(Boolean, default=False)
    is_business = Column(Boolean, default=False)
    is_filtered = Column(Boolean, default=False)
    filter_reason = Column(String, nullable=True)
    draft_created = Column(Boolean, default=False)
    draft_id = Column(String, nullable=True)
    wechat_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Draft(Base):
    """Draft model for storing generated drafts"""
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(String, index=True)
    draft_content = Column(Text)
    draft_subject = Column(String)
    ai_model = Column(String)
    token_usage = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProcessingLog(Base):
    """Log model for tracking processing activities"""
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(String, index=True)
    action = Column(String)  # 'filtered', 'analyzed', 'draft_created', 'notified'
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()