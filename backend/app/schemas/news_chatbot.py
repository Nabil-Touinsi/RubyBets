# Rôle du fichier :
# Ce fichier définit les contrats Pydantic du chatbot d'actualités RubyBets.
# Il valide les demandes de synthèse ou de question et structure les sources citées.

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, HttpUrl, model_validator


class NewsChatbotMode(StrEnum):
    SUMMARY = "summary"
    QUESTION = "question"


class NewsChatbotRequest(BaseModel):
    mode: NewsChatbotMode = NewsChatbotMode.SUMMARY
    question: str | None = Field(default=None, min_length=3, max_length=500)

    # Cette validation impose une question uniquement dans le mode conversationnel.
    @model_validator(mode="after")
    def validate_question_for_mode(self) -> Self:
        clean_question = " ".join(str(self.question or "").split()) or None

        if self.mode is NewsChatbotMode.QUESTION and not clean_question:
            raise ValueError("Une question est obligatoire en mode question.")

        self.question = clean_question
        return self


class NewsChatbotSource(BaseModel):
    article_id: str
    title: str
    url: HttpUrl
    source_name: str | None = None
    published_at: datetime | None = None
    content_status: str


class NewsChatbotResponse(BaseModel):
    status: str
    match_id: int
    mode: NewsChatbotMode
    answer: str
    sources: list[NewsChatbotSource]
    source_articles_count: int
    full_content_articles_count: int
    partial_content_articles_count: int
    unavailable_articles_count: int
    analyzed_articles_count: int
    analyzed_chunks_count: int
    insufficient_data: bool
    cached: bool = False
    generated_at: datetime
    model: str
    match_source: str | None = None
    responsible_note: str
    limitations: list[str] = Field(default_factory=list)


# Schéma de communication :
# frontend futur -> POST /api/matches/{match_id}/news-chat
#     ↓
# NewsChatbotRequest
#     ↓
# match_news_chatbot_service.py
#     ↓
# NewsChatbotResponse + NewsChatbotSource
