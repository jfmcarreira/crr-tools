from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    from app.config import Settings
    from app.database import create_database_engine
    engine = create_database_engine(Settings().database_path)
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()
