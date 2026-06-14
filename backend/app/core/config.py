# Role du fichier :
# Ce fichier centralise la configuration de l API RubyBets :
# sources football, services externes et connexion database.

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "RubyBets API"
    app_version: str = "0.1.0"

    # Football-Data.org - source principale du MVP
    football_data_key: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"

    # API-Football / API-Sports - source secondaire pour enrichir l historique des équipes
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"

    # RapidAPI / FlashScore - source tertiaire d enrichissement
    rapidapi_key: str = ""
    rapidapi_flashscore_host: str = "flashscore4.p.rapidapi.com"
    rapidapi_flashscore_base_url: str = "https://flashscore4.p.rapidapi.com/api/flashscore/v2"

    # Groq - moteur IA d analyse
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # PostgreSQL - base locale RubyBets
    database_url: str = ""

    # Retourne les headers necessaires pour appeler Football-Data.org.
    def get_football_data_headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": self.football_data_key,
            "Accept": "application/json",
        }

    # Retourne les headers necessaires pour appeler API-Football / API-Sports.
    def get_api_football_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "x-apisports-key": self.api_football_key,
        }

    # Retourne les headers necessaires pour appeler RapidAPI / FlashScore.
    def get_rapidapi_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-rapidapi-host": self.rapidapi_flashscore_host,
            "x-rapidapi-key": self.rapidapi_key,
        }

    # Retourne les headers necessaires pour appeler Groq.
    def get_groq_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.groq_api_key}",
        }

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Schema de communication :
# backend/.env
#     ↓
# backend/app/core/config.py
#     ↓
# services backend :
# football_data_client.py
# api_football_client.py
# rapidapi_flashscore_client.py
#     ↓
# FastAPI routes