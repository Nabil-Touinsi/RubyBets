# Role du fichier :
# Ce service centralise la connexion entre le backend FastAPI RubyBets
# et la base PostgreSQL locale du projet.

import psycopg
from psycopg import Connection

from app.core.config import settings


# Ouvre une connexion PostgreSQL a partir de DATABASE_URL.
def get_database_connection() -> Connection:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is missing in backend/.env")

    return psycopg.connect(settings.database_url)


# Verifie rapidement que la base PostgreSQL repond correctement.
def check_database_connection() -> bool:
    try:
        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                result = cursor.fetchone()
                return result == (1,)
    except Exception:
        return False


# Schema de communication :
# backend/.env
#     ↓
# backend/app/core/config.py
#     ↓
# backend/app/services/database_service.py
#     ↓
# PostgreSQL rubybets_db