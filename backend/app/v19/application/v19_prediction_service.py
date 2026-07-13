# Rôle du fichier :
# Ce service orchestre le pipeline produit V19 depuis un match réel jusqu'à DecisionResultV1.

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.services.ml_clubs_v17_8_feature_builder import BUILDER_SOURCE
from app.services.rapidapi_flashscore_client import (
    get_normalized_flashscore_match_details,
)
from app.services.team_history_service import build_team_history_response
from app.v19.acquisition.flashscore_odds_adapter import (
    adapt_flashscore_odds_payload,
)
from app.v19.acquisition.flashscore_odds_provider import (
    get_flashscore_match_odds_for_rubybets,
)
from app.v19.application.decision_orchestrator import (
    orchestrate_legacy_decision,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.market_contracts import (
    MarketModuleStatus,
    MarketQualityFlag,
)
from app.v19.experts.legacy_adapters import build_legacy_expert_candidates
from app.v19.experts.legacy_btts import build_legacy_btts_candidate
from app.v19.experts.legacy_double_chance import (
    build_legacy_double_chance_candidate,
)
from app.v19.experts.legacy_over_15 import build_legacy_over_15_candidate
from app.v19.experts.legacy_strict_1x2 import (
    build_legacy_strict_1x2_candidate,
)
from app.v19.features.market_feature_builder import (
    build_market_feature_snapshot,
    market_features_to_dict,
)


V19_PRODUCT_SERVICE_VERSION = "v19.product-pipeline.legacy-parity.2"
V19_PRODUCT_POLICY_MODE = "LEGACY_PARITY"

V19MatchLoader = Callable[
    [int | str | None],
    tuple[dict[str, Any] | None, dict[str, Any]],
]
V19OddsLoader = Callable[
    [int | str | None],
    tuple[Any | None, dict[str, Any]],
]
V19HistoryLoader = Callable[[int], Awaitable[dict[str, Any]]]
V19Clock = Callable[[], datetime]


# Signale une erreur applicative contrôlée du pipeline produit V19.
class V19ProductApplicationError(RuntimeError):
    pass


# Signale qu'aucun match cible exploitable ne correspond à l'identifiant demandé.
class V19ProductMatchNotFoundError(V19ProductApplicationError):
    pass


# Signale que le fournisseur du match cible n'a pas pu répondre correctement.
class V19ProductMatchProviderError(V19ProductApplicationError):
    pass


# Signale que le match cible ne contient pas les informations minimales du pipeline V19.
class V19ProductMatchInvalidError(V19ProductApplicationError):
    pass


# Retourne l'instant courant sous forme de datetime UTC conscient du fuseau.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Normalise un datetime en UTC conscient du fuseau.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# Détermine si les métadonnées du chargeur décrivent une absence plutôt qu'une panne fournisseur.
def is_target_match_not_found(metadata: dict[str, Any]) -> bool:
    status = str(metadata.get("status") or "").strip().lower()
    return status in {
        "not_flashscore_match_id",
        "not_found",
        "missing_match_id",
        "empty",
    }


# Charge le match cible et transforme les erreurs fournisseur en erreurs applicatives stables.
async def load_target_match(
    match_id: int | str,
    loader: V19MatchLoader,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        match_data, metadata = await run_in_threadpool(loader, match_id)
    except Exception as exc:
        raise V19ProductMatchProviderError(
            f"target_match_provider_error:{type(exc).__name__}"
        ) from exc

    normalized_metadata = metadata if isinstance(metadata, dict) else {}
    if isinstance(match_data, dict) and match_data:
        return match_data, normalized_metadata

    if is_target_match_not_found(normalized_metadata):
        raise V19ProductMatchNotFoundError("target_match_not_found")

    status = str(normalized_metadata.get("status") or "unknown")
    raise V19ProductMatchProviderError(
        f"target_match_provider_unavailable:{status}"
    )


# Extrait les identifiants Market en privilégiant les participants d'événement FlashScore prouvés.
def extract_target_match_identity(
    match_data: dict[str, Any],
) -> tuple[str | None, str, str]:
    home_team = match_data.get("homeTeam")
    away_team = match_data.get("awayTeam")

    if not isinstance(home_team, dict) or not isinstance(away_team, dict):
        raise V19ProductMatchInvalidError("target_match_teams_missing")

    home_market_id = (
        home_team.get("sourceEventParticipantId")
        or home_team.get("sourceTeamId")
        or home_team.get("id")
    )
    away_market_id = (
        away_team.get("sourceEventParticipantId")
        or away_team.get("sourceTeamId")
        or away_team.get("id")
    )

    if home_market_id in (None, "") or away_market_id in (None, ""):
        raise V19ProductMatchInvalidError("target_match_team_ids_missing")

    source_match_id = match_data.get("sourceMatchId")
    return (
        str(source_match_id).strip() if source_match_id else None,
        str(home_market_id).strip(),
        str(away_market_id).strip(),
    )


# Charge les odds de manière défensive et retourne toujours des métadonnées exploitables.
async def load_market_payload(
    match_id: int | str,
    loader: V19OddsLoader,
) -> tuple[Any | None, dict[str, Any]]:
    try:
        payload, metadata = await run_in_threadpool(loader, match_id)
    except Exception as exc:
        return None, {
            "status": "error",
            "message": type(exc).__name__,
        }

    return payload, metadata if isinstance(metadata, dict) else {}


# Charge les historiques sans transformer une indisponibilité partielle en erreur du produit entier.
async def load_team_history(
    match_id: int,
    loader: V19HistoryLoader,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        response = await loader(match_id)
    except Exception as exc:
        return {}, {
            "status": "error",
            "message": type(exc).__name__,
        }

    if not isinstance(response, dict):
        return {}, {
            "status": "invalid_response",
            "message": type(response).__name__,
        }

    return response, {
        "status": "success",
        "data_status": str(response.get("data_status") or "unknown"),
        "source_used": str(response.get("source_used") or "unknown"),
    }


# Produit les candidats Team/Goals en déclarant les features manquantes si la source est indisponible.
def build_team_candidates(
    team_history_response: dict[str, Any],
) -> tuple[ExpertCandidateV1, ExpertCandidateV1]:
    data_status = str(team_history_response.get("data_status") or "").lower()
    if not team_history_response or data_status == "unavailable":
        return (
            build_legacy_over_15_candidate({}),
            build_legacy_btts_candidate({}),
        )

    return build_legacy_expert_candidates(team_history_response)


# Ajoute le flag fournisseur attendu lorsque la récupération des odds a échoué.
def attach_market_fetch_failure(
    normalization,
    market_metadata: dict[str, Any],
):
    provider_status = str(market_metadata.get("status") or "unknown").lower()
    if provider_status in {"success", "empty"}:
        return normalization

    flags = tuple(
        dict.fromkeys(
            (
                *normalization.quality_flags,
                MarketQualityFlag.ODDS_FETCH_FAILED,
            )
        )
    )
    return replace(
        normalization,
        status=MarketModuleStatus.UNAVAILABLE,
        quality_flags=flags,
    )


# Convertit les flags Market internes en codes publics qui ne révèlent aucun détail d'odds.
def build_public_market_quality_flags(
    quality_flags: tuple[MarketQualityFlag, ...],
) -> str | None:
    public_names = {
        MarketQualityFlag.ODDS_FETCH_FAILED: "MARKET_FETCH_FAILED",
        MarketQualityFlag.OPENING_ODDS_UNAVAILABLE: "OPENING_MARKET_UNAVAILABLE",
    }
    values = tuple(public_names.get(flag, flag.value) for flag in quality_flags)
    return ",".join(values) or None


# Construit les métadonnées scalaires du pipeline sans exposer le payload odds ni les bookmakers.
def build_decision_metadata(
    *,
    request_id: str | None,
    target_match_metadata: dict[str, Any],
    market_metadata: dict[str, Any],
    market_status: MarketModuleStatus,
    market_quality_flags: tuple[MarketQualityFlag, ...],
    history_metadata: dict[str, Any],
) -> tuple[tuple[str, str | int | float | bool | None], ...]:
    return (
        ("request_id", request_id),
        ("product_service_version", V19_PRODUCT_SERVICE_VERSION),
        ("policy_mode", V19_PRODUCT_POLICY_MODE),
        ("target_match_provider_status", str(target_match_metadata.get("status") or "unknown")),
        ("market_provider_status", str(market_metadata.get("status") or "unknown")),
        ("market_module_status", market_status.value),
        (
            "market_quality_flags",
            build_public_market_quality_flags(market_quality_flags),
        ),
        ("history_provider_status", str(history_metadata.get("status") or "unknown")),
        ("history_data_status", str(history_metadata.get("data_status") or "unknown")),
        ("history_source_used", str(history_metadata.get("source_used") or "unknown")),
        ("team_feature_builder", BUILDER_SOURCE),
    )


# Exécute le pipeline produit V19 complet sans exposer de route, d'odds brutes ou de logique frontend.
async def build_v19_prediction_for_match(
    *,
    match_id: int,
    request_id: str | None = None,
    match_loader: V19MatchLoader = get_normalized_flashscore_match_details,
    odds_loader: V19OddsLoader = get_flashscore_match_odds_for_rubybets,
    history_loader: V19HistoryLoader = build_team_history_response,
    clock: V19Clock = utc_now,
) -> DecisionResultV1:
    computed_at_utc = ensure_utc_datetime(clock())
    match_data, target_match_metadata = await load_target_match(
        match_id=match_id,
        loader=match_loader,
    )
    source_match_id, home_team_id, away_team_id = extract_target_match_identity(
        match_data
    )

    market_payload, market_metadata = await load_market_payload(
        match_id=match_id,
        loader=odds_loader,
    )
    normalization = adapt_flashscore_odds_payload(
        payload=market_payload,
        match_id=match_id,
        source_match_id=source_match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        fetched_at_utc=computed_at_utc,
    )
    normalization = attach_market_fetch_failure(
        normalization,
        market_metadata,
    )
    market_snapshot = build_market_feature_snapshot(
        normalization=normalization,
        computed_at_utc=computed_at_utc,
    )
    market_features = market_features_to_dict(market_snapshot)

    team_history_response, history_metadata = await load_team_history(
        match_id=match_id,
        loader=history_loader,
    )
    over_15_candidate, btts_candidate = build_team_candidates(
        team_history_response
    )

    candidates = (
        build_legacy_strict_1x2_candidate(market_features),
        build_legacy_double_chance_candidate(market_features),
        over_15_candidate,
        btts_candidate,
    )

    return orchestrate_legacy_decision(
        match_id=match_id,
        candidates=candidates,
        feature_versions=(market_snapshot.feature_set_version,),
        metadata=build_decision_metadata(
            request_id=request_id,
            target_match_metadata=target_match_metadata,
            market_metadata=market_metadata,
            market_status=market_snapshot.status,
            market_quality_flags=market_snapshot.quality_flags,
            history_metadata=history_metadata,
        ),
    )


# Schéma de communication :
# rapidapi_flashscore_client.py / team_history_service.py / flashscore_odds_provider.py
#   -> fournissent match cible, historiques et payload odds au service
# flashscore_odds_adapter.py / market_feature_builder.py / experts legacy
#   -> normalisent les sources puis produisent quatre ExpertCandidateV1
# decision_orchestrator.py
#   -> arbitre les candidats et retourne DecisionResultV1
# experimental_ml_v19.py
#   <- sérialise le résultat sans exposer les odds, les bookmakers ou les payloads fournisseurs
