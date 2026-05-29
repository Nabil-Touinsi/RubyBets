# Rôle du fichier : tester une V5 ML 1X2 centrée sur des features d'équilibre de match, sans modifier la base, l'API, le frontend ou les modèles sauvegardés.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "68_1x2_v5_balance_features_summary.txt"
CSV_PATH = REPORT_DIR / "69_1x2_v5_balance_features_results.csv"
DECISION_PATH = REPORT_DIR / "70_1x2_v5_balance_features_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v2_feature_candidates import (  # noqa: E402
    SELECTED_FEATURE_SETS,
    build_v2_fast_feature_dataframe,
)

warnings.filterwarnings("ignore", category=UserWarning)

CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]
V2_REFERENCE_FEATURE_SET = "last10_plus_team_strength_plus_match_balance"
V2_REFERENCE_MODEL_NAME = "LogisticRegression_balanced"

V2_REFERENCE_ACCURACY = 0.5111
V2_REFERENCE_F1_MACRO = 0.4824
V2_REFERENCE_DRAW_PRECISION = 0.3255
V2_REFERENCE_DRAW_RECALL = 0.2803

MIN_ACCEPTED_ACCURACY = 0.5111
MIN_ACCEPTED_F1_MACRO = 0.4824
MIN_ACCEPTED_DRAW_PRECISION = 0.3255
MIN_ACCEPTED_DRAW_RECALL = 0.2803

V5_CORE_BALANCE_COLUMNS = [
    "home_attack_vs_away_defense",
    "away_attack_vs_home_defense",
    "attack_defense_pressure_diff",
    "abs_attack_defense_pressure_diff",
    "goal_pressure_symmetry_score",
    "form_symmetry_score",
    "strength_symmetry_score",
]

V5_DRAW_CONTEXT_COLUMNS = [
    "total_expected_goal_pressure",
    "scoring_environment_balance",
    "balanced_low_scoring_profile",
    "balanced_defensive_profile",
    "high_concession_draw_risk",
    "both_teams_moderate_attack",
    "close_strength_and_form",
    "close_attack_defense_pressure",
    "draw_context_signal_count",
]

V5_SCORE_COLUMNS = [
    "draw_context_score",
    "draw_risk_feature_score",
]


# Supprime les doublons dans une liste de colonnes en gardant l'ordre initial.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


# Crée le modèle de référence utilisé pour isoler l'effet des features V5.
def build_reference_model() -> Pipeline:
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


# Convertit une colonne en numérique si elle existe dans le DataFrame.
def numeric_column(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        raise RuntimeError(f"Colonne requise absente pour la V5 : {column}")

    return pd.to_numeric(dataframe[column], errors="coerce")


# Ajoute des features d'équilibre et de contexte DRAW à partir des features V2 déjà calculées.
def add_v5_balance_features(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = feature_dataframe.copy()

    required_columns = [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "abs_team_strength_diff",
        "home_expected_goal_pressure",
        "away_expected_goal_pressure",
        "abs_expected_goal_pressure_diff",
        "is_close_form_match",
        "is_close_scoring_match",
        "is_close_defense_match",
        "is_close_goal_pressure_match",
        "is_close_strength_match",
        "match_balance_score_with_strength",
        "draw_profile_score_with_strength",
    ]

    for column in required_columns:
        dataframe[column] = numeric_column(dataframe, column)

    dataframe["home_attack_vs_away_defense"] = (
        dataframe["home_goals_scored_avg_last_10"] - dataframe["away_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["away_attack_vs_home_defense"] = (
        dataframe["away_goals_scored_avg_last_10"] - dataframe["home_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["attack_defense_pressure_diff"] = (
        dataframe["home_attack_vs_away_defense"] - dataframe["away_attack_vs_home_defense"]
    ).round(4)
    dataframe["abs_attack_defense_pressure_diff"] = dataframe["attack_defense_pressure_diff"].abs().round(4)

    dataframe["total_expected_goal_pressure"] = (
        dataframe["home_expected_goal_pressure"] + dataframe["away_expected_goal_pressure"]
    ).round(4)
    dataframe["scoring_environment_balance"] = (
        1 / (1 + (dataframe["total_expected_goal_pressure"] - 2.4).abs())
    ).round(4)

    dataframe["goal_pressure_symmetry_score"] = (
        1 / (1 + dataframe["abs_expected_goal_pressure_diff"] / 0.35)
    ).round(4)
    dataframe["form_symmetry_score"] = (
        1 / (1 + dataframe["abs_form_points_diff"] / 3.0)
    ).round(4)
    dataframe["strength_symmetry_score"] = (
        1 / (1 + dataframe["abs_team_strength_diff"] / 60.0)
    ).round(4)

    dataframe["balanced_low_scoring_profile"] = (
        (dataframe["home_goals_scored_avg_last_10"] <= 1.35)
        & (dataframe["away_goals_scored_avg_last_10"] <= 1.35)
        & (dataframe["abs_expected_goal_pressure_diff"] <= 0.35)
    ).astype(int)
    dataframe["balanced_defensive_profile"] = (
        (dataframe["home_goals_conceded_avg_last_10"] <= 1.25)
        & (dataframe["away_goals_conceded_avg_last_10"] <= 1.25)
        & (dataframe["abs_goals_conceded_diff"] <= 0.35)
    ).astype(int)
    dataframe["high_concession_draw_risk"] = (
        (dataframe["home_goals_conceded_avg_last_10"] >= 1.20)
        & (dataframe["away_goals_conceded_avg_last_10"] >= 1.20)
        & (dataframe["abs_attack_defense_pressure_diff"] <= 0.35)
    ).astype(int)
    dataframe["both_teams_moderate_attack"] = (
        (dataframe["home_goals_scored_avg_last_10"].between(1.0, 1.8, inclusive="both"))
        & (dataframe["away_goals_scored_avg_last_10"].between(1.0, 1.8, inclusive="both"))
    ).astype(int)
    dataframe["close_strength_and_form"] = (
        (dataframe["is_close_strength_match"] == 1)
        & (dataframe["is_close_form_match"] == 1)
    ).astype(int)
    dataframe["close_attack_defense_pressure"] = (
        dataframe["abs_attack_defense_pressure_diff"] <= 0.35
    ).astype(int)

    dataframe["draw_context_signal_count"] = (
        dataframe["is_close_form_match"]
        + dataframe["is_close_scoring_match"]
        + dataframe["is_close_defense_match"]
        + dataframe["is_close_goal_pressure_match"]
        + dataframe["is_close_strength_match"]
        + dataframe["balanced_low_scoring_profile"]
        + dataframe["balanced_defensive_profile"]
        + dataframe["high_concession_draw_risk"]
        + dataframe["both_teams_moderate_attack"]
        + dataframe["close_strength_and_form"]
        + dataframe["close_attack_defense_pressure"]
    )

    dataframe["draw_context_score"] = (
        dataframe["draw_context_signal_count"]
        + dataframe["goal_pressure_symmetry_score"]
        + dataframe["form_symmetry_score"]
        + dataframe["strength_symmetry_score"]
        + dataframe["scoring_environment_balance"]
    ).round(4)

    dataframe["draw_risk_feature_score"] = (
        dataframe["draw_profile_score_with_strength"]
        + dataframe["match_balance_score_with_strength"]
        + dataframe["draw_context_score"]
    ).round(4)

    return dataframe


# Construit les familles de features V5 à comparer avec la V2 de référence.
def build_v5_feature_sets() -> dict[str, list[str]]:
    v2_reference_columns = SELECTED_FEATURE_SETS[V2_REFERENCE_FEATURE_SET]

    return {
        "v2_reference": dedupe_columns(v2_reference_columns),
        "v5_balance_symmetry_core": dedupe_columns(
            v2_reference_columns + V5_CORE_BALANCE_COLUMNS
        ),
        "v5_draw_context_flags": dedupe_columns(
            v2_reference_columns + V5_DRAW_CONTEXT_COLUMNS
        ),
        "v5_draw_context_scores": dedupe_columns(
            v2_reference_columns + V5_SCORE_COLUMNS
        ),
        "v5_balance_features_full": dedupe_columns(
            v2_reference_columns
            + V5_CORE_BALANCE_COLUMNS
            + V5_DRAW_CONTEXT_COLUMNS
            + V5_SCORE_COLUMNS
        ),
    }


# Vérifie que toutes les colonnes d'un set existent dans le DataFrame.
def validate_feature_columns(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> None:
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour la V5 balance features : {missing_columns}")


# Prépare le train/test chronologique pour un set de features donné.
def prepare_train_test(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> tuple:
    validate_feature_columns(feature_dataframe, feature_columns)

    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation V5 balance features.")

    return (
        train_dataframe[feature_columns],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[feature_columns],
        test_dataframe[TARGET_COLUMN],
        working_dataframe,
        train_dataframe,
        test_dataframe,
    )


# Calcule les métriques principales pour juger un candidat V5.
def evaluate_predictions(feature_set_name: str, feature_columns: list[str], y_test: pd.Series, predictions: list[str], working_dataframe: pd.DataFrame, train_dataframe: pd.DataFrame, test_dataframe: pd.DataFrame) -> dict:
    report = classification_report(
        y_test,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    prediction_distribution = pd.Series(predictions).value_counts().to_dict()
    actual_distribution = y_test.value_counts().to_dict()

    return {
        "feature_set": feature_set_name,
        "model": V2_REFERENCE_MODEL_NAME,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": len(working_dataframe),
        "train_rows": len(train_dataframe),
        "test_rows": len(test_dataframe),
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "home_win_precision": round(report["HOME_WIN"]["precision"], 4),
        "home_win_recall": round(report["HOME_WIN"]["recall"], 4),
        "draw_precision": round(report["DRAW"]["precision"], 4),
        "draw_recall": round(report["DRAW"]["recall"], 4),
        "away_win_precision": round(report["AWAY_WIN"]["precision"], 4),
        "away_win_recall": round(report["AWAY_WIN"]["recall"], 4),
        "predicted_home_win_rows": int(prediction_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_distribution.get("AWAY_WIN", 0)),
        "actual_home_win_rows": int(actual_distribution.get("HOME_WIN", 0)),
        "actual_draw_rows": int(actual_distribution.get("DRAW", 0)),
        "actual_away_win_rows": int(actual_distribution.get("AWAY_WIN", 0)),
        "features": ", ".join(feature_columns),
    }


# Entraîne et évalue le modèle de référence sur un set de features.
def evaluate_feature_set(feature_dataframe: pd.DataFrame, feature_set_name: str, feature_columns: list[str]) -> dict:
    x_train, y_train, x_test, y_test, working_dataframe, train_dataframe, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)
    predictions = list(model.predict(x_test))

    return evaluate_predictions(
        feature_set_name=feature_set_name,
        feature_columns=feature_columns,
        y_test=y_test,
        predictions=predictions,
        working_dataframe=working_dataframe,
        train_dataframe=train_dataframe,
        test_dataframe=test_dataframe,
    )


# Lance la comparaison V5 en isolant l'effet des features d'équilibre.
def run_v5_balance_comparison(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    feature_sets = build_v5_feature_sets()

    for feature_set_name, feature_columns in feature_sets.items():
        print(f"Evaluation V5 : {feature_set_name}", flush=True)
        results.append(
            evaluate_feature_set(
                feature_dataframe=feature_dataframe,
                feature_set_name=feature_set_name,
                feature_columns=feature_columns,
            )
        )

    results_dataframe = pd.DataFrame(results)

    return results_dataframe.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    )


# Sélectionne le meilleur candidat V5 selon les critères définis avant l'expérience.
def select_best_candidate(results_dataframe: pd.DataFrame) -> tuple[pd.Series | None, pd.Series]:
    v5_rows = results_dataframe[results_dataframe["feature_set"] != "v2_reference"].copy()

    eligible_rows = v5_rows[
        (v5_rows["accuracy"] >= MIN_ACCEPTED_ACCURACY)
        & (v5_rows["f1_macro"] > MIN_ACCEPTED_F1_MACRO)
        & (v5_rows["draw_recall"] > MIN_ACCEPTED_DRAW_RECALL)
        & (v5_rows["draw_precision"] >= MIN_ACCEPTED_DRAW_PRECISION)
        & (v5_rows["predicted_draw_rows"] > 0)
    ].copy()

    exploratory_best = v5_rows.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    ).iloc[0]

    if eligible_rows.empty:
        return None, exploratory_best

    eligible_best = eligible_rows.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    ).iloc[0]

    return eligible_best, exploratory_best


# Construit le résumé texte de l'expérience V5.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, results_dataframe: pd.DataFrame) -> str:
    reference_row = results_dataframe[results_dataframe["feature_set"] == "v2_reference"].iloc[0]
    eligible_best, exploratory_best = select_best_candidate(results_dataframe)

    lines = [
        "RubyBets - ML 1X2 V5 balance features experiment",
        "68 - Synthese de l'experimentation balance features",
        "",
        "Objectif :",
        "Tester des features ciblees sur l'equilibre du match et le contexte DRAW, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes.",
        "",
        "Contexte :",
        "La V4 DRAW-aware n'a pas ameliore la V2. Le detecteur DRAW a montre un signal, mais pas assez propre pour ameliorer le 1X2 complet.",
        "La V5 ne multiplie donc pas les modeles : elle teste uniquement si de meilleures variables d'equilibre ameliorent le modele de reference.",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features V5 construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Reference V2 attendue :",
        f"- Accuracy : {V2_REFERENCE_ACCURACY:.4f}",
        f"- F1 macro : {V2_REFERENCE_F1_MACRO:.4f}",
        f"- DRAW precision : {V2_REFERENCE_DRAW_PRECISION:.4f}",
        f"- DRAW recall : {V2_REFERENCE_DRAW_RECALL:.4f}",
        "",
        "Reference V2 recalculee dans ce script :",
        f"- Accuracy : {reference_row['accuracy']}",
        f"- F1 macro : {reference_row['f1_macro']}",
        f"- DRAW precision : {reference_row['draw_precision']}",
        f"- DRAW recall : {reference_row['draw_recall']}",
        f"- Predicted DRAW rows : {reference_row['predicted_draw_rows']}",
        "",
        "Meilleur candidat V5 eligible :",
    ]

    if eligible_best is None:
        lines.extend(
            [
                "- Aucun candidat V5 ne respecte tous les criteres de validation.",
                "",
                "Meilleur candidat exploratoire observe :",
                f"- Feature set : {exploratory_best['feature_set']}",
                f"- Accuracy : {exploratory_best['accuracy']}",
                f"- F1 macro : {exploratory_best['f1_macro']}",
                f"- DRAW precision : {exploratory_best['draw_precision']}",
                f"- DRAW recall : {exploratory_best['draw_recall']}",
                f"- Predicted DRAW rows : {exploratory_best['predicted_draw_rows']}",
            ]
        )
    else:
        lines.extend(
            [
                f"- Feature set : {eligible_best['feature_set']}",
                f"- Accuracy : {eligible_best['accuracy']}",
                f"- F1 macro : {eligible_best['f1_macro']}",
                f"- DRAW precision : {eligible_best['draw_precision']}",
                f"- DRAW recall : {eligible_best['draw_recall']}",
                f"- Predicted DRAW rows : {eligible_best['predicted_draw_rows']}",
            ]
        )

    lines.extend(
        [
            "",
            "Criteres de validation V5 :",
            f"- accuracy >= {MIN_ACCEPTED_ACCURACY:.4f}",
            f"- f1_macro > {MIN_ACCEPTED_F1_MACRO:.4f}",
            f"- draw_recall > {MIN_ACCEPTED_DRAW_RECALL:.4f}",
            f"- draw_precision >= {MIN_ACCEPTED_DRAW_PRECISION:.4f}",
            "- predicted_draw_rows > 0",
            "",
            "Feature sets testes :",
        ]
    )

    for _, row in results_dataframe.sort_values(by="feature_set").iterrows():
        lines.append(
            f"- {row['feature_set']} : accuracy={row['accuracy']}, f1_macro={row['f1_macro']}, draw_precision={row['draw_precision']}, draw_recall={row['draw_recall']}"
        )

    lines.extend(
        [
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
        ]
    )

    return "\n".join(lines)


# Construit la décision finale V5 à partir des résultats obtenus.
def build_decision(results_dataframe: pd.DataFrame) -> str:
    reference_row = results_dataframe[results_dataframe["feature_set"] == "v2_reference"].iloc[0]
    eligible_best, exploratory_best = select_best_candidate(results_dataframe)

    lines = [
        "RubyBets - ML 1X2 V5 balance features decision",
        "70 - Decision apres experimentation balance features",
        "",
        "Decision de perimetre :",
        "- Aucun modele sauvegarde n'est remplace automatiquement.",
        "- Aucune table SQL n'est creee ou modifiee.",
        "- Aucune route API n'est modifiee.",
        "- Aucun composant frontend n'est modifie.",
        "- Le scoring explicable V1 reste le socle produit officiel.",
        "",
        "Reference V2 recalculee :",
        f"- Accuracy : {reference_row['accuracy']}",
        f"- F1 macro : {reference_row['f1_macro']}",
        f"- DRAW precision : {reference_row['draw_precision']}",
        f"- DRAW recall : {reference_row['draw_recall']}",
        f"- Predicted DRAW rows : {reference_row['predicted_draw_rows']}",
        "",
    ]

    if eligible_best is None:
        lines.extend(
            [
                "Decision finale :",
                "La V5 balance features n'est pas retenue comme candidat global pour le moment.",
                "Aucun set de features V5 ne respecte tous les criteres fixes avant l'experience.",
                "",
                "Meilleur signal exploratoire observe :",
                f"- Feature set : {exploratory_best['feature_set']}",
                f"- Accuracy : {exploratory_best['accuracy']}",
                f"- F1 macro : {exploratory_best['f1_macro']}",
                f"- DRAW precision : {exploratory_best['draw_precision']}",
                f"- DRAW recall : {exploratory_best['draw_recall']}",
                f"- Predicted DRAW rows : {exploratory_best['predicted_draw_rows']}",
                "",
                "Suite recommandee :",
                "Ne pas continuer a ajouter des features derivees des memes colonnes si la V5 ne progresse pas. La prochaine vraie piste sera d'enrichir le dataset avec des variables avant-match nouvelles : classement, points saison, forme domicile/exterieur avancee, ecart de classement, repos, calendrier ou odds historiques si source fiable.",
            ]
        )
    else:
        lines.extend(
            [
                "Decision finale :",
                "La V5 balance features est retenue comme candidat experimental a approfondir.",
                "Elle ameliore le traitement du DRAW tout en respectant les seuils minimums fixes avant l'experience.",
                "",
                "Candidat V5 retenu :",
                f"- Feature set : {eligible_best['feature_set']}",
                f"- Accuracy : {eligible_best['accuracy']}",
                f"- F1 macro : {eligible_best['f1_macro']}",
                f"- DRAW precision : {eligible_best['draw_precision']}",
                f"- DRAW recall : {eligible_best['draw_recall']}",
                f"- Predicted DRAW rows : {eligible_best['predicted_draw_rows']}",
                "",
                "Suite recommandee :",
                "Preparer une etape separee pour analyser les erreurs du candidat V5, verifier sa stabilite par ligue et par saison, puis decider s'il doit devenir un candidat sauvegardable.",
            ]
        )

    lines.extend(
        [
            "",
            "Formulation soutenance :",
            "RubyBets ne cherche pas seulement a empiler des modeles : l'experience V5 teste si les variables de contexte et d'equilibre du match ameliorent reellement la prediction 1X2, notamment la classe DRAW.",
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V5 balance features.",
            "- Statut source a mettre a jour : realise si les fichiers 68, 69 et 70 sont generes.",
            "- Fichiers concernes : reports/evidence/ml_training/68, 69 et 70.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les fichiers de synthèse, résultats et décision.
def save_reports(results_dataframe: pd.DataFrame, summary: str, decision: str) -> None:
    ensure_report_dir()
    results_dataframe.to_csv(CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérimentation V5 balance features.
def main() -> None:
    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features V2 de reference en memoire...", flush=True)

    v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

    print("Ajout des features V5 d'equilibre de match...", flush=True)
    v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

    print("Evaluation des sets V5 balance features...", flush=True)
    results_dataframe = run_v5_balance_comparison(v5_feature_dataframe)

    summary = build_summary(clean_matches, v5_feature_dataframe, results_dataframe)
    decision = build_decision(results_dataframe)
    save_reports(results_dataframe, summary, decision)

    eligible_best, exploratory_best = select_best_candidate(results_dataframe)
    displayed_row = exploratory_best if eligible_best is None else eligible_best

    print("OK - Experimentation V5 balance features terminee.", flush=True)
    print(f"Best feature set: {displayed_row['feature_set']}", flush=True)
    print(f"Accuracy: {displayed_row['accuracy']}", flush=True)
    print(f"F1 macro: {displayed_row['f1_macro']}", flush=True)
    print(f"DRAW precision: {displayed_row['draw_precision']}", flush=True)
    print(f"DRAW recall: {displayed_row['draw_recall']}", flush=True)
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()


# Schema de communication :
# experiment_1x2_v5_balance_features.py
#   -> lit ml.clean_matches via les fonctions existantes
#   -> reutilise les features V2 construites en memoire
#   -> ajoute des features V5 d'equilibre et de contexte DRAW
#   -> compare V2 reference et plusieurs sets V5 avec LogisticRegression_balanced
#   -> genere reports/evidence/ml_training/68, 69 et 70
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
