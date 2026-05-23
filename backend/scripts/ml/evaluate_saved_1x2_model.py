# Rôle du fichier : recharger le modèle ML 1X2 sauvegardé, l’évaluer sans réentraînement et générer une preuve RubyBets.

from pathlib import Path
import os

import joblib
import pandas as pd
import psycopg

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
MODEL_PATH = PROJECT_ROOT / "models" / "ml" / "1x2" / "best_1x2_model.joblib"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
REPORT_PATH = REPORT_DIR / "28_saved_1x2_model_evaluation.txt"

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


# Charge les features ML et les métadonnées nécessaires depuis PostgreSQL.
def load_ml_dataset(database_url: str) -> pd.DataFrame:
    query = f"""
        SELECT
            f.id,
            f.clean_match_id,
            cm.match_date,
            cm.league_code,
            cm.season,
            {", ".join([f"f.{column}" for column in FEATURE_COLUMNS])},
            f.{TARGET_COLUMN}
        FROM ml.features f
        JOIN ml.clean_matches cm ON cm.id = f.clean_match_id
        WHERE f.{TARGET_COLUMN} IS NOT NULL
        ORDER BY cm.match_date ASC, f.id ASC;
    """

    with psycopg.connect(database_url) as connection:
        return pd.read_sql(query, connection)


# Prépare le dataset en supprimant les lignes avec features manquantes.
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


# Isole les saisons de test utilisées pendant l’entraînement initial.
def filter_test_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    return dataset[dataset["season"].isin(TEST_SEASONS)].copy()


# Recharge le modèle 1X2 sauvegardé sans relancer l’entraînement.
def load_saved_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modèle ML introuvable : {MODEL_PATH}")

    return joblib.load(MODEL_PATH)


# Évalue le modèle sauvegardé sur les saisons de test.
def evaluate_saved_model(model, test_dataset: pd.DataFrame) -> dict:
    x_test = test_dataset[FEATURE_COLUMNS]
    y_test = test_dataset[TARGET_COLUMN]
    y_pred = model.predict(x_test)

    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    matrix = confusion_matrix(y_test, y_pred, labels=TARGET_LABELS)
    report = classification_report(
        y_test,
        y_pred,
        labels=TARGET_LABELS,
        zero_division=0,
    )

    return {
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "confusion_matrix": matrix,
        "classification_report": report,
    }


# Construit le contenu texte de la preuve d’évaluation.
def build_evaluation_report(
    dataset: pd.DataFrame,
    prepared_dataset: pd.DataFrame,
    rows_removed: int,
    test_dataset: pd.DataFrame,
    evaluation: dict,
) -> str:
    target_distribution = prepared_dataset[TARGET_COLUMN].value_counts()
    test_target_distribution = test_dataset[TARGET_COLUMN].value_counts()
    league_distribution = test_dataset["league_code"].value_counts().sort_index()
    season_distribution = test_dataset["season"].value_counts().sort_index()

    lines = [
        "RubyBets - Saved ML 1X2 model evaluation",
        "28 - Evaluation du modèle sauvegardé",
        "",
        "Positionnement :",
        "Cette évaluation concerne la baseline ML 1X2 expérimentale.",
        "Elle ne remplace pas le scoring explicable V1 et ne garantit aucun résultat sportif.",
        "",
        "Model artifact:",
        str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "",
        "Features used:",
        ", ".join(FEATURE_COLUMNS),
        "",
        "Target column:",
        TARGET_COLUMN,
        "",
        "Dataset control:",
        f"Rows loaded from PostgreSQL: {len(dataset)}",
        f"Rows removed because of missing features: {rows_removed}",
        f"Rows remaining after preparation: {len(prepared_dataset)}",
        "",
        "Target distribution after preparation:",
        target_distribution.to_string(),
        "",
        "Evaluation split:",
        f"Test seasons: {', '.join(TEST_SEASONS)}",
        f"Test rows: {len(test_dataset)}",
        "",
        "Test leagues:",
        league_distribution.to_string(),
        "",
        "Test seasons distribution:",
        season_distribution.to_string(),
        "",
        "Test target distribution:",
        test_target_distribution.to_string(),
        "",
        "Evaluation metrics:",
        f"Accuracy: {evaluation['accuracy']:.4f}",
        f"F1 macro: {evaluation['f1_macro']:.4f}",
        f"F1 weighted: {evaluation['f1_weighted']:.4f}",
        "",
        "Confusion matrix labels: HOME_WIN, DRAW, AWAY_WIN",
        str(evaluation["confusion_matrix"]),
        "",
        "Classification report:",
        evaluation["classification_report"],
        "",
        "Conclusion:",
        "Le modèle sauvegardé a été rechargé et évalué sans relancer l’entraînement complet.",
        "Cette preuve confirme la reproductibilité technique de la baseline ML 1X2 expérimentale.",
        "",
    ]

    return "\n".join(lines)


# Sauvegarde la preuve d’évaluation dans reports/evidence/ml_training.
def save_evaluation_report(content: str) -> None:
    REPORT_PATH.write_text(content, encoding="utf-8")


# Orchestre l’évaluation reproductible du modèle ML 1X2 sauvegardé.
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
    evaluation = evaluate_saved_model(model, test_dataset)

    report_content = build_evaluation_report(
        dataset,
        prepared_dataset,
        rows_removed,
        test_dataset,
        evaluation,
    )
    save_evaluation_report(report_content)

    print("OK - Saved ML 1X2 model evaluated.")
    print(f"Accuracy: {evaluation['accuracy']:.4f}")
    print(f"F1 macro: {evaluation['f1_macro']:.4f}")
    print(f"F1 weighted: {evaluation['f1_weighted']:.4f}")
    print("Report saved: reports/evidence/ml_training/28_saved_1x2_model_evaluation.txt")


if __name__ == "__main__":
    main()


# Schéma de communication :
# evaluate_saved_1x2_model.py
#   -> lit backend/.env pour DATABASE_URL
#   -> lit PostgreSQL : ml.features + ml.clean_matches
#   -> recharge models/ml/1x2/best_1x2_model.joblib
#   -> applique les 6 features officielles de la baseline 1X2
#   -> filtre les saisons de test 2022_2023, 2023_2024, 2024_2025
#   -> écrit reports/evidence/ml_training/28_saved_1x2_model_evaluation.txt