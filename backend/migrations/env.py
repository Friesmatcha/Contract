from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.config import get_settings
from backend.app.modules.contracts.models import (
    Contract,
    ContractAccessGrant,
    ContractFile,
    FileObject,
)
from backend.app.modules.documents.models import (
    DocumentBlock,
    DocumentPage,
    DocumentVersion,
    SourceSpan,
)
from backend.app.modules.identity.models import (
    AuthOneTimeToken,
    AuthRateLimit,
    AuthSession,
    Organization,
    OrganizationMembership,
    PlatformModelConfiguration,
    SupportAccessGrant,
    User,
)
from backend.app.modules.risks.rules.models import RiskRule, RiskRuleBundle, RiskRuleBundleVersion
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import Base
from backend.app.shared.idempotency import IdempotencyRecord

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.get_secret_value())
target_metadata = Base.metadata
_registered_models = (
    Organization,
    OrganizationMembership,
    PlatformModelConfiguration,
    SupportAccessGrant,
    User,
    AuthSession,
    AuthOneTimeToken,
    AuthRateLimit,
    AuditLog,
    IdempotencyRecord,
    Contract,
    ContractAccessGrant,
    FileObject,
    ContractFile,
    DocumentVersion,
    DocumentPage,
    DocumentBlock,
    SourceSpan,
    RiskRuleBundle,
    RiskRuleBundleVersion,
    RiskRule,
)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
