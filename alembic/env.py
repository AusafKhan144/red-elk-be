from logging.config import fileConfig
from sqlalchemy import create_engine
from alembic import context
from app.core.database import Base, ASYNC_DATABASE_URL
from app.models import user  # import models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=ASYNC_DATABASE_URL.replace("+asyncpg", ""),  # sync URL for alembic
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(ASYNC_DATABASE_URL.replace("+asyncpg", ""))
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
