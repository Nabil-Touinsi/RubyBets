# Role du fichier :
# Ce service applique le selecteur national global V18.3.3 strict reliability.
# Il transforme des probabilites multi-marches deja preparees en recommandation ou abstention.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

STRICT_1X2_MARKET = "STRICT_1X2"
OVER_1_5_MARKET = "OVER_1_5"
OVER_2_5_MARKET = "OVER_2_5"
BTTS_MARKET = "BTTS"
DOUBLE_CHANCE_MARKET = "DOUBLE_CHANCE"
ABSTAIN_MARKET = "ABSTAIN"

SELECTOR_VERSION = "v18.3.3"
SELECTOR_PROFILE = "strict_reliability"

SELECTOR_VARIANT = (
    "v18_3_2_s760_o15780_o25700_b750_dc150_"
    "capnone_reference_order_btts1"
)

REFERENCE_RELIABILITY = 0.900893
REFERENCE_COVERAGE = 0.575244
REFERENCE_SELECTED_ROWS = 1120
REFERENCE_DOUBLE_CHANCE_SHARE = 0.716071


@dataclass(frozen=True)
class V1833SelectorConfig:
    strict_1x2_min_confidence: float
    over_1_5_yes_min_confidence: float
    over_2_5_min_confidence: float
    btts_no_min_confidence: float
    double_chance_max_excluded_probability: float
    allow_btts: bool
    priority: tuple[str, ...]


# Retourne la configuration officielle retenue pour V18.3.3.
def get_v18_3_3_selector_config() -> V1833SelectorConfig:
    return V1833SelectorConfig(
        strict_1x2_min_confidence=0.76,
        over_1_5_yes_min_confidence=0.78,
        over_2_5_min_confidence=0.70,
        btts_no_min_confidence=0.75,
        double_chance_max_excluded_probability=0.15,
        allow_btts=True,
        priority=(
            STRICT_1X2_MARKET,
            OVER_1_5_MARKET,
            OVER_2_5_MARKET,
            BTTS_MARKET,
            DOUBLE_CHANCE_MARKET,
        ),
    )


# Convertit une valeur en float sans faire planter le service.
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# Convertit une confiance numerique en niveau de risque lisible.
def compute_risk_level(confidence: float | None) -> str:
    if confidence is None:
        return "none"
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Construit la reponse commune pour une recommandation selectionnee.
def build_recommendation_response(
    market: str,
    prediction: str,
    confidence: float,
    selector_rule: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = {
        "source": "rubybets_ml_national_v18_3_3_selector",
        "scope": "experimental_backend",
        "status": RECOMMEND_STATUS,
        "selector_version": SELECTOR_VERSION,
        "selector_profile": SELECTOR_PROFILE,
        "selector_variant": SELECTOR_VARIANT,
        "selected_market": market,
        "selected_prediction": prediction,
        "selected_confidence": round(confidence, 6),
        "risk_level": compute_risk_level(confidence),
        "selector_rule": selector_rule,
        "reference_reliability": REFERENCE_RELIABILITY,
        "reference_coverage": REFERENCE_COVERAGE,
        "reference_selected_rows": REFERENCE_SELECTED_ROWS,
        "reference_double_chance_share": REFERENCE_DOUBLE_CHANCE_SHARE,
        "responsible_note": (
            "Recommandation analytique experimentale sans garantie de resultat sportif. "
            "Ne pas presenter comme pari reel ni promesse de performance."
        ),
    }

    if extra:
        response.update(extra)

    return response


# Construit une reponse d'abstention quand aucun signal ne respecte les seuils.
def build_abstention_response(reason: str) -> dict[str, Any]:
    return {
        "source": "rubybets_ml_national_v18_3_3_selector",
        "scope": "experimental_backend",
        "status": ABSTAIN_STATUS,
        "selector_version": SELECTOR_VERSION,
        "selector_profile": SELECTOR_PROFILE,
        "selector_variant": SELECTOR_VARIANT,
        "selected_market": ABSTAIN_MARKET,
        "selected_prediction": ABSTAIN_MARKET,
        "selected_confidence": None,
        "risk_level": "none",
        "selector_rule": reason,
        "reference_reliability": REFERENCE_RELIABILITY,
        "reference_coverage": REFERENCE_COVERAGE,
        "responsible_note": (
            "Aucun signal ne respecte les seuils prudents V18.3.3. "
            "L'abstention est conservee pour eviter une recommandation fragile."
        ),
    }


# Tente de selectionner un marche STRICT_1X2.
def try_select_strict_1x2(
    features: dict[str, Any],
    config: V1833SelectorConfig,
) -> dict[str, Any] | None:
    prediction = str(features.get("1x2_prediction", ""))
    confidence = safe_float(features.get("1x2_max_probability"))

    if prediction != "DRAW" and confidence >= config.strict_1x2_min_confidence:
        return build_recommendation_response(
            market=STRICT_1X2_MARKET,
            prediction=prediction,
            confidence=confidence,
            selector_rule=(
                "1X2 non-DRAW avec confiance >= "
                f"{config.strict_1x2_min_confidence}"
            ),
        )

    return None


# Tente de selectionner un marche OVER_1_5.
def try_select_over_1_5(
    features: dict[str, Any],
    config: V1833SelectorConfig,
) -> dict[str, Any] | None:
    prediction = str(features.get("over_1_5_prediction", ""))
    confidence = safe_float(features.get("over_1_5_prob_YES"))

    if prediction == "YES" and confidence >= config.over_1_5_yes_min_confidence:
        return build_recommendation_response(
            market=OVER_1_5_MARKET,
            prediction="YES",
            confidence=confidence,
            selector_rule=(
                "OVER_1_5 YES avec confiance >= "
                f"{config.over_1_5_yes_min_confidence}"
            ),
        )

    return None


# Tente de selectionner un marche OVER_2_5.
def try_select_over_2_5(
    features: dict[str, Any],
    config: V1833SelectorConfig,
) -> dict[str, Any] | None:
    prediction = str(features.get("over_2_5_prediction", ""))
    confidence = safe_float(features.get("over_2_5_max_probability"))

    if prediction and confidence >= config.over_2_5_min_confidence:
        return build_recommendation_response(
            market=OVER_2_5_MARKET,
            prediction=prediction,
            confidence=confidence,
            selector_rule=(
                "OVER_2_5 avec confiance >= "
                f"{config.over_2_5_min_confidence}"
            ),
        )

    return None


# Tente de selectionner un marche BTTS NO.
def try_select_btts_no(
    features: dict[str, Any],
    config: V1833SelectorConfig,
) -> dict[str, Any] | None:
    if not config.allow_btts:
        return None

    prediction = str(features.get("btts_prediction", ""))
    confidence = safe_float(features.get("btts_prob_NO"))

    if prediction == "NO" and confidence >= config.btts_no_min_confidence:
        return build_recommendation_response(
            market=BTTS_MARKET,
            prediction="NO",
            confidence=confidence,
            selector_rule=(
                "BTTS NO avec confiance >= "
                f"{config.btts_no_min_confidence}"
            ),
        )

    return None


# Derive une double chance a partir des probabilites 1X2.
def derive_double_chance(features: dict[str, Any]) -> dict[str, Any]:
    probabilities = {
        "TEAM_A_WIN": safe_float(features.get("1x2_prob_TEAM_A_WIN")),
        "DRAW": safe_float(features.get("1x2_prob_DRAW")),
        "TEAM_B_WIN": safe_float(features.get("1x2_prob_TEAM_B_WIN")),
    }

    excluded_outcome = min(probabilities, key=probabilities.get)
    excluded_probability = probabilities[excluded_outcome]
    confidence = 1.0 - excluded_probability

    if excluded_outcome == "TEAM_A_WIN":
        prediction = "DRAW_OR_TEAM_B"
    elif excluded_outcome == "DRAW":
        prediction = "TEAM_A_OR_TEAM_B"
    else:
        prediction = "TEAM_A_OR_DRAW"

    return {
        "prediction": prediction,
        "confidence": confidence,
        "excluded_outcome": excluded_outcome,
        "excluded_probability": excluded_probability,
    }


# Tente de selectionner DOUBLE_CHANCE si l'issue exclue est suffisamment peu probable.
def try_select_double_chance(
    features: dict[str, Any],
    config: V1833SelectorConfig,
) -> dict[str, Any] | None:
    double_chance = derive_double_chance(features)

    if (
        double_chance["excluded_probability"]
        <= config.double_chance_max_excluded_probability
    ):
        return build_recommendation_response(
            market=DOUBLE_CHANCE_MARKET,
            prediction=double_chance["prediction"],
            confidence=double_chance["confidence"],
            selector_rule=(
                "DOUBLE_CHANCE si probabilite de l'issue exclue <= "
                f"{config.double_chance_max_excluded_probability}"
            ),
            extra={
                "excluded_outcome": double_chance["excluded_outcome"],
                "excluded_probability": round(
                    double_chance["excluded_probability"],
                    6,
                ),
            },
        )

    return None


# Applique le selecteur V18.3.3 dans l'ordre de priorite retenu.
def select_market_with_v18_3_3(features: dict[str, Any]) -> dict[str, Any]:
    config = get_v18_3_3_selector_config()

    selectors = {
        STRICT_1X2_MARKET: try_select_strict_1x2,
        OVER_1_5_MARKET: try_select_over_1_5,
        OVER_2_5_MARKET: try_select_over_2_5,
        BTTS_MARKET: try_select_btts_no,
        DOUBLE_CHANCE_MARKET: try_select_double_chance,
    }

    for market in config.priority:
        result = selectors[market](features, config)
        if result is not None:
            return result

    return build_abstention_response(
        "Aucun signal ne respecte les seuils V18.3.3 strict reliability."
    )


# Schema de communication :
# ml_national_v18_3_3_selector.py
#   -> recoit des probabilites deja preparees par la future couche inference nationale
#   -> applique les seuils V18.3.3 issus des preuves 365/366
#   -> retourne STRICT_1X2, OVER_1_5, OVER_2_5, BTTS, DOUBLE_CHANCE ou ABSTAIN
#   -> reste separe du frontend tant que l'API d'inference n'est pas stabilisee
