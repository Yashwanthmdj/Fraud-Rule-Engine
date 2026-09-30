"""Persistence layer: transactions, fraud flags, reviewer decisions, alerts and settings."""
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, create_engine, event, inspect, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

from . import config

engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    user_name: Mapped[str] = mapped_column(String(128), default="")
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    merchant: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(64), default="retail")
    city: Mapped[str] = mapped_column(String(64), default="")
    country: Mapped[str] = mapped_column(String(64), default="")
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    channel: Mapped[str] = mapped_column(String(16), default="card_present")
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    # clean | flagged | reviewed | cleared | fraud
    status: Mapped[str] = mapped_column(String(16), default="clean", index=True)
    source: Mapped[str] = mapped_column(String(16), default="api")
    scenario: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    # approve | step_up | hold | decline - what the payment switch was told, in real time
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)   # account standing when scored
    stages: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)      # per-stage pipeline timings (ms)

    flags: Mapped[List["Flag"]] = relationship(back_populates="txn", cascade="all, delete-orphan",
                                               order_by="desc(Flag.contribution)")
    reviews: Mapped[List["Review"]] = relationship(back_populates="txn", cascade="all, delete-orphan",
                                                   order_by="Review.ts")

    __table_args__ = (Index("ix_user_ts", "user_id", "ts"),)


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_name: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float)          # raw rule confidence 0..1
    weight: Mapped[float] = mapped_column(Float)
    contribution: Mapped[float] = mapped_column(Float)   # weighted, 0..1
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    txn: Mapped[Transaction] = relationship(back_populates="flags")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))  # reviewed | cleared | fraud | reopened
    from_status: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(64), default="analyst")
    note: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    txn: Mapped[Transaction] = relationship(back_populates="reviews")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(String(32), index=True)
    channel: Mapped[str] = mapped_column(String(16))   # ses | sns
    mode: Mapped[str] = mapped_column(String(16))      # live | dry-run
    status: Mapped[str] = mapped_column(String(16))    # sent | failed | suppressed | simulated
    target: Mapped[str] = mapped_column(String(256), default="")
    subject: Mapped[str] = mapped_column(String(256), default="")
    message_id: Mapped[str] = mapped_column(String(128), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Customer(Base):
    """Known cardholder contact details (only the demo customer is registered)."""
    __tablename__ = "customers"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(256), default="")
    bank: Mapped[str] = mapped_column(String(64), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Tiny forward-only migration so an existing aegis.db picks up new nullable columns."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} "
                                      f"{col.type.compile(engine.dialect)}"))


def get_setting(session, key: str, default=None):
    row = session.get(Setting, key)
    return json.loads(row.value) if row else default


def put_setting(session, key: str, value) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = json.dumps(value)
    else:
        session.add(Setting(key=key, value=json.dumps(value)))