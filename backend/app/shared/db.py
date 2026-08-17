from datetime import datetime
from typing import Any, Self
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")


class UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._transaction: SessionTransaction | None = None

    def __enter__(self) -> Self:
        if self.session.in_transaction():
            raise RuntimeError("UnitOfWork requires a session without an active transaction")
        self._transaction = self.session.begin()
        return self

    def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        self._transaction.commit()
        self._transaction = None

    def rollback(self) -> None:
        if self._transaction is not None:
            self._transaction.rollback()
            self._transaction = None

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.rollback()
