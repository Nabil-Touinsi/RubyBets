# Rôle du fichier : sauvegarder un candidat ML 1X2 V2 séparé, sans remplacer la baseline officielle ni modifier l'API, le frontend ou PostgreSQL.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import json
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]

REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
MODEL_DIR = PROJECT_ROOT / "models" / "ml" / "1x2" / "v2_candidate"

MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"
REPORT_PATH = REPORT_DIR / "49_1x2_v2_candidate_model_saved.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    FEATURE_SETS,
    OFFICIAL_BASELINE_ACCURACY,
    OFFICIAL_BASELINE_F1_MACRO,
    TARGET_COLUMN,
    TEST_SEASONS,
    build_feature_dataframe,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)


MODEL_NAME = "LogisticRegression_balanced"
FEATURE_SET_NAME = "last10_plus_team_strength_plus_match_balance"
MODEL_SCOPE = "experimental_v2_candidate"
TARGET_NAME = "1X2"

INITIAL_TEAM_STRENGTH = 1500.0
TEAM_STRENGTH_K_FACTOR = 20.0
TEAM_STRENGTH_SCALE = 400.0
RECENT_DELTA_MATCH_WINDOW = 5

REFERENCE_TEAM_STRENGTH_ACCURACY = 0.5104
REFERENCE_TEAM_STRENGTH_F1_MACRO = 0.4804
REFERENCE_TEAM_STRENGTH_DRAW_RECALL = 0.2720

CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

TEAM_STRENGTH_COLUMNS = [
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "home_team_strength_recent_delta",
    "away_team_strength_recent_delta",
]

MATCH_BALANCE_WITH_STRENGTH_COLUMNS = [
    "home_expected_goal_pressure",
    "away_expected_goal_pressure",
    "expected_goal_pressure_diff",
    "abs_expected_goal_pressure_diff",
    "is_close_form_match",
    "is_close_scoring_match",
    "is_close_defense_match",
    "is_close_goal_pressure_match",
    "balance_signal_count",
    "match_balance_score",
    "draw_profile_score",
    "is_close_strength_match",
    "balance_signal_count_with_strength",
    "match_balance_score_with_strength",
    "draw_profile_score_with_strength",
]


# Supprime les doublons dans une liste de features tout en conservant l'ordre.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


FEATURE_COLUMNS = dedupe_columns(
    FEATURE_SETS["v2_last10_overall_with_diff_and_abs"]
    + TEAM_STRENGTH_COLUMNS
    + MATCH_BALANCE_WITH_STRENGTH_COLUMNS
)


# Crée le modèle candidat V2 retenu.
def build_candidate_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )


# Calcule le score attendu d'une équipe selon l'écart de force avant-match.
def calculate_expected_score(team_strength: float, opponent_strength: float) -> float:
    return 1 / (1 + 10 ** ((opponent_strength - team_strength) / TEAM_STRENGTH_SCALE))


# Convertit le résultat réel du match en score numérique pour chaque équipe.
def get_actual_scores(result: str) -> tuple[float, float]:
    if result == "HOME_WIN":
        return 1.0, 0.0

    if result == "AWAY_WIN":
        return 0.0, 1.0

    return 0.5, 0.5


# Calcule la variation récente de force d'une équipe.
def calculate_recent_strength_delta(team_history: list[float], current_strength: float) -> float | None:
    if len(team_history) < RECENT_DELTA_MATCH_WINDOW:
        return None

    previous_strength = team_history[-RECENT_DELTA_MATCH_WINDOW]

    return round(current_strength - previous_strength, 2)


# Construit les features de force d'équipe avant-match pour une ligne.
def build_team_strength_row(match: dict, team_strengths: dict, strength_history: dict) -> dict:
    league_code = match["league_code"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    home_key = (league_code, home_team)
    away_key = (league_code, away_team)

    home_strength_before = team_strengths[home_key]
    away_strength_before = team_strengths[away_key]
    strength_diff = round(home_strength_before - away_strength_before, 2)

    return {
        "clean_match_id": match["id"],
        "home_team_strength_before": round(home_strength_before, 2),
        "away_team_strength_before": round(away_strength_before, 2),
        "team_strength_diff": strength_diff,
        "abs_team_strength_diff": abs(strength_diff),
        "home_team_strength_recent_delta": calculate_recent_strength_delta(
            team_history=strength_history[home_key],
            current_strength=home_strength_before,
        ),
        "away_team_strength_recent_delta": calculate_recent_strength_delta(
            team_history=strength_history[away_key],
            current_strength=away_strength_before,
        ),
    }


# Met à jour les forces d'équipe après tous les matchs d'une même date pour éviter la fuite de données.
def update_team_strengths_after_matches(matches_for_date: list[dict], team_strengths: dict, strength_history: dict) -> None:
    updates = []

    for match in matches_for_date:
        league_code = match["league_code"]
        home_team = match["home_team"]
        away_team = match["away_team"]

        home_key = (league_code, home_team)
        away_key = (league_code, away_team)

        home_strength_before = team_strengths[home_key]
        away_strength_before = team_strengths[away_key]

        expected_home = calculate_expected_score(home_strength_before, away_strength_before)
        expected_away = calculate_expected_score(away_strength_before, home_strength_before)
        actual_home, actual_away = get_actual_scores(match["result"])

        new_home_strength = home_strength_before + TEAM_STRENGTH_K_FACTOR * (actual_home - expected_home)
        new_away_strength = away_strength_before + TEAM_STRENGTH_K_FACTOR * (actual_away - expected_away)

        updates.append((home_key, new_home_strength))
        updates.append((away_key, new_away_strength))

    for team_key, new_strength in updates:
        team_strengths[team_key] = new_strength
        strength_history[team_key].append(new_strength)


# Construit le DataFrame des features de force d'équipe en respectant l'ordre chronologique.
def build_team_strength_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    rows = []
    team_strengths = defaultdict(lambda: INITIAL_TEAM_STRENGTH)
    strength_history = defaultdict(list)

    for _, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            rows.append(
                build_team_strength_row(
                    match=match,
                    team_strengths=team_strengths,
                    strength_history=strength_history,
                )
            )

        update_team_strengths_after_matches(
            matches_for_date=matches_for_date,
            team_strengths=team_strengths,
            strength_history=strength_history,
        )

    return pd.DataFrame(rows)


# Convertit une colonne en numérique sans bloquer l'exécution.
def to_numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(dataframe[column], errors="coerce")


# Ajoute les features qui décrivent les matchs équilibrés.
def add_match_balance_features(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = feature_dataframe.copy()

    numeric_columns = [
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "abs_team_strength_diff",
    ]

    for column in numeric_columns:
        dataframe[column] = to_numeric_series(dataframe, column)

    dataframe["home_expected_goal_pressure"] = (
        dataframe["home_goals_scored_avg_last_10"] + dataframe["away_goals_conceded_avg_last_10"]
    ) / 2
    dataframe["away_expected_goal_pressure"] = (
        dataframe["away_goals_scored_avg_last_10"] + dataframe["home_goals_conceded_avg_last_10"]
    ) / 2
    dataframe["expected_goal_pressure_diff"] = (
        dataframe["home_expected_goal_pressure"] - dataframe["away_expected_goal_pressure"]
    ).round(4)
    dataframe["abs_expected_goal_pressure_diff"] = dataframe["expected_goal_pressure_diff"].abs().round(4)

    dataframe["is_close_form_match"] = (dataframe["abs_form_points_diff"] <= 3.0).astype(int)
    dataframe["is_close_scoring_match"] = (dataframe["abs_goals_scored_diff"] <= 0.35).astype(int)
    dataframe["is_close_defense_match"] = (dataframe["abs_goals_conceded_diff"] <= 0.35).astype(int)
    dataframe["is_close_goal_pressure_match"] = (dataframe["abs_expected_goal_pressure_diff"] <= 0.35).astype(int)
    dataframe["is_close_strength_match"] = (dataframe["abs_team_strength_diff"] <= 60.0).astype(int)

    dataframe["balance_signal_count"] = (
        dataframe["is_close_form_match"]
        + dataframe["is_close_scoring_match"]
        + dataframe["is_close_defense_match"]
        + dataframe["is_close_goal_pressure_match"]
    )
    dataframe["balance_signal_count_with_strength"] = (
        dataframe["balance_signal_count"] + dataframe["is_close_strength_match"]
    )

    normalized_balance_gap = (
        dataframe["abs_form_points_diff"].fillna(99) / 3.0
        + dataframe["abs_goals_scored_diff"].fillna(99) / 0.35
        + dataframe["abs_goals_conceded_diff"].fillna(99) / 0.35
        + dataframe["abs_expected_goal_pressure_diff"].fillna(99) / 0.35
    )
    normalized_balance_gap_with_strength = normalized_balance_gap + (
        dataframe["abs_team_strength_diff"].fillna(9999) / 60.0
    )

    dataframe["match_balance_score"] = (1 / (1 + normalized_balance_gap)).round(4)
    dataframe["match_balance_score_with_strength"] = (1 / (1 + normalized_balance_gap_with_strength)).round(4)

    dataframe["draw_profile_score"] = (
        dataframe["balance_signal_count"] + dataframe["match_balance_score"]
    ).round(4)
    dataframe["draw_profile_score_with_strength"] = (
        dataframe["balance_signal_count_with_strength"] + dataframe["match_balance_score_with_strength"]
    ).round(4)

    return dataframe


# Construit toutes les features nécessaires au candidat V2.
def build_v2_candidate_feature_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    base_feature_dataframe = build_feature_dataframe(clean_matches)
    team_strength_dataframe = build_team_strength_dataframe(clean_matches)

    merged_dataframe = base_feature_dataframe.merge(
        team_strength_dataframe,
        on="clean_match_id",
        how="left",
    )

    return add_match_balance_features(merged_dataframe)


# Prépare les données train/test chronologiques.
def prepare_train_test(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    missing_columns = [column for column in FEATURE_COLUMNS if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le DataFrame : {missing_columns}")

    working_dataframe = feature_dataframe.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).copy()

    for column in FEATURE_COLUMNS:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees.")

    return (
        train_dataframe[FEATURE_COLUMNS],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[FEATURE_COLUMNS],
        test_dataframe[TARGET_COLUMN],
        working_dataframe,
    )


# Évalue le modèle candidat sur les saisons de test.
def evaluate_candidate_model(model, x_test: pd.DataFrame, y_test: pd.Series) -> tuple[list[str], dict]:
    predictions = list(model.predict(x_test))

    report = classification_report(
        y_test,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    metrics = {
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "home_win_precision": round(report["HOME_WIN"]["precision"], 4),
        "home_win_recall": round(report["HOME_WIN"]["recall"], 4),
        "draw_precision": round(report["DRAW"]["precision"], 4),
        "draw_recall": round(report["DRAW"]["recall"], 4),
        "away_win_precision": round(report["AWAY_WIN"]["precision"], 4),
        "away_win_recall": round(report["AWAY_WIN"]["recall"], 4),
    }

    return predictions, metrics


# Calcule le signal forte confiance au seuil de référence 0.61.
def evaluate_high_confidence(model, x_test: pd.DataFrame, y_test: pd.Series, predictions: list[str]) -> dict:
    threshold = 0.61
    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)
    selected_mask = max_probabilities >= threshold

    selected_rows = int(selected_mask.sum())

    if selected_rows == 0:
        return {
            "threshold": threshold,
            "selected_rows": 0,
            "coverage": 0.0,
            "accuracy": None,
            "predicted_draw_rows": 0,
        }

    prediction_series = pd.Series(predictions).reset_index(drop=True)
    truth_series = y_test.reset_index(drop=True)

    selected_predictions = prediction_series[selected_mask]
    selected_truth = truth_series[selected_mask]

    return {
        "threshold": threshold,
        "selected_rows": selected_rows,
        "coverage": round(selected_rows / len(y_test), 4),
        "accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
        "predicted_draw_rows": int(selected_predictions.value_counts().to_dict().get("DRAW", 0)),
    }


# Sauvegarde le modèle et ses métadonnées dans un dossier séparé.
def save_candidate_model(model, metadata: dict) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, MODEL_PATH)
    METADATA_PATH.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


# Construit les métadonnées du candidat V2 sauvegardé.
def build_metadata(
    clean_matches: list[dict],
    working_dataframe: pd.DataFrame,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    metrics: dict,
    high_confidence_metrics: dict,
) -> dict:
    return {
        "source": "rubybets_ml_1x2",
        "scope": MODEL_SCOPE,
        "status": "experimental_candidate",
        "model_name": MODEL_NAME,
        "target": TARGET_NAME,
        "target_column": TARGET_COLUMN,
        "target_classes": CLASS_LABELS,
        "feature_set": FEATURE_SET_NAME,
        "features_expected": FEATURE_COLUMNS,
        "feature_count": len(FEATURE_COLUMNS),
        "model_artifact": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "model_metadata": str(METADATA_PATH.relative_to(PROJECT_ROOT)),
        "does_replace_official_baseline": False,
        "does_modify_api": False,
        "does_modify_frontend": False,
        "does_modify_postgresql": False,
        "dataset": {
            "clean_matches_loaded": len(clean_matches),
            "rows_after_cleaning": len(working_dataframe),
            "train_rows": len(x_train),
            "test_rows": len(x_test),
            "test_seasons": TEST_SEASONS,
        },
        "official_baseline_reference": {
            "accuracy": OFFICIAL_BASELINE_ACCURACY,
            "f1_macro": OFFICIAL_BASELINE_F1_MACRO,
        },
        "previous_team_strength_reference": {
            "accuracy": REFERENCE_TEAM_STRENGTH_ACCURACY,
            "f1_macro": REFERENCE_TEAM_STRENGTH_F1_MACRO,
            "draw_recall": REFERENCE_TEAM_STRENGTH_DRAW_RECALL,
        },
        "evaluation_results": metrics,
        "high_confidence_reference_threshold": high_confidence_metrics,
        "decision": {
            "summary": "V2 candidate saved separately for later analysis. It improves F1 macro and DRAW recall compared with the previous team_strength reference, but remains experimental.",
            "main_limit": "Global accuracy remains low for a general predictor. The explainable V1 scoring remains the product baseline.",
        },
    }


# Construit le rapport texte de sauvegarde du candidat V2.
def build_report(metadata: dict) -> str:
    metrics = metadata["evaluation_results"]
    high_confidence = metadata["high_confidence_reference_threshold"]

    lines = [
        "RubyBets - ML 1X2 V2 candidate model saved",
        "49 - Sauvegarde separee du candidat V2 experimental",
        "",
        "Positionnement :",
        "Cette sauvegarde ne remplace pas la baseline officielle.",
        "Elle ne modifie pas PostgreSQL, ne modifie pas l'API et ne touche pas au frontend.",
        "Elle cree uniquement un dossier separe pour conserver le meilleur candidat V2 metier.",
        "",
        "Modele sauvegarde :",
        f"- Model : {metadata['model_name']}",
        f"- Scope : {metadata['scope']}",
        f"- Status : {metadata['status']}",
        f"- Feature set : {metadata['feature_set']}",
        f"- Feature count : {metadata['feature_count']}",
        "",
        "Fichiers generes :",
        f"- {metadata['model_artifact']}",
        f"- {metadata['model_metadata']}",
        f"- {REPORT_PATH.relative_to(PROJECT_ROOT)}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {metadata['dataset']['clean_matches_loaded']}",
        f"- Lignes apres nettoyage : {metadata['dataset']['rows_after_cleaning']}",
        f"- Train rows : {metadata['dataset']['train_rows']}",
        f"- Test rows : {metadata['dataset']['test_rows']}",
        f"- Saisons test : {', '.join(metadata['dataset']['test_seasons'])}",
        "",
        "Resultats evaluation :",
        f"- Accuracy : {metrics['accuracy']}",
        f"- F1 macro : {metrics['f1_macro']}",
        f"- F1 weighted : {metrics['f1_weighted']}",
        f"- HOME_WIN recall : {metrics['home_win_recall']}",
        f"- DRAW recall : {metrics['draw_recall']}",
        f"- AWAY_WIN recall : {metrics['away_win_recall']}",
        "",
        "Signal forte confiance au seuil 0.61 :",
        f"- Selected rows : {high_confidence['selected_rows']}",
        f"- Coverage : {high_confidence['coverage']}",
        f"- Accuracy : {high_confidence['accuracy']}",
        f"- Predicted DRAW rows : {high_confidence['predicted_draw_rows']}",
        "",
        "Decision :",
        "Le candidat V2 est sauvegarde car il est plus defendable metier que la baseline officielle et que la reference team_strength precedente.",
        "Il ameliore legerement le F1 macro et le DRAW recall, mais il reste experimental.",
        "Il ne doit pas etre integre comme predicteur general tant que l'accuracy globale reste faible.",
        "Le scoring explicable V1 reste le socle produit de RubyBets.",
        "",
        "Statut de suivi :",
        "- Tache realisee : sauvegarde separee du candidat V2 experimental.",
        "- Statut source a mettre a jour : realise.",
        "- Fichiers concernes : models/ml/1x2/v2_candidate/ et reports/evidence/ml_training/49.",
        "",
    ]

    return "\n".join(lines)


# Lance la sauvegarde complète du candidat V2.
def main() -> None:
    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features candidat V2 en memoire...", flush=True)

    feature_dataframe = build_v2_candidate_feature_dataframe(clean_matches)
    x_train, y_train, x_test, y_test, working_dataframe = prepare_train_test(feature_dataframe)

    print(f"Train rows : {len(x_train)}", flush=True)
    print(f"Test rows : {len(x_test)}", flush=True)
    print(f"Entrainement du candidat V2 : {MODEL_NAME}", flush=True)

    model = build_candidate_model()
    model.fit(x_train, y_train)

    predictions, metrics = evaluate_candidate_model(model, x_test, y_test)
    high_confidence_metrics = evaluate_high_confidence(model, x_test, y_test, predictions)

    metadata = build_metadata(
        clean_matches=clean_matches,
        working_dataframe=working_dataframe,
        x_train=x_train,
        x_test=x_test,
        metrics=metrics,
        high_confidence_metrics=high_confidence_metrics,
    )

    save_candidate_model(model, metadata)

    report = build_report(metadata)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print("OK - Candidat V2 sauvegarde separement.", flush=True)
    print(f"Model saved: {MODEL_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Metadata saved: {METADATA_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Report saved: {REPORT_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Accuracy: {metrics['accuracy']}", flush=True)
    print(f"F1 macro: {metrics['f1_macro']}", flush=True)
    print(f"DRAW recall: {metrics['draw_recall']}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# save_1x2_v2_candidate_model.py
# ├── lit backend/.env via compare_1x2_feature_sets.py
# ├── lit PostgreSQL : ml.clean_matches
# ├── reconstruit les features V2 en mémoire
# ├── entraîne LogisticRegression_balanced sur le split chronologique
# ├── écrit models/ml/1x2/v2_candidate/model.joblib
# ├── écrit models/ml/1x2/v2_candidate/model_metadata.json
# └── écrit reports/evidence/ml_training/49_1x2_v2_candidate_model_saved.txt
