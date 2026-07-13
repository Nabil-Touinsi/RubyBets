# Rôle du fichier :
# Ce module transforme DecisionResultV1 en explication produit déterministe sans recalculer la décision sportive.

from __future__ import annotations

from enum import Enum
from typing import Any

from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus


EXPLANATION_CONTRACT_VERSION = "v19.explanation.public.1"
MAX_PUBLIC_FACTORS = 4

MARKET_LABELS = {
    "STRICT_1X2": "Résultat du match",
    "DOUBLE_CHANCE": "Double chance",
    "OVER_1_5": "Plus de 1,5 but",
    "BTTS": "Les deux équipes marquent",
}

VALUE_LABELS = {
    "HOME_WIN": "victoire à domicile",
    "DRAW": "match nul",
    "AWAY_WIN": "victoire à l'extérieur",
    "1X": "domicile ou nul",
    "X2": "extérieur ou nul",
    "12": "domicile ou extérieur",
    "OVER_1_5": "plus de 1,5 but",
    "BTTS_YES": "les deux équipes marquent",
    "BTTS_NO": "les deux équipes ne marquent pas toutes les deux",
}

REASON_TEXTS = {
    "STRICT_1X2_V13_1_GATES_PASSED": (
        "Le signal résultat respecte les conditions de la politique historique versionnée."
    ),
    "DOUBLE_CHANCE_V13_1_GATES_PASSED": (
        "Le signal Double chance respecte les conditions de la politique historique versionnée."
    ),
    "OVER_15_V15_GATES_PASSED": (
        "Les historiques récents soutiennent un scénario avec au moins deux buts."
    ),
    "BTTS_V17_8_GATES_PASSED": (
        "Les indicateurs récents nécessaires au signal BTTS convergent."
    ),
    "FAVORITE_PROBABILITY_AT_OR_ABOVE_V13_1_THRESHOLD": (
        "Le signal principal ressort nettement dans les données de marché internes."
    ),
    "FAVORITE_MARGIN_AT_OR_ABOVE_V13_1_THRESHOLD": (
        "L'écart avec l'alternative suivante est suffisant selon la politique versionnée."
    ),
    "TOP2_SUM_AT_OR_ABOVE_V13_1_THRESHOLD": (
        "Deux issues concentrent suffisamment le signal pour une Double chance."
    ),
    "ENTROPY_AT_OR_BELOW_V13_1_MAXIMUM": (
        "L'incertitude du signal reste dans la limite autorisée."
    ),
    "AVAILABLE_TRIPLETS_AT_OR_ABOVE_V13_1_MINIMUM": (
        "La profondeur des données de marché internes est suffisante."
    ),
    "TRIPLET_COUNT_AT_OR_ABOVE_V13_1_MINIMUM": (
        "La profondeur des données de marché internes est suffisante."
    ),
    "BOOKMAKER_AGREEMENT_AT_OR_ABOVE_V13_1_MINIMUM": (
        "Les sources de marché internes sont suffisamment cohérentes."
    ),
    "COMBINED_OVER_15_RATE_AT_OR_ABOVE_V15_THRESHOLD": (
        "Le taux récent de matchs avec au moins deux buts atteint le niveau requis."
    ),
    "HISTORY_AT_OR_ABOVE_V15_MINIMUM": (
        "La profondeur d'historique nécessaire est disponible."
    ),
    "NO_ELIGIBLE_CANDIDATE": (
        "Aucun candidat ne satisfait l'ensemble des garde-fous du moteur."
    ),
    "MISSING_BTTS_FEATURES": (
        "Certaines données indispensables au signal BTTS sont absentes."
    ),
    "BTTS_SCORE_TOO_LOW": (
        "Le signal BTTS reste trop faible pour être retenu."
    ),
    "HISTORY_TOO_LOW": (
        "La profondeur d'historique est insuffisante."
    ),
    "HOME_EXPECTED_GOALS_TOO_LOW": (
        "Le potentiel offensif récent de l'équipe à domicile reste insuffisant."
    ),
    "AWAY_EXPECTED_GOALS_TOO_LOW": (
        "Le potentiel offensif récent de l'équipe à l'extérieur reste insuffisant."
    ),
    "TOTAL_EXPECTED_GOALS_TOO_LOW": (
        "Le volume offensif total attendu reste insuffisant."
    ),
    "BTTS_RATE_TOO_LOW": (
        "Le taux récent de matchs où les deux équipes marquent reste insuffisant."
    ),
    "OVER_15_RATE_TOO_LOW": (
        "Le contexte récent de buts reste insuffisant."
    ),
    "HOME_FAILED_TO_SCORE_RATE_TOO_HIGH": (
        "L'équipe à domicile présente trop de matchs récents sans marquer."
    ),
    "AWAY_FAILED_TO_SCORE_RATE_TOO_HIGH": (
        "L'équipe à l'extérieur présente trop de matchs récents sans marquer."
    ),
    "MARKET_FETCH_FAILED": (
        "Les données de marché internes sont temporairement indisponibles."
    ),
    "MARKET_MODULE_UNAVAILABLE": (
        "Le module de marché interne n'est pas disponible pour ce calcul."
    ),
}

REJECTION_TEXTS = {
    "HIGHER_PRIORITY_CANDIDATE_SELECTED": (
        "Un autre signal, prioritaire dans la politique versionnée, a été retenu."
    ),
    "REPLACED_BY_BTTS_POLICY": (
        "La politique BTTS versionnée a remplacé ce signal."
    ),
    "CANDIDATE_INELIGIBLE": (
        "Les conditions minimales de ce signal ne sont pas satisfaites."
    ),
    "CANDIDATE_ERROR": (
        "Ce signal n'a pas pu être évalué correctement."
    ),
}


# Cette fonction retourne la valeur texte d'un enum ou d'une valeur simple.
def get_code_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)

    return str(value or "")


# Cette fonction transforme un code technique inconnu en message public générique.
def humanize_unknown_code(code: str) -> str:
    if not code.strip():
        return "Une limite non détaillée impose davantage de prudence."

    return "Une limite interne non détaillée impose davantage de prudence."


# Cette fonction traduit un reason code en texte produit sans inventer de causalité.
def translate_reason(code: Any) -> str:
    value = get_code_value(code)
    return REASON_TEXTS.get(value, humanize_unknown_code(value))


# Cette fonction retourne un libellé public de marché.
def format_market_label(value: Any) -> str:
    code = get_code_value(value)
    return MARKET_LABELS.get(code, code.replace("_", " ").title())


# Cette fonction retourne un libellé public de valeur recommandée.
def format_recommendation_value(value: Any) -> str:
    code = get_code_value(value)
    return VALUE_LABELS.get(code, code.replace("_", " ").lower())


# Cette fonction déduplique une liste tout en conservant son ordre et une taille produit limitée.
def unique_limited(
    values: list[str],
    limit: int = MAX_PUBLIC_FACTORS,
) -> list[str]:
    unique_values: list[str] = []

    for value in values:
        cleaned = value.strip()

        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)

        if len(unique_values) >= limit:
            break

    return unique_values


# Cette fonction construit les facteurs favorables depuis le candidat réellement retenu.
def build_supporting_factors(result: DecisionResultV1) -> list[str]:
    candidate = result.selected_candidate

    if candidate is None:
        return []

    factors = [
        translate_reason(reason)
        for reason in candidate.positive_reasons
    ]

    if not factors:
        factors.append(
            "Le candidat retenu respecte les règles d'éligibilité "
            "de sa politique versionnée."
        )

    return unique_limited(factors)


# Cette fonction construit les facteurs de prudence sans transformer un score brut en probabilité.
def build_caution_factors(result: DecisionResultV1) -> list[str]:
    factors: list[str] = []
    candidate = result.selected_candidate

    if candidate is not None:
        factors.extend(
            translate_reason(reason)
            for reason in candidate.caution_reasons
        )

    if result.missing_features:
        factors.append(
            "Certaines variables restent manquantes et sont conservées "
            "comme limite du calcul."
        )

    metadata = dict(result.metadata)
    market_status = str(
        metadata.get("market_module_status") or ""
    ).upper()
    history_status = str(
        metadata.get("history_data_status") or ""
    ).upper()

    if market_status in {"UNAVAILABLE", "INVALID", "DEGRADED"}:
        factors.append(
            "La qualité des données de marché internes impose "
            "une lecture prudente."
        )

    if history_status in {"UNAVAILABLE", "PARTIAL"}:
        factors.append(
            "Les historiques d'équipes sont incomplets "
            "ou partiellement disponibles."
        )

    return unique_limited(factors)


# Cette fonction résume les candidats écartés avec leur motif d'arbitrage public.
def build_rejected_alternatives(
    result: DecisionResultV1,
) -> list[str]:
    alternatives: list[str] = []

    for rejected in result.rejected_candidates:
        market_label = format_market_label(
            rejected.candidate.market_type
        )
        reason_code = get_code_value(rejected.reason)
        reason_text = REJECTION_TEXTS.get(
            reason_code,
            (
                "Ce signal n'a pas été retenu par la politique "
                "d'arbitrage versionnée."
            ),
        )

        alternatives.append(
            f"{market_label} : {reason_text}"
        )

    return unique_limited(alternatives)


# Cette fonction résume la qualité des entrées sans exposer les données fournisseur brutes.
def build_data_quality_summary(
    result: DecisionResultV1,
) -> str:
    metadata = dict(result.metadata)

    target_status = str(
        metadata.get("target_match_provider_status") or "unknown"
    ).lower()
    market_status = str(
        metadata.get("market_module_status") or "unknown"
    ).upper()
    history_status = str(
        metadata.get("history_data_status") or "unknown"
    ).lower()

    if (
        target_status == "success"
        and market_status == "READY"
        and history_status == "available"
    ):
        return (
            "Le match cible, les données de marché internes et les historiques "
            "nécessaires sont disponibles pour ce calcul."
        )

    unavailable_parts: list[str] = []

    if target_status != "success":
        unavailable_parts.append("match cible")

    if market_status != "READY":
        unavailable_parts.append("données de marché internes")

    if history_status != "available":
        unavailable_parts.append("historiques d'équipes")

    if not unavailable_parts:
        return (
            "La qualité des données est disponible dans les diagnostics "
            "techniques du moteur."
        )

    return (
        "La qualité est partielle pour : "
        + ", ".join(unavailable_parts)
        + ". Le moteur conserve cette limite dans sa décision."
    )


# Cette fonction explique la confiance sans afficher de faux pourcentage de réussite.
def build_confidence_explanation(
    result: DecisionResultV1,
) -> str:
    candidate = result.selected_candidate

    if candidate is None:
        return (
            "Aucun niveau de confiance produit n'est affiché puisqu'aucune "
            "recommandation n'a été retenue."
        )

    if candidate.calibrated_probability is None:
        return (
            "Le score expert n'est pas une probabilité calibrée. "
            "Aucun pourcentage de réussite n'est présenté."
        )

    if candidate.confidence_level:
        return (
            "Le niveau de confiance décrit la solidité relative du signal "
            "dans le moteur ; il ne garantit pas le résultat sportif."
        )

    return (
        "La calibration produit n'est pas encore disponible. "
        "Aucun pourcentage de réussite n'est présenté."
    )


# Cette fonction explique une abstention à partir des motifs réellement produits par l'orchestrateur.
def build_abstention_explanation(
    result: DecisionResultV1,
) -> str | None:
    if result.status is not DecisionStatus.ABSTAIN:
        return None

    reasons = [
        translate_reason(reason)
        for reason in result.abstention_reasons
    ]

    if result.missing_features:
        reasons.append(
            "Des variables nécessaires à certains experts sont manquantes."
        )

    public_reasons = unique_limited(
        reasons,
        limit=3,
    )

    if not public_reasons:
        return (
            "RubyBets préfère ne pas formuler de recommandation lorsque "
            "les garde-fous du moteur ne sont pas suffisamment satisfaits."
        )

    return " ".join(public_reasons)


# Cette fonction construit la projection publique conforme au contrat d'explicabilité V19.
def build_public_explanation(
    *,
    result: DecisionResultV1,
    responsible_note: str,
) -> dict[str, Any]:
    candidate = result.selected_candidate

    if (
        result.status is DecisionStatus.RECOMMEND
        and candidate is not None
    ):
        market_label = format_market_label(
            candidate.market_type
        )
        value_label = format_recommendation_value(
            candidate.recommendation_value
        )
        headline = "Décision RubyBets V19"
        summary = f"{market_label} : {value_label}."
    else:
        headline = "Aucune recommandation retenue"
        summary = (
            "RubyBets s'abstient lorsque les données ou les signaux "
            "ne permettent pas une décision suffisamment responsable."
        )

    return {
        "contract_version": EXPLANATION_CONTRACT_VERSION,
        "headline": headline,
        "summary": summary,
        "supporting_factors": build_supporting_factors(result),
        "caution_factors": build_caution_factors(result),
        "rejected_alternatives": build_rejected_alternatives(result),
        "data_quality_summary": build_data_quality_summary(result),
        "confidence_explanation": build_confidence_explanation(result),
        "abstention_explanation": build_abstention_explanation(result),
        "source_freshness_summary": (
            "La fraîcheur détaillée reste disponible dans les diagnostics "
            "techniques et n'est pas transformée en promesse produit."
        ),
        "responsible_note": responsible_note,
    }


# Schéma de communication :
# DecisionResultV1 / ExpertCandidateV1
#   -> explanation_builder.py traduit statuts, reason codes, rejets et qualité
# experimental_ml_v19.py
#   <- reçoit une projection publique déterministe sans odds ni probabilité inventée
# frontend Prédictions
#   <- consommera cette projection sans recalculer la décision métier