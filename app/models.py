import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    clicks: Mapped[list["Click"]] = relationship(
        "Click", back_populates="link", cascade="all, delete-orphan"
    )
    daily_counts: Mapped[list["DailyClickCount"]] = relationship(
        "DailyClickCount", back_populates="link", cascade="all, delete-orphan"
    )


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("links.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    clicked_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    referrer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    link: Mapped["Link"] = relationship("Link", back_populates="clicks")

    __table_args__ = (Index("ix_clicks_link_id_clicked_at", "link_id", "clicked_at"),)


class DailyClickCount(Base):
    __tablename__ = "daily_click_counts"

    link_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("links.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    link: Mapped["Link"] = relationship("Link", back_populates="daily_counts")
