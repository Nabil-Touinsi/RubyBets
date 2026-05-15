# Role du fichier :
# Ce fichier expose les routes de santé de l API RubyBets.
# Il permet de vérifier que le backend fonctionne et que la base PostgreSQL répond.

from fastapi import APIRouter

from app.services.database_service import check_database_connection

router = APIRouter(tags=["Health"])


# Vérifie que l API RubyBets répond correctement.
@router.get("/")
def read_root():
    return {"message": "RubyBets API is running"}


# Vérifie l état général du backend sans changer le contrat existant.
@router.get("/health")
def health_check():
    return {"status": "ok"}


# Vérifie spécifiquement la connexion à la base PostgreSQL RubyBets.
@router.get("/health/database")
def database_health_check():
    database_is_available = check_database_connection()

    return {
        "service": "database",
        "status": "ok" if database_is_available else "unavailable",
        "database": "rubybets_db",
    }


# Schema de communication :
# frontend / navigateur / tests
#     ↓
# backend/app/api/health.py
#     ↓
# backend/app/services/database_service.py
#     ↓
# PostgreSQL rubybets_db