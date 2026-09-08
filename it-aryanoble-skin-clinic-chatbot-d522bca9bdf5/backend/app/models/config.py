import uuid
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, TimestampMixin

class AppConfig(Base, TimestampMixin):
    __tablename__ = "app_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
