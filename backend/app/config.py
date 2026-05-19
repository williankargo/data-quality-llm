"""Application configuration.

This module is the single source of truth for all environment variables.
No other module may read os.environ directly; use `settings` instead.

Note on CORS_ORIGINS: pydantic-settings v2 JSON-parses env values for
complex fields (list, dict) at the source layer, before field_validators
run.  A plain comma-separated URL string therefore fails JSON parsing.
The field is kept as `str` internally; callers use the `cors_origins_list`
property which returns the parsed `list[str]`.  This is the spec-intended
"parsed from comma-separated string" behaviour.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # LLM
    LLM_PROVIDER: str = "anthropic"
    LLM_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_API_KEY: str

    # CORS — raw comma-separated string; use cors_origins_list for list[str].
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS parsed into a list of stripped origin strings."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# Module-level singleton — import this everywhere instead of instantiating Settings directly.
settings = Settings()
