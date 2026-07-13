# Rôle du fichier :
# Ce fichier adapte une réponse team-history réelle vers les features attendues par les experts V15 et V17.8 V19.

from __future__ import annotations

from typing import Any

from app.services.ml_clubs_v17_8_feature_builder import compute_clubs_btts_features
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.experts.legacy_btts import build_legacy_btts_candidate
from app.v19.experts.legacy_over_15 import build_legacy_over_15_candidate


# Construit un dictionnaire commun contenant les noms historiques V15 et V17.8.
def build_legacy_expert_features(
    team_history_response: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(team_history_response, dict):
        raise TypeError("team_history_response must be a dict")

    features = compute_clubs_btts_features(team_history_response)
    min_history_count = features.get("min_history_count_last_10")

    return {
        **features,
        "combined_over_15_rate_last10": features.get(
            "combined_over_1_5_rate_last_10"
        ),
        "min_history_count_last10": min_history_count,
        "match_id": team_history_response.get("match_id"),
        "source_used": team_history_response.get("source_used"),
        "data_status": team_history_response.get("data_status"),
        "legacy_zero_defaults_used": min_history_count == 0,
    }


# Produit simultanément les candidats Over 1.5 et BTTS depuis une réponse team-history.
def build_legacy_expert_candidates(
    team_history_response: dict[str, Any],
) -> tuple[ExpertCandidateV1, ExpertCandidateV1]:
    features = build_legacy_expert_features(team_history_response)

    return (
        build_legacy_over_15_candidate(features),
        build_legacy_btts_candidate(features),
    )


# Schéma de communication :
# legacy_adapters.py
#   <- reçoit la réponse réelle de team_history_service.py
#   <- réutilise compute_clubs_btts_features() sans modifier le builder historique
#   -> fournit les aliases V15 à legacy_over_15.py
#   -> fournit les features V17.8 à legacy_btts.py
#   -> retourne deux candidats indépendants sans décision globale
