from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    database_path: Path
    openai_api_key: str | None
    openai_model: str
    max_sql_retries: int

    @classmethod
    def from_env(cls) -> 'Settings':
        root = Path(__file__).resolve().parents[1]
        return cls(root / os.getenv('DATABASE_PATH', 'anexo_desafio_1.db'), os.getenv('OPENAI_API_KEY'),
                   os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), int(os.getenv('MAX_SQL_RETRIES', '2')))
