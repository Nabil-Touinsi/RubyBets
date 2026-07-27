# Ce fichier regroupe les tests backend du domaine v19 experts.
# Les sections sources restent identifiables pour préserver la traçabilité et faciliter la maintenance.

from __future__ import annotations


# ============================================================================
# Section issue de : backend/tests/test_v19_expert_contracts.py
# ============================================================================

# Rôle du fichier :
# Ces tests protègent le vocabulaire et le contrat commun des candidats experts V19.

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Construit un candidat expert synthétique complet pour les tests de contrat.
def build_eligible_expert_candidate() -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id="expert-test-strict-1x2",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.STRICT_1X2,
        recommendation_value="HOME_WIN",
        status=ExpertCandidateStatus.ELIGIBLE,
        raw_score=0.8,
        calibrated_probability=None,
        confidence_level="high",
        local_risk_level="low",
        required_features=("market_home_prob_avg", "market_entropy"),
        missing_features=(),
        positive_reasons=("TEST_SIGNAL_AVAILABLE",),
        caution_reasons=(),
        quality_requirements=(("market_snapshot_available", True),),
        metadata=(("policy_mode", "TEST"),),
    )


# Vérifie que le contrat commun est une dataclass immuable.
def test_v19_expert_candidate_is_a_frozen_dataclass() -> None:
    assert is_dataclass(ExpertCandidateV1)
    assert ExpertCandidateV1.__dataclass_params__.frozen is True


# Vérifie les valeurs exactes du vocabulaire contrôlé des experts V19.
def test_v19_expert_enums_keep_expected_values() -> None:
    assert [status.value for status in ExpertCandidateStatus] == [
        "ELIGIBLE",
        "INELIGIBLE",
        "ERROR",
    ]
    assert [market.value for market in ExpertMarketType] == [
        "STRICT_1X2",
        "DOUBLE_CHANCE",
        "OVER_1_5",
        "BTTS",
    ]


# Vérifie qu'un candidat éligible conserve toutes ses informations standardisées.
def test_v19_eligible_expert_candidate_can_be_composed() -> None:
    candidate = build_eligible_expert_candidate()

    assert candidate.expert_id == "expert-test-strict-1x2"
    assert candidate.market_type == ExpertMarketType.STRICT_1X2
    assert candidate.recommendation_value == "HOME_WIN"
    assert candidate.status == ExpertCandidateStatus.ELIGIBLE
    assert candidate.required_features == (
        "market_home_prob_avg",
        "market_entropy",
    )
    assert candidate.quality_requirements == (
        ("market_snapshot_available", True),
    )


# Vérifie qu'un candidat inéligible peut déclarer ses features manquantes.
def test_v19_ineligible_expert_candidate_preserves_missing_features() -> None:
    candidate = ExpertCandidateV1(
        expert_id="expert-test-over-15",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.OVER_1_5,
        recommendation_value=None,
        status=ExpertCandidateStatus.INELIGIBLE,
        raw_score=None,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=("combined_over_15_rate_last10",),
        missing_features=("combined_over_15_rate_last10",),
        positive_reasons=(),
        caution_reasons=("TEST_FEATURE_MISSING",),
        quality_requirements=(),
        metadata=(),
    )

    assert candidate.status == ExpertCandidateStatus.INELIGIBLE
    assert candidate.recommendation_value is None
    assert candidate.missing_features == (
        "combined_over_15_rate_last10",
    )
    assert candidate.caution_reasons == ("TEST_FEATURE_MISSING",)


# Vérifie qu'un expert peut signaler une erreur sans inventer de recommandation.
def test_v19_error_expert_candidate_can_be_composed() -> None:
    candidate = ExpertCandidateV1(
        expert_id="expert-test-btts",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.BTTS,
        recommendation_value=None,
        status=ExpertCandidateStatus.ERROR,
        raw_score=None,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=(),
        missing_features=(),
        positive_reasons=(),
        caution_reasons=("TEST_EXPERT_ERROR",),
        quality_requirements=(),
        metadata=(("error_code", "TEST_ERROR"),),
    )

    assert candidate.status == ExpertCandidateStatus.ERROR
    assert candidate.recommendation_value is None
    assert candidate.metadata == (("error_code", "TEST_ERROR"),)


# Vérifie que le candidat refuse toute mutation après sa création.
def test_v19_expert_candidate_is_immutable() -> None:
    candidate = build_eligible_expert_candidate()

    with pytest.raises(FrozenInstanceError):
        setattr(candidate, "status", ExpertCandidateStatus.INELIGIBLE)


# Vérifie que les collections mutables sont refusées par le contrat.
def test_v19_expert_candidate_rejects_mutable_collections() -> None:
    with pytest.raises(TypeError, match="required_features must be a tuple"):
        ExpertCandidateV1(
            expert_id="expert-test-double-chance",
            expert_version="v19.expert.test.1",
            market_type=ExpertMarketType.DOUBLE_CHANCE,
            recommendation_value=None,
            status=ExpertCandidateStatus.INELIGIBLE,
            raw_score=None,
            calibrated_probability=None,
            confidence_level=None,
            local_risk_level=None,
            required_features=["market_top2_sum"],  # type: ignore[arg-type]
            missing_features=(),
            positive_reasons=(),
            caution_reasons=(),
            quality_requirements=(),
            metadata=(),
        )


# Schéma de communication :
# test_v19_expert_contracts.py
#   -> valide expert_enums.py et expert_contracts.py
#   -> protège le futur branchement des experts et de l'orchestrateur V19
#   -> ne dépend d'aucune API externe ni d'aucune donnée sportive réelle

# ============================================================================
# Section issue de : backend/tests/test_v19_explanation_builder.py
# ============================================================================

# Rôle du fichier :
# Ces tests valident la projection publique d'explicabilité V19 sans recalculer la décision sportive.


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

# ============================================================================
# Section issue de : backend/tests/test_v19_legacy_experts.py
# ============================================================================

# Rôle du fichier :
# Ce fichier vérifie la parité des règles V15/V17.8 encapsulées dans les candidats experts RubyBets V19.

from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)
from app.v19.experts.legacy_adapters import (
    build_legacy_expert_candidates,
    build_legacy_expert_features,
)
from app.v19.experts.legacy_btts import build_legacy_btts_candidate
from app.v19.experts.legacy_over_15 import build_legacy_over_15_candidate


# Construit un jeu de features qui satisfait exactement les seuils BTTS V17.8.
def build_btts_features_at_thresholds() -> dict[str, float | int]:
    return {
        "v17_6_score": 0.52,
        "min_history_count_last_10": 8,
        "expected_home_goals_proxy": 0.90,
        "expected_away_goals_proxy": 0.90,
        "expected_total_goals_proxy": 1.80,
        "combined_btts_rate_last_10": 0.55,
        "combined_over_1_5_rate_last_10": 0.50,
        "home_failed_to_score_rate_last_10": 0.45,
        "away_failed_to_score_rate_last_10": 0.45,
    }


# Construit un historique de dix matchs favorables aux marchés Over 1.5 et BTTS.
def build_team_history_response(match_count: int = 10) -> dict[str, object]:
    recent_matches = [
        {
            "goals_for": 2,
            "goals_against": 1,
        }
        for _ in range(match_count)
    ]

    return {
        "match_id": 1813105023365578,
        "source_used": "flashscore",
        "data_status": "complete",
        "home_team_history": {
            "team_name": "Home FC",
            "recent_matches": recent_matches,
        },
        "away_team_history": {
            "team_name": "Away FC",
            "recent_matches": recent_matches,
        },
        "head_to_head": [],
    }


# Vérifie qu'un taux de 0,80 avec dix matchs produit un candidat Over 1.5 éligible.
def test_legacy_over_15_candidate_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.80,
            "min_history_count_last10": 10,
        }
    )

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.OVER_1_5
    assert candidate.recommendation_value == "OVER_1_5"
    assert candidate.raw_score == 0.80
    assert candidate.calibrated_probability is None
    assert candidate.confidence_level == "medium"
    assert candidate.local_risk_level == "medium"


# Vérifie que la politique V15 refuse un taux Over 1.5 inférieur à 0,80.
def test_legacy_over_15_candidate_rejects_low_rate() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.79,
            "min_history_count_last10": 10,
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.recommendation_value is None
    assert "OVER_15_RATE_BELOW_V15_THRESHOLD" in candidate.caution_reasons


# Vérifie que la politique V15 refuse une profondeur inférieure à dix matchs.
def test_legacy_over_15_candidate_rejects_low_history() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.90,
            "min_history_count_last10": 9,
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "HISTORY_DEPTH_BELOW_V15_MINIMUM" in candidate.caution_reasons


# Vérifie que les features V15 absentes sont déclarées dans le contrat.
def test_legacy_over_15_candidate_reports_missing_features() -> None:
    candidate = build_legacy_over_15_candidate({})

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.missing_features == (
        "combined_over_15_rate_last10",
        "min_history_count_last10",
    )
    assert candidate.caution_reasons == ("MISSING_REQUIRED_FEATURES",)


# Vérifie que les seuils exacts V17.8 rendent le candidat BTTS éligible.
def test_legacy_btts_candidate_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_btts_candidate(build_btts_features_at_thresholds())

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.BTTS
    assert candidate.recommendation_value == "BTTS_YES"
    assert candidate.raw_score == 0.52
    assert candidate.calibrated_probability is None
    assert candidate.confidence_level == "medium"
    assert candidate.local_risk_level == "high"
    assert candidate.positive_reasons == ("BTTS_V17_8_GATES_PASSED",)


# Vérifie que les raisons de rejet proviennent directement des gates V17.8.
def test_legacy_btts_candidate_preserves_v17_8_rejection_reasons() -> None:
    features = build_btts_features_at_thresholds()
    features["combined_btts_rate_last_10"] = 0.54
    features["home_failed_to_score_rate_last_10"] = 0.46

    candidate = build_legacy_btts_candidate(features)

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.caution_reasons == (
        "BTTS_RATE_TOO_LOW",
        "HOME_FAILED_TO_SCORE_RATE_TOO_HIGH",
    )


# Vérifie que les features BTTS absentes restent visibles pour l'orchestrateur futur.
def test_legacy_btts_candidate_reports_missing_features() -> None:
    candidate = build_legacy_btts_candidate({})

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert len(candidate.missing_features) == 9
    assert candidate.caution_reasons == ("MISSING_BTTS_FEATURES",)


# Vérifie que l'expert BTTS reste local et ne tranche pas selon un candidat 1X2 externe.
def test_legacy_btts_candidate_does_not_orchestrate_other_markets() -> None:
    features = build_btts_features_at_thresholds()
    features.update(
        {
            "v17_recommendation_status": "RECOMMEND",
            "v17_recommendation_type": "STRICT_1X2",
        }
    )

    candidate = build_legacy_btts_candidate(features)

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert ("selection_mode", "replace_over15_or_fallback") in candidate.quality_requirements


# Vérifie que l'adapter produit les aliases V15 sans modifier les noms V17.8.
def test_legacy_adapter_builds_v15_and_v17_8_feature_names() -> None:
    features = build_legacy_expert_features(build_team_history_response())

    assert features["combined_over_15_rate_last10"] == 1.0
    assert features["combined_over_1_5_rate_last_10"] == 1.0
    assert features["min_history_count_last10"] == 10
    assert features["min_history_count_last_10"] == 10
    assert features["legacy_zero_defaults_used"] is False


# Vérifie qu'une réponse team-history réelle produit deux candidats indépendants éligibles.
def test_legacy_adapter_builds_over_15_and_btts_candidates() -> None:
    over_candidate, btts_candidate = build_legacy_expert_candidates(
        build_team_history_response()
    )

    assert over_candidate.market_type is ExpertMarketType.OVER_1_5
    assert btts_candidate.market_type is ExpertMarketType.BTTS
    assert over_candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert btts_candidate.status is ExpertCandidateStatus.ELIGIBLE


# Vérifie qu'un historique trop court conduit les deux experts à s'abstenir localement.
def test_legacy_adapter_rejects_insufficient_history() -> None:
    over_candidate, btts_candidate = build_legacy_expert_candidates(
        build_team_history_response(match_count=7)
    )

    assert over_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert btts_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "HISTORY_DEPTH_BELOW_V15_MINIMUM" in over_candidate.caution_reasons
    assert "HISTORY_TOO_LOW" in btts_candidate.caution_reasons


# Vérifie que l'adapter refuse un payload qui n'est pas un dictionnaire team-history.
def test_legacy_adapter_rejects_invalid_payload_type() -> None:
    try:
        build_legacy_expert_features([])  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == "team_history_response must be a dict"
    else:
        raise AssertionError("TypeError attendu pour un payload invalide")


# Schéma de communication :
# test_v19_legacy_experts.py
#   -> teste legacy_adapters.py, legacy_over_15.py et legacy_btts.py
#   -> réutilise les seuils historiques exacts V15/V17.8
#   -> protège le contrat ExpertCandidateV1 avant l'ajout de l'orchestrateur

# Schéma de communication du fichier :
# backend/tests/test_v19_experts.py
#   ├── importe les routes, services et contrats du domaine testé
#   ├── utilise les fixtures partagées de backend/tests/conftest.py
#   └── est collecté par pytest dans la suite backend complète
