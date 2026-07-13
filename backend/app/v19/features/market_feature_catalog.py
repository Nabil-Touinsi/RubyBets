# Rôle du fichier :
# Ce fichier versionne le catalogue des features Market V13 et V19 calculables par RubyBets.

from __future__ import annotations

from dataclasses import dataclass


LEGACY_MARKET_FEATURE_SET_VERSION = "v19.market.legacy-parity.1"
ENHANCED_MARKET_FEATURE_SET_VERSION = "v19.market.enhanced.1"
MARKET_FEATURE_SET_VERSION = f"{LEGACY_MARKET_FEATURE_SET_VERSION}+{ENHANCED_MARKET_FEATURE_SET_VERSION}"


# Décrit une feature Market, sa famille, son type et sa formule de référence.
@dataclass(frozen=True)
class MarketFeatureDefinition:
    name: str
    family: str
    data_type: str
    formula: str
    required_for_legacy_parity: bool


LEGACY_MARKET_FEATURE_NAMES = (
    "market_home_prob_avg",
    "market_draw_prob_avg",
    "market_away_prob_avg",
    "market_favorite_prob",
    "market_margin_top1_top2",
    "market_top2_sum",
    "market_entropy",
    "market_available_triplets",
    "market_bookmaker_agreement_score",
)

LEGACY_MARKET_DERIVED_NAMES = (
    "market_consensus_prediction",
    "v13_strict_prediction",
    "v13_omitted_class",
    "v13_double_chance",
)

ENHANCED_MARKET_FEATURE_NAMES = (
    "v19_market_home_prob",
    "v19_market_draw_prob",
    "v19_market_away_prob",
    "v19_market_favorite_prob",
    "v19_market_margin_top1_top2",
    "v19_market_top2_sum",
    "v19_market_entropy",
    "v19_market_opening_home_prob",
    "v19_market_opening_draw_prob",
    "v19_market_opening_away_prob",
    "v19_home_prob_movement",
    "v19_draw_prob_movement",
    "v19_away_prob_movement",
    "v19_favorite_changed_since_opening",
    "v19_home_prob_std",
    "v19_draw_prob_std",
    "v19_away_prob_std",
    "v19_bookmaker_agreement_score",
    "v19_favorite_vote_share",
    "v19_overround_mean",
    "v19_overround_min",
    "v19_overround_max",
    "v19_overround_std",
    "v19_current_triplets_count",
    "v19_opening_triplets_count",
    "v19_odds_age_seconds",
    "v19_market_favorite_stability",
    "v19_market_data_quality_score",
)


MARKET_FEATURE_CATALOG = (
    MarketFeatureDefinition("market_home_prob_avg", "LEGACY_CONSENSUS", "float", "mean(p_home) then renormalize", True),
    MarketFeatureDefinition("market_draw_prob_avg", "LEGACY_CONSENSUS", "float", "mean(p_draw) then renormalize", True),
    MarketFeatureDefinition("market_away_prob_avg", "LEGACY_CONSENSUS", "float", "mean(p_away) then renormalize", True),
    MarketFeatureDefinition("market_favorite_prob", "LEGACY_CONSENSUS", "float", "max(consensus probabilities)", True),
    MarketFeatureDefinition("market_margin_top1_top2", "LEGACY_CONSENSUS", "float", "top1 - top2", True),
    MarketFeatureDefinition("market_top2_sum", "LEGACY_CONSENSUS", "float", "top1 + top2", True),
    MarketFeatureDefinition("market_entropy", "LEGACY_CONSENSUS", "float", "-sum(p_i * ln(p_i))", True),
    MarketFeatureDefinition("market_available_triplets", "LEGACY_COVERAGE", "int", "count(valid current triplets)", True),
    MarketFeatureDefinition("market_bookmaker_agreement_score", "LEGACY_AGREEMENT", "float", "bookmakers matching consensus favorite / valid triplets", True),
)


# Retourne les noms officiels dans un ordre stable pour sérialiser les snapshots.
def get_market_feature_names() -> tuple[str, ...]:
    return LEGACY_MARKET_FEATURE_NAMES + LEGACY_MARKET_DERIVED_NAMES + ENHANCED_MARKET_FEATURE_NAMES


# Recherche la définition d'une feature legacy par son nom officiel.
def get_market_feature_definition(name: str) -> MarketFeatureDefinition | None:
    return next((definition for definition in MARKET_FEATURE_CATALOG if definition.name == name), None)


# Schéma de communication :
# market_feature_catalog.py
#   -> fournit versions et ordre stable à market_feature_builder.py
# market_feature_builder.py
#   -> calcule les neuf features historiques et les diagnostics enhanced
# legacy_strict_1x2.py / legacy_double_chance.py
#   -> utilisent uniquement les noms legacy nécessaires à la parité V13.1
