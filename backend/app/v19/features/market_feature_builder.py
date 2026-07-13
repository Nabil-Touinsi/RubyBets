# Rôle du fichier :
# Ce fichier calcule les features Market V13/V19 à partir des triplets normalisés sans prendre de décision finale.

from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import mean, stdev

from app.v19.domain.market_contracts import (
    MarketFeatureSnapshotV1,
    MarketFeatureScalar,
    MarketModuleStatus,
    MarketNormalizationResultV1,
    MarketOddsTripletV1,
    MarketOutcome,
    MarketQualityFlag,
)
from app.v19.features.market_feature_catalog import (
    MARKET_FEATURE_SET_VERSION,
    get_market_feature_names,
)


MARKET_FEATURE_SNAPSHOT_CONTRACT_VERSION = "MarketFeatureSnapshotV1"
_OUTCOME_ORDER = (
    MarketOutcome.HOME_WIN,
    MarketOutcome.DRAW,
    MarketOutcome.AWAY_WIN,
)


# Retourne l'instant courant sous forme de datetime UTC conscient du fuseau.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Calcule un écart-type échantillonnal comme pandas V13, avec zéro pour un seul bookmaker.
def sample_std(values: list[float]) -> float:
    return stdev(values) if len(values) > 1 else 0.0


# Renormalise trois moyennes de probabilités pour reproduire la chaîne historique V13.
def renormalize_consensus(home: float, draw: float, away: float) -> tuple[float, float, float] | None:
    total = home + draw + away
    if total <= 0.0:
        return None

    probabilities = (home / total, draw / total, away / total)
    if abs(sum(probabilities) - 1.0) > 1e-9:
        return None
    return probabilities


# Retourne l'issue d'indice maximal avec le même ordre déterministe que NumPy V13.
def argmax_outcome(probabilities: tuple[float, float, float]) -> MarketOutcome:
    index = max(range(len(probabilities)), key=lambda item: probabilities[item])
    return _OUTCOME_ORDER[index]


# Retourne l'issue d'indice minimal avec le même ordre déterministe que NumPy V13.
def argmin_outcome(probabilities: tuple[float, float, float]) -> MarketOutcome:
    index = min(range(len(probabilities)), key=lambda item: probabilities[item])
    return _OUTCOME_ORDER[index]


# Convertit la classe la moins probable en valeur Double Chance historique.
def map_omitted_outcome_to_double_chance(outcome: MarketOutcome) -> str:
    return {
        MarketOutcome.AWAY_WIN: "1X",
        MarketOutcome.HOME_WIN: "X2",
        MarketOutcome.DRAW: "12",
    }[outcome]


# Calcule l'entropie naturelle du consensus 1X2.
def compute_entropy(probabilities: tuple[float, float, float]) -> float:
    return -sum(probability * math.log(probability) for probability in probabilities if probability > 0.0)


# Calcule un consensus current ou opening sur les triplets disposant des trois probabilités.
def build_consensus(
    triplets: tuple[MarketOddsTripletV1, ...],
    opening: bool,
) -> tuple[float, float, float] | None:
    if opening:
        eligible = [
            triplet
            for triplet in triplets
            if triplet.opening_home_probability is not None
            and triplet.opening_draw_probability is not None
            and triplet.opening_away_probability is not None
        ]
        if not eligible:
            return None
        return renormalize_consensus(
            mean(float(item.opening_home_probability) for item in eligible),
            mean(float(item.opening_draw_probability) for item in eligible),
            mean(float(item.opening_away_probability) for item in eligible),
        )

    if not triplets:
        return None
    return renormalize_consensus(
        mean(item.current_home_probability for item in triplets),
        mean(item.current_draw_probability for item in triplets),
        mean(item.current_away_probability for item in triplets),
    )


# Calcule les features historiques et enhanced depuis les triplets valides.
def compute_market_features(
    normalization: MarketNormalizationResultV1,
    computed_at_utc: datetime,
) -> dict[str, MarketFeatureScalar]:
    triplets = normalization.triplets
    current = build_consensus(triplets, opening=False)
    opening = build_consensus(triplets, opening=True)

    features: dict[str, MarketFeatureScalar] = {
        feature_name: None
        for feature_name in get_market_feature_names()
    }
    features["market_available_triplets"] = len(triplets)
    features["v19_current_triplets_count"] = len(triplets)
    features["v19_opening_triplets_count"] = sum(
        item.opening_home_probability is not None
        and item.opening_draw_probability is not None
        and item.opening_away_probability is not None
        for item in triplets
    )
    features["v19_odds_age_seconds"] = max(
        0.0,
        (computed_at_utc - normalization.fetched_at_utc).total_seconds(),
    )
    features["v19_market_data_quality_score"] = None

    if current is None:
        return features

    home_probability, draw_probability, away_probability = current
    sorted_probabilities = sorted(current)
    favorite = argmax_outcome(current)
    omitted = argmin_outcome(current)
    favorite_probability = sorted_probabilities[-1]
    second_probability = sorted_probabilities[-2]
    top2_sum = favorite_probability + second_probability
    margin = favorite_probability - second_probability
    entropy = compute_entropy(current)

    bookmaker_favorites = [
        argmax_outcome(
            (
                item.current_home_probability,
                item.current_draw_probability,
                item.current_away_probability,
            )
        )
        for item in triplets
    ]
    agreement = (
        sum(bookmaker_favorite == favorite for bookmaker_favorite in bookmaker_favorites)
        / len(triplets)
    )

    overrounds = [item.current_overround for item in triplets]
    home_probabilities = [item.current_home_probability for item in triplets]
    draw_probabilities = [item.current_draw_probability for item in triplets]
    away_probabilities = [item.current_away_probability for item in triplets]

    features.update(
        {
            "market_home_prob_avg": home_probability,
            "market_draw_prob_avg": draw_probability,
            "market_away_prob_avg": away_probability,
            "market_favorite_prob": favorite_probability,
            "market_margin_top1_top2": margin,
            "market_top2_sum": top2_sum,
            "market_entropy": entropy,
            "market_bookmaker_agreement_score": agreement,
            "market_consensus_prediction": favorite.value,
            "v13_strict_prediction": favorite.value,
            "v13_omitted_class": omitted.value,
            "v13_double_chance": map_omitted_outcome_to_double_chance(omitted),
            "v19_market_home_prob": home_probability,
            "v19_market_draw_prob": draw_probability,
            "v19_market_away_prob": away_probability,
            "v19_market_favorite_prob": favorite_probability,
            "v19_market_margin_top1_top2": margin,
            "v19_market_top2_sum": top2_sum,
            "v19_market_entropy": entropy,
            "v19_home_prob_std": sample_std(home_probabilities),
            "v19_draw_prob_std": sample_std(draw_probabilities),
            "v19_away_prob_std": sample_std(away_probabilities),
            "v19_bookmaker_agreement_score": agreement,
            "v19_favorite_vote_share": agreement,
            "v19_overround_mean": mean(overrounds),
            "v19_overround_min": min(overrounds),
            "v19_overround_max": max(overrounds),
            "v19_overround_std": sample_std(overrounds),
        }
    )

    if opening is not None:
        opening_favorite = argmax_outcome(opening)
        favorite_changed = opening_favorite != favorite
        features.update(
            {
                "v19_market_opening_home_prob": opening[0],
                "v19_market_opening_draw_prob": opening[1],
                "v19_market_opening_away_prob": opening[2],
                "v19_home_prob_movement": home_probability - opening[0],
                "v19_draw_prob_movement": draw_probability - opening[1],
                "v19_away_prob_movement": away_probability - opening[2],
                "v19_favorite_changed_since_opening": favorite_changed,
                "v19_market_favorite_stability": 0.0 if favorite_changed else 1.0,
            }
        )

    return features


# Construit le snapshot immuable de features Market consommé par les experts V19.
def build_market_feature_snapshot(
    normalization: MarketNormalizationResultV1,
    computed_at_utc: datetime | None = None,
) -> MarketFeatureSnapshotV1:
    computed_at = computed_at_utc or utc_now()
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    else:
        computed_at = computed_at.astimezone(timezone.utc)

    feature_values = compute_market_features(normalization, computed_at)
    ordered_features = tuple(
        (name, feature_values.get(name))
        for name in get_market_feature_names()
    )
    flags = list(normalization.quality_flags)

    if feature_values.get("v19_favorite_changed_since_opening") is True:
        flags.append(MarketQualityFlag.FAVORITE_CHANGED)

    return MarketFeatureSnapshotV1(
        contract_version=MARKET_FEATURE_SNAPSHOT_CONTRACT_VERSION,
        match_id=normalization.match_id,
        computed_at_utc=computed_at,
        feature_set_version=MARKET_FEATURE_SET_VERSION,
        status=normalization.status,
        features=ordered_features,
        quality_flags=tuple(dict.fromkeys(flags)),
        source_bookmakers=tuple(item.bookmaker_id for item in normalization.triplets),
    )


# Convertit le snapshot immuable en mapping de lecture pour les experts spécialisés.
def market_features_to_dict(snapshot: MarketFeatureSnapshotV1) -> dict[str, MarketFeatureScalar]:
    return dict(snapshot.features)


# Schéma de communication :
# flashscore_odds_adapter.py
#   -> fournit MarketNormalizationResultV1 et ses triplets valides
# market_feature_catalog.py
#   -> fournit versions et ordre stable des features
# market_feature_builder.py
#   -> produit MarketFeatureSnapshotV1 et un mapping de lecture
# legacy_strict_1x2.py / legacy_double_chance.py
#   -> consomment les features legacy sans accéder aux odds brutes
