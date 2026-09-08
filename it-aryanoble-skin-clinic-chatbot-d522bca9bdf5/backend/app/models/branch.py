import uuid
from typing import Optional
from sqlalchemy import String, Numeric, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, TimestampMixin, SoftDeleteMixin

class Branch(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="chk_lat"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="chk_long"),
    )

class UserBranch(Base, TimestampMixin):
    __tablename__ = "user_branch"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True)
