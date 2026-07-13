# Rôle du fichier :
# Ce fichier centralise le vocabulaire contrôlé de la décision finale RubyBets V19.

from __future__ import annotations

from enum import Enum


# États produit possibles après arbitrage de tous les candidats experts V19.
class DecisionStatus(str, Enum):
    RECOMMEND = "RECOMMEND"
    ABSTAIN = "ABSTAIN"


# Motifs standardisés expliquant pourquoi un candidat n'a pas été retenu.
class CandidateRejectionReason(str, Enum):
    HIGHER_PRIORITY_CANDIDATE_SELECTED = "HIGHER_PRIORITY_CANDIDATE_SELECTED"
    REPLACED_BY_BTTS_POLICY = "REPLACED_BY_BTTS_POLICY"
    CANDIDATE_INELIGIBLE = "CANDIDATE_INELIGIBLE"
    CANDIDATE_ERROR = "CANDIDATE_ERROR"


# Motif stable utilisé lorsque l'orchestrateur ne peut retenir aucun candidat.
class DecisionAbstentionReason(str, Enum):
    NO_ELIGIBLE_CANDIDATE = "NO_ELIGIBLE_CANDIDATE"


# Schéma de communication :
# decision_enums.py
#   -> fournit les statuts et motifs à decision_contracts.py
#   -> est utilisé par decision_orchestrator.py pour tracer l'arbitrage
#   -> ne dépend ni des fournisseurs, ni de FastAPI, ni du frontend
#   -> ne contient aucune règle sportive ni aucun seuil de marché
