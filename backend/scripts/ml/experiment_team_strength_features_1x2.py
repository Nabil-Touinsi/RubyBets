# Rôle du fichier : tester des features de force d’équipe avant-match pour améliorer les prédictions ML 1X2 sans modifier la base ni remplacer la baseline validée.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "39_1x2_team_strength_features_comparison.txt"
CSV_PATH = REPORT_DIR / "40_1x2_team_strength_features_comparison.csv"

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
CONFIDENCE_THRESHOLD = 0.60
CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

TEAM_STRENGTH_COLUMNS = [
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "home_team_strength_recent_delta",
    "away_team_strength_recent_delta",
]

SELECTED_FEATURE_SETS = {
    "current_best_last10_diff": FEATURE_SETS["v2_last10_overall_with_diff"],
    "team_strength_only": TEAM_STRENGTH_COLUMNS,
    "last10_diff_plus_team_strength": FEATURE_SETS["v2_last10_overall_with_diff"] + TEAM_STRENGTH_COLUMNS,
    "balanced_last10_diff_abs_venue_plus_team_strength": FEATURE_SETS["v2_last10_diff_abs_venue_strength"] + TEAM_STRENGTH_COLUMNS,
}


# Crée les modèles candidats à comparer sur les mêmes features.
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
            n_estimators=200,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            min_samples_leaf=5,
        ),
        "GradientBoosting": GradientBoostingClassifier(
            random_state=42,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            random_state=42,
            max_iter=200,
            learning_rate=0.06,
        ),
    }

    try:
        from xgboost import XGBClassifier

        models["XGBoost"] = XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_estimators=250,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
        )
    except Exception:
        print("Info - XGBoost non disponible, comparaison continue sans XGBoost.", flush=True)

    return models


# Calcule le score attendu d’une équipe selon l’écart de force avant-match.
def calculate_expected_score(team_strength: float, opponent_strength: float) -> float:
    return 1 / (1 + 10 ** ((opponent_strength - team_strength) / TEAM_STRENGTH_SCALE))


# Convertit le résultat 1X2 en score numérique pour l’équipe à domicile et l’équipe extérieure.
def get_actual_scores(result: str) -> tuple[float, float]:
    if result == "HOME_WIN":
        return 1.0, 0.0

    if result == "AWAY_WIN":
        return 0.0, 1.0

    return 0.5, 0.5


# Calcule la progression récente d’une équipe par rapport à son niveau quelques matchs plus tôt.
def calculate_recent_strength_delta(team_history: list[float], current_strength: float) -> float | None:
    if len(team_history) < RECENT_DELTA_MATCH_WINDOW:
        return None

    previous_strength = team_history[-RECENT_DELTA_MATCH_WINDOW]

    return round(current_strength - previous_strength, 2)


# Construit les features de force d’équipe avant mise à jour par le résultat du match.
def build_team_strength_row(match: dict, team_strengths: dict, strength_history: dict) -> dict:
    league_code = match["league_code"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    home_key = (league_code, home_team)
    away_key = (league_code, away_team)

    home_strength_before = team_strengths[home_key]
    away_strength_before = team_strengths[away_key]

    home_recent_delta = calculate_recent_strength_delta(
        team_history=strength_history[home_key],
        current_strength=home_strength_before,
    )
    away_recent_delta = calculate_recent_strength_delta(
        team_history=strength_history[away_key],
        current_strength=away_strength_before,
    )

    strength_diff = round(home_strength_before - away_strength_before, 2)

    return {
        "clean_match_id": match["id"],
        "home_team_strength_before": round(home_strength_before, 2),
        "away_team_strength_before": round(away_strength_before, 2),
        "team_strength_diff": strength_diff,
        "abs_team_strength_diff": abs(strength_diff),
        "home_team_strength_recent_delta": home_recent_delta,
        "away_team_strength_recent_delta": away_recent_delta,
    }


# Met à jour les forces d’équipe après les matchs d’une même date pour éviter toute fuite de données.
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


# Construit toutes les features de force d’équipe en respectant l’ordre chronologique des matchs.
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


# Fusionne les features existantes last10 avec les nouvelles features de force d’équipe.
def build_experiment_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    base_feature_dataframe = build_feature_dataframe(clean_matches)
    team_strength_dataframe = build_team_strength_dataframe(clean_matches)

    return base_feature_dataframe.merge(
        team_strength_dataframe,
        on="clean_match_id",
        how="left",
    )


# Prépare les données train/test chronologiques pour un feature set donné.
def prepare_train_test(
    feature_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees.")

    x_train = train_dataframe[feature_columns]
    y_train = train_dataframe[TARGET_COLUMN]
    x_test = test_dataframe[feature_columns]
    y_test = test_dataframe[TARGET_COLUMN]

    return x_train, y_train, x_test, y_test, working_dataframe


# Prépare les labels numériques nécessaires à XGBoost.
def encode_target_for_xgboost(y_train: pd.Series, y_test: pd.Series) -> tuple[pd.Series, pd.Series, dict]:
    label_mapping = {
        "AWAY_WIN": 0,
        "DRAW": 1,
        "HOME_WIN": 2,
    }

    return y_train.map(label_mapping), y_test.map(label_mapping), label_mapping


# Reconvertit les prédictions numériques XGBoost vers les labels métier RubyBets.
def decode_xgboost_predictions(predictions, label_mapping: dict) -> list[str]:
    reverse_mapping = {value: key for key, value in label_mapping.items()}

    return [reverse_mapping[int(prediction)] for prediction in predictions]


# Calcule les métriques sur les prédictions où la probabilité maximale dépasse le seuil retenu.
def calculate_high_confidence_metrics(model, x_test: pd.DataFrame, y_test: pd.Series, predictions) -> dict:
    if not hasattr(model, "predict_proba"):
        return {
            "high_confidence_threshold": CONFIDENCE_THRESHOLD,
            "high_confidence_rows": 0,
            "high_confidence_coverage": 0.0,
            "high_confidence_accuracy": None,
            "high_confidence_home_win_rows": 0,
            "high_confidence_draw_rows": 0,
            "high_confidence_away_win_rows": 0,
        }

    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)
    selected_mask = max_probabilities >= CONFIDENCE_THRESHOLD
    selected_count = int(selected_mask.sum())

    if selected_count == 0:
        return {
            "high_confidence_threshold": CONFIDENCE_THRESHOLD,
            "high_confidence_rows": 0,
            "high_confidence_coverage": 0.0,
            "high_confidence_accuracy": None,
            "high_confidence_home_win_rows": 0,
            "high_confidence_draw_rows": 0,
            "high_confidence_away_win_rows": 0,
        }

    selected_predictions = pd.Series(predictions).reset_index(drop=True)[selected_mask]
    selected_truth = y_test.reset_index(drop=True)[selected_mask]
    selected_distribution = selected_predictions.value_counts().to_dict()

    return {
        "high_confidence_threshold": CONFIDENCE_THRESHOLD,
        "high_confidence_rows": selected_count,
        "high_confidence_coverage": round(selected_count / len(y_test), 4),
        "high_confidence_accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
        "high_confidence_home_win_rows": int(selected_distribution.get("HOME_WIN", 0)),
        "high_confidence_draw_rows": int(selected_distribution.get("DRAW", 0)),
        "high_confidence_away_win_rows": int(selected_distribution.get("AWAY_WIN", 0)),
    }


# Entraîne et évalue un modèle sur un seul feature set.
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
        y_train_encoded, _, label_mapping = encode_target_for_xgboost(y_train, y_test)
        model_to_train.fit(x_train, y_train_encoded)
        raw_predictions = model_to_train.predict(x_test)
        predictions = decode_xgboost_predictions(raw_predictions, label_mapping)
    else:
        model_to_train.fit(x_train, y_train)
        predictions = model_to_train.predict(x_test)

    report = classification_report(
        y_test,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    high_confidence = calculate_high_confidence_metrics(
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
        **high_confidence,
        "features": ", ".join(feature_columns),
    }


# Compare tous les modèles sur les familles de features sélectionnées.
def compare_models(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    candidate_models = build_candidate_models()

    for feature_set_name, feature_columns in SELECTED_FEATURE_SETS.items():
        for model_name, model in candidate_models.items():
            print(f"Evaluation : {model_name} sur {feature_set_name}", flush=True)

            result = evaluate_model_on_feature_set(
                feature_dataframe=feature_dataframe,
                feature_set_name=feature_set_name,
                feature_columns=feature_columns,
                model_name=model_name,
                model=model,
            )

            results.append(result)

    comparison = pd.DataFrame(results)

    return comparison.sort_values(
        by=["accuracy", "f1_macro", "high_confidence_accuracy"],
        ascending=False,
    )


# Construit le texte de synthèse lisible pour les preuves RNCP.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, comparison: pd.DataFrame) -> str:
    best_accuracy_row = comparison.sort_values(by=["accuracy", "f1_macro"], ascending=False).iloc[0]
    best_f1_macro_row = comparison.sort_values(by=["f1_macro", "accuracy"], ascending=False).iloc[0]
    high_confidence_dataframe = comparison.dropna(subset=["high_confidence_accuracy"]).copy()

    lines = [
        "RubyBets - ML 1X2 team strength features comparison",
        "39 - Experimentation force d'equipe avant-match sans modification de la base",
        "",
        "Positionnement :",
        "Cette experimentation teste des features de force d'equipe avant-match.",
        "Elle ne remplace pas le scoring explicable V1, ne modifie pas PostgreSQL et ne remplace pas la baseline ML sauvegardee.",
        "",
        "Nom retenu :",
        "- team_strength_rating : indice de force d'equipe avant-match.",
        "- Ancien nom technique possible : Elo, mais non utilise dans les libelles principaux pour rester clair en soutenance.",
        "",
        "Principe anti-fuite de donnees :",
        "- La force d'equipe est lue avant le match.",
        "- La mise a jour de la force est faite uniquement apres les matchs d'une meme date.",
        "- Les matchs du jour ne s'influencent pas entre eux.",
        "",
        "Baseline officielle actuelle :",
        f"- Accuracy officielle : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- F1 macro officiel : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        "",
        "Parametres team_strength_rating :",
        f"- Initial team strength : {INITIAL_TEAM_STRENGTH}",
        f"- K factor : {TEAM_STRENGTH_K_FACTOR}",
        f"- Recent delta window : {RECENT_DELTA_MATCH_WINDOW} matchs",
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
        f"- High confidence accuracy : {best_accuracy_row['high_confidence_accuracy']}",
        f"- High confidence coverage : {best_accuracy_row['high_confidence_coverage']}",
        f"- High confidence DRAW rows : {best_accuracy_row['high_confidence_draw_rows']}",
        "",
        "Best F1 macro:",
        f"- Feature set : {best_f1_macro_row['feature_set']}",
        f"- Model : {best_f1_macro_row['model']}",
        f"- Accuracy : {best_f1_macro_row['accuracy']}",
        f"- F1 macro : {best_f1_macro_row['f1_macro']}",
        f"- DRAW recall : {best_f1_macro_row['draw_recall']}",
        "",
    ]

    if not high_confidence_dataframe.empty:
        best_high_confidence_row = high_confidence_dataframe.sort_values(
            by=["high_confidence_accuracy", "high_confidence_coverage"],
            ascending=False,
        ).iloc[0]

        lines.extend(
            [
                "Best high-confidence signal:",
                f"- Feature set : {best_high_confidence_row['feature_set']}",
                f"- Model : {best_high_confidence_row['model']}",
                f"- High confidence threshold : {best_high_confidence_row['high_confidence_threshold']}",
                f"- High confidence accuracy : {best_high_confidence_row['high_confidence_accuracy']}",
                f"- High confidence coverage : {best_high_confidence_row['high_confidence_coverage']}",
                f"- High confidence rows : {best_high_confidence_row['high_confidence_rows']}",
                f"- High confidence DRAW rows : {best_high_confidence_row['high_confidence_draw_rows']}",
                "",
            ]
        )

    lines.extend(
        [
            "Comparison table:",
            comparison[
                [
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
                    "high_confidence_accuracy",
                    "high_confidence_coverage",
                    "high_confidence_rows",
                    "high_confidence_draw_rows",
                ]
            ].to_string(index=False),
            "",
            "Decision rules:",
            "- Si les features de force d'equipe ameliorent fortement accuracy et F1 macro, elles pourront servir a preparer une V2 separee.",
            "- Si l'accuracy globale reste loin de 0.70, le modele reste experimental.",
            "- Si seule la forte confiance atteint environ 0.70, le ML reste un signal limite aux matchs tres confiants.",
            "- Aucun modele sauvegarde, aucune API et aucune table SQL ne sont modifies par cette experimentation.",
            "",
            "Generated files:",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les résultats CSV et TXT de l’expérimentation.
def save_reports(comparison: pd.DataFrame, summary: str) -> None:
    comparison.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre toute l’expérimentation de force d’équipe.
def main() -> None:
    try:
        ensure_report_dir()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features last10 + force d'equipe en memoire...", flush=True)

        feature_dataframe = build_experiment_dataframe(clean_matches)

        print(f"Lignes de features construites : {len(feature_dataframe)}", flush=True)
        print("Comparaison des modeles avec team_strength_rating...", flush=True)

        comparison = compare_models(feature_dataframe)
        summary = build_summary(clean_matches, feature_dataframe, comparison)

        save_reports(comparison, summary)

        best_row = comparison.iloc[0]

        print("OK - Experimentation team_strength_rating terminee.")
        print(f"Best feature set: {best_row['feature_set']}")
        print(f"Best model: {best_row['model']}")
        print(f"Accuracy: {best_row['accuracy']}")
        print(f"F1 macro: {best_row['f1_macro']}")
        print(f"DRAW recall: {best_row['draw_recall']}")
        print(f"High confidence accuracy: {best_row['high_confidence_accuracy']}")
        print(f"High confidence coverage: {best_row['high_confidence_coverage']}")
        print("Summary saved: reports/evidence/ml_training/39_1x2_team_strength_features_comparison.txt")
        print("CSV saved: reports/evidence/ml_training/40_1x2_team_strength_features_comparison.csv")

    except Exception as error:
        print("Erreur pendant l'experimentation team_strength_rating.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# experiment_team_strength_features_1x2.py
#   -> réutilise compare_1x2_feature_sets.py pour charger PostgreSQL et reconstruire les features last10
#   -> lit backend/.env pour DATABASE_URL sans afficher de secret
#   -> lit PostgreSQL : ml.clean_matches
#   -> construit en mémoire les features team_strength_rating avant-match
#   -> compare plusieurs feature sets et modèles sans modifier ml.features
#   -> ne remplace pas models/ml/1x2/best_1x2_model.joblib
#   -> écrit reports/evidence/ml_training/39_1x2_team_strength_features_comparison.txt
#   -> écrit reports/evidence/ml_training/40_1x2_team_strength_features_comparison.csv
