# Ce fichier gère un cache JSON simple pour stocker temporairement les données récupérées par RubyBets.

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import json


CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"


def ensure_cache_dir_exists() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(cache_name: str) -> Path:
    ensure_cache_dir_exists()
    safe_name = cache_name.replace("/", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe_name}.json"


def save_cache(cache_name: str, data: dict[str, Any]) -> dict[str, Any]:
    cache_payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "source": "football-data.org",
        "data": data,
    }

    cache_path = get_cache_path(cache_name)
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return cache_payload


def load_cache(cache_name: str) -> dict[str, Any] | None:
    cache_path = get_cache_path(cache_name)

    if not cache_path.exists():
        return None

    return json.loads(cache_path.read_text(encoding="utf-8"))


def is_cache_fresh(cache_payload: dict[str, Any], ttl_minutes: int = 60) -> bool:
    updated_at = cache_payload.get("updated_at")

    if not updated_at:
        return False

    updated_at_datetime = datetime.fromisoformat(updated_at)
    expiration_datetime = updated_at_datetime + timedelta(minutes=ttl_minutes)

    return datetime.now(UTC) <= expiration_datetime