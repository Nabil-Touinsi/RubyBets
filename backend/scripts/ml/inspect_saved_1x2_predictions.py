# Rôle du fichier : inspecter les prédictions du modèle ML 1X2 sauvegardé match par match et générer une preuve lisible de fiabilité.

from pathlib import Path
import os

import joblib
import pandas as pd
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
MODEL_PATH = PROJECT_ROOT / "models" / "ml" / "1x2" / "best_1x2_model.joblib"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
INSPECTION_CSV_PATH = REPORT_DIR / "30_saved_1x2_predictions_inspection.csv"
SUMMARY_PATH = REPORT_DIR / "31_saved_1x2_reliability_summary.txt"

FEATURE_COLUMNS = [
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_goals_scored_avg_last_5",
    "away_goals_scored_avg_last_5",
    "home_goals_conceded_avg_last_5",
    "away_goals_conceded_avg_last_5",
]

TARGET_COLUMN = "target_result"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TARGET_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]


# Charge les variables du fichier backend/.env si elles ne sont pas déjà disponibles.
def load_backend_env() -> None:
    if not BACKEND_ENV_PATH.exists():
        return

    for line in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# Récupère l’URL PostgreSQL depuis l’environnement.
def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL introuvable. Vérifie la session PowerShell ou backend/.env."
        )

    return database_url


# Crée le dossier de preuves ML si nécessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Recharge le modèle 1X2 sauvegardé sans relancer l’entraînement.
def load_saved_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modèle ML introuvable : {MODEL_PATH}")

    return joblib.load(MODEL_PATH)


# Charge les matchs de test avec équipes, résultat réel et features officielles.
def load_ml_dataset(database_url: str) -> pd.DataFrame:
    query = f"""
        SELECT
            f.id AS feature_id,
            f.clean_match_id,
            cm.match_date,
            cm.league_code,
            cm.season,
            cm.home_team,
            cm.away_team,
            cm.result AS actual_result,
            {", ".join([f"f.{column}" for column in FEATURE_COLUMNS])},
            f.{TARGET_COLUMN}
        FROM ml.features f
        JOIN ml.clean_matches cm ON cm.id = f.clean_match_id
        WHERE f.{TARGET_COLUMN} IS NOT NULL
        ORDER BY cm.match_date ASC, f.id ASC;
    """

    with psycopg.connect(database_url) as connection:
        return pd.read_sql(query, connection)


# Prépare le dataset en supprimant les lignes dont les features sont incomplètes.
def prepare_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    rows_before = len(dataset)
    prepared_dataset = dataset.copy()

    for column in FEATURE_COLUMNS:
        prepared_dataset[column] = pd.to_numeric(
            prepared_dataset[column],
            errors="coerce",
        )

    prepared_dataset = prepared_dataset.dropna(
        subset=FEATURE_COLUMNS + [TARGET_COLUMN]
    ).copy()

    rows_removed = rows_before - len(prepared_dataset)

    return prepared_dataset, rows_removed


# Isole les saisons de test utilisées pour évaluer la baseline ML.
def filter_test_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    return dataset[dataset["season"].isin(TEST_SEASONS)].copy()


# Récupère les classes connues par le modèle sauvegardé.
def get_model_classes(model) -> list[str]:
    if hasattr(model, "classes_"):
        return list(model.classes_)

    if hasattr(model, "named_steps"):
        classifier = model.named_steps.get("classifier")
        if classifier is not None and hasattr(classifier, "classes_"):
            return list(classifier.classes_)

    raise RuntimeError("Impossible de récupérer les classes du modèle sauvegardé.")


# Produit un niveau simple à partir de la probabilité maximale.
def build_probability_bucket(max_probability: float) -> str:
    if max_probability >= 0.70:
        return "very_high"
    if max_probability >= 0.60:
        return "high"
    if max_probability >= 0.50:
        return "medium"
    if max_probability >= 0.40:
        return "low"
    return "very_low"


# Génère le tableau d’inspection match par match.
def build_predictions_inspection(model, test_dataset: pd.DataFrame) -> pd.DataFrame:
    x_test = test_dataset[FEATURE_COLUMNS]
    predicted_results = model.predict(x_test)

    if not hasattr(model, "predict_proba"):
        raise RuntimeError("Le modèle sauvegardé ne permet pas predict_proba.")

    model_classes = get_model_classes(model)
    probability_rows = model.predict_proba(x_test)

    inspection_rows = []

    for index, (_, row) in enumerate(test_dataset.iterrows()):
        probabilities = {
            class_name: float(probability)
            for class_name, probability in zip(model_classes, probability_rows[index])
        }

        predicted_result = predicted_results[index]
        actual_result = row["actual_result"]
        max_probability = max(probabilities.values())

        inspection_rows.append(
            {
                "feature_id": row["feature_id"],
                "clean_match_id": row["clean_match_id"],
                "match_date": row["match_date"],
                "league_code": row["league_code"],
                "season": row["season"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "match": f"{row['home_team']} vs {row['away_team']}",
                "actual_result": actual_result,
                "predicted_result": predicted_result,
                "prob_home_win": round(probabilities.get("HOME_WIN", 0.0), 4),
                "prob_draw": round(probabilities.get("DRAW", 0.0), 4),
                "prob_away_win": round(probabilities.get("AWAY_WIN", 0.0), 4),
                "max_probability": round(max_probability, 4),
                "probability_bucket": build_probability_bucket(max_probability),
                "correct": predicted_result == actual_result,
            }
        )

    return pd.DataFrame(inspection_rows)


# Construit un tableau texte court avec nombre, bonnes prédictions et précision.
def build_accuracy_table(dataframe: pd.DataFrame, group_column: str) -> str:
    grouped = (
        dataframe.groupby(group_column)
        .agg(
            rows=("correct", "size"),
            correct_predictions=("correct", "sum"),
            accuracy=("correct", "mean"),
        )
        .reset_index()
    )

    grouped["accuracy"] = grouped["accuracy"].round(4)

    return grouped.to_string(index=False)


# Construit une lecture métier courte de la fiabilité du modèle.
def build_reliability_summary(
    dataset: pd.DataFrame,
    prepared_dataset: pd.DataFrame,
    rows_removed: int,
    test_dataset: pd.DataFrame,
    inspection: pd.DataFrame,
) -> str:
    total_predictions = len(inspection)
    correct_predictions = int(inspection["correct"].sum())
    accuracy = correct_predictions / total_predictions if total_predictions else 0

    confusion_table = pd.crosstab(
        inspection["actual_result"],
        inspection["predicted_result"],
        rownames=["actual_result"],
        colnames=["predicted_result"],
        dropna=False,
    )

    strongest_predictions = inspection.sort_values(
        by="max_probability",
        ascending=False,
    ).head(10)

    strongest_view = strongest_predictions[
        [
            "match_date",
            "league_code",
            "match",
            "actual_result",
            "predicted_result",
            "max_probability",
            "correct",
        ]
    ].to_string(index=False)

    lines = [
        "RubyBets - Saved ML 1X2 predictions inspection",
        "31 - Synthese de fiabilite lisible",
        "",
        "Positionnement :",
        "Cette inspection concerne la baseline ML 1X2 experimentale.",
        "Elle ne remplace pas le scoring explicable V1 et ne garantit aucun resultat sportif.",
        "",
        "Dataset control:",
        f"Rows loaded from PostgreSQL: {len(dataset)}",
        f"Rows removed because of missing features: {rows_removed}",
        f"Rows remaining after preparation: {len(prepared_dataset)}",
        f"Test seasons: {', '.join(TEST_SEASONS)}",
        f"Test rows inspected: {len(test_dataset)}",
        "",
        "Global reliability:",
        f"Total predictions inspected: {total_predictions}",
        f"Correct predictions: {correct_predictions}",
        f"Accuracy from inspection: {accuracy:.4f}",
        "",
        "Accuracy by actual result:",
        build_accuracy_table(inspection, "actual_result"),
        "",
        "Accuracy by predicted result:",
        build_accuracy_table(inspection, "predicted_result"),
        "",
        "Accuracy by probability bucket:",
        build_accuracy_table(inspection, "probability_bucket"),
        "",
        "Confusion table:",
        confusion_table.to_string(),
        "",
        "Top 10 strongest predictions by model probability:",
        strongest_view,
        "",
        "Business reading:",
        "- Le fichier CSV permet de voir chaque match, la prediction, les probabilites et si le modele a eu raison.",
        "- La fiabilite doit etre lue comme une preuve experimentale, pas comme une promesse produit.",
        "- Les matchs nuls restent une classe difficile a predire et doivent etre analyses avec prudence.",
        "- Le modele peut etre defendu comme baseline ML technique, mais il ne remplace pas encore le scoring explicable V1.",
        "",
        "Generated files:",
        str(INSPECTION_CSV_PATH.relative_to(PROJECT_ROOT)),
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde le tableau CSV d’inspection.
def save_predictions_inspection(inspection: pd.DataFrame) -> None:
    inspection.to_csv(
        INSPECTION_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )


# Sauvegarde la synthèse texte de fiabilité.
def save_reliability_summary(content: str) -> None:
    SUMMARY_PATH.write_text(content, encoding="utf-8")


# Orchestre l’inspection concrète des prédictions du modèle sauvegardé.
def main() -> None:
    ensure_report_dir()
    load_backend_env()

    database_url = get_database_url()
    dataset = load_ml_dataset(database_url)
    prepared_dataset, rows_removed = prepare_dataset(dataset)
    test_dataset = filter_test_dataset(prepared_dataset)

    if test_dataset.empty:
        raise RuntimeError(
            f"Aucune ligne trouvée pour les saisons de test : {TEST_SEASONS}"
        )

    model = load_saved_model()
    inspection = build_predictions_inspection(model, test_dataset)
    summary = build_reliability_summary(
        dataset,
        prepared_dataset,
        rows_removed,
        test_dataset,
        inspection,
    )

    save_predictions_inspection(inspection)
    save_reliability_summary(summary)

    total_predictions = len(inspection)
    correct_predictions = int(inspection["correct"].sum())
    accuracy = correct_predictions / total_predictions if total_predictions else 0

    print("OK - Saved ML 1X2 predictions inspected.")
    print(f"Predictions inspected: {total_predictions}")
    print(f"Correct predictions: {correct_predictions}")
    print(f"Accuracy: {accuracy:.4f}")
    print("CSV saved: reports/evidence/ml_training/30_saved_1x2_predictions_inspection.csv")
    print("Summary saved: reports/evidence/ml_training/31_saved_1x2_reliability_summary.txt")


if __name__ == "__main__":
    main()


# Schéma de communication :
# inspect_saved_1x2_predictions.py
#   -> lit backend/.env pour DATABASE_URL
#   -> lit PostgreSQL : ml.features + ml.clean_matches
#   -> recharge models/ml/1x2/best_1x2_model.joblib
#   -> applique les 6 features officielles de la baseline 1X2
#   -> filtre les saisons de test 2022_2023, 2023_2024, 2024_2025
#   -> compare prediction ML et resultat reel match par match
#   -> écrit reports/evidence/ml_training/30_saved_1x2_predictions_inspection.csv
#   -> écrit reports/evidence/ml_training/31_saved_1x2_reliability_summary.txt