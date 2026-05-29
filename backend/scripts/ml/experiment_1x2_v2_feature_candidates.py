# Rôle du fichier : lancer une expérimentation ML 1X2 V2 rapide en testant team_strength_rating et match_balance_features dans un seul script, sans modifier la base, l'API ou le modèle sauvegardé.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "46_1x2_v2_fast_experiment_summary.txt"
CSV_PATH = REPORT_DIR / "47_1x2_v2_fast_experiment_results.csv"
DECISION_PATH = REPORT_DIR / "48_1x2_v2_fast_experiment_decision.txt"

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

warnings.filterwarnings("ignore", category=UserWarning)

INITIAL_TEAM_STRENGTH = 1500.0
TEAM_STRENGTH_K_FACTOR = 20.0
TEAM_STRENGTH_SCALE = 400.0
RECENT_DELTA_MATCH_WINDOW = 5

REFERENCE_TEAM_STRENGTH_ACCURACY = 0.5104
REFERENCE_TEAM_STRENGTH_F1_MACRO = 0.4804
REFERENCE_TEAM_STRENGTH_DRAW_RECALL = 0.2720
REFERENCE_HIGH_CONFIDENCE_ACCURACY = 0.7007
REFERENCE_HIGH_CONFIDENCE_COVERAGE = 0.1721
REFERENCE_HIGH_CONFIDENCE_THRESHOLD = 0.61

HIGH_CONFIDENCE_THRESHOLDS = [round(value / 100, 2) for value in range(50, 81)]
CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

TEAM_STRENGTH_COLUMNS = [
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "home_team_strength_recent_delta",
    "away_team_strength_recent_delta",
]

MATCH_BALANCE_COLUMNS = [
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
]

MATCH_BALANCE_WITH_STRENGTH_COLUMNS = MATCH_BALANCE_COLUMNS + [
    "is_close_strength_match",
    "balance_signal_count_with_strength",
    "match_balance_score_with_strength",
    "draw_profile_score_with_strength",
]


# Supprime les doublons dans une liste de colonnes tout en conservant l'ordre.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


SELECTED_FEATURE_SETS = {
    "last10_plus_team_strength": dedupe_columns(
        FEATURE_SETS["v2_last10_overall_with_diff"] + TEAM_STRENGTH_COLUMNS
    ),
    "last10_plus_match_balance": dedupe_columns(
        FEATURE_SETS["v2_last10_overall_with_diff_and_abs"] + MATCH_BALANCE_COLUMNS
    ),
    "last10_plus_team_strength_plus_match_balance": dedupe_columns(
        FEATURE_SETS["v2_last10_overall_with_diff_and_abs"]
        + TEAM_STRENGTH_COLUMNS
        + MATCH_BALANCE_WITH_STRENGTH_COLUMNS
    ),
    "venue_plus_team_strength_plus_match_balance": dedupe_columns(
        FEATURE_SETS["v2_last10_diff_abs_venue_strength"]
        + TEAM_STRENGTH_COLUMNS
        + MATCH_BALANCE_WITH_STRENGTH_COLUMNS
    ),
}


# Crée les modèles utiles pour une comparaison rapide et efficace.
def build_candidate_models() -> dict:
    models = {
        "LogisticRegression_balanced": Pipeline(
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
        ),
        "RandomForest_balanced": RandomForestClassifier(
            n_estimators=180,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            min_samples_leaf=5,
        ),
        "GradientBoosting": GradientBoostingClassifier(
            random_state=42,
        ),
    }

    try:
        from xgboost import XGBClassifier

        models["XGBoost"] = XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_estimators=220,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            n_jobs=-1,
        )
    except Exception:
        print("Info - XGBoost non disponible, comparaison continue sans XGBoost.", flush=True)

    return models


# Calcule le score attendu d'une équipe selon l'écart de force avant-match.
def calculate_expected_score(team_strength: float, opponent_strength: float) -> float:
    return 1 / (1 + 10 ** ((opponent_strength - team_strength) / TEAM_STRENGTH_SCALE))


# Convertit le résultat 1X2 en score numérique pour chaque équipe.
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


# Construit les features de force d'équipe avant le match.
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


# Construit les features team_strength_rating en respectant l'ordre chronologique.
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


# Transforme une série en numérique sans interrompre l'exécution.
def to_numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(dataframe[column], errors="coerce")


# Ajoute des features destinées à repérer les matchs équilibrés, donc potentiellement plus favorables au DRAW.
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
        if column in dataframe.columns:
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


# Construit toutes les features V2 rapides en mémoire.
def build_v2_fast_feature_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    base_feature_dataframe = build_feature_dataframe(clean_matches)
    team_strength_dataframe = build_team_strength_dataframe(clean_matches)

    merged_dataframe = base_feature_dataframe.merge(
        team_strength_dataframe,
        on="clean_match_id",
        how="left",
    )

    return add_match_balance_features(merged_dataframe)


# Prépare les données train/test chronologiques pour un set de features.
def prepare_train_test(
    feature_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le DataFrame : {missing_columns}")

    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees.")

    return (
        train_dataframe[feature_columns],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[feature_columns],
        test_dataframe[TARGET_COLUMN],
        working_dataframe,
    )


# Prépare les labels numériques nécessaires à XGBoost.
def encode_target_for_xgboost(y_train: pd.Series) -> tuple[pd.Series, dict]:
    label_mapping = {
        "AWAY_WIN": 0,
        "DRAW": 1,
        "HOME_WIN": 2,
    }

    return y_train.map(label_mapping), label_mapping


# Reconvertit les prédictions numériques XGBoost vers les labels métier.
def decode_xgboost_predictions(predictions, label_mapping: dict) -> list[str]:
    reverse_mapping = {value: key for key, value in label_mapping.items()}

    return [reverse_mapping[int(prediction)] for prediction in predictions]


# Calcule les métriques de forte confiance pour un seuil précis.
def calculate_threshold_metrics(
    threshold: float,
    y_test: pd.Series,
    predictions: list[str],
    max_probabilities,
) -> dict:
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
    selected_distribution = selected_predictions.value_counts().to_dict()

    return {
        "threshold": threshold,
        "selected_rows": selected_rows,
        "coverage": round(selected_rows / len(y_test), 4),
        "accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
        "predicted_draw_rows": int(selected_distribution.get("DRAW", 0)),
    }


# Sélectionne les meilleurs seuils de forte confiance utiles à la décision.
def calculate_high_confidence_summary(model, x_test: pd.DataFrame, y_test: pd.Series, predictions: list[str]) -> dict:
    if not hasattr(model, "predict_proba"):
        return {
            "hc_061_accuracy": None,
            "hc_061_coverage": 0.0,
            "hc_061_rows": 0,
            "hc_061_draw_rows": 0,
            "hc_70_threshold": None,
            "hc_70_accuracy": None,
            "hc_70_coverage": 0.0,
            "hc_70_rows": 0,
            "hc_70_draw_rows": 0,
            "hc_practical_threshold": None,
            "hc_practical_accuracy": None,
            "hc_practical_coverage": 0.0,
            "hc_practical_rows": 0,
            "hc_practical_draw_rows": 0,
        }

    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)

    threshold_results = [
        calculate_threshold_metrics(
            threshold=threshold,
            y_test=y_test,
            predictions=predictions,
            max_probabilities=max_probabilities,
        )
        for threshold in HIGH_CONFIDENCE_THRESHOLDS
    ]

    threshold_dataframe = pd.DataFrame(threshold_results)
    threshold_061_row = threshold_dataframe[threshold_dataframe["threshold"] == REFERENCE_HIGH_CONFIDENCE_THRESHOLD].iloc[0]

    eligible_70 = threshold_dataframe[
        (threshold_dataframe["accuracy"].notna())
        & (threshold_dataframe["accuracy"] >= REFERENCE_HIGH_CONFIDENCE_ACCURACY)
    ].copy()

    if eligible_70.empty:
        best_70 = None
    else:
        best_70 = eligible_70.sort_values(
            by=["coverage", "accuracy"],
            ascending=False,
        ).iloc[0]

    practical = threshold_dataframe[
        (threshold_dataframe["accuracy"].notna())
        & (threshold_dataframe["selected_rows"] >= 500)
    ].copy()

    if practical.empty:
        best_practical = None
    else:
        best_practical = practical.sort_values(
            by=["accuracy", "coverage"],
            ascending=False,
        ).iloc[0]

    return {
        "hc_061_accuracy": threshold_061_row["accuracy"],
        "hc_061_coverage": threshold_061_row["coverage"],
        "hc_061_rows": int(threshold_061_row["selected_rows"]),
        "hc_061_draw_rows": int(threshold_061_row["predicted_draw_rows"]),
        "hc_70_threshold": None if best_70 is None else best_70["threshold"],
        "hc_70_accuracy": None if best_70 is None else best_70["accuracy"],
        "hc_70_coverage": 0.0 if best_70 is None else best_70["coverage"],
        "hc_70_rows": 0 if best_70 is None else int(best_70["selected_rows"]),
        "hc_70_draw_rows": 0 if best_70 is None else int(best_70["predicted_draw_rows"]),
        "hc_practical_threshold": None if best_practical is None else best_practical["threshold"],
        "hc_practical_accuracy": None if best_practical is None else best_practical["accuracy"],
        "hc_practical_coverage": 0.0 if best_practical is None else best_practical["coverage"],
        "hc_practical_rows": 0 if best_practical is None else int(best_practical["selected_rows"]),
        "hc_practical_draw_rows": 0 if best_practical is None else int(best_practical["predicted_draw_rows"]),
    }


# Entraîne et évalue un modèle sur un set de features.
def evaluate_model_on_feature_set(
    feature_dataframe: pd.DataFrame,
    feature_set_name: str,
    feature_columns: list[str],
    model_name: str,
    model,
) -> dict:
    x_train, y_train, x_test, y_test, working_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model_to_train = clone(model)

    if model_name == "XGBoost":
        y_train_encoded, label_mapping = encode_target_for_xgboost(y_train)
        model_to_train.fit(x_train, y_train_encoded)
        raw_predictions = model_to_train.predict(x_test)
        predictions = decode_xgboost_predictions(raw_predictions, label_mapping)
    else:
        model_to_train.fit(x_train, y_train)
        predictions = list(model_to_train.predict(x_test))

    report = classification_report(
        y_test,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    high_confidence_summary = calculate_high_confidence_summary(
        model=model_to_train,
        x_test=x_test,
        y_test=y_test,
        predictions=predictions,
    )

    return {
        "feature_set": feature_set_name,
        "model": model_name,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": len(working_dataframe),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "home_win_precision": round(report["HOME_WIN"]["precision"], 4),
        "home_win_recall": round(report["HOME_WIN"]["recall"], 4),
        "draw_precision": round(report["DRAW"]["precision"], 4),
        "draw_recall": round(report["DRAW"]["recall"], 4),
        "away_win_precision": round(report["AWAY_WIN"]["precision"], 4),
        "away_win_recall": round(report["AWAY_WIN"]["recall"], 4),
        **high_confidence_summary,
        "features": ", ".join(feature_columns),
    }


# Compare rapidement tous les modèles sur les familles de features V2.
def run_fast_comparison(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    candidate_models = build_candidate_models()

    for feature_set_name, feature_columns in SELECTED_FEATURE_SETS.items():
        for model_name, model in candidate_models.items():
            print(f"Evaluation : {model_name} sur {feature_set_name}", flush=True)

            results.append(
                evaluate_model_on_feature_set(
                    feature_dataframe=feature_dataframe,
                    feature_set_name=feature_set_name,
                    feature_columns=feature_columns,
                    model_name=model_name,
                    model=model,
                )
            )

    comparison = pd.DataFrame(results)

    return comparison.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    )


# Récupère une cellule de manière sûre pour les textes de synthèse.
def format_optional_value(value) -> str:
    if value is None or pd.isna(value):
        return "None"

    return str(value)


# Construit la synthèse générale de l'expérimentation V2 rapide.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, comparison: pd.DataFrame) -> str:
    best_accuracy_row = comparison.sort_values(by=["accuracy", "f1_macro"], ascending=False).iloc[0]
    best_f1_row = comparison.sort_values(by=["f1_macro", "draw_recall", "accuracy"], ascending=False).iloc[0]
    best_draw_row = comparison.sort_values(by=["draw_recall", "f1_macro", "accuracy"], ascending=False).iloc[0]

    eligible_high_confidence = comparison[
        comparison["hc_70_accuracy"].notna()
    ].copy()

    if eligible_high_confidence.empty:
        best_high_confidence_row = None
    else:
        best_high_confidence_row = eligible_high_confidence.sort_values(
            by=["hc_70_coverage", "hc_70_accuracy", "f1_macro"],
            ascending=False,
        ).iloc[0]

    lines = [
        "RubyBets - ML 1X2 V2 fast experiment",
        "46 - Experimentation rapide team_strength_rating + match_balance_features",
        "",
        "Positionnement :",
        "Cette experimentation teste plusieurs familles de features V2 dans un seul script.",
        "Elle ne remplace pas le scoring explicable V1, ne modifie pas PostgreSQL, ne remplace pas le modele sauvegarde et ne touche pas au frontend.",
        "",
        "Objectif :",
        "- Aller plus vite que les micro-experiences separees.",
        "- Tester directement si les features match_balance ameliorent le DRAW recall.",
        "- Verifier si le signal forte confiance depasse la reference actuelle.",
        "",
        "References actuelles :",
        f"- Baseline officielle accuracy : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- Baseline officielle F1 macro : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        f"- Meilleur compromis team_strength deja observe accuracy : {REFERENCE_TEAM_STRENGTH_ACCURACY:.4f}",
        f"- Meilleur compromis team_strength deja observe F1 macro : {REFERENCE_TEAM_STRENGTH_F1_MACRO:.4f}",
        f"- Meilleur compromis team_strength deja observe DRAW recall : {REFERENCE_TEAM_STRENGTH_DRAW_RECALL:.4f}",
        f"- Reference forte confiance accuracy : {REFERENCE_HIGH_CONFIDENCE_ACCURACY:.4f}",
        f"- Reference forte confiance coverage : {REFERENCE_HIGH_CONFIDENCE_COVERAGE:.4f}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Best global accuracy:",
        f"- Feature set : {best_accuracy_row['feature_set']}",
        f"- Model : {best_accuracy_row['model']}",
        f"- Accuracy : {best_accuracy_row['accuracy']}",
        f"- F1 macro : {best_accuracy_row['f1_macro']}",
        f"- DRAW recall : {best_accuracy_row['draw_recall']}",
        "",
        "Best F1 macro / equilibre metier:",
        f"- Feature set : {best_f1_row['feature_set']}",
        f"- Model : {best_f1_row['model']}",
        f"- Accuracy : {best_f1_row['accuracy']}",
        f"- F1 macro : {best_f1_row['f1_macro']}",
        f"- DRAW recall : {best_f1_row['draw_recall']}",
        "",
        "Best DRAW recall:",
        f"- Feature set : {best_draw_row['feature_set']}",
        f"- Model : {best_draw_row['model']}",
        f"- Accuracy : {best_draw_row['accuracy']}",
        f"- F1 macro : {best_draw_row['f1_macro']}",
        f"- DRAW recall : {best_draw_row['draw_recall']}",
        "",
    ]

    if best_high_confidence_row is not None:
        lines.extend(
            [
                "Best high-confidence signal with at least reference accuracy:",
                f"- Feature set : {best_high_confidence_row['feature_set']}",
                f"- Model : {best_high_confidence_row['model']}",
                f"- Threshold : {best_high_confidence_row['hc_70_threshold']}",
                f"- Accuracy : {best_high_confidence_row['hc_70_accuracy']}",
                f"- Coverage : {best_high_confidence_row['hc_70_coverage']}",
                f"- Rows : {best_high_confidence_row['hc_70_rows']}",
                f"- Predicted DRAW rows : {best_high_confidence_row['hc_70_draw_rows']}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Best high-confidence signal with at least reference accuracy:",
                "- Aucun candidat ne depasse la reference de forte confiance actuelle.",
                "",
            ]
        )

    display_columns = [
        "feature_set",
        "model",
        "feature_count",
        "train_rows",
        "test_rows",
        "accuracy",
        "f1_macro",
        "f1_weighted",
        "home_win_recall",
        "draw_recall",
        "away_win_recall",
        "hc_061_accuracy",
        "hc_061_coverage",
        "hc_061_rows",
        "hc_061_draw_rows",
        "hc_70_threshold",
        "hc_70_accuracy",
        "hc_70_coverage",
        "hc_70_rows",
        "hc_70_draw_rows",
    ]

    lines.extend(
        [
            "Comparison table:",
            comparison[display_columns].to_string(index=False),
            "",
            "Generated files:",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
        ]
    )

    return "\n".join(lines)


# Construit la décision expérimentale claire pour éviter de multiplier les fichiers.
def build_decision(comparison: pd.DataFrame) -> str:
    best_f1_row = comparison.sort_values(by=["f1_macro", "draw_recall", "accuracy"], ascending=False).iloc[0]
    best_draw_row = comparison.sort_values(by=["draw_recall", "f1_macro", "accuracy"], ascending=False).iloc[0]

    eligible_high_confidence = comparison[
        comparison["hc_70_accuracy"].notna()
    ].copy()

    best_high_confidence_row = None

    if not eligible_high_confidence.empty:
        best_high_confidence_row = eligible_high_confidence.sort_values(
            by=["hc_70_coverage", "hc_70_accuracy", "f1_macro"],
            ascending=False,
        ).iloc[0]

    improves_f1 = best_f1_row["f1_macro"] > REFERENCE_TEAM_STRENGTH_F1_MACRO
    improves_draw = best_f1_row["draw_recall"] > REFERENCE_TEAM_STRENGTH_DRAW_RECALL

    improves_high_confidence = False

    if best_high_confidence_row is not None:
        improves_high_confidence = (
            best_high_confidence_row["hc_70_accuracy"] >= REFERENCE_HIGH_CONFIDENCE_ACCURACY
            and best_high_confidence_row["hc_70_coverage"] > REFERENCE_HIGH_CONFIDENCE_COVERAGE
        )

    lines = [
        "RubyBets - ML 1X2 V2 fast experiment decision",
        "48 - Decision apres experimentation rapide team_strength_rating + match_balance_features",
        "",
        "Decision de perimetre :",
        "- Aucun modele sauvegarde n'est remplace automatiquement.",
        "- Aucune table SQL n'est creee.",
        "- Aucune API et aucun composant frontend ne sont modifies.",
        "- Les resultats restent des preuves experimentales dans reports/evidence/ml_training/.",
        "",
        "Reference a battre :",
        f"- F1 macro : {REFERENCE_TEAM_STRENGTH_F1_MACRO:.4f}",
        f"- DRAW recall : {REFERENCE_TEAM_STRENGTH_DRAW_RECALL:.4f}",
        f"- Forte confiance accuracy : {REFERENCE_HIGH_CONFIDENCE_ACCURACY:.4f}",
        f"- Forte confiance coverage : {REFERENCE_HIGH_CONFIDENCE_COVERAGE:.4f}",
        "",
        "Meilleur compromis F1 macro observe :",
        f"- Feature set : {best_f1_row['feature_set']}",
        f"- Model : {best_f1_row['model']}",
        f"- Accuracy : {best_f1_row['accuracy']}",
        f"- F1 macro : {best_f1_row['f1_macro']}",
        f"- DRAW recall : {best_f1_row['draw_recall']}",
        "",
        "Meilleur DRAW recall observe :",
        f"- Feature set : {best_draw_row['feature_set']}",
        f"- Model : {best_draw_row['model']}",
        f"- Accuracy : {best_draw_row['accuracy']}",
        f"- F1 macro : {best_draw_row['f1_macro']}",
        f"- DRAW recall : {best_draw_row['draw_recall']}",
        "",
    ]

    if best_high_confidence_row is not None:
        lines.extend(
            [
                "Meilleur signal forte confiance observe :",
                f"- Feature set : {best_high_confidence_row['feature_set']}",
                f"- Model : {best_high_confidence_row['model']}",
                f"- Threshold : {best_high_confidence_row['hc_70_threshold']}",
                f"- Accuracy : {best_high_confidence_row['hc_70_accuracy']}",
                f"- Coverage : {best_high_confidence_row['hc_70_coverage']}",
                f"- Rows : {best_high_confidence_row['hc_70_rows']}",
                f"- Predicted DRAW rows : {best_high_confidence_row['hc_70_draw_rows']}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Meilleur signal forte confiance observe :",
                "- Aucun candidat ne depasse la reference forte confiance.",
                "",
            ]
        )

    if improves_f1 and improves_draw and improves_high_confidence:
        final_decision = (
            "Decision : candidat V2 interessant. Les features match_balance ameliorent l'equilibre global, "
            "le DRAW recall et le signal forte confiance. Il faut ensuite preparer une V2 separee, sans toucher a la V1."
        )
    elif improves_f1 or improves_draw:
        final_decision = (
            "Decision : amelioration partielle. Les features match_balance apportent un signal utile, "
            "mais pas encore assez solide pour remplacer ou integrer le modele. Garder comme piste V2."
        )
    elif improves_high_confidence:
        final_decision = (
            "Decision : amelioration surtout utile en forte confiance. Le modele reste experimental "
            "et ne doit pas etre integre comme predicteur general."
        )
    else:
        final_decision = (
            "Decision : pas d'amelioration suffisante. Conserver la reference team_strength_rating precedente "
            "et ne pas poursuivre cette piste avant une autre famille de features."
        )

    lines.extend(
        [
            "Decision finale :",
            final_decision,
            "",
            "Formulation soutenance :",
            "RubyBets a teste rapidement une piste V2 visant a mieux reperer les matchs equilibres.",
            "Les resultats doivent etre compares a la reference team_strength_rating deja obtenue.",
            "Le scoring explicable V1 reste le socle produit tant qu'une V2 ML n'est pas validee globalement.",
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V2 rapide team_strength + match_balance.",
            "- Statut source a mettre a jour : realise si les fichiers 46, 47 et 48 sont generes.",
            "- Fichiers concernes : 46, 47 et 48 dans reports/evidence/ml_training/.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les rapports CSV et TXT générés par l'expérience.
def save_reports(comparison: pd.DataFrame, summary: str, decision: str) -> None:
    ensure_report_dir()
    comparison.to_csv(CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérimentation V2 rapide.
def main() -> None:
    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features V2 rapides en memoire...", flush=True)

    feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

    print("Evaluation des feature sets et modeles candidats...", flush=True)

    comparison = run_fast_comparison(feature_dataframe)
    summary = build_summary(clean_matches, feature_dataframe, comparison)
    decision = build_decision(comparison)

    save_reports(comparison, summary, decision)

    best_f1_row = comparison.sort_values(by=["f1_macro", "draw_recall", "accuracy"], ascending=False).iloc[0]

    print("OK - Experimentation V2 rapide terminee.", flush=True)
    print(f"Best feature set: {best_f1_row['feature_set']}", flush=True)
    print(f"Best model: {best_f1_row['model']}", flush=True)
    print(f"Accuracy: {best_f1_row['accuracy']}", flush=True)
    print(f"F1 macro: {best_f1_row['f1_macro']}", flush=True)
    print(f"DRAW recall: {best_f1_row['draw_recall']}", flush=True)
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# run_1x2_v2_fast_experiment.py
# ├── lit backend/.env via compare_1x2_feature_sets.py
# ├── lit PostgreSQL : ml.clean_matches
# ├── réutilise les features last10 existantes en mémoire
# ├── ajoute team_strength_rating + match_balance_features
# ├── entraîne LogisticRegression / RandomForest / GradientBoosting / XGBoost si disponible
# └── écrit reports/evidence/ml_training/46, 47 et 48
