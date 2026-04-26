from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "RubyBets API"
    app_version: str = "0.1.0"

    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"

    rapidapi_key: str = ""
    rapidapi_flashscore_host: str = "flashscore4.p.rapidapi.com"
    rapidapi_flashscore_base_url: str = "https://flashscore4.p.rapidapi.com/api/flashscore/v2"

    def get_api_football_headers(self) -> dict[str, str]:
        return {
            "x-apisports-key": self.api_football_key,
        }

    def get_rapidapi_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-rapidapi-host": self.rapidapi_flashscore_host,
            "x-rapidapi-key": self.rapidapi_key,
        }

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()