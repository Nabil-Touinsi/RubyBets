# Rôle du fichier :
# Ce fichier centralise la configuration de l'API RubyBets :
# sources football, chatbot Groq, services externes et connexion database.

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "RubyBets API"
    app_version: str = "0.1.0"

    # Football-Data.org - source principale du MVP
    football_data_key: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"

    # API-Football / API-Sports - source secondaire pour enrichir l'historique des équipes
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"

    # RapidAPI / FlashScore - source tertiaire d'enrichissement
    rapidapi_key: str = ""
    rapidapi_flashscore_host: str = "flashscore4.p.rapidapi.com"
    rapidapi_flashscore_base_url: str = "https://flashscore4.p.rapidapi.com/api/flashscore/v2"

    # Groq - moteur gratuit retenu pour le chatbot d'actualités RubyBets
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_api_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 45.0
    groq_max_completion_tokens: int = 1400
    groq_max_retries: int = 3
    groq_retry_max_wait_seconds: float = 65.0
    groq_tokens_per_minute: int = 8000
    groq_rate_limit_safety_ratio: float = 0.82

    # Chatbot d'actualités - limites de collecte, de cache et de découpage
    news_chatbot_max_articles: int = 12
    news_chatbot_cache_ttl_minutes: int = 30
    news_chatbot_article_summary_cache_ttl_minutes: int = 1440
    news_chatbot_article_timeout_seconds: float = 10.0
    news_chatbot_max_article_characters: int = 120000
    news_chatbot_article_chunk_characters: int = 6200
    news_chatbot_chunk_summary_tokens: int = 420

    # Hugging Face - ancien système contextuel conservé désactivé pendant la transition
    huggingface_enabled: bool = False
    huggingface_api_token: str = ""
    huggingface_model_name: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
    huggingface_api_base_url: str = "https://router.huggingface.co/hf-inference/models"

    # PostgreSQL - base locale RubyBets
    database_url: str = ""

    # Retourne les headers nécessaires pour appeler Football-Data.org.
    def get_football_data_headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": self.football_data_key,
            "Accept": "application/json",
        }

    # Retourne les headers nécessaires pour appeler API-Football / API-Sports.
    def get_api_football_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "x-apisports-key": self.api_football_key,
        }

    # Retourne les headers nécessaires pour appeler RapidAPI / FlashScore.
    def get_rapidapi_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-rapidapi-host": self.rapidapi_flashscore_host,
            "x-rapidapi-key": self.rapidapi_key,
        }

    # Retourne les headers nécessaires pour appeler le chatbot Groq.
    def get_groq_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.groq_api_key}",
        }

    # Retourne l'URL de complétion conversationnelle du chatbot Groq.
    def get_groq_chat_completions_url(self) -> str:
        return f"{self.groq_api_base_url.rstrip('/')}/chat/completions"

    # Retourne les headers nécessaires pour appeler Hugging Face.
    def get_huggingface_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.huggingface_api_token}",
        }

    # Retourne l'URL complète du modèle Hugging Face configuré.
    def get_huggingface_model_url(self) -> str:
        return f"{self.huggingface_api_base_url}/{self.huggingface_model_name}"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Schéma de communication :
# backend/.env
#     ↓
# backend/app/core/config.py
#     ├── clients football et FlashScore
#     ├── groq_chatbot_client.py
#     ├── news_article_content_service.py
#     └── services database / Hugging Face transitoire
#     ↓
# routes FastAPI
