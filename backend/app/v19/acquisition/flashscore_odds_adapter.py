# Rôle du fichier :
# Ce fichier transforme les odds FlashScore brutes en triplets 1X2 immuables et traçables.

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from app.v19.domain.market_contracts import (
    MarketModuleStatus,
    MarketNormalizationResultV1,
    MarketOddsTripletV1,
    MarketOutcome,
    MarketQualityFlag,
)


MARKET_NORMALIZATION_CONTRACT_VERSION = "MarketNormalizationResultV1"
MARKET_NORMALIZATION_VERSION = "v19.market.flashscore-normalizer.1"
MARKET_TYPE_HOME_DRAW_AWAY = "HOME_DRAW_AWAY"
MARKET_PERIOD_FULL_TIME = "FULL_TIME"
MARKET_SOURCE_ENDPOINT = "/matches/odds"

_BOOKMAKER_CONTAINER_KEYS = (
    "bookmaker",
    "bookmaker_info",
    "bookmakerInfo",
    "provider",
)
_MARKET_COLLECTION_KEYS = (
    "markets",
    "oddsMarkets",
    "odds_markets",
    "marketGroups",
)
_OPTION_COLLECTION_KEYS = (
    "options",
    "selections",
    "outcomes",
    "odds",
    "values",
)
_MISSING = object()


# Normalise un datetime en UTC conscient du fuseau.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# Normalise les libellés fournisseur pour comparer marché et période sans dépendre de la casse.
def normalize_token(value: object) -> str:
    if isinstance(value, Mapping):
        value = first_present(value, ("code", "name", "type", "value"))
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in token.split("_") if part)


# Retourne la première valeur présente parmi plusieurs clés possibles.
def first_present(mapping: Mapping[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


# Convertit une cote décimale en float valide strictement supérieur à 1.
def parse_valid_odd(value: object) -> float | None:
    try:
        odd = float(value)
    except (TypeError, ValueError):
        return None

    if odd <= 1.0:
        return None
    return odd


# Extrait l'identité du bookmaker depuis le nœud courant ou son contexte parent.
def extract_bookmaker_identity(
    node: Mapping[str, Any],
    inherited_id: str | None,
    inherited_name: str | None,
) -> tuple[str | None, str | None]:
    bookmaker_value = first_present(node, _BOOKMAKER_CONTAINER_KEYS)
    bookmaker_id = inherited_id
    bookmaker_name = inherited_name

    if isinstance(bookmaker_value, Mapping):
        bookmaker_id = str(
            first_present(
                bookmaker_value,
                ("id", "bookmaker_id", "bookmakerId", "provider_id", "providerId"),
                bookmaker_id,
            )
            or ""
        ).strip() or bookmaker_id
        bookmaker_name = str(
            first_present(
                bookmaker_value,
                ("name", "bookmaker_name", "bookmakerName", "provider_name", "providerName"),
                bookmaker_name,
            )
            or ""
        ).strip() or bookmaker_name
    elif bookmaker_value not in (None, ""):
        bookmaker_name = str(bookmaker_value).strip() or bookmaker_name

    direct_id = first_present(
        node,
        ("bookmaker_id", "bookmakerId", "provider_id", "providerId"),
    )
    direct_name = first_present(
        node,
        ("bookmaker_name", "bookmakerName", "provider_name", "providerName"),
    )

    if direct_id not in (None, ""):
        bookmaker_id = str(direct_id).strip()
    if direct_name not in (None, ""):
        bookmaker_name = str(direct_name).strip()

    return bookmaker_id, bookmaker_name


# Extrait le type et la période d'un nœud marché potentiel.
def extract_market_signature(node: Mapping[str, Any]) -> tuple[str, str]:
    market_type = normalize_token(
        first_present(
            node,
            ("market_type", "marketType", "type", "odds_type", "oddsType", "name"),
        )
    )
    market_period = normalize_token(
        first_present(
            node,
            ("period", "period_type", "periodType", "scope", "odds_period", "oddsPeriod"),
        )
    )
    return market_type, market_period


# Extrait la liste des options d'un marché sans confondre un objet scalaire avec une collection.
def extract_market_options(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in _OPTION_COLLECTION_KEYS:
        value = node.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


# Parcourt récursivement le payload et restitue les marchés 1X2 avec leur bookmaker.
def iter_home_draw_away_markets(
    payload: Any,
    inherited_id: str | None = None,
    inherited_name: str | None = None,
) -> Iterable[tuple[str, str, list[Mapping[str, Any]]]]:
    if isinstance(payload, list):
        for item in payload:
            yield from iter_home_draw_away_markets(
                item,
                inherited_id=inherited_id,
                inherited_name=inherited_name,
            )
        return

    if not isinstance(payload, Mapping):
        return

    bookmaker_id, bookmaker_name = extract_bookmaker_identity(
        payload,
        inherited_id=inherited_id,
        inherited_name=inherited_name,
    )
    market_type, market_period = extract_market_signature(payload)
    options = extract_market_options(payload)

    if (
        market_type == MARKET_TYPE_HOME_DRAW_AWAY
        and market_period == MARKET_PERIOD_FULL_TIME
        and options
    ):
        fallback_name = bookmaker_name or bookmaker_id or "UNKNOWN_BOOKMAKER"
        fallback_id = bookmaker_id or fallback_name
        yield fallback_id, fallback_name, options

    for key, value in payload.items():
        if key in _OPTION_COLLECTION_KEYS:
            continue
        if key in _MARKET_COLLECTION_KEYS or isinstance(value, (dict, list)):
            yield from iter_home_draw_away_markets(
                value,
                inherited_id=bookmaker_id,
                inherited_name=bookmaker_name,
            )


# Mappe une option active sur HOME_WIN, DRAW ou AWAY_WIN grâce aux identifiants fournisseurs.
def map_option_outcome(
    option: Mapping[str, Any],
    home_team_id: str,
    away_team_id: str,
) -> tuple[MarketOutcome | None, MarketQualityFlag | None]:
    participant_id = first_present(
        option,
        ("eventParticipantId", "event_participant_id", "participantId", "participant_id"),
        _MISSING,
    )

    if participant_id is _MISSING:
        return None, MarketQualityFlag.AMBIGUOUS_PARTICIPANT_MAPPING
    if participant_id is None:
        return MarketOutcome.DRAW, None

    normalized_participant_id = str(participant_id).strip()
    if normalized_participant_id == home_team_id:
        return MarketOutcome.HOME_WIN, None
    if normalized_participant_id == away_team_id:
        return MarketOutcome.AWAY_WIN, None

    return None, MarketQualityFlag.HOME_AWAY_MAPPING_MISMATCH


# Convertit un triplet de cotes en probabilités implicites normalisées et overround brut.
def normalize_probability_triplet(
    home_odd: float,
    draw_odd: float,
    away_odd: float,
) -> tuple[float, float, float, float] | None:
    raw_home = 1.0 / home_odd
    raw_draw = 1.0 / draw_odd
    raw_away = 1.0 / away_odd
    overround = raw_home + raw_draw + raw_away

    if overround <= 0.0:
        return None

    probabilities = (
        raw_home / overround,
        raw_draw / overround,
        raw_away / overround,
    )

    if any(probability < 0.0 or probability > 1.0 for probability in probabilities):
        return None
    if abs(sum(probabilities) - 1.0) > 1e-9:
        return None

    return (*probabilities, overround)


# Détermine si une option current reste active selon les représentations fournisseur usuelles.
def is_option_active(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"false", "0", "inactive", "no"}


# Détermine si opening représente un marqueur de snapshot plutôt qu'une cote numérique.
def parse_opening_marker(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes"}:
            return True
        if normalized in {"false", "no"}:
            return False
    return None


# Ajoute une cote tout en détectant les doublons contradictoires pour la même issue.
def register_odd(
    target: dict[MarketOutcome, float],
    outcome: MarketOutcome,
    odd: float,
) -> MarketQualityFlag | None:
    existing = target.get(outcome)

    if existing is None:
        target[outcome] = odd
        return None
    if existing == odd:
        return None

    return MarketQualityFlag.DUPLICATE_CONTRADICTORY_SELECTION


# Normalise toutes les options d'un bookmaker en un triplet complet ou un motif de rejet.
def build_bookmaker_triplet(
    bookmaker_id: str,
    bookmaker_name: str,
    options: list[Mapping[str, Any]],
    home_team_id: str,
    away_team_id: str,
) -> tuple[MarketOddsTripletV1 | None, MarketQualityFlag | None]:
    current_selections: dict[MarketOutcome, float] = {}
    opening_selections: dict[MarketOutcome, float] = {}

    for option in options:
        outcome, mapping_flag = map_option_outcome(
            option=option,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
        if mapping_flag is not None:
            return None, mapping_flag
        if outcome is None:
            return None, MarketQualityFlag.AMBIGUOUS_PARTICIPANT_MAPPING

        odd = parse_valid_odd(
            first_present(option, ("value", "current", "currentValue", "current_odd", "currentOdd", "odd"))
        )
        if odd is None:
            return None, MarketQualityFlag.INVALID_ODD_VALUE

        raw_opening = first_present(option, ("opening",), _MISSING)
        opening_marker = parse_opening_marker(raw_opening)
        active = is_option_active(option.get("active"))

        if opening_marker is True:
            duplicate_flag = register_odd(opening_selections, outcome, odd)
        else:
            if not active:
                continue
            duplicate_flag = register_odd(current_selections, outcome, odd)

        if duplicate_flag is not None:
            return None, duplicate_flag

        direct_opening_value = first_present(
            option,
            ("openingValue", "opening_value", "opening_odd", "openingOdd"),
            _MISSING,
        )
        if direct_opening_value is _MISSING and raw_opening is not _MISSING and opening_marker is None:
            direct_opening_value = raw_opening

        if direct_opening_value not in (_MISSING, None, ""):
            direct_opening_odd = parse_valid_odd(direct_opening_value)
            if direct_opening_odd is None:
                return None, MarketQualityFlag.INVALID_ODD_VALUE
            duplicate_flag = register_odd(opening_selections, outcome, direct_opening_odd)
            if duplicate_flag is not None:
                return None, duplicate_flag

    required_outcomes = {
        MarketOutcome.HOME_WIN,
        MarketOutcome.DRAW,
        MarketOutcome.AWAY_WIN,
    }
    if set(current_selections) != required_outcomes:
        return None, MarketQualityFlag.NO_VALID_MARKET_TRIPLET

    home_odd = current_selections[MarketOutcome.HOME_WIN]
    draw_odd = current_selections[MarketOutcome.DRAW]
    away_odd = current_selections[MarketOutcome.AWAY_WIN]
    current_probabilities = normalize_probability_triplet(home_odd, draw_odd, away_odd)

    if current_probabilities is None:
        return None, MarketQualityFlag.INVALID_PROBABILITY_DISTRIBUTION

    opening_home_odd = opening_selections.get(MarketOutcome.HOME_WIN)
    opening_draw_odd = opening_selections.get(MarketOutcome.DRAW)
    opening_away_odd = opening_selections.get(MarketOutcome.AWAY_WIN)
    opening_values = (opening_home_odd, opening_draw_odd, opening_away_odd)

    if all(value is not None for value in opening_values):
        opening_probabilities = normalize_probability_triplet(
            float(opening_home_odd),
            float(opening_draw_odd),
            float(opening_away_odd),
        )
        if opening_probabilities is None:
            return None, MarketQualityFlag.INVALID_PROBABILITY_DISTRIBUTION
    else:
        opening_probabilities = None

    return MarketOddsTripletV1(
        bookmaker_id=bookmaker_id,
        bookmaker_name=bookmaker_name,
        current_home_odd=home_odd,
        current_draw_odd=draw_odd,
        current_away_odd=away_odd,
        current_home_probability=current_probabilities[0],
        current_draw_probability=current_probabilities[1],
        current_away_probability=current_probabilities[2],
        current_overround=current_probabilities[3],
        opening_home_odd=opening_home_odd,
        opening_draw_odd=opening_draw_odd,
        opening_away_odd=opening_away_odd,
        opening_home_probability=(opening_probabilities[0] if opening_probabilities else None),
        opening_draw_probability=(opening_probabilities[1] if opening_probabilities else None),
        opening_away_probability=(opening_probabilities[2] if opening_probabilities else None),
        opening_overround=(opening_probabilities[3] if opening_probabilities else None),
    ), None


# Déduit le statut global sans introduire de seuil numérique de qualité non validé.
def infer_market_status(
    triplets: tuple[MarketOddsTripletV1, ...],
    quality_flags: tuple[MarketQualityFlag, ...],
) -> MarketModuleStatus:
    if triplets:
        return MarketModuleStatus.DEGRADED if quality_flags else MarketModuleStatus.READY

    invalid_flags = {
        MarketQualityFlag.AMBIGUOUS_PARTICIPANT_MAPPING,
        MarketQualityFlag.HOME_AWAY_MAPPING_MISMATCH,
        MarketQualityFlag.INVALID_ODD_VALUE,
        MarketQualityFlag.DUPLICATE_CONTRADICTORY_SELECTION,
        MarketQualityFlag.INVALID_PROBABILITY_DISTRIBUTION,
    }
    if any(flag in invalid_flags for flag in quality_flags):
        return MarketModuleStatus.INVALID

    return MarketModuleStatus.UNAVAILABLE


# Adapte le payload FlashScore complet en résultat de normalisation V19.
def adapt_flashscore_odds_payload(
    *,
    payload: Any,
    match_id: str | int,
    source_match_id: str | None,
    home_team_id: str | int,
    away_team_id: str | int,
    fetched_at_utc: datetime,
) -> MarketNormalizationResultV1:
    normalized_home_team_id = str(home_team_id).strip()
    normalized_away_team_id = str(away_team_id).strip()
    markets = list(iter_home_draw_away_markets(payload))
    grouped_options: dict[str, tuple[str, list[Mapping[str, Any]]]] = {}

    for bookmaker_id, bookmaker_name, options in markets:
        key = str(bookmaker_id or bookmaker_name).strip() or "UNKNOWN_BOOKMAKER"
        if key not in grouped_options:
            grouped_options[key] = (bookmaker_name, list(options))
        else:
            existing_name, existing_options = grouped_options[key]
            grouped_options[key] = (existing_name or bookmaker_name, existing_options + list(options))

    triplets: list[MarketOddsTripletV1] = []
    rejected: list[tuple[str, str]] = []
    flags: list[MarketQualityFlag] = []

    for bookmaker_id, (bookmaker_name, options) in grouped_options.items():
        triplet, rejection_flag = build_bookmaker_triplet(
            bookmaker_id=bookmaker_id,
            bookmaker_name=bookmaker_name or bookmaker_id,
            options=options,
            home_team_id=normalized_home_team_id,
            away_team_id=normalized_away_team_id,
        )
        if triplet is not None:
            triplets.append(triplet)
            continue

        reason = rejection_flag or MarketQualityFlag.NO_VALID_MARKET_TRIPLET
        rejected.append((bookmaker_id, reason.value))
        if reason not in flags:
            flags.append(reason)

    if not triplets and MarketQualityFlag.NO_VALID_MARKET_TRIPLET not in flags:
        flags.append(MarketQualityFlag.NO_VALID_MARKET_TRIPLET)

    if len(triplets) == 1:
        flags.append(MarketQualityFlag.SINGLE_BOOKMAKER_ONLY)

    opening_count = sum(
        triplet.opening_home_probability is not None
        and triplet.opening_draw_probability is not None
        and triplet.opening_away_probability is not None
        for triplet in triplets
    )
    any_opening_count = sum(
        any(
            value is not None
            for value in (
                triplet.opening_home_odd,
                triplet.opening_draw_odd,
                triplet.opening_away_odd,
            )
        )
        for triplet in triplets
    )
    if triplets and any_opening_count == 0:
        flags.append(MarketQualityFlag.OPENING_ODDS_UNAVAILABLE)
    elif opening_count < len(triplets):
        flags.append(MarketQualityFlag.PARTIAL_MOVEMENT_DATA)

    unique_flags = tuple(dict.fromkeys(flags))
    normalized_triplets = tuple(sorted(triplets, key=lambda item: item.bookmaker_id))

    return MarketNormalizationResultV1(
        contract_version=f"{MARKET_NORMALIZATION_CONTRACT_VERSION}:{MARKET_NORMALIZATION_VERSION}",
        match_id=str(match_id),
        source_match_id=(str(source_match_id).strip() if source_match_id else None),
        home_team_id=normalized_home_team_id,
        away_team_id=normalized_away_team_id,
        fetched_at_utc=ensure_utc_datetime(fetched_at_utc),
        source_endpoint=MARKET_SOURCE_ENDPOINT,
        status=infer_market_status(normalized_triplets, unique_flags),
        triplets=normalized_triplets,
        bookmaker_count_total=len(grouped_options),
        bookmaker_count_eligible=len(normalized_triplets),
        rejected_bookmakers=tuple(rejected),
        quality_flags=unique_flags,
    )


# Schéma de communication :
# flashscore_odds_provider.py
#   -> fournit le payload brut /matches/odds
# flashscore_odds_adapter.py
#   -> filtre HOME_DRAW_AWAY / FULL_TIME et mappe les équipes par identifiants
# market_contracts.py
#   <- reçoit MarketOddsTripletV1 et MarketNormalizationResultV1 immuables
# market_feature_builder.py
#   -> consomme uniquement les triplets valides, sans cote affichée ni recommandation finale
