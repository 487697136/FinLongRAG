"""PostgreSQL engine/session construction."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith("postgresql://") or database_url.startswith("postgresql+")


def to_async_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    raise ValueError("FinLongRAG requires a PostgreSQL database URL.")


def to_sync_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql+asyncpg://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    raise ValueError("FinLongRAG requires a PostgreSQL database URL.")


@lru_cache(maxsize=8)
def get_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(to_async_url(database_url), pool_pre_ping=True)


def get_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(database_url), expire_on_commit=False)


@lru_cache(maxsize=8)
def get_sync_engine(database_url: str) -> Engine:
    return create_engine(to_sync_url(database_url), pool_pre_ping=True)


def get_sync_sessionmaker(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(database_url), expire_on_commit=False)
