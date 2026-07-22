# Rôle du fichier :
# Ce client appelle l'API Groq pour le chatbot RubyBets avec le modèle GPT-OSS 120B.
# Il protège la clé, limite le débit gratuit, respecte Retry-After et renvoie un JSON contrôlé.

from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
from threading import Lock
from time import monotonic, perf_counter
from typing import Any, Awaitable, Callable

import httpx

from app.core.config import settings


LOGGER = logging.getLogger(__name__)
_GROQ_RATE_LIMIT_WINDOW_SECONDS = 60.0
_GROQ_LONG_STRUCTURED_PROMPT_CHARACTERS = 5000
_GROQ_LONG_STRUCTURED_OUTPUT_TOKENS = 1024
_GROQ_JSON_RETRY_OUTPUT_TOKENS = 2048
_GROQ_STRUCTURED_RETRY_CODES = {"json_validate_failed", "tool_use_failed"}
_GROQ_JSON_OBJECT_RESPONSE_FORMAT = {"type": "json_object"}
_GROQ_TOKEN_EVENTS: deque[tuple[float, int]] = deque()
_GROQ_TOKEN_EVENTS_LOCK = Lock()


class GroqChatbotError(RuntimeError):
    # Cette initialisation conserve un code technique sûr et un statut HTTP exploitable par la route.
    def __init__(self, code: str, public_message: str, status_code: int) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.status_code = status_code


# Cette fonction efface l'état local du limiteur pour les tests ou une réinitialisation explicite.
def clear_groq_rate_limit_state() -> None:
    with _GROQ_TOKEN_EVENTS_LOCK:
        _GROQ_TOKEN_EVENTS.clear()


# Cette fonction retire d'éventuelles balises Markdown avant de décoder le JSON du modèle.
def parse_groq_json_content(content: str | None) -> dict[str, Any]:
    clean_content = str(content or "").strip()

    if clean_content.startswith("```"):
        clean_content = clean_content.removeprefix("```json").removeprefix("```")
        clean_content = clean_content.removesuffix("```").strip()

    try:
        parsed_content = json.loads(clean_content)
    except json.JSONDecodeError as error:
        raise GroqChatbotError(
            code="GROQ_INVALID_RESPONSE",
            public_message="Le chatbot a retourné une réponse non exploitable.",
            status_code=502,
        ) from error

    if not isinstance(parsed_content, dict):
        raise GroqChatbotError(
            code="GROQ_INVALID_RESPONSE",
            public_message="Le chatbot a retourné un format inattendu.",
            status_code=502,
        )

    return parsed_content


# Cette fonction estime prudemment les tokens d'une requête à partir des caractères et de la sortie réservée.
def estimate_groq_request_tokens(
    messages: list[dict[str, str]],
    max_completion_tokens: int,
) -> int:
    message_characters = sum(
        len(str(message.get("content") or "")) + len(str(message.get("role") or ""))
        for message in messages
    )
    estimated_input_tokens = max(1, (message_characters + 3) // 4)
    protocol_margin = 120
    return estimated_input_tokens + max_completion_tokens + protocol_margin


# Cette fonction réserve un budget local de tokens avant chaque appel afin de rester sous le quota minute.
async def wait_for_groq_token_budget(
    estimated_tokens: int,
    sleep_func: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    configured_budget = max(1, settings.groq_tokens_per_minute)
    safety_ratio = min(max(settings.groq_rate_limit_safety_ratio, 0.1), 1.0)
    safe_budget = max(1, int(configured_budget * safety_ratio))
    reserved_tokens = min(max(1, estimated_tokens), safe_budget)

    if estimated_tokens > safe_budget:
        LOGGER.warning(
            "Groq request estimate exceeds local safe budget: estimated=%s safe_budget=%s",
            estimated_tokens,
            safe_budget,
        )

    while True:
        now = monotonic()

        with _GROQ_TOKEN_EVENTS_LOCK:
            while (
                _GROQ_TOKEN_EVENTS
                and now - _GROQ_TOKEN_EVENTS[0][0] >= _GROQ_RATE_LIMIT_WINDOW_SECONDS
            ):
                _GROQ_TOKEN_EVENTS.popleft()

            used_tokens = sum(event_tokens for _, event_tokens in _GROQ_TOKEN_EVENTS)

            if used_tokens + reserved_tokens <= safe_budget:
                _GROQ_TOKEN_EVENTS.append((now, reserved_tokens))
                return

            oldest_timestamp = _GROQ_TOKEN_EVENTS[0][0]
            wait_seconds = max(
                0.05,
                _GROQ_RATE_LIMIT_WINDOW_SECONDS - (now - oldest_timestamp) + 0.05,
            )

        LOGGER.info(
            "Groq local throttle: wait_seconds=%.2f estimated_tokens=%s",
            wait_seconds,
            estimated_tokens,
        )
        await sleep_func(wait_seconds)


# Cette fonction lit Retry-After sans dépasser le délai maximal configuré.
def parse_groq_retry_after_seconds(response: httpx.Response, attempt: int) -> float:
    raw_retry_after = str(response.headers.get("retry-after") or "").strip()

    try:
        retry_after = float(raw_retry_after)
    except ValueError:
        retry_after = float(min(5 * (2 ** attempt), 30))

    return min(
        max(retry_after, 0.5),
        max(settings.groq_retry_max_wait_seconds, 0.5),
    )


# Cette fonction extrait le contenu conversationnel d'une réponse Groq valide.
def extract_groq_message_content(response_payload: dict[str, Any]) -> str | None:
    choices = response_payload.get("choices") or []

    if not choices or not isinstance(choices[0], dict):
        return None

    message = choices[0].get("message") or {}
    return message.get("content") if isinstance(message, dict) else None


# Cette fonction lit les informations d'erreur Groq sans journaliser le contenu généré ni les sources.
def extract_groq_provider_error(
    response: httpx.Response,
) -> tuple[str | None, str | None, str | None]:
    try:
        response_payload = response.json()
    except ValueError:
        return None, None, None

    error_payload = response_payload.get("error") if isinstance(response_payload, dict) else None

    if not isinstance(error_payload, dict):
        return None, None, None

    return (
        str(error_payload.get("code") or "").strip() or None,
        str(error_payload.get("message") or "").strip() or None,
        str(error_payload.get("param") or "").strip() or None,
    )


# Cette fonction augmente uniquement le budget des sorties structurées longues qui risquent d'être tronquées.
def adapt_groq_completion_tokens(
    messages: list[dict[str, str]],
    completion_tokens: int,
    response_schema: dict[str, Any] | None,
) -> int:
    message_characters = sum(
        len(str(message.get("content") or ""))
        for message in messages
    )

    if (
        response_schema
        and message_characters >= _GROQ_LONG_STRUCTURED_PROMPT_CHARACTERS
    ):
        return max(completion_tokens, _GROQ_LONG_STRUCTURED_OUTPUT_TOKENS)

    return completion_tokens


# Cette fonction construit un format JSON Schema strict pour garantir une réponse exploitable.
def build_groq_response_format(
    schema_name: str,
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": response_schema,
        },
    }


# Cette fonction prépare une nouvelle tentative structurée sans revenir vers un format plus strict.
def apply_groq_structured_output_recovery(
    payload: dict[str, Any],
    structured_failure_count: int,
) -> str:
    payload["max_completion_tokens"] = min(
        max(
            int(payload["max_completion_tokens"]) * 2,
            _GROQ_LONG_STRUCTURED_OUTPUT_TOKENS,
        ),
        _GROQ_JSON_RETRY_OUTPUT_TOKENS,
    )
    payload["temperature"] = 0.0
    payload["tool_choice"] = "none"
    payload["parallel_tool_calls"] = False
    current_format = str(
        (payload.get("response_format") or {}).get("type") or ""
    )

    if current_format == "json_object" or structured_failure_count >= 2:
        payload["response_format"] = dict(_GROQ_JSON_OBJECT_RESPONSE_FORMAT)
        return "json_object"

    return "json_schema"


# Cette fonction appelle Groq sans outil externe en JSON contrôlé ou en texte simple selon le besoin.
async def request_groq_chatbot_completion(
    messages: list[dict[str, str]],
    max_completion_tokens: int | None = None,
    response_schema: dict[str, Any] | None = None,
    response_schema_name: str = "rubybets_chatbot_response",
    response_format_mode: str | None = None,
    structured_retry_limit: int | None = None,
    client: httpx.AsyncClient | None = None,
    sleep_func: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> dict[str, Any]:
    if not settings.groq_api_key.strip():
        raise GroqChatbotError(
            code="GROQ_NOT_CONFIGURED",
            public_message="Le chatbot d'actualités n'est pas configuré.",
            status_code=503,
        )

    requested_completion_tokens = max(
        64,
        int(max_completion_tokens or settings.groq_max_completion_tokens),
    )
    completion_tokens = adapt_groq_completion_tokens(
        messages=messages,
        completion_tokens=requested_completion_tokens,
        response_schema=response_schema,
    )
    normalized_response_format_mode = response_format_mode or (
        "json_schema" if response_schema else "json_object"
    )

    if normalized_response_format_mode not in {"json_schema", "json_object", "text"}:
        raise ValueError("Unsupported Groq response format mode.")

    payload = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": completion_tokens,
        "reasoning_format": "hidden",
        "reasoning_effort": "low",
        "tool_choice": "none",
        "parallel_tool_calls": False,
        "stream": False,
    }

    if normalized_response_format_mode == "json_schema":
        if not response_schema:
            raise ValueError("A response schema is required for JSON Schema mode.")
        payload["response_format"] = build_groq_response_format(
            response_schema_name,
            response_schema,
        )
    elif normalized_response_format_mode == "json_object":
        payload["response_format"] = dict(_GROQ_JSON_OBJECT_RESPONSE_FORMAT)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(settings.groq_timeout_seconds)
    )
    started_at = perf_counter()
    structured_generation_failure_count = 0
    structured_retry_budget = (
        max(0, settings.groq_max_retries)
        if structured_retry_limit is None
        else max(0, structured_retry_limit)
    )

    try:
        for attempt in range(max(0, settings.groq_max_retries) + 1):
            estimated_tokens = estimate_groq_request_tokens(
                messages,
                int(payload["max_completion_tokens"]),
            )
            await wait_for_groq_token_budget(estimated_tokens, sleep_func=sleep_func)

            try:
                response = await active_client.post(
                    settings.get_groq_chat_completions_url(),
                    headers=settings.get_groq_headers(),
                    json=payload,
                )
                response.raise_for_status()

                response_payload = response.json()

                message_content = extract_groq_message_content(response_payload)

                if normalized_response_format_mode == "text":
                    clean_message_content = str(message_content or "").strip()
                    if not clean_message_content:
                        raise GroqChatbotError(
                            code="GROQ_INVALID_RESPONSE",
                            public_message="Le chatbot a retourné une réponse vide.",
                            status_code=502,
                        )
                    parsed_content = {"answer": clean_message_content}
                else:
                    try:
                        parsed_content = parse_groq_json_content(message_content)
                    except GroqChatbotError as error:
                        can_retry = attempt < max(0, settings.groq_max_retries)
                        can_retry_structured = (
                            can_retry
                            and structured_generation_failure_count < structured_retry_budget
                        )

                        if error.code == "GROQ_INVALID_RESPONSE" and can_retry_structured:
                            structured_generation_failure_count += 1
                            recovery_mode = apply_groq_structured_output_recovery(
                                payload,
                                structured_generation_failure_count,
                            )
                            LOGGER.warning(
                                "Groq chatbot invalid JSON retry: model=%s mode=%s attempt=%s max_completion_tokens=%s",
                                settings.groq_model,
                                recovery_mode,
                                attempt + 1,
                                payload["max_completion_tokens"],
                            )
                            continue

                        raise

                usage = response_payload.get("usage") or {}

                LOGGER.info(
                    "Groq chatbot success: model=%s duration_ms=%s prompt_tokens=%s completion_tokens=%s",
                    settings.groq_model,
                    round((perf_counter() - started_at) * 1000),
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                )
                return parsed_content

            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                can_retry = attempt < max(0, settings.groq_max_retries)

                provider_code, provider_message, provider_param = (
                    extract_groq_provider_error(error.response)
                )
                LOGGER.warning(
                    "Groq chatbot HTTP error: model=%s status=%s code=%s param=%s attempt=%s duration_ms=%s",
                    settings.groq_model,
                    status_code,
                    provider_code,
                    provider_param,
                    attempt + 1,
                    round((perf_counter() - started_at) * 1000),
                )

                can_retry_structured = (
                    can_retry
                    and normalized_response_format_mode != "text"
                    and structured_generation_failure_count < structured_retry_budget
                )
                if (
                    status_code == 400
                    and provider_code in _GROQ_STRUCTURED_RETRY_CODES
                    and can_retry_structured
                ):
                    structured_generation_failure_count += 1
                    recovery_mode = apply_groq_structured_output_recovery(
                        payload,
                        structured_generation_failure_count,
                    )
                    LOGGER.info(
                        "Groq structured output retry: model=%s code=%s mode=%s attempt=%s max_completion_tokens=%s",
                        settings.groq_model,
                        provider_code,
                        recovery_mode,
                        attempt + 1,
                        payload["max_completion_tokens"],
                    )
                    continue

                if status_code == 429 and can_retry:
                    await sleep_func(parse_groq_retry_after_seconds(error.response, attempt))
                    continue

                if status_code in {500, 502, 503, 504} and can_retry:
                    await sleep_func(min(2 ** attempt, 8))
                    continue

                if status_code == 429:
                    raise GroqChatbotError(
                        code="GROQ_RATE_LIMITED",
                        public_message=(
                            "Le quota gratuit du chatbot est temporairement atteint. "
                            "Réessaie après le délai indiqué par Groq."
                        ),
                        status_code=429,
                    ) from error

                if status_code in {401, 403}:
                    raise GroqChatbotError(
                        code="GROQ_ACCESS_DENIED",
                        public_message="Le chatbot n'est pas autorisé avec la configuration actuelle.",
                        status_code=503,
                    ) from error

                if status_code in {400, 413, 422}:
                    raise GroqChatbotError(
                        code="GROQ_REQUEST_REJECTED",
                        public_message="Le fournisseur a refusé une requête du chatbot.",
                        status_code=502,
                    ) from error

                raise GroqChatbotError(
                    code="GROQ_PROVIDER_ERROR",
                    public_message="Le service du chatbot est temporairement indisponible.",
                    status_code=503,
                ) from error

            except httpx.RequestError as error:
                if attempt < max(0, settings.groq_max_retries):
                    await sleep_func(min(2 ** attempt, 8))
                    continue

                LOGGER.warning(
                    "Groq chatbot network error: model=%s duration_ms=%s",
                    settings.groq_model,
                    round((perf_counter() - started_at) * 1000),
                )
                raise GroqChatbotError(
                    code="GROQ_NETWORK_ERROR",
                    public_message="Le service du chatbot est indisponible ou trop lent.",
                    status_code=503,
                ) from error

            except (KeyError, TypeError, ValueError) as error:
                raise GroqChatbotError(
                    code="GROQ_INVALID_RESPONSE",
                    public_message="Le chatbot a retourné une réponse non exploitable.",
                    status_code=502,
                ) from error

        raise GroqChatbotError(
            code="GROQ_PROVIDER_ERROR",
            public_message="Le service du chatbot est temporairement indisponible.",
            status_code=503,
        )

    finally:
        if owns_client:
            await active_client.aclose()


# Schéma de communication :
# services chatbot RubyBets
#     ↓ messages contrôlés + budget TPM local
# groq_chatbot_client.py
#     ↓ HTTPS + GROQ_API_KEY depuis config.py + Retry-After
# API Groq / openai/gpt-oss-120b
#     ↓ JSON simple pour les fragments ou texte cité pour la réponse finale
# route news_chatbot.py
