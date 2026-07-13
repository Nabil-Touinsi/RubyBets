# Rôle du fichier :
# Ce package expose la projection d'explicabilité publique et déterministe de RubyBets V19.

from app.v19.explainability.explanation_builder import (
    EXPLANATION_CONTRACT_VERSION,
    build_public_explanation,
)

__all__ = [
    "EXPLANATION_CONTRACT_VERSION",
    "build_public_explanation",
]

# Schéma de communication :
# explanation_builder.py -> __init__.py -> route API expérimentale V19
