# Rôle du fichier : préparer le dataset ML 1X2, entraîner les premières baselines et générer les preuves RubyBets.

from pathlib import Path
import os
import time
import joblib
import pandas as pd
import psycopg

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, classification_report
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder
from xgboost import XGBClassifier


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
MODEL_DIR = PROJECT_ROOT / "models" / "ml" / "1x2"

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


# Récupère l’URL de connexion PostgreSQL depuis l’environnement.
def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL introuvable. Vérifie la session PowerShell ou backend/.env."
        )

    return database_url


# Crée les dossiers nécessaires pour stocker les preuves ML.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


# Ajoute une ligne dans le log principal d’exécution ML.
def append_training_log(message: str) -> None:
    log_path = REPORT_DIR / "02_training_execution_log.txt"

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n{message}\n")


# Charge les features ML et les métadonnées de saison/ligue depuis PostgreSQL.
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


# Prépare le dataset entraînable en retirant seulement les lignes avec features rolling manquantes.
def prepare_trainable_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    rows_before = len(dataset)
    prepared_dataset = dataset.copy()

    for column in FEATURE_COLUMNS:
        prepared_dataset[column] = pd.to_numeric(prepared_dataset[column], errors="coerce")

    prepared_dataset = prepared_dataset.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).copy()
    rows_removed = rows_before - len(prepared_dataset)

    return prepared_dataset, rows_removed


# Sépare le dataset en train/test selon une logique chronologique.
def split_dataset_chronologically(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    test_dataset = dataset[dataset["season"].isin(TEST_SEASONS)].copy()
    train_dataset = dataset[~dataset["season"].isin(TEST_SEASONS)].copy()

    return train_dataset, test_dataset


# Construit le contenu texte du résumé dataset.
def build_dataset_summary(
    dataset: pd.DataFrame,
    prepared_dataset: pd.DataFrame,
    rows_removed: int,
    train_dataset: pd.DataFrame,
    test_dataset: pd.DataFrame,
) -> str:
    missing_values = dataset[FEATURE_COLUMNS].isna().sum()
    target_distribution = dataset[TARGET_COLUMN].value_counts()
    league_distribution = dataset["league_code"].value_counts().sort_index()
    season_distribution = dataset["season"].value_counts().sort_index()

    train_target_distribution = train_dataset[TARGET_COLUMN].value_counts()
    test_target_distribution = test_dataset[TARGET_COLUMN].value_counts()

    lines = [
        "RubyBets - ML baseline 1X2",
        "01 - Dataset summary",
        "",
        f"Total rows loaded: {len(dataset)}",
        f"Features used: {', '.join(FEATURE_COLUMNS)}",
        f"Target column: {TARGET_COLUMN}",
        "",
        "Leagues available:",
        league_distribution.to_string(),
        "",
        "Seasons available:",
        season_distribution.to_string(),
        "",
        "Target distribution before ML preparation:",
        target_distribution.to_string(),
        "",
        "Missing values by feature before ML preparation:",
        missing_values.to_string(),
        "",
        "ML dataset preparation:",
        f"Rows before preparation: {len(dataset)}",
        f"Rows removed because of missing rolling features: {rows_removed}",
        f"Rows remaining after preparation: {len(prepared_dataset)}",
        "",
        "Chronological split:",
        "Train seasons: 2000_2001 to 2021_2022",
        f"Test seasons: {', '.join(TEST_SEASONS)}",
        f"Train rows: {len(train_dataset)}",
        f"Test rows: {len(test_dataset)}",
        "",
        "Train target distribution:",
        train_target_distribution.to_string(),
        "",
        "Test target distribution:",
        test_target_distribution.to_string(),
        "",
        "Home advantage note:",
        "home_advantage is excluded from the first baseline because it is constant in the current feature table.",
        "",
    ]

    return "\n".join(lines)


# Sauvegarde le résumé dataset dans le dossier de preuves.
def save_dataset_summary(content: str) -> None:
    summary_path = REPORT_DIR / "01_dataset_summary.txt"
    summary_path.write_text(content, encoding="utf-8")


# Entraîne le modèle naïf DummyClassifier.
def train_dummy_classifier(train_dataset: pd.DataFrame) -> tuple[DummyClassifier, float]:
    x_train = train_dataset[FEATURE_COLUMNS]
    y_train = train_dataset[TARGET_COLUMN]

    model = DummyClassifier(strategy="most_frequent")

    start_time = time.perf_counter()
    model.fit(x_train, y_train)
    training_duration = time.perf_counter() - start_time

    return model, training_duration


# Entraîne une régression logistique avec standardisation des variables numériques.
def train_logistic_regression(train_dataset: pd.DataFrame) -> tuple[Pipeline, float]:
    x_train = train_dataset[FEATURE_COLUMNS]
    y_train = train_dataset[TARGET_COLUMN]

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )

    start_time = time.perf_counter()
    model.fit(x_train, y_train)
    training_duration = time.perf_counter() - start_time

    return model, training_duration


# Entraîne un Random Forest avec paramètres simples et reproductibles.
def train_random_forest(train_dataset: pd.DataFrame) -> tuple[RandomForestClassifier, float]:
    x_train = train_dataset[FEATURE_COLUMNS]
    y_train = train_dataset[TARGET_COLUMN]

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    start_time = time.perf_counter()
    model.fit(x_train, y_train)
    training_duration = time.perf_counter() - start_time

    return model, training_duration


# Adapte XGBoost pour entraîner sur des labels encodés et retourner les labels texte.
class XGBoostLabelModel:
    def __init__(self) -> None:
        self.label_encoder = LabelEncoder()
        self.model = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
        )

    def fit(self, x_train: pd.DataFrame, y_train: pd.Series) -> "XGBoostLabelModel":
        y_train_encoded = self.label_encoder.fit_transform(y_train)
        self.model.fit(x_train, y_train_encoded)
        return self

    def predict(self, x_test: pd.DataFrame):
        y_pred_encoded = self.model.predict(x_test)
        return self.label_encoder.inverse_transform(y_pred_encoded.astype(int))

    def get_params(self, deep: bool = True) -> dict:
        return self.model.get_params(deep=deep)


# Entraîne un modèle XGBoost avec labels encodés pour la classification 1X2.
def train_xgboost_classifier(train_dataset: pd.DataFrame) -> tuple[XGBoostLabelModel, float]:
    x_train = train_dataset[FEATURE_COLUMNS]
    y_train = train_dataset[TARGET_COLUMN]

    model = XGBoostLabelModel()

    start_time = time.perf_counter()
    model.fit(x_train, y_train)
    training_duration = time.perf_counter() - start_time

    return model, training_duration


# Sauvegarde un rapport détaillé pour un modèle entraîné.
def save_model_report(
    report_filename: str,
    model_name: str,
    model,
    training_duration: float,
    accuracy: float,
    f1_macro: float,
    f1_weighted: float,
    matrix,
    report: str,
) -> None:
    report_path = REPORT_DIR / report_filename

    lines = [
        f"RubyBets - ML baseline 1X2 - {model_name}",
        "",
        f"Model: {model_name}",
        f"Parameters: {model.get_params()}",
        f"Training duration seconds: {training_duration:.4f}",
        f"Accuracy: {accuracy:.4f}",
        f"F1 macro: {f1_macro:.4f}",
        f"F1 weighted: {f1_weighted:.4f}",
        "",
        "Confusion matrix labels: HOME_WIN, DRAW, AWAY_WIN",
        str(matrix),
        "",
        "Classification report:",
        report,
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")


# Évalue un modèle sur le dataset de test.
def evaluate_model(
    model_name: str,
    model,
    test_dataset: pd.DataFrame,
    training_duration: float,
    report_filename: str | None = None,
) -> dict:
    x_test = test_dataset[FEATURE_COLUMNS]
    y_test = test_dataset[TARGET_COLUMN]
    y_pred = model.predict(x_test)

    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    matrix = confusion_matrix(y_test, y_pred, labels=TARGET_LABELS)
    report = classification_report(y_test, y_pred, labels=TARGET_LABELS, zero_division=0)

    append_training_log(f"Model: {model_name}")
    append_training_log(f"Parameters: {model.get_params()}")
    append_training_log(f"Training duration seconds: {training_duration:.4f}")
    append_training_log(f"Accuracy: {accuracy:.4f}")
    append_training_log(f"F1 macro: {f1_macro:.4f}")
    append_training_log(f"F1 weighted: {f1_weighted:.4f}")
    append_training_log("Confusion matrix labels: HOME_WIN, DRAW, AWAY_WIN")
    append_training_log(str(matrix))
    append_training_log("Classification report:")
    append_training_log(report)

    if report_filename:
        save_model_report(
            report_filename,
            model_name,
            model,
            training_duration,
            accuracy,
            f1_macro,
            f1_weighted,
            matrix,
            report,
        )

    return {
        "model": model_name,
        "accuracy": round(accuracy, 4),
        "f1_macro": round(f1_macro, 4),
        "f1_weighted": round(f1_weighted, 4),
        "training_duration_seconds": round(training_duration, 4),
    }


# Sauvegarde le modèle retenu dans le dossier models/ml/1x2.
def save_best_model(model) -> None:
    model_path = MODEL_DIR / "best_1x2_model.joblib"
    joblib.dump(model, model_path)


# Sauvegarde le tableau comparatif des modèles.
def save_model_comparison(results: list[dict]) -> None:
    comparison_path = REPORT_DIR / "03_model_comparison.csv"
    comparison_df = pd.DataFrame(results)
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8")


# Orchestre le chargement, la préparation ML, le split et les premières baselines.
def main() -> None:
    ensure_report_dir()
    load_backend_env()

    database_url = get_database_url()
    dataset = load_ml_dataset(database_url)

    prepared_dataset, rows_removed = prepare_trainable_dataset(dataset)
    train_dataset, test_dataset = split_dataset_chronologically(prepared_dataset)

    summary = build_dataset_summary(
        dataset,
        prepared_dataset,
        rows_removed,
        train_dataset,
        test_dataset,
    )
    save_dataset_summary(summary)

    append_training_log("Step 3 - ML dataset preparation")
    append_training_log(f"Rows before preparation: {len(dataset)}")
    append_training_log(f"Rows removed because of missing rolling features: {rows_removed}")
    append_training_log(f"Rows remaining after preparation: {len(prepared_dataset)}")

    append_training_log("Step 4 - Chronological train/test split")
    append_training_log("Train seasons: 2000_2001 to 2021_2022")
    append_training_log(f"Test seasons: {', '.join(TEST_SEASONS)}")
    append_training_log(f"Train rows: {len(train_dataset)}")
    append_training_log(f"Test rows: {len(test_dataset)}")

    results = []

    append_training_log("Step 5 - DummyClassifier baseline")
    dummy_model, dummy_duration = train_dummy_classifier(train_dataset)
    dummy_result = evaluate_model(
        "DummyClassifier_most_frequent",
        dummy_model,
        test_dataset,
        dummy_duration,
    )
    results.append(dummy_result)

    append_training_log("Step 6 - Logistic Regression baseline")
    logistic_model, logistic_duration = train_logistic_regression(train_dataset)
    logistic_result = evaluate_model(
        "LogisticRegression_balanced",
        logistic_model,
        test_dataset,
        logistic_duration,
        "04_logistic_regression_report.txt",
    )
    results.append(logistic_result)

    save_best_model(logistic_model)
    append_training_log("Best model saved: models/ml/1x2/best_1x2_model.joblib")

    append_training_log("Step 7 - Random Forest baseline")
    random_forest_model, random_forest_duration = train_random_forest(train_dataset)
    random_forest_result = evaluate_model(
        "RandomForest_balanced",
        random_forest_model,
        test_dataset,
        random_forest_duration,
        "05_random_forest_report.txt",
    )
    results.append(random_forest_result)

    append_training_log("Step 8 - XGBoost baseline")
    xgboost_model, xgboost_duration = train_xgboost_classifier(train_dataset)
    xgboost_result = evaluate_model(
        "XGBoost_classifier",
        xgboost_model,
        test_dataset,
        xgboost_duration,
        "06_xgboost_report.txt",
    )
    results.append(xgboost_result)

    save_model_comparison(results)

    print("OK - DummyClassifier, Logistic Regression, Random Forest and XGBoost trained and evaluated.")
    print("Model comparison:")
    for result in results:
        print(
            f"- {result['model']} | accuracy={result['accuracy']} | "
            f"f1_macro={result['f1_macro']} | f1_weighted={result['f1_weighted']}"
        )
    print("Comparison saved: reports/evidence/ml_training/03_model_comparison.csv")
    print("Logistic report saved: reports/evidence/ml_training/04_logistic_regression_report.txt")


if __name__ == "__main__":
    main()


# Schéma de communication :
# train_1x2_models.py
#   -> lit backend/.env pour DATABASE_URL
#   -> lit PostgreSQL : ml.features + ml.clean_matches
#   -> prépare le dataset ML entraînable
#   -> crée un split chronologique train/test
#   -> entraîne DummyClassifier
#   -> entraîne Logistic Regression
#   -> entraîne Random Forest
#   -> entraîne XGBoost
#   -> écrit reports/evidence/ml_training/01_dataset_summary.txt
#   -> complète reports/evidence/ml_training/02_training_execution_log.txt
#   -> écrit reports/evidence/ml_training/03_model_comparison.csv
#   -> écrit reports/evidence/ml_training/04_logistic_regression_report.txt
#   -> écrit reports/evidence/ml_training/05_random_forest_report.txt
#   -> écrit reports/evidence/ml_training/06_xgboost_report.txt
#   -> écrit models/ml/1x2/best_1x2_model.joblib




