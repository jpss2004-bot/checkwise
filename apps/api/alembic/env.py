from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from app.core.config import settings
from app.db.base import Base
from app.models import entities  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.alembic_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _ensure_wide_version_table(connection) -> None:
    # Alembic creates alembic_version.version_num as VARCHAR(32), but revision id
    # 0025_user_notification_preferences is 34 chars, so fresh databases fail at
    # 0024->0025 with StringDataRightTruncation. Pre-create (or widen) the table
    # before migrations run. Committed separately so a failed migration run does
    # not roll this back.
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
    )
    connection.commit()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.alembic_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Each migration gets its own transaction so a mid-chain failure
        # rolls back only the failing revision (see run_migrations_online).
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_wide_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Wrap EACH migration in its own transaction instead of the whole
            # pending set in one. ~10 migrations (0034/0035/0046/0048/0049/
            # 0050/0051/0053/0055) enter an op.get_context().autocommit_block()
            # for CONCURRENTLY index builds; entering that block commits all
            # *preceding* pending revisions in the run. With one big
            # transaction, a later failure left the earlier DDL committed while
            # alembic_version may not have advanced — an inconsistent state
            # needing a manual `alembic stamp`. Per-migration scoping bounds the
            # autocommit-block commit to a single revision, so a failure rolls
            # back only that file. This is Alembic's recommended pairing with
            # autocommit_block and does not change how those blocks behave.
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
