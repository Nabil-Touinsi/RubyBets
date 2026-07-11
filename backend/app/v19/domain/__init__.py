# Rôle du fichier :
# Ce fichier déclare le package contenant les contrats de domaine RubyBets V19.

# Schéma de communication :
# domain/
#   -> définit les contrats et vocabulaires indépendants des fournisseurs
#   -> est consommé par acquisition/, normalization/ et features/
#   -> ne dépend ni de FastAPI, ni de FlashScore, ni des moteurs historiques