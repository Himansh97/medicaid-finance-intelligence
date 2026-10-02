"""Runtime migrations take credentials only from DATABASE_URL."""
import os
from alembic import context
from sqlalchemy import create_engine

url = os.environ['DATABASE_URL']
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
