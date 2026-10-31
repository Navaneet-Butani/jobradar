"""Settings are built at import time; give them harmless values so the pure
matching/filter code can be imported without a database or .env file."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-for-anything-real")
