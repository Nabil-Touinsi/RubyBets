# Rôle du fichier :
# Ce fichier centralise les énumérations partagées du module H2H natif RubyBets V19.

from __future__ import annotations

from enum import Enum


# Types d'entités pouvant participer à une confrontation directe.
class H2HEntityType(str, Enum):
    CLUB = "CLUB"
    NATIONAL_TEAM = "NATIONAL_TEAM"


# États possibles de la résolution d'identité d'une équipe.
class H2HIdentityStatus(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


# Méthodes autorisées pour résoudre l'identité d'une équipe.
class H2HIdentityMethod(str, Enum):
    PROVIDER_ID_EXACT = "PROVIDER_ID_EXACT"
    CANONICAL_ID_EXACT = "CANONICAL_ID_EXACT"
    PROVIDER_ALIAS = "PROVIDER_ALIAS"
    NORMALIZED_NAME = "NORMALIZED_NAME"
    NAME_HEURISTIC = "NAME_HEURISTIC"
    MANUAL_MAPPING = "MANUAL_MAPPING"
    UNRESOLVED = "UNRESOLVED"


# Catégories de compétitions reconnues par le module H2H.
class H2HCompetitionCategory(str, Enum):
    DOMESTIC_LEAGUE = "DOMESTIC_LEAGUE"
    DOMESTIC_CUP = "DOMESTIC_CUP"
    CONTINENTAL_CLUB_COMPETITION = "CONTINENTAL_CLUB_COMPETITION"
    INTERNATIONAL_TOURNAMENT = "INTERNATIONAL_TOURNAMENT"
    INTERNATIONAL_QUALIFIER = "INTERNATIONAL_QUALIFIER"
    NATIONS_LEAGUE = "NATIONS_LEAGUE"
    FRIENDLY = "FRIENDLY"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# Nature officielle, amicale ou inconnue d'une confrontation.
class H2HOfficialStatus(str, Enum):
    OFFICIAL = "OFFICIAL"
    FRIENDLY = "FRIENDLY"
    UNKNOWN = "UNKNOWN"


# Valeur ternaire utilisée lorsque l'information peut être inconnue.
class H2HTriState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


# Nature du score disponible pour une confrontation historique.
class H2HScoreType(str, Enum):
    REGULATION_90 = "REGULATION_90"
    AFTER_EXTRA_TIME = "AFTER_EXTRA_TIME"
    AFTER_PENALTIES = "AFTER_PENALTIES"
    AWARDED_RESULT = "AWARDED_RESULT"
    UNKNOWN = "UNKNOWN"


# Format de confrontation dans lequel le match historique s'inscrit.
class H2HTieFormat(str, Enum):
    SINGLE_MATCH = "SINGLE_MATCH"
    TWO_LEGGED_TIE = "TWO_LEGGED_TIE"
    MULTI_LEG_OTHER = "MULTI_LEG_OTHER"
    UNKNOWN = "UNKNOWN"


# Niveau de fiabilité du score normalisé.
class H2HScoreReliability(str, Enum):
    RELIABLE = "RELIABLE"
    PARTIAL = "PARTIAL"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


# Position du match dans une confrontation aller-retour ou multi-manches.
class H2HLegNumber(str, Enum):
    FIRST_LEG = "FIRST_LEG"
    SECOND_LEG = "SECOND_LEG"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# État final de normalisation d'une confrontation historique.
class H2HNormalizationState(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    CONFLICTING = "CONFLICTING"
    INVALID = "INVALID"


# Fournisseurs ou sources pouvant contribuer aux données H2H.
class H2HProvider(str, Enum):
    FLASHSCORE = "FLASHSCORE"
    FOOTBALL_DATA = "FOOTBALL_DATA"
    TEAM_HISTORY_SERVICE = "TEAM_HISTORY_SERVICE"
    RUBYBETS_ARCHIVE = "RUBYBETS_ARCHIVE"
    OTHER = "OTHER"


# États de cache observables pendant l'acquisition H2H.
class H2HCacheState(str, Enum):
    MISS = "MISS"
    HIT_FRESH = "HIT_FRESH"
    HIT_STALE_ALLOWED = "HIT_STALE_ALLOWED"
    UNKNOWN = "UNKNOWN"


# États possibles d'une récupération auprès d'un fournisseur H2H.
class H2HProviderResultStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


# Profils métier définissant les politiques H2H applicables.
class H2HDomainProfile(str, Enum):
    CLUB_H2H_V1 = "CLUB_H2H_V1"
    NATIONAL_TEAM_H2H_V1 = "NATIONAL_TEAM_H2H_V1"


# État technique global produit par le module H2H.
class H2HModuleStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


# Résultat local du module, distinct d'une décision sportive globale.
class H2HModuleOutcome(str, Enum):
    FEATURES_PRODUCED = "FEATURES_PRODUCED"
    H2H_MODULE_ABSTAIN = "H2H_MODULE_ABSTAIN"


# Types de données autorisés dans le catalogue de features H2H.
class H2HFeatureDataType(str, Enum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"


# Unités autorisées pour documenter les features H2H.
class H2HFeatureUnit(str, Enum):
    RATE = "RATE"
    GOALS = "GOALS"
    DAYS = "DAYS"
    COUNT = "COUNT"


# Niveaux synthétiques de qualité des données H2H.
class H2HQualityLevel(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    POOR = "POOR"
    UNKNOWN = "UNKNOWN"


# Niveaux de sévérité des anomalies détectées.
class H2HIssueSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


# États de disponibilité des features pour un consommateur spécialisé.
class H2HConsumerReadinessStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    NOT_READY = "NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# Consommateurs spécialisés initialement autorisés à lire le résultat H2H.
class H2HConsumerId(str, Enum):
    BTTS = "BTTS"
    OVER_1_5 = "OVER_1_5"


# Codes structurés décrivant les anomalies du pipeline H2H.
class H2HIssueCode(str, Enum):
    H2H_NO_ELIGIBLE_MEETING = "H2H_NO_ELIGIBLE_MEETING"
    H2H_TEMPORAL_VIOLATION = "H2H_TEMPORAL_VIOLATION"
    H2H_TARGET_MATCH_INCLUDED = "H2H_TARGET_MATCH_INCLUDED"
    H2H_TEAM_IDENTITY_AMBIGUOUS = "H2H_TEAM_IDENTITY_AMBIGUOUS"
    H2H_SCORE_UNRELIABLE = "H2H_SCORE_UNRELIABLE"
    H2H_DUPLICATE_CONFLICT = "H2H_DUPLICATE_CONFLICT"
    H2H_SOURCE_UNAVAILABLE = "H2H_SOURCE_UNAVAILABLE"
    H2H_COMPETITION_CONTEXT_MISSING = "H2H_COMPETITION_CONTEXT_MISSING"
    H2H_NEUTRAL_GROUND_UNKNOWN = "H2H_NEUTRAL_GROUND_UNKNOWN"


# Motifs contrôlés expliquant l'exclusion d'une confrontation.
class H2HExclusionReason(str, Enum):
    H2H_CLUB_FRIENDLY_EXCLUDED = "H2H_CLUB_FRIENDLY_EXCLUDED"


# Indicateurs non bloquants décrivant la qualité de la population H2H.
class H2HQualityFlag(str, Enum):
    H2H_ONLY_FRIENDLIES = "H2H_ONLY_FRIENDLIES"
    H2H_DEPTH_INSUFFICIENT_FOR_EXPERT = (
        "H2H_DEPTH_INSUFFICIENT_FOR_EXPERT"
    )
    H2H_DEPTH_INSUFFICIENT_FOR_BTTS = (
        "H2H_DEPTH_INSUFFICIENT_FOR_BTTS"
    )


# Schéma de communication :
# h2h_enums.py
#   -> fournit le vocabulaire contrôlé à h2h_contracts.py
#   -> est utilisé par les providers, normalizers et policies H2H V19
#   -> est utilisé par h2h_feature_catalog.py et h2h_feature_builder.py
#   -> ne dépend ni de FlashScore, ni de FastAPI, ni des moteurs historiques
#   -> ne produit aucune feature ni recommandation sportive