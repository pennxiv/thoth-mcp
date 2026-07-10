"""Pydantic models for datasource configuration."""

import os
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
    SettingsConfigDict,
)
from thoth_mcp.utils.logger import logger


class MySQLDatasourceConfig(BaseModel):
    """Configuration for a MySQL datasource."""

    host: str = Field(..., description="MySQL server hostname")
    port: int = Field(default=3306, ge=1, le=65535, description="MySQL server port")
    user: str = Field(..., description="Database user")
    password: str = Field(..., repr=False, description="Database password")
    database: str = Field(..., description="Database name")

    # Optional connection pool settings
    min_pool_size: int = Field(default=1, ge=1, description="Minimum pool connections")
    max_pool_size: int = Field(default=10, ge=1, description="Maximum pool connections")


class RedisDatasourceConfig(BaseModel):
    """Configuration for a Redis instance."""

    host: str = Field(..., description="Redis server hostname")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis server port")
    password: str | None = Field(default=None, repr=False, description="Redis password")
    db: int = Field(default=0, ge=0, description="Redis database number")

    # Optional connection pool settings
    min_pool_size: int = Field(default=1, ge=1, description="Minimum pool connections")
    max_pool_size: int = Field(default=10, ge=1, description="Maximum pool connections")


class PostgreSQLDatasourceConfig(BaseModel):
    """Configuration for a PostgreSQL datasource."""

    host: str = Field(..., description="PostgreSQL server hostname")
    port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL server port")
    user: str = Field(..., description="Database user")
    password: str = Field(..., repr=False, description="Database password")
    database: str = Field(..., description="Database name")
    schema_: str = Field(default="public", alias="schema", description="Database schema")

    # Optional connection pool settings
    min_pool_size: int = Field(default=1, ge=1, description="Minimum pool connections")
    max_pool_size: int = Field(default=10, ge=1, description="Maximum pool connections")

    model_config = {"populate_by_name": True}


class DatasourcesConfig(BaseSettings):
    """Root configuration for all datasources.

    Loads configuration from YAML file with environment variable overrides.
    Priority: init > env > YAML > secrets.

    Environment variable pattern: THOTH_{TYPE}__{NAME}__{FIELD}
    Example: THOTH_MYSQL__PROD_DB__PASSWORD
    """

    model_config = SettingsConfigDict(
        yaml_file=os.environ.get(
            "THOTH_DATASOURCES_FILE",
            str(Path(__file__).parent.parent.parent / "config" / "datasources.yaml"),
        ),
        yaml_file_encoding="utf-8",
        env_prefix="THOTH_",  # D-04
        env_nested_delimiter="__",  # D-04: Enables THOTH_MYSQL__PROD_DB__PASSWORD
        extra="forbid",  # Reject unknown fields
    )

    mysql: dict[str, MySQLDatasourceConfig] = Field(default_factory=dict)
    redis: dict[str, RedisDatasourceConfig] = Field(default_factory=dict)
    postgres: dict[str, PostgreSQLDatasourceConfig] = Field(default_factory=dict)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources priority: init > env > YAML > secrets."""
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def load_config() -> DatasourcesConfig:
    """Load and validate configuration. Exits on validation failure.

    Returns:
        DatasourcesConfig: Validated configuration object.

    Raises:
        SystemExit: On validation failure (exit code 1).

    Note:
        Error messages go to stderr (not stdout) per D-11.
        Password values are masked in error messages per T-1-02 mitigation.
    """
    # Check if config file exists before attempting to load
    yaml_path = Path(os.environ.get(
        "THOTH_DATASOURCES_FILE",
        str(Path(__file__).parent.parent.parent / "config" / "datasources.yaml"),
    ))
    if not yaml_path.exists():
        logger.error(f"Configuration file not found: {yaml_path}")
        raise SystemExit(1) from None

    try:
        config = DatasourcesConfig()
        logger.info(f"Loaded {len(config.mysql)} MySQL, {len(config.postgres)} PostgreSQL, {len(config.redis)} Redis datasources")
        return config
    except ValidationError as e:
        # Extract field-specific errors
        errors = e.errors()
        error_messages = []
        for error in errors:
            loc = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            # Mask sensitive values in error messages (T-1-02 mitigation)
            if "password" in loc.lower():
                error_messages.append(f"  • {loc}: <secret value invalid>")
            else:
                error_messages.append(f"  • {loc}: {msg}")

        # Log to stderr (not stdout!) per D-11
        logger.error("Configuration validation failed:")
        for msg in error_messages:
            logger.error(msg)

        raise SystemExit(1) from None
