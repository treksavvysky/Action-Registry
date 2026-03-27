from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Action(Base):
    __tablename__ = "actions"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    versions: Mapped[list["ActionVersion"]] = relationship(
        back_populates="action",
        cascade="all, delete-orphan",
    )


class ActionVersion(Base):
    __tablename__ = "action_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_action_versions_name_version"),
        Index("ix_action_versions_name", "name"),
        Index("ix_action_versions_version", "version"),
        Index("ix_action_versions_sig_kid", "sig_kid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("actions.name", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    hash: Mapped[str] = mapped_column(String(80), nullable=False)
    sig_alg: Mapped[str] = mapped_column(String(32), nullable=False)
    sig_kid: Mapped[str] = mapped_column(String(255), nullable=False)
    sig_b64: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    action: Mapped[Action] = relationship(back_populates="versions")
