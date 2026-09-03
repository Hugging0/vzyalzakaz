from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import JSON, Column, DateTime, Float, Index, String, Text, inspect, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    # 0001 historically created tables from live ORM metadata instead of a frozen
    # schema. Keep fresh installs replayable without editing applied revision 0008:
    # bootstrap its legacy columns only while the database has no Alembic state.
    inspector = inspect(connection)
    if "alembic_version" not in inspector.get_table_names():
        _add_bootstrap_legacy_opportunity_columns()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def _add_bootstrap_legacy_opportunity_columns() -> None:
    table = Base.metadata.tables["opportunities"]
    additions = (
        Column("prefilter_score", Float),
        Column("prefilter_reasons", JSON),
        Column("fit_score", Float),
        Column("money_score", Float),
        Column("win_score", Float),
        Column("freshness_score", Float),
        Column("final_score", Float, index=True),
        Column("estimated_effort_hours", Float),
        Column("estimated_effective_hourly_rate", Float),
        Column("analysis", JSON),
        Column("proposal", Text),
        Column("portfolio_item", String(100)),
        Column("notified_at", DateTime(timezone=True)),
        Column("approved_at", DateTime(timezone=True)),
        Column("sent_at", DateTime(timezone=True)),
    )
    for column in additions:
        if column.name not in table.c:
            table.append_column(column)
    if "ix_opportunity_status_score" not in {index.name for index in table.indexes}:
        Index("ix_opportunity_status_score", table.c.status, table.c.final_score)


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Alembic's synchronous context manages migration transactions, but the
    # outer AsyncConnection still has to commit them.  Without ``begin()`` the
    # DDL may survive on SQLite while ``alembic_version`` is rolled back, which
    # makes the next invocation replay the whole history.
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
