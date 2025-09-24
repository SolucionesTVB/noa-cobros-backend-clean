from __future__ import annotations
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Config de Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importa metadata desde la app
# Nota: app.py debe poder importarse sin romper
from app import db, url as APP_DB_URL  # 'url' ya normalizado en app.py
target_metadata = db.metadata

# Permitir que alembic.ini sea sobrescrito por código (config.set_main_option)
if APP_DB_URL:
    config.set_main_option("sqlalchemy.url", APP_DB_URL)

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    cfg = config.get_section(config.config_ini_section)
    connectable = engine_from_config(
        cfg, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
