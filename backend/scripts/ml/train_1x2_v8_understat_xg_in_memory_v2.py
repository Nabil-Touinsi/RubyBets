# Rôle du fichier : lancer une expérience ML 1X2 V8 avec les features rolling xG Understat en mémoire, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.
# Correction V2 : le CSV de prédictions gère les colonnes de score comme optionnelles, car ml.clean_matches ne les expose pas toujours sous les noms home_goals / away_goals.

from pathlib import Path
import json
import sys
import warnings

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

ROLLING_XG_PATH = REPORT_DIR / "125_1x2_understat_rolling_xg_dry_run_features.csv"
SUMMARY_PATH = REPORT_DIR / "129_1x2_v8_understat_xg_in_memory_summary.txt"
RESULTS_CSV_PATH = REPORT_DIR / "130_1x2_v8_understat_xg_in_memory_results.csv"
PREDICTIONS_CSV_PATH = REPORT_DIR / "131_1x2_v8_understat_xg_in_memory_best_predictions.csv"
REPORT_JSON_PATH = REPORT_DIR / "132_1x2_v8_understat_xg_in_memory_classification_report.json"
DECISION_PATH = REPORT_DIR / "133_1x2_v8_understat_xg_in_memory_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v5_balance_features import (  # noqa: E402
    CLASS_LABELS,
    V2_REFERENCE_MODEL_NAME,
    add_v5_balance_features,
    build_reference_model,
    build_v5_feature_sets,
)
from experiment_1x2_v6_market_prior import (  # noqa: E402
    MARKET_GAP_COLUMNS,
    MARKET_PROBABILITY_COLUMNS,
    build_market_prior_dataframe,
    fetch_market_raw_data,
    merge_market_prior_features,
)
from experiment_1x2_v2_feature_candidates import build_v2_fast_feature_dataframe  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)

TRAIN_SEASONS = [
    "2014_2015",
    "2015_2016",
    "2016_2017",
    "2017_2018",
    "2018_2019",
    "2019_2020",
    "2020_2021",
    "2021_2022",
]
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]

V6_GLOBAL_BEST_ACCURACY = 0.5205
V6_GLOBAL_BEST_F1_MACRO = 0.4878
V6_GLOBAL_BEST_DRAW_PRECISION = 0.3166
V6_GLOBAL_BEST_DRAW_RECALL = 0.2628

XG_ROLLING_FEATURE_COLUMNS = [
    "home_xg_for_avg_last_5",
    "home_xg_against_avg_last_5",
    "home_xg_diff_avg_last_5",
    "away_xg_for_avg_last_5",
    "away_xg_against_avg_last_5",
    "away_xg_diff_avg_last_5",
    "xg_for_diff_last_5",
    "xg_against_diff_last_5",
    "xg_balance_diff_last_5",
]

XG_BALANCE_ONLY_COLUMNS = [
    "home_xg_diff_avg_last_5",
    "away_xg_diff_avg_last_5",
    "xg_for_diff_last_5",
    "xg_against_diff_last_5",
    "xg_balance_diff_last_5",
]

XG_METADATA_COLUMNS = [
    "clean_match_id",
    "understat_match_id",
    "match_url",
    "home_xg_matches_available_last_5",
    "away_xg_matches_available_last_5",
] + XG_ROLLING_FEATURE_COLUMNS


# Crée le dossier de preuves ML si nécessaire.
def ensure_v8_report_dir() -> None:
    ensure_report_dir()


# Arrondit une valeur numérique pour stabiliser les sorties CSV et texte.
def rounded(value: float | int | None, digits: int = 4) -> float:
    if value is None:
        return 0.0

    return round(float(value), digits)


# Supprime les doublons dans une liste en conservant l'ordre initial.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


# Charge les features rolling xG générées par le dry-run précédent.
def load_rolling_xg_features() -> pd.DataFrame:
    if not ROLLING_XG_PATH.exists():
        raise FileNotFoundError(f"CSV rolling xG introuvable : {ROLLING_XG_PATH}")

    dataframe = pd.read_csv(ROLLING_XG_PATH)

    missing_columns = [column for column in XG_METADATA_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise RuntimeError(f"Colonnes rolling xG manquantes : {missing_columns}")

    dataframe = dataframe[XG_METADATA_COLUMNS].copy()
    dataframe["clean_match_id"] = pd.to_numeric(dataframe["clean_match_id"], errors="coerce")
    dataframe = dataframe.dropna(subset=["clean_match_id"]).copy()
    dataframe["clean_match_id"] = dataframe["clean_match_id"].astype(int)

    for column in XG_ROLLING_FEATURE_COLUMNS + [
        "home_xg_matches_available_last_5",
        "away_xg_matches_available_last_5",
    ]:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    return dataframe.drop_duplicates(subset=["clean_match_id"]).copy()


# Construit le DataFrame de base V2/V5/V6 et y ajoute les features rolling xG.
def build_v8_feature_dataframe(database_url: str) -> tuple[pd.DataFrame, dict]:
    clean_matches = fetch_clean_matches(database_url)
    v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)
    v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

    market_raw_rows = fetch_market_raw_data(database_url)
    market_dataframe = build_market_prior_dataframe(market_raw_rows)
    market_feature_dataframe = merge_market_prior_features(v5_feature_dataframe, market_dataframe)

    rolling_xg_dataframe = load_rolling_xg_features()
    v8_feature_dataframe = market_feature_dataframe.merge(
        rolling_xg_dataframe,
        on="clean_match_id",
        how="inner",
    )

    metadata = {
        "clean_matches_loaded": len(clean_matches),
        "v2_rows": len(v2_feature_dataframe),
        "v5_rows": len(v5_feature_dataframe),
        "market_rows": len(market_feature_dataframe),
        "rolling_xg_rows": len(rolling_xg_dataframe),
        "v8_merged_rows": len(v8_feature_dataframe),
    }

    return v8_feature_dataframe, metadata


# Vérifie que les colonnes demandées existent avant l'entraînement.
def validate_feature_columns(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> None:
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour V8 : {missing_columns}")


# Prépare un split chronologique strict : train 2014-2021, test 2022-2024.
def prepare_train_test(feature_dataframe: pd.DataFrame, feature_columns: list[str]) -> tuple:
    validate_feature_columns(feature_dataframe, feature_columns)

    required_columns = feature_columns + [TARGET_COLUMN, "season", "clean_match_id"]
    working_dataframe = feature_dataframe.dropna(subset=required_columns).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=required_columns).copy()
    train_dataframe = working_dataframe[working_dataframe["season"].isin(TRAIN_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError(
            "Train ou test vide pour V8. "
            f"Train seasons={TRAIN_SEASONS}, test seasons={TEST_SEASONS}."
        )

    return (
        train_dataframe[feature_columns],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[feature_columns],
        test_dataframe[TARGET_COLUMN],
        working_dataframe,
        train_dataframe,
        test_dataframe,
    )


# Calcule les métriques principales pour comparer une stratégie V8.
def compute_metrics(
    strategy_name: str,
    feature_columns: list[str],
    y_true: pd.Series,
    predictions: list[str] | pd.Series,
    train_rows: int,
    test_rows: int,
    rows_after_cleaning: int,
    base_test_rows: int,
) -> dict:
    prediction_series = pd.Series(predictions).reset_index(drop=True)
    truth_series = y_true.reset_index(drop=True)
    report = classification_report(
        truth_series,
        prediction_series,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )
    prediction_distribution = prediction_series.value_counts().to_dict()
    actual_distribution = truth_series.value_counts().to_dict()

    return {
        "strategy": strategy_name,
        "model": V2_REFERENCE_MODEL_NAME,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": int(rows_after_cleaning),
        "train_rows": int(train_rows),
        "test_rows": int(test_rows),
        "test_coverage_vs_xg_scope": rounded(test_rows / base_test_rows if base_test_rows else 0.0),
        "accuracy": rounded(accuracy_score(truth_series, prediction_series)),
        "f1_macro": rounded(f1_score(truth_series, prediction_series, average="macro")),
        "f1_weighted": rounded(f1_score(truth_series, prediction_series, average="weighted")),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "predicted_home_win_rows": int(prediction_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_distribution.get("AWAY_WIN", 0)),
        "actual_home_win_rows": int(actual_distribution.get("HOME_WIN", 0)),
        "actual_draw_rows": int(actual_distribution.get("DRAW", 0)),
        "actual_away_win_rows": int(actual_distribution.get("AWAY_WIN", 0)),
        "features": ", ".join(feature_columns),
    }


# Entraîne LogisticRegression_balanced et retourne métriques, modèle et lignes de test.
def evaluate_feature_strategy(
    feature_dataframe: pd.DataFrame,
    strategy_name: str,
    feature_columns: list[str],
    base_test_rows: int,
) -> tuple[dict, object, pd.DataFrame, list[str]]:
    x_train, y_train, x_test, y_test, working_dataframe, train_dataframe, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)
    predictions = list(model.predict(x_test))

    metrics = compute_metrics(
        strategy_name=strategy_name,
        feature_columns=feature_columns,
        y_true=y_test,
        predictions=predictions,
        train_rows=len(train_dataframe),
        test_rows=len(test_dataframe),
        rows_after_cleaning=len(working_dataframe),
        base_test_rows=base_test_rows,
    )

    return metrics, model, test_dataframe, predictions


# Construit les familles de features V8 à tester en mémoire.
def build_v8_feature_sets() -> dict[str, list[str]]:
    v5_feature_sets = build_v5_feature_sets()
    v2_reference_columns = v5_feature_sets["v2_reference"]
    v5_reference_columns = v5_feature_sets["v5_draw_context_scores"]
    market_probability_and_gap_columns = MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS

    return {
        "v8_xg_balance_only": dedupe_columns(XG_BALANCE_ONLY_COLUMNS),
        "v8_xg_only_last5": dedupe_columns(XG_ROLLING_FEATURE_COLUMNS),
        "v8_v2_reference_same_xg_scope": dedupe_columns(v2_reference_columns),
        "v8_v5_draw_context_same_xg_scope": dedupe_columns(v5_reference_columns),
        "v8_v2_plus_xg": dedupe_columns(v2_reference_columns + XG_ROLLING_FEATURE_COLUMNS),
        "v8_v5_plus_xg": dedupe_columns(v5_reference_columns + XG_ROLLING_FEATURE_COLUMNS),
        "v8_market_only_probs_same_xg_scope": dedupe_columns(MARKET_PROBABILITY_COLUMNS),
        "v8_market_probs_plus_xg": dedupe_columns(MARKET_PROBABILITY_COLUMNS + XG_ROLLING_FEATURE_COLUMNS),
        "v8_market_probs_gaps_plus_xg": dedupe_columns(
            market_probability_and_gap_columns + XG_ROLLING_FEATURE_COLUMNS
        ),
        "v8_v5_market_probs_plus_xg": dedupe_columns(
            v5_reference_columns + MARKET_PROBABILITY_COLUMNS + XG_ROLLING_FEATURE_COLUMNS
        ),
        "v8_v5_market_probs_gaps_plus_xg": dedupe_columns(
            v5_reference_columns + market_probability_and_gap_columns + XG_ROLLING_FEATURE_COLUMNS
        ),
    }


# Calcule le nombre de lignes de test disponibles sur le périmètre xG complet.
def calculate_base_test_rows(feature_dataframe: pd.DataFrame) -> int:
    xg_ready_dataframe = feature_dataframe.dropna(subset=XG_ROLLING_FEATURE_COLUMNS + [TARGET_COLUMN]).copy()
    return int(len(xg_ready_dataframe[xg_ready_dataframe["season"].isin(TEST_SEASONS)]))


# Lance toutes les stratégies V8 et conserve le meilleur modèle uniquement en mémoire.
def run_v8_experiment(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, dict, object, pd.DataFrame, list[str]]:
    feature_sets = build_v8_feature_sets()
    base_test_rows = calculate_base_test_rows(feature_dataframe)

    if base_test_rows == 0:
        raise RuntimeError("Aucune ligne de test disponible sur le périmètre xG complet.")

    results = []
    best_payload = None

    for strategy_name, feature_columns in feature_sets.items():
        print(f"Evaluation V8 : {strategy_name}", flush=True)
        metrics, model, test_dataframe, predictions = evaluate_feature_strategy(
            feature_dataframe=feature_dataframe,
            strategy_name=strategy_name,
            feature_columns=feature_columns,
            base_test_rows=base_test_rows,
        )
        results.append(metrics)

        if best_payload is None or (
            metrics["f1_macro"], metrics["accuracy"], metrics["draw_recall"]
        ) > (
            best_payload[0]["f1_macro"],
            best_payload[0]["accuracy"],
            best_payload[0]["draw_recall"],
        ):
            best_payload = (metrics, model, test_dataframe, predictions)

    if best_payload is None:
        raise RuntimeError("Aucune stratégie V8 évaluée.")

    results_dataframe = pd.DataFrame(results).sort_values(
        by=["f1_macro", "accuracy", "draw_recall"],
        ascending=False,
    )

    best_metrics, best_model, best_test_dataframe, best_predictions = best_payload
    return results_dataframe, best_metrics, best_model, best_test_dataframe, best_predictions


# Construit le CSV des prédictions du meilleur candidat V8 avec des colonnes metadata robustes.
def build_best_predictions_dataframe(
    best_model,
    best_metrics: dict,
    best_test_dataframe: pd.DataFrame,
    best_predictions: list[str],
) -> pd.DataFrame:
    feature_columns = best_metrics["features"].split(", ") if best_metrics["features"] else []
    preferred_metadata_columns = [
        "clean_match_id",
        "understat_match_id",
        "season",
        "league_code",
        "match_date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "home_score",
        "away_score",
        "full_time_home_goals",
        "full_time_away_goals",
        TARGET_COLUMN,
    ]
    available_metadata_columns = [
        column for column in preferred_metadata_columns if column in best_test_dataframe.columns
    ]
    available_feature_columns = [
        column for column in feature_columns if column in best_test_dataframe.columns
    ]

    if TARGET_COLUMN not in available_metadata_columns:
        raise RuntimeError(f"Colonne cible manquante dans le test dataframe : {TARGET_COLUMN}")

    predictions_dataframe = best_test_dataframe[
        dedupe_columns(available_metadata_columns + available_feature_columns)
    ].copy()

    predictions_dataframe["predicted_result"] = best_predictions
    predictions_dataframe["is_correct"] = predictions_dataframe[TARGET_COLUMN] == predictions_dataframe["predicted_result"]

    if hasattr(best_model, "predict_proba"):
        probabilities = best_model.predict_proba(best_test_dataframe[feature_columns])
        model_classes = list(best_model.classes_)
        for target_class in CLASS_LABELS:
            if target_class in model_classes:
                predictions_dataframe[f"prob_{target_class}"] = probabilities[:, model_classes.index(target_class)]

    predictions_dataframe.insert(0, "strategy", best_metrics["strategy"])

    return predictions_dataframe


# Construit un rapport JSON détaillé pour le meilleur candidat V8.
def build_best_classification_report(
    best_metrics: dict,
    best_test_dataframe: pd.DataFrame,
    best_predictions: list[str],
) -> dict:
    y_true = best_test_dataframe[TARGET_COLUMN].reset_index(drop=True)
    prediction_series = pd.Series(best_predictions).reset_index(drop=True)

    return {
        "strategy": best_metrics["strategy"],
        "train_seasons": TRAIN_SEASONS,
        "test_seasons": TEST_SEASONS,
        "classification_report": classification_report(
            y_true,
            prediction_series,
            labels=CLASS_LABELS,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix_labels": CLASS_LABELS,
        "confusion_matrix": confusion_matrix(
            y_true,
            prediction_series,
            labels=CLASS_LABELS,
        ).tolist(),
    }


# Détermine le statut de l'expérience V8 par rapport au meilleur repère global V6.
def determine_v8_status(best_metrics: dict) -> str:
    improves_accuracy = best_metrics["accuracy"] > V6_GLOBAL_BEST_ACCURACY
    improves_f1 = best_metrics["f1_macro"] > V6_GLOBAL_BEST_F1_MACRO
    improves_draw_precision = best_metrics["draw_precision"] > V6_GLOBAL_BEST_DRAW_PRECISION
    improves_draw_recall = best_metrics["draw_recall"] > V6_GLOBAL_BEST_DRAW_RECALL

    if improves_accuracy and improves_f1:
        return "V8_UNDERSTAT_XG_IN_MEMORY_GLOBAL_GAIN"

    if improves_accuracy or improves_f1 or (improves_draw_precision and improves_draw_recall):
        return "V8_UNDERSTAT_XG_IN_MEMORY_SELECTIVE_GAIN"

    return "V8_UNDERSTAT_XG_IN_MEMORY_NO_GLOBAL_GAIN"


# Rédige la synthèse textuelle de l'expérience V8.
def build_summary(metadata: dict, feature_dataframe: pd.DataFrame, results_dataframe: pd.DataFrame, best_metrics: dict) -> str:
    lines = [
        "RubyBets - ML 1X2 V8 Understat xG in-memory",
        "129 - Synthese experience V8 rolling xG",
        "",
        "Objectif :",
        "Tester en memoire si les features rolling xG Understat ameliorent la prediction globale 1X2.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration produit d'Understat.",
        "- Experience ML interne uniquement, sans sauvegarde de modele.",
        "",
        "Split chronologique :",
        f"- Train : {', '.join(TRAIN_SEASONS)}",
        f"- Test : {', '.join(TEST_SEASONS)}",
        "",
        "Volumes :",
        f"- Clean matches loaded : {metadata['clean_matches_loaded']}",
        f"- Rolling xG rows loaded : {metadata['rolling_xg_rows']}",
        f"- V8 merged rows : {metadata['v8_merged_rows']}",
        f"- Rows with complete xG rolling features : {len(feature_dataframe.dropna(subset=XG_ROLLING_FEATURE_COLUMNS + [TARGET_COLUMN]))}",
        "",
        "Meilleure strategie V8 :",
        f"- Strategy : {best_metrics['strategy']}",
        f"- Model : {best_metrics['model']}",
        f"- Train rows : {best_metrics['train_rows']}",
        f"- Test rows : {best_metrics['test_rows']}",
        f"- Accuracy : {best_metrics['accuracy']}",
        f"- F1 macro : {best_metrics['f1_macro']}",
        f"- DRAW precision : {best_metrics['draw_precision']}",
        f"- DRAW recall : {best_metrics['draw_recall']}",
        "",
        "Reference V6 globale observee :",
        f"- Accuracy : {V6_GLOBAL_BEST_ACCURACY}",
        f"- F1 macro : {V6_GLOBAL_BEST_F1_MACRO}",
        f"- DRAW precision : {V6_GLOBAL_BEST_DRAW_PRECISION}",
        f"- DRAW recall : {V6_GLOBAL_BEST_DRAW_RECALL}",
        "",
        "Top strategies :",
    ]

    for _, row in results_dataframe.head(6).iterrows():
        lines.append(
            f"- {row['strategy']} | acc={row['accuracy']} | f1_macro={row['f1_macro']} | "
            f"draw_precision={row['draw_precision']} | draw_recall={row['draw_recall']} | "
            f"test_rows={row['test_rows']}"
        )

    lines.extend(
        [
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH),
            str(RESULTS_CSV_PATH),
            str(PREDICTIONS_CSV_PATH),
            str(REPORT_JSON_PATH),
            str(DECISION_PATH),
        ]
    )

    return "\n".join(lines)


# Rédige la décision technique après comparaison des stratégies V8.
def build_decision(best_metrics: dict, status: str) -> str:
    lines = [
        "RubyBets - ML 1X2 V8 Understat xG in-memory",
        "133 - Decision experimentale V8",
        "",
        f"Status : {status}",
        "",
        "Decision :",
    ]

    if status == "V8_UNDERSTAT_XG_IN_MEMORY_GLOBAL_GAIN":
        lines.append(
            "Les features rolling xG produisent un gain global par rapport au meilleur repere V6. "
            "La prochaine action est une analyse de stabilite par ligue, saison et classe avant toute insertion en base."
        )
    elif status == "V8_UNDERSTAT_XG_IN_MEMORY_SELECTIVE_GAIN":
        lines.append(
            "Les features rolling xG produisent un gain selectif. "
            "Elles doivent etre analysees par segments avant d'etre considerees comme candidates pour une V8 officielle."
        )
    else:
        lines.append(
            "Les features rolling xG ne produisent pas de gain global suffisant dans cette premiere experience. "
            "Elles restent exploitables mais ne doivent pas etre integrees automatiquement."
        )

    lines.extend(
        [
            "",
            "Meilleure strategie :",
            f"- Strategy : {best_metrics['strategy']}",
            f"- Accuracy : {best_metrics['accuracy']}",
            f"- F1 macro : {best_metrics['f1_macro']}",
            f"- DRAW precision : {best_metrics['draw_precision']}",
            f"- DRAW recall : {best_metrics['draw_recall']}",
            "",
            "Garde-fou :",
            "Ne pas modifier ml.features, ne pas sauvegarder de modele et ne pas brancher Understat a l'API ou au frontend avant validation de stabilite.",
            "",
            "Prochaine action recommandee :",
            "Analyser les performances V8 par ligue, saison, classe et niveau de confiance avant toute decision d'integration.",
            "",
            "Statut de suivi :",
            "- Tache realisee si les fichiers 129, 130, 131, 132 et 133 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour l'experience ML V8 Understat xG en memoire.",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les preuves CSV, JSON et TXT de l'expérience V8.
def save_reports(
    results_dataframe: pd.DataFrame,
    predictions_dataframe: pd.DataFrame,
    report_payload: dict,
    summary: str,
    decision: str,
) -> None:
    ensure_v8_report_dir()
    results_dataframe.to_csv(RESULTS_CSV_PATH, index=False, encoding="utf-8")
    predictions_dataframe.to_csv(PREDICTIONS_CSV_PATH, index=False, encoding="utf-8")
    REPORT_JSON_PATH.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérience V8 Understat xG en mémoire.
def main() -> None:
    try:
        database_url = get_database_url()

        print("Chargement des matchs nettoyes et des features V2/V5/V6...", flush=True)
        feature_dataframe, metadata = build_v8_feature_dataframe(database_url)
        print(f"V8 merged rows: {metadata['v8_merged_rows']}", flush=True)

        print("Evaluation des strategies V8 Understat xG en memoire...", flush=True)
        results_dataframe, best_metrics, best_model, best_test_dataframe, best_predictions = run_v8_experiment(
            feature_dataframe
        )

        predictions_dataframe = build_best_predictions_dataframe(
            best_model=best_model,
            best_metrics=best_metrics,
            best_test_dataframe=best_test_dataframe,
            best_predictions=best_predictions,
        )
        report_payload = build_best_classification_report(
            best_metrics=best_metrics,
            best_test_dataframe=best_test_dataframe,
            best_predictions=best_predictions,
        )
        status = determine_v8_status(best_metrics)
        summary = build_summary(
            metadata=metadata,
            feature_dataframe=feature_dataframe,
            results_dataframe=results_dataframe,
            best_metrics=best_metrics,
        )
        decision = build_decision(best_metrics=best_metrics, status=status)
        save_reports(
            results_dataframe=results_dataframe,
            predictions_dataframe=predictions_dataframe,
            report_payload=report_payload,
            summary=summary,
            decision=decision,
        )

        print("OK - Experience V8 Understat xG en memoire terminee.", flush=True)
        print(f"Status: {status}", flush=True)
        print(f"Best strategy: {best_metrics['strategy']}", flush=True)
        print(f"Train rows: {best_metrics['train_rows']}", flush=True)
        print(f"Test rows: {best_metrics['test_rows']}", flush=True)
        print(f"Accuracy: {best_metrics['accuracy']}", flush=True)
        print(f"F1 macro: {best_metrics['f1_macro']}", flush=True)
        print(f"DRAW precision: {best_metrics['draw_precision']}", flush=True)
        print(f"DRAW recall: {best_metrics['draw_recall']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH}", flush=True)
        print(f"Results CSV saved: {RESULTS_CSV_PATH}", flush=True)
        print(f"Predictions CSV saved: {PREDICTIONS_CSV_PATH}", flush=True)
        print(f"Report JSON saved: {REPORT_JSON_PATH}", flush=True)
        print(f"Decision saved: {DECISION_PATH}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experience V8 Understat xG en memoire.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
#
# backend/scripts/ml/train_1x2_v8_understat_xg_in_memory.py
#   -> lit backend/.env via get_database_url()
#   -> lit PostgreSQL en lecture seule : ml.clean_matches + ml.raw_matches.raw_data
#   -> lit reports/evidence/ml_training/125_1x2_understat_rolling_xg_dry_run_features.csv
#   -> reutilise les builders V2/V5/V6 en memoire
#   -> ecrit uniquement des preuves dans reports/evidence/ml_training/129 a 133
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
