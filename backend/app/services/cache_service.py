# Ce fichier gère le cache JSON local utilisé par RubyBets pour limiter les appels API externes.
# Il trace la source, la date de mise à jour et la fraîcheur des données utilisées par le backend.

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import json

from app.services.football_data_client import get_football_data


CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
DEFAULT_CACHE_SOURCE = "football-data.org"


# Cette fonction crée le dossier de cache local s'il n'existe pas encore.
def ensure_cache_dir_exists() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Cette fonction transforme un nom de cache en chemin de fichier JSON sécurisé.
def get_cache_path(cache_name: str) -> Path:
    ensure_cache_dir_exists()
    safe_name = (
        cache_name.replace("/", "_")
        .replace(" ", "_")
        .replace(":", "_")
        .replace("?", "_")
        .replace("&", "_")
        .replace("=", "_")
    )
    return CACHE_DIR / f"{safe_name}.json"


# Cette fonction construit un nom de cache stable à partir d'un préfixe et de paramètres métier.
def build_cache_name(prefix: str, *parts: Any) -> str:
    cleaned_parts = [
        str(part).lower().replace(" ", "_")
        for part in parts
        if part is not None and part != ""
    ]

    if not cleaned_parts:
        return prefix

    return "_".join([prefix, *cleaned_parts])


# Cette fonction sauvegarde des données API dans un fichier JSON local avec des métadonnées de fraîcheur.
def save_cache(
    cache_name: str,
    data: dict[str, Any],
    source: str = DEFAULT_CACHE_SOURCE,
) -> dict[str, Any]:
    cache_payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "data": data,
    }

    cache_path = get_cache_path(cache_name)
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return cache_payload


# Cette fonction relit un cache JSON existant et retourne None si le cache est absent ou illisible.
def load_cache(cache_name: str) -> dict[str, Any] | None:
    cache_path = get_cache_path(cache_name)

    if not cache_path.exists():
        return None

    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# Cette fonction vérifie si un cache est encore utilisable selon sa durée de validité.
def is_cache_fresh(cache_payload: dict[str, Any], ttl_minutes: int = 60) -> bool:
    updated_at = cache_payload.get("updated_at")

    if not updated_at:
        return False

    try:
        updated_at_datetime = datetime.fromisoformat(updated_at)
    except ValueError:
        return False

    expiration_datetime = updated_at_datetime + timedelta(minutes=ttl_minutes)

    return datetime.now(UTC) <= expiration_datetime


# Cette fonction formate les informations de fraîcheur renvoyées dans les réponses API.
def build_data_freshness(
    cache_payload: dict[str, Any],
    from_cache: bool,
    ttl_minutes: int,
) -> dict[str, Any]:
    return {
        "source": cache_payload.get("source", DEFAULT_CACHE_SOURCE),
        "from_cache": from_cache,
        "updated_at": cache_payload.get("updated_at"),
        "ttl_minutes": ttl_minutes,
    }


# Cette fonction récupère des données depuis le cache si possible, sinon depuis Football-Data.
async def get_cached_football_data(
    cache_name: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    ttl_minutes: int = 60,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cached_payload = load_cache(cache_name)

    if cached_payload and is_cache_fresh(cached_payload, ttl_minutes=ttl_minutes):
        return cached_payload.get("data", {}), build_data_freshness(
            cache_payload=cached_payload,
            from_cache=True,
            ttl_minutes=ttl_minutes,
        )

    data = await get_football_data(endpoint, params=params)
    saved_payload = save_cache(cache_name, data)

    return saved_payload["data"], build_data_freshness(
        cache_payload=saved_payload,
        from_cache=False,
        ttl_minutes=ttl_minutes,
    )


# Schéma de communication du fichier :
# cache_service.py
# ├── appelle football_data_client.py si le cache est absent ou expiré
# ├── écrit et lit les fichiers JSON dans app/data/cache/
# ├── alimente competitions.py, matches.py, match_service.py et recommendations.py
# └── renvoie les métadonnées data_freshness aux routes API
