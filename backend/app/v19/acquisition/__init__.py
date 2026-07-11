# Rôle du fichier :
# Ce fichier déclare la couche d'acquisition H2H native de RubyBets V19.

# Schéma de communication :
# acquisition/__init__.py
#   -> regroupe flashscore_h2h_adapter.py et h2h_acquisition_service.py
#   -> dépend des contrats immuables de backend/app/v19/domain/
#   -> ne calcule aucune feature et ne produit aucune recommandation sportive
