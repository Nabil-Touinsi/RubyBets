# Rôle du fichier :
# Ce fichier définit les contrats immuables du Market Module RubyBets V19.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypeAlias


# États possibles du Market Module après normalisation des odds FlashScore.
class MarketModuleStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


# Issues 1X2 utilisées par le consensus marché et les experts historiques.
class MarketOutcome(str, Enum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"


# Instant fonctionnel auquel une cote normalisée appartient.
class MarketSnapshotKind(str, Enum):
    CURRENT_SNAPSHOT = "CURRENT_SNAPSHOT"
    OPENING_SNAPSHOT = "OPENING_SNAPSHOT"


# Flags stables décrivant les anomalies et dégradations du Market Module.
class MarketQualityFlag(str, Enum):
    AMBIGUOUS_PARTICIPANT_MAPPING = "AMBIGUOUS_PARTICIPANT_MAPPING"
    HOME_AWAY_MAPPING_MISMATCH = "HOME_AWAY_MAPPING_MISMATCH"
    NO_VALID_MARKET_TRIPLET = "NO_VALID_MARKET_TRIPLET"
    INVALID_ODD_VALUE = "INVALID_ODD_VALUE"
    DUPLICATE_CONTRADICTORY_SELECTION = "DUPLICATE_CONTRADICTORY_SELECTION"
    INVALID_PROBABILITY_DISTRIBUTION = "INVALID_PROBABILITY_DISTRIBUTION"
    ODDS_FETCH_FAILED = "ODDS_FETCH_FAILED"
    LOW_BOOKMAKER_COVERAGE = "LOW_BOOKMAKER_COVERAGE"
    SINGLE_BOOKMAKER_ONLY = "SINGLE_BOOKMAKER_ONLY"
    OPENING_ODDS_UNAVAILABLE = "OPENING_ODDS_UNAVAILABLE"
    PARTIAL_MOVEMENT_DATA = "PARTIAL_MOVEMENT_DATA"
    FAVORITE_CHANGED = "FAVORITE_CHANGED"


MarketFeatureScalar: TypeAlias = str | int | float | bool | None
MarketFeatureEntries: TypeAlias = tuple[tuple[str, MarketFeatureScalar], ...]
MarketRejectedBookmakers: TypeAlias = tuple[tuple[str, str], ...]


# Représente un triplet 1X2 complet et normalisé pour un bookmaker.
@dataclass(frozen=True)
class MarketOddsTripletV1:
    bookmaker_id: str
    bookmaker_name: str
    current_home_odd: float
    current_draw_odd: float
    current_away_odd: float
    current_home_probability: float
    current_draw_probability: float
    current_away_probability: float
    current_overround: float
    opening_home_odd: float | None
    opening_draw_odd: float | None
    opening_away_odd: float | None
    opening_home_probability: float | None
    opening_draw_probability: float | None
    opening_away_probability: float | None
    opening_overround: float | None


# Transporte le résultat de normalisation des odds avant tout calcul de features.
@dataclass(frozen=True)
class MarketNormalizationResultV1:
    contract_version: str
    match_id: str
    source_match_id: str | None
    home_team_id: str
    away_team_id: str
    fetched_at_utc: datetime
    source_endpoint: str
    status: MarketModuleStatus
    triplets: tuple[MarketOddsTripletV1, ...]
    bookmaker_count_total: int
    bookmaker_count_eligible: int
    rejected_bookmakers: MarketRejectedBookmakers
    quality_flags: tuple[MarketQualityFlag, ...]


# Transporte les features Market versionnées sans produire de recommandation finale.
@dataclass(frozen=True)
class MarketFeatureSnapshotV1:
    contract_version: str
    match_id: str
    computed_at_utc: datetime
    feature_set_version: str
    status: MarketModuleStatus
    features: MarketFeatureEntries
    quality_flags: tuple[MarketQualityFlag, ...]
    source_bookmakers: tuple[str, ...]


# Schéma de communication :
# flashscore_odds_provider.py
#   -> récupère le payload brut sans l'exposer au frontend
# flashscore_odds_adapter.py
#   -> produit MarketNormalizationResultV1
# market_feature_builder.py
#   -> consomme les triplets et produit MarketFeatureSnapshotV1
# legacy_strict_1x2.py / legacy_double_chance.py
#   -> consomment uniquement les features, jamais les odds brutes
