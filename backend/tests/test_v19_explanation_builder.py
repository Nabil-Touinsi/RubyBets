# Rôle du fichier :
# Ces tests valident la projection publique d'explicabilité V19 sans recalculer la décision sportive.

from __future__ import annotations

from types import SimpleNamespace

from app.v19.domain.decision_enums import (
    CandidateRejectionReason,
    DecisionStatus,
)
from app.v19.domain.expert_enums import ExpertMarketType
from app.v19.explainability.explanation_builder import (
    EXPLANATION_CONTRACT_VERSION,
    build_public_explanation,
)


RESPONSIBLE_NOTE = (
    "Décision analytique expérimentale avant-match. "
    "RubyBets ne garantit aucun résultat sportif."
)


# Cette fonction construit un candidat léger compatible avec le builder d'explication.
def build_candidate(
    *,
    market_type: ExpertMarketType,
    value: str,
    positive_reasons: tuple[str, ...] = (),
    caution_reasons: tuple[str, ...] = (),
    calibrated_probability: float | None = None,
    confidence_level: str | None = None,
):
    return SimpleNamespace(
        market_type=market_type,
        recommendation_value=value,
        positive_reasons=positive_reasons,
        caution_reasons=caution_reasons,
        calibrated_probability=calibrated_probability,
        confidence_level=confidence_level,
    )


# Cette fonction construit un résultat léger compatible avec le builder d'explication.
def build_result(
    *,
    status: DecisionStatus,
    selected_candidate=None,
    rejected_candidates: tuple = (),
    missing_features: tuple[str, ...] = (),
    abstention_reasons: tuple[str, ...] = (),
):
    return SimpleNamespace(
        status=status,
        selected_candidate=selected_candidate,
        rejected_candidates=rejected_candidates,
        missing_features=missing_features,
        abstention_reasons=abstention_reasons,
        metadata=(
            ("target_match_provider_status", "success"),
            ("market_module_status", "READY"),
            ("history_data_status", "available"),
        ),
    )


# Vérifie qu'une recommandation produit est expliquée sans faux pourcentage de confiance.
def test_build_public_explanation_for_recommendation() -> None:
    selected = build_candidate(
        market_type=ExpertMarketType.DOUBLE_CHANCE,
        value="1X",
        positive_reasons=("DOUBLE_CHANCE_V13_1_GATES_PASSED",),
        calibrated_probability=None,
        confidence_level=None,
    )
    rejected = SimpleNamespace(
        candidate=build_candidate(
            market_type=ExpertMarketType.STRICT_1X2,
            value="HOME_WIN",
        ),
        reason=CandidateRejectionReason.CANDIDATE_INELIGIBLE,
    )
    result = build_result(
        status=DecisionStatus.RECOMMEND,
        selected_candidate=selected,
        rejected_candidates=(rejected,),
    )

    explanation = build_public_explanation(
        result=result,
        responsible_note=RESPONSIBLE_NOTE,
    )

    assert explanation["contract_version"] == EXPLANATION_CONTRACT_VERSION
    assert explanation["headline"] == "Décision RubyBets V19"
    assert explanation["summary"] == "Double chance : domicile ou nul."
    assert explanation["supporting_factors"]
    assert explanation["rejected_alternatives"]
    assert "probabilité calibrée" in explanation["confidence_explanation"]
    assert "%" not in explanation["confidence_explanation"]
    assert explanation["abstention_explanation"] is None
    assert explanation["responsible_note"] == RESPONSIBLE_NOTE


# Vérifie que le reason code réel des triplets est traduit en texte produit.
def test_translate_real_triplet_reason_code() -> None:
    selected = build_candidate(
        market_type=ExpertMarketType.DOUBLE_CHANCE,
        value="1X",
        positive_reasons=("TRIPLET_COUNT_AT_OR_ABOVE_V13_1_MINIMUM",),
    )
    result = build_result(
        status=DecisionStatus.RECOMMEND,
        selected_candidate=selected,
    )

    explanation = build_public_explanation(
        result=result,
        responsible_note=RESPONSIBLE_NOTE,
    )

    assert explanation["supporting_factors"] == [
        "La profondeur des données de marché internes est suffisante."
    ]
    assert "triplet count" not in " ".join(
        explanation["supporting_factors"]
    ).lower()


# Vérifie qu'une abstention restitue les motifs réellement produits par le moteur.
def test_build_public_explanation_for_abstention() -> None:
    result = build_result(
        status=DecisionStatus.ABSTAIN,
        missing_features=("market_entropy",),
        abstention_reasons=("NO_ELIGIBLE_CANDIDATE",),
    )

    explanation = build_public_explanation(
        result=result,
        responsible_note=RESPONSIBLE_NOTE,
    )

    assert explanation["headline"] == "Aucune recommandation retenue"
    assert explanation["supporting_factors"] == []
    assert explanation["abstention_explanation"] is not None
    assert "Aucun candidat" in explanation["abstention_explanation"]
    assert "variables nécessaires" in explanation["abstention_explanation"]
    assert explanation["confidence_explanation"].startswith(
        "Aucun niveau de confiance produit"
    )


# Vérifie que la qualité partielle est décrite sans révéler de payload fournisseur.
def test_build_public_explanation_reports_partial_quality() -> None:
    result = build_result(
        status=DecisionStatus.ABSTAIN,
        abstention_reasons=("NO_ELIGIBLE_CANDIDATE",),
    )
    result.metadata = (
        ("target_match_provider_status", "success"),
        ("market_module_status", "UNAVAILABLE"),
        ("history_data_status", "partial"),
    )

    explanation = build_public_explanation(
        result=result,
        responsible_note=RESPONSIBLE_NOTE,
    )

    quality_summary = explanation["data_quality_summary"]
    assert "données de marché internes" in quality_summary
    assert "historiques d'équipes" in quality_summary
    assert "bookmaker" not in quality_summary.lower()
    assert "odd" not in quality_summary.lower()

# Vérifie qu’un reason code inconnu n’est jamais exposé dans la réponse publique.
def test_unknown_reason_code_is_not_exposed_publicly() -> None:
    selected = build_candidate(
        market_type=ExpertMarketType.DOUBLE_CHANCE,
        value="1X",
        positive_reasons=("UNKNOWN_INTERNAL_REASON_CODE",),
    )
    result = build_result(
        status=DecisionStatus.RECOMMEND,
        selected_candidate=selected,
    )

    explanation = build_public_explanation(
        result=result,
        responsible_note=RESPONSIBLE_NOTE,
    )

    factors = " ".join(explanation["supporting_factors"]).lower()

    assert "unknown internal reason code" not in factors
    assert "limite interne non détaillée" in factors

# Schéma de communication :
# test_v19_explanation_builder.py
#   -> construit des résultats V19 légers et déterministes
#   -> teste explanation_builder.py pour RECOMMEND, ABSTAIN et qualité partielle
#   -> protège l'absence de faux pourcentage, d'odds et de bookmaker dans la projection publique
