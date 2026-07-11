# Rôle du fichier :
# Ce fichier formalise le catalogue déterministe v19.h2h.core.1 et les politiques de profil H2H.

from __future__ import annotations

from dataclasses import dataclass

from app.v19.domain.h2h_enums import (
    H2HCompetitionCategory,
    H2HConsumerId,
    H2HDomainProfile,
    H2HFeatureDataType,
    H2HFeatureUnit,
)


H2H_FEATURE_SET_VERSION = "v19.h2h.core.1"
H2H_FEATURE_BUILDER_VERSION = "v19.h2h.feature-builder.1"
H2H_DEDUPLICATION_POLICY_VERSION = "v19.h2h.deduplication.1"

H2H_POPULATION_A = "A"
H2H_POPULATION_U = "U"


# Décrit une feature stable du catalogue H2H et ses consommateurs autorisés.
@dataclass(frozen=True)
class H2HFeatureSpec:
    name: str
    data_type: H2HFeatureDataType
    unit: H2HFeatureUnit
    population: str
    consumers: tuple[H2HConsumerId, ...]


# Décrit les fenêtres et limites verrouillées pour un profil H2H.
@dataclass(frozen=True)
class H2HProfilePolicy:
    domain_profile: H2HDomainProfile
    absolute_window_years: int
    friendly_supplement_years: int | None
    max_meetings: int
    allowed_official_categories: tuple[H2HCompetitionCategory, ...]


H2H_FEATURE_SPECS = (
    H2HFeatureSpec(
        name="h2h_matches_count",
        data_type=H2HFeatureDataType.INTEGER,
        unit=H2HFeatureUnit.COUNT,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.OVER_1_5, H2HConsumerId.BTTS),
    ),
    H2HFeatureSpec(
        name="h2h_total_goals_avg",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.GOALS,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.OVER_1_5,),
    ),
    H2HFeatureSpec(
        name="h2h_over_15_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.OVER_1_5,),
    ),
    H2HFeatureSpec(
        name="h2h_over_25_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(),
    ),
    H2HFeatureSpec(
        name="h2h_btts_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.BTTS,),
    ),
    H2HFeatureSpec(
        name="h2h_home_team_scored_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.BTTS,),
    ),
    H2HFeatureSpec(
        name="h2h_away_team_scored_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(H2HConsumerId.BTTS,),
    ),
    H2HFeatureSpec(
        name="h2h_days_since_last_meeting",
        data_type=H2HFeatureDataType.INTEGER,
        unit=H2HFeatureUnit.DAYS,
        population=H2H_POPULATION_U,
        consumers=(),
    ),
    H2HFeatureSpec(
        name="h2h_identity_resolved_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_A,
        consumers=(),
    ),
    H2HFeatureSpec(
        name="h2h_reliable_score_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_A,
        consumers=(),
    ),
    H2HFeatureSpec(
        name="h2h_official_match_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(),
    ),
    H2HFeatureSpec(
        name="h2h_neutral_ground_unknown_rate",
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        population=H2H_POPULATION_U,
        consumers=(),
    ),
)

H2H_FEATURE_NAMES = tuple(spec.name for spec in H2H_FEATURE_SPECS)
H2H_SPORT_FEATURE_NAMES = H2H_FEATURE_NAMES[:8]
H2H_QUALITY_FEATURE_NAMES = H2H_FEATURE_NAMES[8:]

H2H_OVER_15_REQUIRED_FEATURES = (
    "h2h_matches_count",
    "h2h_total_goals_avg",
    "h2h_over_15_rate",
)

H2H_BTTS_REQUIRED_FEATURES = (
    "h2h_matches_count",
    "h2h_btts_rate",
    "h2h_home_team_scored_rate",
    "h2h_away_team_scored_rate",
)

H2H_CONSUMER_MINIMUM_DEPTH = {
    H2HConsumerId.OVER_1_5: 3,
    H2HConsumerId.BTTS: 4,
}

CLUB_H2H_POLICY = H2HProfilePolicy(
    domain_profile=H2HDomainProfile.CLUB_H2H_V1,
    absolute_window_years=6,
    friendly_supplement_years=None,
    max_meetings=5,
    allowed_official_categories=(
        H2HCompetitionCategory.DOMESTIC_LEAGUE,
        H2HCompetitionCategory.DOMESTIC_CUP,
        H2HCompetitionCategory.CONTINENTAL_CLUB_COMPETITION,
    ),
)

NATIONAL_TEAM_H2H_POLICY = H2HProfilePolicy(
    domain_profile=H2HDomainProfile.NATIONAL_TEAM_H2H_V1,
    absolute_window_years=12,
    friendly_supplement_years=6,
    max_meetings=8,
    allowed_official_categories=(
        H2HCompetitionCategory.INTERNATIONAL_TOURNAMENT,
        H2HCompetitionCategory.INTERNATIONAL_QUALIFIER,
        H2HCompetitionCategory.NATIONS_LEAGUE,
    ),
)


# Retourne la spécification d'une feature à partir de son nom stable.
def get_h2h_feature_spec(feature_name: str) -> H2HFeatureSpec:
    for feature_spec in H2H_FEATURE_SPECS:
        if feature_spec.name == feature_name:
            return feature_spec

    raise KeyError(f"Unknown H2H feature: {feature_name}")


# Retourne la politique normative associée au profil déclaré dans l'entrée.
def get_h2h_profile_policy(
    domain_profile: H2HDomainProfile,
) -> H2HProfilePolicy:
    if domain_profile == H2HDomainProfile.NATIONAL_TEAM_H2H_V1:
        return NATIONAL_TEAM_H2H_POLICY

    return CLUB_H2H_POLICY


# Retourne les dépendances H2H minimales du consommateur demandé.
def get_h2h_consumer_required_features(
    consumer_id: H2HConsumerId,
) -> tuple[str, ...]:
    if consumer_id == H2HConsumerId.BTTS:
        return H2H_BTTS_REQUIRED_FEATURES

    return H2H_OVER_15_REQUIRED_FEATURES


# Schéma de communication :
# h2h_feature_catalog.py
#   -> dépend uniquement de backend/app/v19/domain/h2h_enums.py
#   -> fournit les 12 features, les fenêtres et les seuils à h2h_feature_builder.py
#   -> fournit les dépendances H2H aux futurs experts Over 1.5 et BTTS
#   -> ne lit aucune donnée fournisseur et ne calcule aucune recommandation
