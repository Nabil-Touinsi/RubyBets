# Rôle du fichier :
# Ce fichier vérifie la normalisation FlashScore, les features V13 et les experts Market RubyBets V19.

from datetime import datetime, timezone
from math import isclose

from app.services.rapidapi_flashscore_client import encode_flashscore_match_id
from app.v19.acquisition.flashscore_odds_adapter import adapt_flashscore_odds_payload
from app.v19.acquisition.flashscore_odds_provider import (
    FLASHSCORE_ODDS_ENDPOINT,
    get_flashscore_match_odds,
    get_flashscore_match_odds_for_rubybets,
)
from app.v19.domain.expert_enums import ExpertCandidateStatus, ExpertMarketType
from app.v19.domain.market_contracts import MarketModuleStatus, MarketQualityFlag
from app.v19.experts.legacy_double_chance import build_legacy_double_chance_candidate
from app.v19.experts.legacy_strict_1x2 import build_legacy_strict_1x2_candidate
from app.v19.features.market_feature_builder import (
    build_market_feature_snapshot,
    market_features_to_dict,
)


FIXED_FETCHED_AT = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)
FIXED_COMPUTED_AT = datetime(2026, 7, 13, 8, 5, tzinfo=timezone.utc)
HOME_TEAM_ID = "home-1"
AWAY_TEAM_ID = "away-2"


# Construit les trois options 1X2 attendues par le mapping FlashScore validé.
def build_options(
    home_odd: float,
    draw_odd: float,
    away_odd: float,
    *,
    opening_home: float | None = None,
    opening_draw: float | None = None,
    opening_away: float | None = None,
    active: bool = True,
) -> list[dict[str, object]]:
    return [
        {
            "eventParticipantId": HOME_TEAM_ID,
            "value": home_odd,
            "opening": opening_home,
            "active": active,
        },
        {
            "eventParticipantId": None,
            "value": draw_odd,
            "opening": opening_draw,
            "active": active,
        },
        {
            "eventParticipantId": AWAY_TEAM_ID,
            "value": away_odd,
            "opening": opening_away,
            "active": active,
        },
    ]


# Construit un bookmaker FlashScore contenant un marché HOME_DRAW_AWAY / FULL_TIME.
def build_bookmaker(
    bookmaker_id: str,
    bookmaker_name: str,
    options: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "bookmaker": {
            "id": bookmaker_id,
            "name": bookmaker_name,
        },
        "markets": [
            {
                "marketType": "HOME_DRAW_AWAY",
                "period": "FULL_TIME",
                "options": options,
            }
        ],
    }


# Adapte un payload de test avec les identités de match communes aux scénarios.
def adapt_payload(payload: object):
    return adapt_flashscore_odds_payload(
        payload=payload,
        match_id="1813105023365578",
        source_match_id="AbC123",
        home_team_id=HOME_TEAM_ID,
        away_team_id=AWAY_TEAM_ID,
        fetched_at_utc=FIXED_FETCHED_AT,
    )


# Vérifie que le provider appelle exactement l'endpoint odds et transmet match_id.
def test_flashscore_odds_provider_calls_expected_endpoint() -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []

    def fake_client(endpoint: str, params: dict[str, object] | None):
        calls.append((endpoint, params))
        return {"data": []}

    payload, metadata = get_flashscore_match_odds("AbC123", client=fake_client)

    assert payload == {"data": []}
    assert calls == [(FLASHSCORE_ODDS_ENDPOINT, {"match_id": "AbC123"})]
    assert metadata["status"] == "success"


# Vérifie que le provider convertit une erreur HTTP maîtrisée en métadonnées sans exception.
def test_flashscore_odds_provider_preserves_controlled_error() -> None:
    def fake_client(endpoint: str, params: dict[str, object] | None):
        return {"status": "error", "status_code": 429, "message": "quota"}

    payload, metadata = get_flashscore_match_odds("AbC123", client=fake_client)

    assert payload is None
    assert metadata["status"] == "error"
    assert metadata["status_code"] == 429


# Vérifie que le wrapper RubyBets décode l'identifiant avant d'appeler FlashScore.
def test_flashscore_odds_provider_decodes_rubybets_match_id() -> None:
    rubybets_match_id = encode_flashscore_match_id("AbC123")
    observed_params: list[dict[str, object] | None] = []

    def fake_client(endpoint: str, params: dict[str, object] | None):
        observed_params.append(params)
        return []

    payload, metadata = get_flashscore_match_odds_for_rubybets(
        rubybets_match_id,
        client=fake_client,
    )

    assert payload == []
    assert observed_params == [{"match_id": "AbC123"}]
    assert metadata["rubybets_match_id"] == rubybets_match_id


# Vérifie le mapping domicile / nul / extérieur et la séparation current / opening.
def test_odds_adapter_normalizes_complete_current_and_opening_triplet() -> None:
    payload = [
        build_bookmaker(
            "bk-1",
            "Bookmaker One",
            build_options(
                2.0,
                4.0,
                5.0,
                opening_home=2.2,
                opening_draw=3.8,
                opening_away=4.8,
            ),
        ),
        build_bookmaker(
            "bk-2",
            "Bookmaker Two",
            build_options(
                2.1,
                3.9,
                4.7,
                opening_home=2.3,
                opening_draw=3.7,
                opening_away=4.6,
            ),
        ),
    ]

    result = adapt_payload(payload)

    assert result.status is MarketModuleStatus.READY
    assert result.bookmaker_count_total == 2
    assert result.bookmaker_count_eligible == 2
    assert result.quality_flags == ()
    first_triplet = result.triplets[0]
    assert first_triplet.bookmaker_id == "bk-1"
    assert isclose(
        first_triplet.current_home_probability
        + first_triplet.current_draw_probability
        + first_triplet.current_away_probability,
        1.0,
    )
    assert first_triplet.opening_home_probability is not None
    assert first_triplet.current_home_odd == 2.0
    assert first_triplet.opening_home_odd == 2.2


# Vérifie que le booléen opening sépare les enregistrements current et ouverture du fournisseur.
def test_odds_adapter_supports_boolean_opening_indicator() -> None:
    current_options = build_options(2.0, 4.0, 5.0)
    for option in current_options:
        option["opening"] = False

    opening_options = build_options(2.2, 3.8, 4.8, active=False)
    for option in opening_options:
        option["opening"] = True

    result = adapt_payload(
        [build_bookmaker("bk-1", "Boolean Opening", current_options + opening_options)]
    )

    assert result.bookmaker_count_eligible == 1
    triplet = result.triplets[0]
    assert triplet.current_home_odd == 2.0
    assert triplet.opening_home_odd == 2.2
    assert triplet.opening_home_probability is not None


# Vérifie qu'un bookmaker sans triplet complet est rejeté et tracé.
def test_odds_adapter_rejects_incomplete_triplet() -> None:
    incomplete_options = build_options(2.0, 4.0, 5.0)[:2]

    result = adapt_payload([build_bookmaker("bk-1", "Incomplete", incomplete_options)])

    assert result.status is MarketModuleStatus.UNAVAILABLE
    assert result.bookmaker_count_eligible == 0
    assert result.rejected_bookmakers == (("bk-1", "NO_VALID_MARKET_TRIPLET"),)
    assert MarketQualityFlag.NO_VALID_MARKET_TRIPLET in result.quality_flags


# Vérifie que les options explicitement inactives ne construisent pas de triplet exploitable.
def test_odds_adapter_excludes_inactive_options() -> None:
    result = adapt_payload(
        [build_bookmaker("bk-1", "Inactive", build_options(2.0, 4.0, 5.0, active=False))]
    )

    assert result.status is MarketModuleStatus.UNAVAILABLE
    assert result.bookmaker_count_eligible == 0


# Vérifie qu'un identifiant d'équipe inconnu bloque le bookmaker avec un code stable.
def test_odds_adapter_blocks_home_away_mapping_mismatch() -> None:
    options = build_options(2.0, 4.0, 5.0)
    options[2]["eventParticipantId"] = "unknown-team"

    result = adapt_payload([build_bookmaker("bk-1", "Mismatch", options)])

    assert result.status is MarketModuleStatus.INVALID
    assert result.rejected_bookmakers == (("bk-1", "HOME_AWAY_MAPPING_MISMATCH"),)
    assert MarketQualityFlag.HOME_AWAY_MAPPING_MISMATCH in result.quality_flags


# Vérifie qu'une option sans eventParticipantId n'est jamais interprétée comme le nul.
def test_odds_adapter_blocks_missing_participant_key() -> None:
    options = build_options(2.0, 4.0, 5.0)
    options[1].pop("eventParticipantId")

    result = adapt_payload([build_bookmaker("bk-1", "Ambiguous", options)])

    assert result.status is MarketModuleStatus.INVALID
    assert MarketQualityFlag.AMBIGUOUS_PARTICIPANT_MAPPING in result.quality_flags


# Vérifie qu'une cote inférieure ou égale à 1 est rejetée sans calcul de probabilité.
def test_odds_adapter_rejects_invalid_odd_value() -> None:
    result = adapt_payload(
        [build_bookmaker("bk-1", "Invalid", build_options(1.0, 4.0, 5.0))]
    )

    assert result.status is MarketModuleStatus.INVALID
    assert MarketQualityFlag.INVALID_ODD_VALUE in result.quality_flags


# Vérifie que deux sélections contradictoires pour la même issue bloquent le bookmaker.
def test_odds_adapter_rejects_duplicate_contradictory_selection() -> None:
    options = build_options(2.0, 4.0, 5.0)
    options.append(
        {
            "eventParticipantId": HOME_TEAM_ID,
            "value": 2.2,
            "opening": None,
            "active": True,
        }
    )

    result = adapt_payload([build_bookmaker("bk-1", "Duplicate", options)])

    assert result.status is MarketModuleStatus.INVALID
    assert MarketQualityFlag.DUPLICATE_CONTRADICTORY_SELECTION in result.quality_flags


# Vérifie que l'absence d'opening dégrade le module sans substituer les valeurs current.
def test_odds_adapter_marks_missing_opening_without_substitution() -> None:
    result = adapt_payload(
        [
            build_bookmaker("bk-1", "One", build_options(2.0, 4.0, 5.0)),
            build_bookmaker("bk-2", "Two", build_options(2.1, 3.9, 4.7)),
        ]
    )

    assert result.status is MarketModuleStatus.DEGRADED
    assert MarketQualityFlag.OPENING_ODDS_UNAVAILABLE in result.quality_flags
    assert all(item.opening_home_probability is None for item in result.triplets)


# Vérifie les neuf features V13 sur deux bookmakers et l'accord exact des favoris.
def test_market_feature_builder_reproduces_v13_consensus_and_agreement() -> None:
    result = adapt_payload(
        [
            build_bookmaker("bk-1", "Home Favorite", build_options(1.5, 4.0, 6.0)),
            build_bookmaker("bk-2", "Away Favorite", build_options(4.0, 3.5, 1.8)),
        ]
    )
    snapshot = build_market_feature_snapshot(result, computed_at_utc=FIXED_COMPUTED_AT)
    features = market_features_to_dict(snapshot)

    assert isclose(
        features["market_home_prob_avg"]
        + features["market_draw_prob_avg"]
        + features["market_away_prob_avg"],
        1.0,
    )
    assert features["market_available_triplets"] == 2
    assert features["market_bookmaker_agreement_score"] == 0.5
    assert features["v19_favorite_vote_share"] == 0.5
    assert features["market_entropy"] > 0.0
    assert features["v13_double_chance"] in {"1X", "X2", "12"}


# Vérifie que les mouvements opening/current sont calculés sans mélanger les snapshots.
def test_market_feature_builder_computes_opening_movements() -> None:
    result = adapt_payload(
        [
            build_bookmaker(
                "bk-1",
                "One",
                build_options(
                    1.5,
                    4.0,
                    6.0,
                    opening_home=3.5,
                    opening_draw=4.0,
                    opening_away=2.0,
                ),
            ),
            build_bookmaker(
                "bk-2",
                "Two",
                build_options(
                    1.6,
                    4.1,
                    5.8,
                    opening_home=3.6,
                    opening_draw=4.1,
                    opening_away=2.1,
                ),
            ),
        ]
    )
    snapshot = build_market_feature_snapshot(result, computed_at_utc=FIXED_COMPUTED_AT)
    features = market_features_to_dict(snapshot)

    assert features["v19_market_opening_home_prob"] is not None
    assert features["v19_home_prob_movement"] is not None
    assert features["v19_favorite_changed_since_opening"] is True
    assert MarketQualityFlag.FAVORITE_CHANGED in snapshot.quality_flags
    assert features["v19_odds_age_seconds"] == 300.0


# Vérifie qu'un module indisponible retourne les features legacy nulles sauf le compteur de triplets.
def test_market_feature_builder_preserves_missingness_when_unavailable() -> None:
    result = adapt_payload([])
    snapshot = build_market_feature_snapshot(result, computed_at_utc=FIXED_COMPUTED_AT)
    features = market_features_to_dict(snapshot)

    assert snapshot.status is MarketModuleStatus.UNAVAILABLE
    assert features["market_available_triplets"] == 0
    assert features["market_home_prob_avg"] is None
    assert features["market_favorite_prob"] is None


# Vérifie que le seuil exact 0,80 / 0,10 produit un candidat 1X2 strict éligible.
def test_strict_1x2_expert_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_strict_1x2_candidate(
        {
            "market_favorite_prob": 0.80,
            "market_margin_top1_top2": 0.10,
            "v13_strict_prediction": "HOME_WIN",
        }
    )

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.STRICT_1X2
    assert candidate.recommendation_value == "HOME_WIN"
    assert candidate.raw_score == 0.80
    assert candidate.calibrated_probability is None


# Vérifie que le nul reste interdit par la politique stricte V13.1.
def test_strict_1x2_expert_rejects_draw_even_with_strong_probability() -> None:
    candidate = build_legacy_strict_1x2_candidate(
        {
            "market_favorite_prob": 0.85,
            "market_margin_top1_top2": 0.20,
            "v13_strict_prediction": "DRAW",
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "DRAW_NOT_ALLOWED_BY_V13_1_STRICT_POLICY" in candidate.caution_reasons


# Vérifie que le strict déclare les features manquantes plutôt que d'inventer un score.
def test_strict_1x2_expert_reports_missing_features() -> None:
    candidate = build_legacy_strict_1x2_candidate({})

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.raw_score is None
    assert candidate.missing_features == (
        "market_favorite_prob",
        "market_margin_top1_top2",
        "v13_strict_prediction",
    )


# Vérifie que les seuils exacts Double Chance produisent un candidat éligible hors priorité stricte.
def test_double_chance_expert_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_double_chance_candidate(
        {
            "market_top2_sum": 0.76,
            "market_entropy": 1.07,
            "market_available_triplets": 1,
            "market_bookmaker_agreement_score": 0.00,
            "v13_double_chance": "1X",
            "market_favorite_prob": 0.70,
            "market_margin_top1_top2": 0.05,
            "v13_strict_prediction": "HOME_WIN",
        }
    )

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.DOUBLE_CHANCE
    assert candidate.recommendation_value == "1X"
    assert candidate.raw_score == 0.76


# Vérifie que Double Chance s'efface lorsque le strict possède la priorité historique.
def test_double_chance_expert_respects_strict_historical_priority() -> None:
    candidate = build_legacy_double_chance_candidate(
        {
            "market_top2_sum": 0.85,
            "market_entropy": 0.70,
            "market_available_triplets": 3,
            "market_bookmaker_agreement_score": 1.0,
            "v13_double_chance": "1X",
            "market_favorite_prob": 0.80,
            "market_margin_top1_top2": 0.10,
            "v13_strict_prediction": "HOME_WIN",
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "STRICT_1X2_HAS_HISTORICAL_PRIORITY" in candidate.caution_reasons


# Vérifie que Double Chance refuse une entropie supérieure au maximum V13.1.
def test_double_chance_expert_rejects_high_entropy() -> None:
    candidate = build_legacy_double_chance_candidate(
        {
            "market_top2_sum": 0.80,
            "market_entropy": 1.071,
            "market_available_triplets": 2,
            "market_bookmaker_agreement_score": 0.50,
            "v13_double_chance": "X2",
            "market_favorite_prob": 0.60,
            "market_margin_top1_top2": 0.04,
            "v13_strict_prediction": "AWAY_WIN",
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "ENTROPY_ABOVE_V13_1_MAXIMUM" in candidate.caution_reasons


# Vérifie de bout en bout qu'un consensus très fort active le strict et bloque Double Chance.
def test_market_pipeline_builds_strict_candidate_before_double_chance() -> None:
    payload = [
        build_bookmaker(
            f"bk-{index}",
            f"Bookmaker {index}",
            build_options(1.05, 15.0, 20.0),
        )
        for index in range(3)
    ]
    normalization = adapt_payload(payload)
    snapshot = build_market_feature_snapshot(normalization, computed_at_utc=FIXED_COMPUTED_AT)
    features = market_features_to_dict(snapshot)

    strict_candidate = build_legacy_strict_1x2_candidate(features)
    double_candidate = build_legacy_double_chance_candidate(features)

    assert strict_candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert strict_candidate.recommendation_value == "HOME_WIN"
    assert double_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "STRICT_1X2_HAS_HISTORICAL_PRIORITY" in double_candidate.caution_reasons


# Vérifie que le pipeline ne produit aucun candidat Market lorsque les odds sont absentes.
def test_market_pipeline_abstains_locally_when_no_valid_triplet_exists() -> None:
    normalization = adapt_payload([])
    snapshot = build_market_feature_snapshot(normalization, computed_at_utc=FIXED_COMPUTED_AT)
    features = market_features_to_dict(snapshot)

    strict_candidate = build_legacy_strict_1x2_candidate(features)
    double_candidate = build_legacy_double_chance_candidate(features)

    assert strict_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert double_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert strict_candidate.recommendation_value is None
    assert double_candidate.recommendation_value is None


# Schéma de communication :
# test_v19_market_module.py
#   -> teste flashscore_odds_provider.py et flashscore_odds_adapter.py
#   -> protège les formules V13 de market_feature_builder.py
#   -> vérifie legacy_strict_1x2.py et legacy_double_chance.py
#   -> garantit que les odds restent internes et qu'aucune décision globale n'est produite
