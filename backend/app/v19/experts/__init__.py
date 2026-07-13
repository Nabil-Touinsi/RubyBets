# Rôle du fichier :
# Ce fichier expose les premiers experts historiques encapsulés dans les contrats RubyBets V19.

from app.v19.experts.legacy_adapters import (
    build_legacy_expert_candidates,
    build_legacy_expert_features,
)
from app.v19.experts.legacy_btts import build_legacy_btts_candidate
from app.v19.experts.legacy_over_15 import build_legacy_over_15_candidate


__all__ = [
    "build_legacy_btts_candidate",
    "build_legacy_expert_candidates",
    "build_legacy_expert_features",
    "build_legacy_over_15_candidate",
]


# Schéma de communication :
# experts/__init__.py
#   -> expose les adapters et experts legacy au reste de backend/app/v19
#   -> ne contient aucune logique métier supplémentaire
#   -> sera consommé plus tard par le service applicatif et l'orchestrateur V19
