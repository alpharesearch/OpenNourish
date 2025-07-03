from logging.config import fileConfig

from sqlalchemy import engine_from_config
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
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# We need to import the Flask app and db object to get the metadata
try:
    from app import create_app
    from models import db
    app = create_app()
    app.app_context().push()
    # Define target_metadata for each bind
    target_db_metadata = {
        None: db.metadata,  # Default bind for user_data.db
        'usda': db.metadata  # usda bind for usda_data.db
    }
except Exception as e:
    print(f"Error importing app or db: {e}")
    target_db_metadata = {}


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
    # handle multiple databases
    # from https://alembic.sqlalchemy.org/en/latest/cookbook.html#multiple-databases
    for name, metadata in target_db_metadata.items():
        print(f"Running migrations for bind: {name if name else 'default'}")
        if name == 'usda':
            continue
        if name:
            url = config.get_main_option(f"sqlalchemy.url.{name}")
        else:
            url = config.get_main_option("sqlalchemy.url")

        connectable = engine_from_config(
            {'sqlalchemy.url': url},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=metadata,
                # Set the current_app.config['SQLALCHEMY_BINDS'] for the current bind
                # This is a bit of a hack, but necessary for Flask-SQLAlchemy to work with Alembic
                # in a multi-bind scenario during autogenerate
                # context_opts={'bind_name': name}
            )

            with context.begin_transaction():
                context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
