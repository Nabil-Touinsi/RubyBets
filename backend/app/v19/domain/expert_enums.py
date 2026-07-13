# Rôle du fichier :
# Ce fichier centralise le vocabulaire contrôlé des candidats experts RubyBets V19.

from __future__ import annotations

from enum import Enum


# États possibles d'un candidat produit par un expert spécialisé.
class ExpertCandidateStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    ERROR = "ERROR"


# Marchés prioritaires pouvant être évalués par les experts V19 initiaux.
class ExpertMarketType(str, Enum):
    STRICT_1X2 = "STRICT_1X2"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    OVER_1_5 = "OVER_1_5"
    BTTS = "BTTS"


# Schéma de communication :
# expert_enums.py
#   -> fournit le vocabulaire contrôlé à expert_contracts.py
#   -> est utilisé par les futurs experts spécialisés et l'orchestrateur V19
#   -> ne dépend ni de FastAPI, ni des fournisseurs, ni du frontend
#   -> ne calcule aucune feature et ne produit aucune décision finale
