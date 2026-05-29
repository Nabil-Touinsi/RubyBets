# Rôle du fichier : tester une stratégie ML 1X2 V4 centrée sur le risque de match nul, sans modifier la base, l'API, le frontend ou les modèles sauvegardés.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "65_1x2_v4_draw_aware_summary.txt"
CSV_PATH = REPORT_DIR / "66_1x2_v4_draw_aware_results.csv"
DECISION_PATH = REPORT_DIR / "67_1x2_v4_draw_aware_decision.txt"

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
V2_REFERENCE_DRAW_RECALL = 0.2803

MIN_ACCEPTED_ACCURACY = 0.5050
MIN_ACCEPTED_F1_MACRO = 0.4824
MIN_ACCEPTED_DRAW_RECALL = 0.3000
MIN_ACCEPTED_DRAW_PRECISION = 0.3000

DRAW_RISK_THRESHOLDS = [round(value / 100, 2) for value in range(30, 71, 5)]


# Crée le modèle 1X2 de référence V2 pour garder une comparaison stable.
def build_v2_reference_model() -> Pipeline:
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


# Crée le modèle binaire chargé de détecter le risque de match nul.
def build_draw_detector_model() -> Pipeline:
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


# Vérifie que les colonnes V2 attendues sont disponibles dans le DataFrame.
def validate_feature_columns(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> None:
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour la V4 DRAW-aware : {missing_columns}")


# Prépare le train/test chronologique utilisé par la V2 et la V4.
def prepare_train_test(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> tuple:
    validate_feature_columns(feature_dataframe, feature_columns)

    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation V4 DRAW-aware.")

    return (
        train_dataframe[feature_columns],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[feature_columns],
        test_dataframe[TARGET_COLUMN],
        train_dataframe,
        test_dataframe,
    )


# Transforme la cible 1X2 en cible binaire DRAW / NOT_DRAW.
def build_binary_draw_target(target_series: pd.Series) -> pd.Series:
    return target_series.apply(lambda value: "DRAW" if value == "DRAW" else "NOT_DRAW")


# Récupère la probabilité DRAW prédite par le détecteur binaire.
def extract_draw_probabilities(draw_detector_model: Pipeline, x_test: pd.DataFrame) -> pd.Series:
    classifier = draw_detector_model.named_steps["classifier"]
    class_labels = list(classifier.classes_)

    if "DRAW" not in class_labels:
        raise RuntimeError("Le detecteur DRAW ne contient pas la classe DRAW.")

    draw_index = class_labels.index("DRAW")
    probabilities = draw_detector_model.predict_proba(x_test)[:, draw_index]

    return pd.Series(probabilities, index=x_test.index)


# Calcule les métriques principales pour une liste de prédictions 1X2.
def evaluate_1x2_predictions(
    strategy_name: str,
    y_test: pd.Series,
    predictions: list[str],
    train_rows: int,
    test_rows: int,
    feature_count: int,
    draw_threshold: float | None = None,
    overridden_to_draw_rows: int = 0,
) -> dict:
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
        "strategy": strategy_name,
        "draw_threshold": draw_threshold,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "feature_count": feature_count,
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
        "overridden_to_draw_rows": overridden_to_draw_rows,
    }


# Évalue le détecteur binaire DRAW / NOT_DRAW seul.
def evaluate_draw_detector(y_test: pd.Series, draw_probabilities: pd.Series) -> dict:
    y_test_binary = build_binary_draw_target(y_test)
    binary_predictions = ["DRAW" if probability >= 0.50 else "NOT_DRAW" for probability in draw_probabilities]

    return {
        "draw_detector_threshold": 0.50,
        "draw_detector_precision": round(
            precision_score(y_test_binary, binary_predictions, pos_label="DRAW", zero_division=0),
            4,
        ),
        "draw_detector_recall": round(
            recall_score(y_test_binary, binary_predictions, pos_label="DRAW", zero_division=0),
            4,
        ),
        "draw_detector_predicted_draw_rows": int(pd.Series(binary_predictions).value_counts().get("DRAW", 0)),
        "draw_detector_actual_draw_rows": int(y_test_binary.value_counts().get("DRAW", 0)),
    }


# Applique la stratégie two-step : si risque DRAW élevé, on force DRAW, sinon on garde la V2.
def build_draw_aware_predictions(
    base_predictions: list[str],
    draw_probabilities: pd.Series,
    threshold: float,
) -> tuple[list[str], int]:
    final_predictions = []
    overridden_to_draw_rows = 0

    for base_prediction, draw_probability in zip(base_predictions, draw_probabilities):
        if draw_probability >= threshold and base_prediction != "DRAW":
            final_predictions.append("DRAW")
            overridden_to_draw_rows += 1
        else:
            final_predictions.append(base_prediction)

    return final_predictions, overridden_to_draw_rows


# Lance la comparaison entre V2 référence et variantes V4 DRAW-aware.
def run_draw_aware_experiment(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    feature_columns = SELECTED_FEATURE_SETS[V2_REFERENCE_FEATURE_SET]

    x_train, y_train, x_test, y_test, train_dataframe, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    v2_model = build_v2_reference_model()
    v2_model.fit(x_train, y_train)
    base_predictions = list(v2_model.predict(x_test))

    draw_detector_model = build_draw_detector_model()
    draw_detector_model.fit(x_train, build_binary_draw_target(y_train))
    draw_probabilities = extract_draw_probabilities(draw_detector_model, x_test)

    results = [
        evaluate_1x2_predictions(
            strategy_name="v2_reference_logistic_regression",
            y_test=y_test,
            predictions=base_predictions,
            train_rows=len(train_dataframe),
            test_rows=len(test_dataframe),
            feature_count=len(feature_columns),
        )
    ]

    for threshold in DRAW_RISK_THRESHOLDS:
        draw_aware_predictions, overridden_to_draw_rows = build_draw_aware_predictions(
            base_predictions=base_predictions,
            draw_probabilities=draw_probabilities,
            threshold=threshold,
        )
        results.append(
            evaluate_1x2_predictions(
                strategy_name="v4_draw_aware_two_step",
                y_test=y_test,
                predictions=draw_aware_predictions,
                train_rows=len(train_dataframe),
                test_rows=len(test_dataframe),
                feature_count=len(feature_columns),
                draw_threshold=threshold,
                overridden_to_draw_rows=overridden_to_draw_rows,
            )
        )

    return pd.DataFrame(results), evaluate_draw_detector(y_test, draw_probabilities)


# Sélectionne le meilleur candidat selon les critères de validation V4.
def select_best_candidate(results_dataframe: pd.DataFrame) -> tuple[pd.Series | None, pd.Series]:
    draw_aware_rows = results_dataframe[results_dataframe["strategy"] == "v4_draw_aware_two_step"].copy()

    eligible_rows = draw_aware_rows[
        (draw_aware_rows["accuracy"] >= MIN_ACCEPTED_ACCURACY)
        & (draw_aware_rows["f1_macro"] > MIN_ACCEPTED_F1_MACRO)
        & (draw_aware_rows["draw_recall"] > MIN_ACCEPTED_DRAW_RECALL)
        & (draw_aware_rows["draw_precision"] >= MIN_ACCEPTED_DRAW_PRECISION)
        & (draw_aware_rows["predicted_draw_rows"] > 0)
    ].copy()

    exploratory_best = draw_aware_rows.sort_values(
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


# Construit le résumé texte de l'expérience V4.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, results_dataframe: pd.DataFrame, detector_metrics: dict) -> str:
    reference_row = results_dataframe[results_dataframe["strategy"] == "v2_reference_logistic_regression"].iloc[0]
    eligible_best, exploratory_best = select_best_candidate(results_dataframe)

    lines = [
        "RubyBets - ML 1X2 V4 DRAW-aware experiment",
        "65 - Synthese de l'experimentation DRAW-aware",
        "",
        "Objectif :",
        "Tester une strategie dediee au risque de match nul sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes.",
        "",
        "Contexte :",
        "La phase V3 a montre une bonne precision forte confiance, mais une faiblesse majeure sur les DRAW.",
        "La V4 teste donc une approche two-step : detecter le risque DRAW, puis ajuster la prediction 1X2.",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features candidates construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Reference V2 attendue :",
        f"- Accuracy : {V2_REFERENCE_ACCURACY:.4f}",
        f"- F1 macro : {V2_REFERENCE_F1_MACRO:.4f}",
        f"- DRAW recall : {V2_REFERENCE_DRAW_RECALL:.4f}",
        "",
        "Reference V2 recalculee dans ce script :",
        f"- Accuracy : {reference_row['accuracy']}",
        f"- F1 macro : {reference_row['f1_macro']}",
        f"- DRAW precision : {reference_row['draw_precision']}",
        f"- DRAW recall : {reference_row['draw_recall']}",
        f"- Predicted DRAW rows : {reference_row['predicted_draw_rows']}",
        "",
        "Detecteur binaire DRAW / NOT_DRAW :",
        f"- Threshold : {detector_metrics['draw_detector_threshold']}",
        f"- DRAW precision : {detector_metrics['draw_detector_precision']}",
        f"- DRAW recall : {detector_metrics['draw_detector_recall']}",
        f"- Predicted DRAW rows : {detector_metrics['draw_detector_predicted_draw_rows']}",
        f"- Actual DRAW rows : {detector_metrics['draw_detector_actual_draw_rows']}",
        "",
        "Meilleur candidat V4 eligible :",
    ]

    if eligible_best is None:
        lines.extend(
            [
                "- Aucun candidat V4 ne respecte tous les criteres de validation.",
                "",
                "Meilleur candidat exploratoire observe :",
                f"- Threshold DRAW : {exploratory_best['draw_threshold']}",
                f"- Accuracy : {exploratory_best['accuracy']}",
                f"- F1 macro : {exploratory_best['f1_macro']}",
                f"- DRAW precision : {exploratory_best['draw_precision']}",
                f"- DRAW recall : {exploratory_best['draw_recall']}",
                f"- Predicted DRAW rows : {exploratory_best['predicted_draw_rows']}",
                f"- Overridden to DRAW rows : {exploratory_best['overridden_to_draw_rows']}",
            ]
        )
    else:
        lines.extend(
            [
                f"- Threshold DRAW : {eligible_best['draw_threshold']}",
                f"- Accuracy : {eligible_best['accuracy']}",
                f"- F1 macro : {eligible_best['f1_macro']}",
                f"- DRAW precision : {eligible_best['draw_precision']}",
                f"- DRAW recall : {eligible_best['draw_recall']}",
                f"- Predicted DRAW rows : {eligible_best['predicted_draw_rows']}",
                f"- Overridden to DRAW rows : {eligible_best['overridden_to_draw_rows']}",
            ]
        )

    lines.extend(
        [
            "",
            "Criteres de validation V4 :",
            f"- accuracy >= {MIN_ACCEPTED_ACCURACY:.4f}",
            f"- f1_macro > {MIN_ACCEPTED_F1_MACRO:.4f}",
            f"- draw_recall > {MIN_ACCEPTED_DRAW_RECALL:.4f}",
            f"- draw_precision >= {MIN_ACCEPTED_DRAW_PRECISION:.4f}",
            "- predicted_draw_rows > 0",
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
        ]
    )

    return "\n".join(lines)


# Construit la décision finale V4 à partir des résultats obtenus.
def build_decision(results_dataframe: pd.DataFrame, detector_metrics: dict) -> str:
    reference_row = results_dataframe[results_dataframe["strategy"] == "v2_reference_logistic_regression"].iloc[0]
    eligible_best, exploratory_best = select_best_candidate(results_dataframe)

    lines = [
        "RubyBets - ML 1X2 V4 DRAW-aware decision",
        "67 - Decision apres experimentation DRAW-aware",
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
        "Detecteur DRAW :",
        f"- DRAW precision : {detector_metrics['draw_detector_precision']}",
        f"- DRAW recall : {detector_metrics['draw_detector_recall']}",
        f"- Predicted DRAW rows : {detector_metrics['draw_detector_predicted_draw_rows']}",
        "",
    ]

    if eligible_best is None:
        lines.extend(
            [
                "Decision finale :",
                "La V4 DRAW-aware n'est pas retenue comme candidat global pour le moment.",
                "Aucun seuil two-step ne respecte tous les criteres de validation fixes avant l'experience.",
                "",
                "Meilleur signal exploratoire observe :",
                f"- Threshold DRAW : {exploratory_best['draw_threshold']}",
                f"- Accuracy : {exploratory_best['accuracy']}",
                f"- F1 macro : {exploratory_best['f1_macro']}",
                f"- DRAW precision : {exploratory_best['draw_precision']}",
                f"- DRAW recall : {exploratory_best['draw_recall']}",
                f"- Predicted DRAW rows : {exploratory_best['predicted_draw_rows']}",
                "",
                "Suite recommandee :",
                "Ne pas multiplier les modeles generaux. Si la V4 n'ameliore pas le DRAW sans casser l'accuracy, la prochaine vraie piste sera l'enrichissement de donnees et de features specifiques au contexte avant-match.",
            ]
        )
    else:
        lines.extend(
            [
                "Decision finale :",
                "La V4 DRAW-aware est retenue comme candidat experimental a approfondir.",
                "Elle ameliore le traitement du DRAW tout en respectant les seuils minimums fixes avant l'experience.",
                "",
                "Candidat V4 retenu :",
                f"- Threshold DRAW : {eligible_best['draw_threshold']}",
                f"- Accuracy : {eligible_best['accuracy']}",
                f"- F1 macro : {eligible_best['f1_macro']}",
                f"- DRAW precision : {eligible_best['draw_precision']}",
                f"- DRAW recall : {eligible_best['draw_recall']}",
                f"- Predicted DRAW rows : {eligible_best['predicted_draw_rows']}",
                "",
                "Suite recommandee :",
                "Preparer une etape separee pour exporter les predictions V4, analyser les erreurs et verifier la stabilite par ligue et par saison avant toute sauvegarde de modele.",
            ]
        )

    lines.extend(
        [
            "",
            "Formulation soutenance :",
            "RubyBets a teste une strategie ML plus responsable pour le 1X2 : au lieu de chercher seulement l'accuracy globale, l'experience V4 verifie si le risque de match nul peut etre detecte et integre proprement.",
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V4 DRAW-aware.",
            "- Statut source a mettre a jour : realise si les fichiers 65, 66 et 67 sont generes.",
            "- Fichiers concernes : reports/evidence/ml_training/65, 66 et 67.",
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


# Lance toute l'expérimentation V4 DRAW-aware.
def main() -> None:
    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features V2 de reference en memoire...", flush=True)

    feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

    print("Evaluation de la strategie V4 DRAW-aware...", flush=True)

    results_dataframe, detector_metrics = run_draw_aware_experiment(feature_dataframe)
    summary = build_summary(clean_matches, feature_dataframe, results_dataframe, detector_metrics)
    decision = build_decision(results_dataframe, detector_metrics)

    save_reports(results_dataframe, summary, decision)

    eligible_best, exploratory_best = select_best_candidate(results_dataframe)
    displayed_row = exploratory_best if eligible_best is None else eligible_best

    print("OK - Experimentation V4 DRAW-aware terminee.", flush=True)
    print(f"Best threshold: {displayed_row['draw_threshold']}", flush=True)
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
# experiment_1x2_v4_draw_aware_strategy.py
#   -> lit ml.clean_matches via les fonctions existantes
#   -> reutilise les features V2 construites en memoire
#   -> entraine un modele V2 de reference et un detecteur DRAW binaire
#   -> genere reports/evidence/ml_training/65, 66 et 67
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
