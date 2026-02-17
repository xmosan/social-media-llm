from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)

    status = Column(String, nullable=False, default="submitted")
    source_type = Column(String, nullable=False, default="form")
    source_text = Column(Text, nullable=True)

    # MUST be a public https URL for Instagram publishing
    media_url = Column(Text, nullable=True)

    caption = Column(Text, nullable=True)
    hashtags = Column(SQLiteJSON, nullable=True)
    alt_text = Column(Text, nullable=True)

    flags = Column(SQLiteJSON, nullable=False, default=dict)

    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    published_time = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)