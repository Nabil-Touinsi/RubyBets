# Rôle du fichier :
# Ce fichier déclare la couche de construction des features H2H RubyBets V19.

# Schéma de communication :
# features/__init__.py
#   -> regroupe h2h_feature_catalog.py et h2h_feature_builder.py
#   -> consomme les contrats immuables de backend/app/v19/domain/
#   -> reçoit H2HModuleInputV1 depuis backend/app/v19/acquisition/
#   -> ne produit aucune recommandation sportive
