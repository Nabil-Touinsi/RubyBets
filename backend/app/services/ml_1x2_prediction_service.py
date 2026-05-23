# Rôle du fichier :
# Ce service charge le modèle ML 1X2 sauvegardé et permet de produire une prédiction expérimentale.

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = PROJECT_ROOT / "models" / "ml" / "1x2" / "best_1x2_model.joblib"

FEATURE_COLUMNS = [
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_goals_scored_avg_last_5",
    "away_goals_scored_avg_last_5",
    "home_goals_conceded_avg_last_5",
    "away_goals_conceded_avg_last_5",
]


# Charge le modèle ML 1X2 une seule fois pour éviter de le relire à chaque prédiction.
@lru_cache(maxsize=1)
def load_1x2_model() -> Any:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modèle ML introuvable : {MODEL_PATH}")

    return joblib.load(MODEL_PATH)


# Vérifie que toutes les features nécessaires sont présentes avant prédiction.
def validate_1x2_features(features: dict[str, float]) -> None:
    missing_features = [
        column for column in FEATURE_COLUMNS if column not in features
    ]

    if missing_features:
        raise ValueError(
            f"Features manquantes pour la prédiction ML 1X2 : {missing_features}"
        )


# Transforme les features reçues en DataFrame dans le même ordre que l'entraînement.
def build_1x2_feature_frame(features: dict[str, float]) -> pd.DataFrame:
    validate_1x2_features(features)

    ordered_features = {
        column: [features[column]]
        for column in FEATURE_COLUMNS
    }

    return pd.DataFrame(ordered_features)


# Produit une prédiction expérimentale 1X2 à partir du modèle sauvegardé.
def predict_1x2_result(features: dict[str, float]) -> dict[str, Any]:
    model = load_1x2_model()
    feature_frame = build_1x2_feature_frame(features)

    predicted_class = model.predict(feature_frame)[0]

    probabilities = {}
    if hasattr(model, "predict_proba"):
        predicted_probabilities = model.predict_proba(feature_frame)[0]
        probabilities = {
            class_name: round(float(probability), 4)
            for class_name, probability in zip(model.classes_, predicted_probabilities)
        }

    return {
        "status": "experimental_ml_baseline",
        "model_name": "LogisticRegression_balanced",
        "target": "1X2",
        "predicted_class": predicted_class,
        "probabilities": probabilities,
        "features_used": FEATURE_COLUMNS,
        "model_artifact": "models/ml/1x2/best_1x2_model.joblib","responsible_note": "Baseline ML experimentale. Ne remplace pas le scoring explicable V1 et ne garantit aucun resultat sportif.",
        
    }


# Schéma de communication :
# ml_1x2_prediction_service.py
#   -> lit models/ml/1x2/best_1x2_model.joblib
#   -> reçoit 6 features numériques
#   -> retourne une prédiction expérimentale HOME_WIN / DRAW / AWAY_WIN
#   -> sera appelé plus tard par une route FastAPI dédiée