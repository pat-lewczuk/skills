import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from docproc.settings import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


class Partner(Base):
    __tablename__ = "partners"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    api_key_sha256: Mapped[str] = mapped_column(String(64), unique=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id: Mapped[str] = mapped_column(ForeignKey("partners.id"))
    filename: Mapped[str]
    storage_path: Mapped[str]
    webhook_url: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Result(Base):
    __tablename__ = "results"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    doc_type: Mapped[str]
    fields: Mapped[dict] = mapped_column(JSON)
