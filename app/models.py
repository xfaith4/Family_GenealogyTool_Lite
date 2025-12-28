from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Table, Column, Index, Enum as SQLEnum, Float, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum

class Base(DeclarativeBase):
    pass

# Association table for family children
family_children = Table(
    'family_children',
    Base.metadata,
    Column('family_id', Integer, ForeignKey('families.id', ondelete='CASCADE'), primary_key=True),
    Column('child_person_id', Integer, ForeignKey('persons.id', ondelete='CASCADE'), primary_key=True)
)

# Association table for relationships (parent-child)
relationships = Table(
    'relationships',
    Base.metadata,
    Column('parent_person_id', Integer, ForeignKey('persons.id', ondelete='CASCADE'), primary_key=True),
    Column('child_person_id', Integer, ForeignKey('persons.id', ondelete='CASCADE'), primary_key=True),
    Column('rel_type', String(50), nullable=False, server_default='parent', primary_key=True)
)

class EventType(enum.Enum):
    BIRTH = "birth"
    DEATH = "death"
    MARRIAGE = "marriage"
    DIVORCE = "divorce"
    CENSUS = "census"
    RESIDENCE = "residence"
    OCCUPATION = "occupation"
    IMMIGRATION = "immigration"
    EMIGRATION = "emigration"
    NATURALIZATION = "naturalization"
    OTHER = "other"

class Person(Base):
    __tablename__ = 'persons'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xref: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    given: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    surname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)

    # Legacy date/place fields (for backward compatibility)
    birth_date: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    birth_place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    death_date: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    death_place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="person", cascade="all, delete-orphan", foreign_keys="Event.person_id")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="person", cascade="all, delete-orphan", foreign_keys="Note.person_id")
    media_links: Mapped[List["MediaLink"]] = relationship("MediaLink", back_populates="person", cascade="all, delete-orphan", foreign_keys="MediaLink.person_id")
    attributes: Mapped[List["PersonAttribute"]] = relationship("PersonAttribute", back_populates="person", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_persons_name', 'surname', 'given'),
    )

class Family(Base):
    __tablename__ = 'families'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xref: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    husband_person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('persons.id', ondelete='SET NULL'), nullable=True)
    wife_person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('persons.id', ondelete='SET NULL'), nullable=True)

    # Legacy marriage fields
    marriage_date: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    marriage_place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    husband: Mapped[Optional["Person"]] = relationship("Person", foreign_keys=[husband_person_id])
    wife: Mapped[Optional["Person"]] = relationship("Person", foreign_keys=[wife_person_id])
    events: Mapped[List["Event"]] = relationship("Event", back_populates="family", cascade="all, delete-orphan", foreign_keys="Event.family_id")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="family", cascade="all, delete-orphan", foreign_keys="Note.family_id")
    media_links: Mapped[List["MediaLink"]] = relationship("MediaLink", back_populates="family", cascade="all, delete-orphan", foreign_keys="MediaLink.family_id")

class Event(Base):
    __tablename__ = 'events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('persons.id', ondelete='CASCADE'), nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=True)

    # Raw/original fields from GEDCOM
    date_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    place_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Canonical date (for sorting/queries)
    date_canonical: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Optional place reference
    place_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('places.id', ondelete='SET NULL'), nullable=True)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="events", foreign_keys=[person_id])
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="events", foreign_keys=[family_id])
    place: Mapped[Optional["Place"]] = relationship("Place", back_populates="events", foreign_keys="Event.place_id")

    __table_args__ = (
        Index('idx_events_person', 'person_id'),
        Index('idx_events_family', 'family_id'),
        Index('idx_events_date_canonical', 'date_canonical'),
    )

class Place(Base):
    __tablename__ = 'places'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_canonical: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Optional enrichment fields
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # NEW: optional “authority” attachment (non-breaking)
    authority_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    authority_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="place", foreign_keys="Event.place_id")
    variants: Mapped[List["PlaceVariant"]] = relationship("PlaceVariant", back_populates="place", cascade="all, delete-orphan")

class PlaceVariant(Base):
    __tablename__ = 'place_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey('places.id', ondelete='CASCADE'), nullable=False)
    name_variant: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    place: Mapped["Place"] = relationship("Place", back_populates="variants", foreign_keys=[place_id])


class PersonAttribute(Base):
    __tablename__ = "person_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    person: Mapped["Person"] = relationship("Person", back_populates="attributes")

    __table_args__ = (
        Index("idx_person_attributes_person_key", "person_id", "key"),
    )

class MediaAsset(Base):
    __tablename__ = 'media_assets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumb_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumb_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="unassigned")
    source_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_media_assets_original_filename', 'original_filename'),
    )

    # Relationships
    links: Mapped[List["MediaLink"]] = relationship("MediaLink", back_populates="media_asset", cascade="all, delete-orphan")

class MediaLink(Base):
    __tablename__ = 'media_links'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey('media_assets.id', ondelete='CASCADE'), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('persons.id', ondelete='CASCADE'), nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=True)

    # Support for unassigned media (neither person nor family)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    media_asset: Mapped["MediaAsset"] = relationship("MediaAsset", back_populates="links")
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="media_links", foreign_keys=[person_id])
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="media_links", foreign_keys=[family_id])

    __table_args__ = (
        Index('idx_media_links_person', 'person_id'),
        Index('idx_media_links_family', 'family_id'),
    )

class Note(Base):
    __tablename__ = 'notes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('persons.id', ondelete='CASCADE'), nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="notes", foreign_keys=[person_id])
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="notes", foreign_keys=[family_id])

class DataQualityFlag(Base):
    __tablename__ = 'data_quality_flags'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'person', 'family', 'event', etc.
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    flag_type: Mapped[str] = mapped_column(String(100), nullable=False)  # 'missing_date', 'incomplete_name', etc.
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # 'info', 'warning', 'error'
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_data_quality_entity', 'entity_type', 'entity_id'),
        Index('idx_data_quality_flag_type', 'flag_type'),
    )

class DataQualityIssue(Base):
    __tablename__ = "dq_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning", index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list for flexibility
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    impact_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    explanation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_dq_issue_type_status", "issue_type", "status"),
        Index("idx_dq_issue_detected", "detected_at"),
    )

class DataQualityActionLog(Base):
    __tablename__ = "dq_action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    undo_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    applied_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

class DateNormalization(Base):
    __tablename__ = "date_normalizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'person' | 'event' | 'family'
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    raw_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)  # yyyy or yyyy-MM or yyyy-MM-dd
    precision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # year|month|day|range
    qualifier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # about/before/after/between
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_date_norm_entity", "entity_type", "entity_id"),
        Index("idx_date_norm_confidence", "confidence"),
    )
