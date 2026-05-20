"""Shared pytest fixtures.

db_session: yields a real SQLAlchemy Session that rolls back after each test,
keeping the Supabase DB clean.  Tests that need a live DB import this fixture.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


@pytest.fixture()
def db_session():
    """Transaction-scoped session: every change is rolled back after the test."""
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()
