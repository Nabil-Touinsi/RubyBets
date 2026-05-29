# Rôle du fichier : exporter les prédictions ML 1X2 V3 à forte confiance, avec le meilleur signal V3 observé, sans modifier la base, l'API, le frontend ou le modèle officiel RubyBets.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

CSV_OUTPUT_PATH = REPORT_DIR / "53_1x2_v3_high_confidence_predictions.csv"
SUMMARY_OUTPUT_PATH = REPORT_DIR / "54_1x2_v3_high_confidence_summary.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v3_feature_groups import (  # noqa: E402
    FEATURE_GROUPS,
    HOME_AWAY_CONTEXT_COLUMNS,
    V2_CANDIDATE_ACCURACY,
    V2_CANDIDATE_DRAW_RECALL,
    V2_CANDIDATE_F1_MACRO,
    build_candidate_models,
    build_v3_feature_dataframe,
)

warnings.filterwarnings("ignore", category=UserWarning)

FEATURE_GROUP_NAME = "v2_reference_plus_home_away_context"
MODEL_NAME = "XGBoost"
CONFIDENCE_THRESHOLD = 0.62
REFERENCE_V3_HIGH_CONFIDENCE_ACCURACY = 0.7006
REFERENCE_V3_HIGH_CONFIDENCE_COVERAGE = 0.2615

LABEL_MAPPING = {
    "AWAY_WIN": 0,
    "DRAW": 1,
    "HOME_WIN": 2,
}
REVERSE_LABEL_MAPPING = {value: key for key, value in LABEL_MAPPING.items()}

METADATA_COLUMNS = [
    "clean_match_id",
    "match_date",
    "league_code",
    "season",
    "home_team",
    "away_team",
]

PREDICTION_COLUMNS = [
    "match",
    "actual_result",
    "predicted_result",
    "prob_home_win",
    "prob_draw",
    "prob_away_win",
    "max_probability",
    "correct",
]

V2_READABLE_COLUMNS = [
    "home_form_points_last_10",
    "away_form_points_last_10",
    "form_points_diff",
    "abs_form_points_diff",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "goals_scored_diff",
    "abs_goals_scored_diff",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
    "goals_conceded_diff",
    "abs_goals_conceded_diff",
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "draw_profile_score_with_strength",
]

EXPORT_COLUMNS = METADATA_COLUMNS + PREDICTION_COLUMNS + V2_READABLE_COLUMNS + HOME_AWAY_CONTEXT_COLUMNS


# Vérifie que la configuration d'export correspond bien au meilleur signal V3 identifié dans les fichiers 50 à 52.
def validate_configuration() -> None:
    if FEATURE_GROUP_NAME not in FEATURE_GROUPS:
        raise RuntimeError(f"Feature group introuvable : {FEATURE_GROUP_NAME}")

    candidate_models = build_candidate_models()

    if MODEL_NAME not in candidate_models:
        raise RuntimeError(
            "XGBoost n'est pas disponible dans l'environnement actuel. "
            "Installe xgboost ou relance l'export avec un modèle disponible."
        )


# Convertit les colonnes de features en numérique et prépare le split chronologique train/test.
def prepare_train_test_export(
    feature_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, list[str]]:
    feature_columns = FEATURE_GROUPS[FEATURE_GROUP_NAME]
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le DataFrame V3 : {missing_columns}")

    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees V3.")

    x_train = train_dataframe[feature_columns]
    y_train = train_dataframe[TARGET_COLUMN]
    x_test = test_dataframe[feature_columns]
    y_test = test_dataframe[TARGET_COLUMN]

    return x_train, y_train, x_test, y_test, test_dataframe, feature_columns


# Entraîne le modèle XGBoost retenu en mémoire avec les labels numériques attendus par la librairie.
def train_xgboost_model(x_train: pd.DataFrame, y_train: pd.Series):
    candidate_models = build_candidate_models()
    model = clone(candidate_models[MODEL_NAME])
    y_train_encoded = y_train.map(LABEL_MAPPING)

    if y_train_encoded.isna().any():
        raise RuntimeError("Certains labels ne correspondent pas au mapping 1X2 attendu.")

    model.fit(x_train, y_train_encoded)

    return model


# Reconvertit les prédictions numériques XGBoost en labels métier RubyBets.
def decode_predictions(raw_predictions) -> pd.Series:
    return pd.Series([REVERSE_LABEL_MAPPING[int(prediction)] for prediction in raw_predictions])


# Construit les colonnes de probabilités avec l'ordre explicite AWAY/DRAW/HOME de XGBoost.
def build_probability_dataframe(probabilities) -> pd.DataFrame:
    probability_dataframe = pd.DataFrame(
        probabilities,
        columns=["prob_away_win", "prob_draw", "prob_home_win"],
    )

    return probability_dataframe[["prob_home_win", "prob_draw", "prob_away_win"]]


# Construit le tableau complet des prédictions test avec métadonnées, probabilités et features lisibles.
def build_predictions_dataframe(
    model,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    test_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    raw_predictions = model.predict(x_test)
    predictions = decode_predictions(raw_predictions).reset_index(drop=True)
    probabilities = model.predict_proba(x_test)
    probability_dataframe = build_probability_dataframe(probabilities)

    useful_feature_columns = [column for column in feature_columns if column in EXPORT_COLUMNS]
    output_dataframe = test_dataframe[METADATA_COLUMNS + useful_feature_columns].reset_index(drop=True)

    output_dataframe["match"] = output_dataframe["home_team"] + " vs " + output_dataframe["away_team"]
    output_dataframe["actual_result"] = y_test.reset_index(drop=True)
    output_dataframe["predicted_result"] = predictions
    output_dataframe = pd.concat([output_dataframe, probability_dataframe], axis=1)

    probability_columns = ["prob_home_win", "prob_draw", "prob_away_win"]
    output_dataframe["max_probability"] = output_dataframe[probability_columns].max(axis=1)
    output_dataframe["correct"] = output_dataframe["actual_result"] == output_dataframe["predicted_result"]

    ordered_columns = [column for column in EXPORT_COLUMNS if column in output_dataframe.columns]

    return output_dataframe[ordered_columns]


# Filtre uniquement les matchs dont la probabilité maximale atteint le seuil V3 retenu.
def filter_high_confidence_predictions(predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    high_confidence = predictions_dataframe[
        predictions_dataframe["max_probability"] >= CONFIDENCE_THRESHOLD
    ].copy()

    high_confidence = high_confidence.sort_values(
        by=["max_probability", "match_date"],
        ascending=[False, True],
    )

    numeric_columns = [
        column
        for column in high_confidence.columns
        if column.startswith("prob_")
        or column.startswith("home_")
        or column.startswith("away_")
        or column.endswith("_diff")
        or column.endswith("_score")
        or column.endswith("_strength")
        or column == "max_probability"
    ]

    for column in numeric_columns:
        if column in high_confidence.columns:
            high_confidence[column] = pd.to_numeric(high_confidence[column], errors="coerce").round(4)

    return high_confidence


# Calcule une distribution HOME_WIN / DRAW / AWAY_WIN à partir d'une colonne de résultats.
def calculate_distribution(values: pd.Series) -> dict[str, int]:
    value_counts = values.value_counts().to_dict()

    return {
        "HOME_WIN": int(value_counts.get("HOME_WIN", 0)),
        "DRAW": int(value_counts.get("DRAW", 0)),
        "AWAY_WIN": int(value_counts.get("AWAY_WIN", 0)),
    }


# Construit le texte de synthèse de l'export V3 forte confiance.
def build_summary(
    clean_matches: list[dict],
    feature_dataframe: pd.DataFrame,
    high_confidence: pd.DataFrame,
    train_rows: int,
    test_rows: int,
    feature_columns: list[str],
) -> str:
    selected_rows = len(high_confidence)
    correct_predictions = int(high_confidence["correct"].sum()) if selected_rows else 0
    accuracy = accuracy_score(high_confidence["actual_result"], high_confidence["predicted_result"]) if selected_rows else 0
    coverage = selected_rows / test_rows if test_rows else 0
    predicted_distribution = calculate_distribution(high_confidence["predicted_result"]) if selected_rows else {}
    actual_distribution = calculate_distribution(high_confidence["actual_result"]) if selected_rows else {}

    lines = [
        "RubyBets - ML 1X2 V3 high-confidence predictions export",
        "54 - Synthese de l'export forte confiance V3",
        "",
        "Positionnement :",
        "Cet export documente uniquement la piste V3 utile en forte confiance.",
        "Il ne remplace pas la baseline officielle, ne sauvegarde pas de candidat V3, ne modifie pas PostgreSQL, l'API ou le frontend.",
        "Le scoring explicable V1 reste le socle produit.",
        "",
        "Configuration retenue :",
        f"- Feature group : {FEATURE_GROUP_NAME}",
        f"- Model : {MODEL_NAME}",
        f"- Confidence threshold : {CONFIDENCE_THRESHOLD}",
        "- Objectif : exporter les matchs selectionnes par le meilleur signal high-confidence observe dans l'experimentation V3.",
        "",
        "Reference V2 globale :",
        f"- Accuracy V2 : {V2_CANDIDATE_ACCURACY:.4f}",
        f"- F1 macro V2 : {V2_CANDIDATE_F1_MACRO:.4f}",
        f"- DRAW recall V2 : {V2_CANDIDATE_DRAW_RECALL:.4f}",
        "",
        "Reference V3 forte confiance observee dans le fichier 52 :",
        f"- Accuracy forte confiance : {REFERENCE_V3_HIGH_CONFIDENCE_ACCURACY:.4f}",
        f"- Coverage forte confiance : {REFERENCE_V3_HIGH_CONFIDENCE_COVERAGE:.4f}",
        "- Limite observee : 0 prediction DRAW en forte confiance.",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features construites : {len(feature_dataframe)}",
        f"- Train rows : {train_rows}",
        f"- Test rows : {test_rows}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Resultat export forte confiance V3 :",
        f"- Selected rows : {selected_rows}",
        f"- Coverage : {coverage:.4f}",
        f"- Correct predictions : {correct_predictions}",
        f"- Accuracy : {accuracy:.4f}",
        f"- Predicted HOME_WIN rows : {predicted_distribution.get('HOME_WIN', 0)}",
        f"- Predicted DRAW rows : {predicted_distribution.get('DRAW', 0)}",
        f"- Predicted AWAY_WIN rows : {predicted_distribution.get('AWAY_WIN', 0)}",
        f"- Actual HOME_WIN rows : {actual_distribution.get('HOME_WIN', 0)}",
        f"- Actual DRAW rows : {actual_distribution.get('DRAW', 0)}",
        f"- Actual AWAY_WIN rows : {actual_distribution.get('AWAY_WIN', 0)}",
        "",
        "Features utilisees :",
        *[f"- {column}" for column in feature_columns],
        "",
        "Lecture metier :",
        "- La V3 n'est pas meilleure que la V2 comme modele general 1X2.",
        "- La piste home/away context + XGBoost est utile seulement pour isoler des matchs a forte confiance.",
        "- L'absence de predictions DRAW en forte confiance reste une limite forte.",
        "- Ce resultat peut servir de preuve experimentale, pas de fonctionnalite produit finale.",
        "",
        "Generated files :",
        str(CSV_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        str(SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde le CSV détaillé et le résumé TXT dans reports/evidence/ml_training.
def save_reports(high_confidence: pd.DataFrame, summary: str) -> None:
    high_confidence.to_csv(CSV_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_OUTPUT_PATH.write_text(summary, encoding="utf-8")


# Orchestre l'export des prédictions V3 à forte confiance.
def main() -> None:
    try:
        ensure_report_dir()
        validate_configuration()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features V3 en memoire...", flush=True)

        feature_dataframe = build_v3_feature_dataframe(clean_matches)

        x_train, y_train, x_test, y_test, test_dataframe, feature_columns = prepare_train_test_export(
            feature_dataframe=feature_dataframe,
        )

        print(f"Train rows : {len(x_train)}", flush=True)
        print(f"Test rows : {len(x_test)}", flush=True)
        print(f"Entrainement du modele {MODEL_NAME} sur {FEATURE_GROUP_NAME}...", flush=True)

        model = train_xgboost_model(x_train=x_train, y_train=y_train)

        predictions_dataframe = build_predictions_dataframe(
            model=model,
            x_test=x_test,
            y_test=y_test,
            test_dataframe=test_dataframe,
            feature_columns=feature_columns,
        )

        high_confidence = filter_high_confidence_predictions(predictions_dataframe)
        summary = build_summary(
            clean_matches=clean_matches,
            feature_dataframe=feature_dataframe,
            high_confidence=high_confidence,
            train_rows=len(x_train),
            test_rows=len(x_test),
            feature_columns=feature_columns,
        )

        save_reports(high_confidence=high_confidence, summary=summary)

        selected_rows = len(high_confidence)
        correct_predictions = int(high_confidence["correct"].sum()) if selected_rows else 0
        accuracy = correct_predictions / selected_rows if selected_rows else 0
        coverage = selected_rows / len(x_test) if len(x_test) else 0
        predicted_draw_rows = int((high_confidence["predicted_result"] == "DRAW").sum()) if selected_rows else 0

        print("OK - Export des predictions forte confiance V3 termine.", flush=True)
        print(f"Feature group: {FEATURE_GROUP_NAME}", flush=True)
        print(f"Model: {MODEL_NAME}", flush=True)
        print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}", flush=True)
        print(f"Selected rows: {selected_rows}", flush=True)
        print(f"Coverage: {coverage:.4f}", flush=True)
        print(f"Correct predictions: {correct_predictions}", flush=True)
        print(f"Accuracy: {accuracy:.4f}", flush=True)
        print(f"Predicted DRAW rows: {predicted_draw_rows}", flush=True)
        print("CSV saved: reports/evidence/ml_training/53_1x2_v3_high_confidence_predictions.csv", flush=True)
        print("Summary saved: reports/evidence/ml_training/54_1x2_v3_high_confidence_summary.txt", flush=True)

    except Exception as error:
        print("Erreur pendant l'export forte confiance V3.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# export_1x2_v3_high_confidence_predictions.py
# ├── réutilise experiment_1x2_v3_feature_groups.py pour reconstruire les features V3
# ├── réutilise compare_1x2_feature_sets.py pour lire PostgreSQL et les constantes ML
# ├── lit backend/.env pour DATABASE_URL sans afficher de secret
# ├── lit PostgreSQL : ml.clean_matches
# ├── entraîne XGBoost en mémoire sur v2_reference_plus_home_away_context
# ├── filtre les matchs avec max_probability >= 0.62
# ├── ne modifie pas ml.features, l'API, le frontend ou models/ml/1x2/best_1x2_model.joblib
# ├── écrit reports/evidence/ml_training/53_1x2_v3_high_confidence_predictions.csv
# └── écrit reports/evidence/ml_training/54_1x2_v3_high_confidence_summary.txt
