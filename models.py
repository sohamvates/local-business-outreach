from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    website = Column(String)
    email = Column(String)
    category = Column(String)
    rating = Column(Float)
    reviews_count = Column(Integer)
    digital_score = Column(Float)          # 0–100 score from our scoring logic
    source = Column(String)                # 'google_maps' | 'scraper_agencies'
    company_type = Column(String)          # 'client' | 'agency'
    stack_keywords = Column(Text)          # JSON array string
    place_id = Column(String, unique=True) # Google Maps place_id for deduplication
    created_at = Column(DateTime, default=datetime.utcnow)

    emails = relationship("Email", back_populates="company")
    outreach_records = relationship("OutreachRecord", back_populates="company")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    subject = Column(String)
    body = Column(Text)
    from_address = Column(String)          # which sender was used
    status = Column(String, default="pending")  # pending | approved | discarded | sent
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)
    sent_at = Column(DateTime)
    review_notes = Column(Text)

    company = relationship("Company", back_populates="emails")
    outreach_records = relationship("OutreachRecord", back_populates="email")


class OutreachRecord(Base):
    __tablename__ = "outreach_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id"))
    status = Column(String, default="sent")  # sent | replied | follow_up | closed
    sent_at = Column(DateTime)
    replied_at = Column(DateTime)
    follow_up_date = Column(DateTime)
    follow_up_sent = Column(Boolean, default=False)
    notes = Column(Text)
    sheets_row = Column(Integer)           # Row number in Google Sheets for sync
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="outreach_records")
    email = relationship("Email", back_populates="outreach_records")


class DoNotContact(Base):
    __tablename__ = "do_not_contact"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    domain = Column(String, index=True)
    company_name = Column(String, index=True)
    reason = Column(String, nullable=False)
    source = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
