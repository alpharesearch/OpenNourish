from logging.config import fileConfig

from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool

from alembic import context

# Import your Flask app and db object
import os
import sys
from flask import current_app

# Add your project directory to the path
sys.path.append(os.getcwd())

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# We need to import the Flask app and db object to get the metadata
from opennourish import create_app
from models import db

# Create the Flask app instance
app = create_app()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# We explicitly set the sqlalchemy.url here from the Flask app config
# to ensure it's always correctly picked up by Alembic.
config.set_main_option("sqlalchemy.url", app.config['SQLALCHEMY_DATABASE_URI'])

# Define target_metadata for each bind
# This should map bind keys to their respective MetaData objects
# For Flask-SQLAlchemy, db.metadata holds the default bind's metadata
# For other binds, you might need to access them via db.metadata.binds or define them explicitly
target_db_metadata = {
    None: db.metadata  # Default bind for user_data.db
}


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # This function is not typically used with multiple binds in this manner
    # For simplicity, we'll just use the default URL
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_db_metadata.get(None), # Use default metadata
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Only run migrations for the default bind (user_data.db)
    url = app.config['SQLALCHEMY_DATABASE_URI']
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_db_metadata.get(None),
        )

        with context.begin_transaction():
            context.run_migrations()
