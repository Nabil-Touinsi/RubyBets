# Rôle du fichier : lancer l'expérimentation ML 1X2 V6 Market prior avec les cotes B365 pré-match, sans modifier la base, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from pathlib import Path
import json
import sys
import warnings

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from sklearn.metrics import accuracy_score, classification_report, f1_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "76_1x2_v6_market_prior_summary.txt"
CSV_PATH = REPORT_DIR / "77_1x2_v6_market_prior_results.csv"
DECISION_PATH = REPORT_DIR / "78_1x2_v6_market_prior_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v5_balance_features import (  # noqa: E402
    CLASS_LABELS,
    V2_REFERENCE_ACCURACY,
    V2_REFERENCE_DRAW_PRECISION,
    V2_REFERENCE_DRAW_RECALL,
    V2_REFERENCE_F1_MACRO,
    V2_REFERENCE_MODEL_NAME,
    add_v5_balance_features,
    build_reference_model,
    build_v5_feature_sets,
    build_v2_fast_feature_dataframe,
    prepare_train_test,
)

warnings.filterwarnings("ignore", category=UserWarning)

ODDS_COLUMNS = ["B365H", "B365D", "B365A"]
MARKET_PROBABILITY_COLUMNS = [
    "market_home_prob",
    "market_draw_prob",
    "market_away_prob",
]
MARKET_GAP_COLUMNS = [
    "market_favorite_prob",
    "market_second_prob",
    "market_confidence_gap",
    "market_home_away_gap",
    "market_abs_home_away_gap",
    "market_draw_gap",
]
MARKET_NUMERIC_COLUMNS = MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS
V2_REFERENCE_FEATURE_SET_NAME = "v2_reference"
V5_REFERENCE_FEATURE_SET_NAME = "v5_draw_context_scores"
MARKET_DIRECT_STRATEGY_NAME = "v6_market_favorite_direct"
AGREEMENT_STRATEGY_NAME = "v6_agreement_v5_market_favorite"

MIN_MARKET_COVERAGE_RATE = 0.70
INTERESTING_ACCURACY = 0.5200
INTERESTING_F1_MACRO = 0.4900
INTERESTING_DRAW_RECALL = 0.3000
INTERESTING_DRAW_PRECISION = 0.3300
SERIOUS_ACCURACY = 0.5400
SERIOUS_F1_MACRO = 0.5100
SERIOUS_DRAW_RECALL = 0.3300


# Convertit une valeur brute de cote en float exploitable.
def parse_odd_value(value) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        numeric_value = float(value)
    else:
        cleaned_value = str(value).strip().replace(",", ".")

        if not cleaned_value:
            return None

        try:
            numeric_value = float(cleaned_value)
        except ValueError:
            return None

    if numeric_value <= 1.0:
        return None

    return numeric_value


# Lit une valeur dans raw_data, que PostgreSQL retourne un dict JSONB ou une chaîne JSON.
def get_raw_data_value(raw_data, column: str):
    if raw_data is None:
        return None

    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            return None

    if not isinstance(raw_data, dict):
        return None

    return raw_data.get(column)


# Arrondit une valeur numérique pour stabiliser les exports texte et CSV.
def rounded(value: float | int | None, digits: int = 4) -> float:
    if value is None:
        return 0.0

    return round(float(value), digits)


# Evite les doublons de colonnes quand on combine plusieurs familles de features.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


# Transforme trois cotes 1X2 en probabilités implicites normalisées sans marge brute.
def normalize_market_probabilities(home_odd: float, draw_odd: float, away_odd: float) -> tuple[float, float, float]:
    home_implied = 1 / home_odd
    draw_implied = 1 / draw_odd
    away_implied = 1 / away_odd
    total_implied = home_implied + draw_implied + away_implied

    return (
        round(home_implied / total_implied, 6),
        round(draw_implied / total_implied, 6),
        round(away_implied / total_implied, 6),
    )


# Déduit la classe favorite du marché à partir des probabilités normalisées.
def get_market_favorite_class(home_prob: float, draw_prob: float, away_prob: float) -> str:
    probabilities = {
        "HOME_WIN": home_prob,
        "DRAW": draw_prob,
        "AWAY_WIN": away_prob,
    }

    return max(probabilities, key=probabilities.get)


# Construit les features Market prior pour un match à partir de ses cotes B365.
def build_market_prior_row(clean_match_id: int, raw_data) -> dict:
    home_odd = parse_odd_value(get_raw_data_value(raw_data, "B365H"))
    draw_odd = parse_odd_value(get_raw_data_value(raw_data, "B365D"))
    away_odd = parse_odd_value(get_raw_data_value(raw_data, "B365A"))

    row = {
        "clean_match_id": clean_match_id,
        "b365_home_odd": home_odd,
        "b365_draw_odd": draw_odd,
        "b365_away_odd": away_odd,
    }

    if home_odd is None or draw_odd is None or away_odd is None:
        for column in MARKET_NUMERIC_COLUMNS:
            row[column] = None
        row["market_favorite_class"] = None
        return row

    home_prob, draw_prob, away_prob = normalize_market_probabilities(
        home_odd=home_odd,
        draw_odd=draw_odd,
        away_odd=away_odd,
    )
    ordered_probabilities = sorted([home_prob, draw_prob, away_prob], reverse=True)
    favorite_prob = ordered_probabilities[0]
    second_prob = ordered_probabilities[1]
    favorite_class = get_market_favorite_class(
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
    )

    row.update(
        {
            "market_home_prob": home_prob,
            "market_draw_prob": draw_prob,
            "market_away_prob": away_prob,
            "market_favorite_class": favorite_class,
            "market_favorite_prob": round(favorite_prob, 6),
            "market_second_prob": round(second_prob, 6),
            "market_confidence_gap": round(favorite_prob - second_prob, 6),
            "market_home_away_gap": round(home_prob - away_prob, 6),
            "market_abs_home_away_gap": round(abs(home_prob - away_prob), 6),
            "market_draw_gap": round(favorite_prob - draw_prob, 6),
        }
    )

    return row


# Charge les raw_data reliées aux matchs nettoyés pour récupérer les cotes historiques.
def fetch_market_raw_data(database_url: str) -> list[dict]:
    query = """
        SELECT
            clean.id AS clean_match_id,
            raw.raw_data
        FROM ml.clean_matches AS clean
        INNER JOIN ml.raw_matches AS raw
            ON raw.id = clean.raw_match_id
        WHERE clean.is_valid = TRUE
        ORDER BY clean.match_date ASC, clean.id ASC;
    """

    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())


# Construit le DataFrame des probabilités implicites à partir des cotes B365.
def build_market_prior_dataframe(market_raw_rows: list[dict]) -> pd.DataFrame:
    rows = [
        build_market_prior_row(
            clean_match_id=row["clean_match_id"],
            raw_data=row["raw_data"],
        )
        for row in market_raw_rows
    ]

    return pd.DataFrame(rows)


# Ajoute les features Market prior aux features V5 déjà construites en mémoire.
def merge_market_prior_features(feature_dataframe: pd.DataFrame, market_dataframe: pd.DataFrame) -> pd.DataFrame:
    merged_dataframe = feature_dataframe.merge(
        market_dataframe,
        on="clean_match_id",
        how="left",
    )

    for column in MARKET_NUMERIC_COLUMNS + ["b365_home_odd", "b365_draw_odd", "b365_away_odd"]:
        merged_dataframe[column] = pd.to_numeric(merged_dataframe[column], errors="coerce")

    return merged_dataframe


# Filtre le périmètre d'étude pour comparer V2, V5 et V6 sur les mêmes lignes avec cotes disponibles.
def filter_market_ready_scope(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    return feature_dataframe.dropna(subset=MARKET_PROBABILITY_COLUMNS + [TARGET_COLUMN]).copy()


# Construit les familles de features à comparer dans l'expérience V6.
def build_v6_feature_sets() -> dict[str, list[str]]:
    v5_feature_sets = build_v5_feature_sets()
    v2_reference_columns = v5_feature_sets[V2_REFERENCE_FEATURE_SET_NAME]
    v5_reference_columns = v5_feature_sets[V5_REFERENCE_FEATURE_SET_NAME]

    return {
        V2_REFERENCE_FEATURE_SET_NAME: dedupe_columns(v2_reference_columns),
        V5_REFERENCE_FEATURE_SET_NAME: dedupe_columns(v5_reference_columns),
        "v6_market_only_probs": dedupe_columns(MARKET_PROBABILITY_COLUMNS),
        "v6_market_only_probs_and_gaps": dedupe_columns(MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS),
        "v6_v5_plus_market_probs": dedupe_columns(v5_reference_columns + MARKET_PROBABILITY_COLUMNS),
        "v6_v5_plus_market_probs_and_gaps": dedupe_columns(
            v5_reference_columns + MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS
        ),
    }


# Calcule les métriques principales pour une stratégie 1X2.
def compute_metrics(
    strategy_name: str,
    model_name: str,
    feature_columns: list[str],
    y_true: pd.Series,
    predictions: list[str] | pd.Series,
    train_rows: int,
    test_rows: int,
    rows_after_cleaning: int,
    base_test_rows: int,
    coverage_scope: str,
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
        "model": model_name,
        "coverage_scope": coverage_scope,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": rows_after_cleaning,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "coverage": rounded(test_rows / base_test_rows if base_test_rows else 0.0),
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
        "features": ", ".join(feature_columns) if feature_columns else "market_favorite_class",
    }


# Entraîne LogisticRegression_balanced sur une famille de features et retourne ses métriques.
def evaluate_feature_strategy(
    feature_dataframe: pd.DataFrame,
    strategy_name: str,
    feature_columns: list[str],
    base_test_rows: int,
) -> dict:
    x_train, y_train, x_test, y_test, working_dataframe, train_dataframe, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)
    predictions = list(model.predict(x_test))

    return compute_metrics(
        strategy_name=strategy_name,
        model_name=V2_REFERENCE_MODEL_NAME,
        feature_columns=feature_columns,
        y_true=y_test,
        predictions=predictions,
        train_rows=len(train_dataframe),
        test_rows=len(test_dataframe),
        rows_after_cleaning=len(working_dataframe),
        base_test_rows=base_test_rows,
        coverage_scope="full_market_ready_test_scope",
    )


# Evalue directement la classe favorite du marché, sans entraînement ML.
def evaluate_market_favorite_direct(feature_dataframe: pd.DataFrame, base_test_rows: int) -> dict:
    working_dataframe = feature_dataframe.dropna(
        subset=["market_favorite_class", TARGET_COLUMN] + MARKET_PROBABILITY_COLUMNS
    ).copy()
    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if test_dataframe.empty:
        raise RuntimeError("Test vide pour la stratégie market_favorite_direct.")

    return compute_metrics(
        strategy_name=MARKET_DIRECT_STRATEGY_NAME,
        model_name="NoTraining_market_favorite",
        feature_columns=[],
        y_true=test_dataframe[TARGET_COLUMN],
        predictions=test_dataframe["market_favorite_class"],
        train_rows=len(train_dataframe),
        test_rows=len(test_dataframe),
        rows_after_cleaning=len(working_dataframe),
        base_test_rows=base_test_rows,
        coverage_scope="full_market_ready_test_scope",
    )


# Produit les prédictions d'un modèle entraîné pour permettre les stratégies d'accord.
def train_and_predict_strategy(
    feature_dataframe: pd.DataFrame,
    strategy_name: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    x_train, y_train, x_test, y_test, _, _, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)
    predictions = pd.Series(model.predict(x_test), index=x_test.index, name=f"{strategy_name}_prediction")

    prediction_dataframe = test_dataframe[
        [
            "clean_match_id",
            "match_date",
            "league_code",
            "season",
            "home_team",
            "away_team",
            TARGET_COLUMN,
            "market_favorite_class",
            "market_favorite_prob",
            "market_confidence_gap",
            "market_draw_prob",
        ]
    ].copy()
    prediction_dataframe = prediction_dataframe.join(predictions)

    return prediction_dataframe.reset_index(drop=True)


# Evalue les matchs où le modèle V5 et le favori marché donnent la même classe.
def evaluate_v5_market_agreement(
    feature_dataframe: pd.DataFrame,
    v5_feature_columns: list[str],
    base_test_rows: int,
) -> dict:
    prediction_dataframe = train_and_predict_strategy(
        feature_dataframe=feature_dataframe,
        strategy_name=V5_REFERENCE_FEATURE_SET_NAME,
        feature_columns=v5_feature_columns,
    )
    agreement_dataframe = prediction_dataframe[
        prediction_dataframe[f"{V5_REFERENCE_FEATURE_SET_NAME}_prediction"]
        == prediction_dataframe["market_favorite_class"]
    ].copy()

    if agreement_dataframe.empty:
        return {
            "strategy": AGREEMENT_STRATEGY_NAME,
            "model": "Agreement_V5_and_market_favorite",
            "coverage_scope": "agreement_only",
            "feature_count": len(v5_feature_columns),
            "rows_after_cleaning": len(prediction_dataframe),
            "train_rows": 0,
            "test_rows": 0,
            "coverage": 0.0,
            "accuracy": 0.0,
            "f1_macro": 0.0,
            "f1_weighted": 0.0,
            "home_win_precision": 0.0,
            "home_win_recall": 0.0,
            "draw_precision": 0.0,
            "draw_recall": 0.0,
            "away_win_precision": 0.0,
            "away_win_recall": 0.0,
            "predicted_home_win_rows": 0,
            "predicted_draw_rows": 0,
            "predicted_away_win_rows": 0,
            "actual_home_win_rows": 0,
            "actual_draw_rows": 0,
            "actual_away_win_rows": 0,
            "features": ", ".join(v5_feature_columns) + " + market_favorite_class agreement",
        }

    return compute_metrics(
        strategy_name=AGREEMENT_STRATEGY_NAME,
        model_name="Agreement_V5_and_market_favorite",
        feature_columns=v5_feature_columns + ["market_favorite_class"],
        y_true=agreement_dataframe[TARGET_COLUMN],
        predictions=agreement_dataframe["market_favorite_class"],
        train_rows=0,
        test_rows=len(agreement_dataframe),
        rows_after_cleaning=len(prediction_dataframe),
        base_test_rows=base_test_rows,
        coverage_scope="agreement_only",
    )


# Compare les stratégies V2, V5, V6 Market prior et accord V5/marché.
def run_v6_market_prior_comparison(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    feature_sets = build_v6_feature_sets()
    base_test_rows = int(feature_dataframe[feature_dataframe["season"].isin(TEST_SEASONS)].shape[0])

    print("Evaluation V6 : market_favorite_direct", flush=True)
    results.append(evaluate_market_favorite_direct(feature_dataframe, base_test_rows))

    for strategy_name, feature_columns in feature_sets.items():
        print(f"Evaluation V6 : {strategy_name}", flush=True)
        results.append(
            evaluate_feature_strategy(
                feature_dataframe=feature_dataframe,
                strategy_name=strategy_name,
                feature_columns=feature_columns,
                base_test_rows=base_test_rows,
            )
        )

    print("Evaluation V6 : agreement V5 + marche", flush=True)
    results.append(
        evaluate_v5_market_agreement(
            feature_dataframe=feature_dataframe,
            v5_feature_columns=feature_sets[V5_REFERENCE_FEATURE_SET_NAME],
            base_test_rows=base_test_rows,
        )
    )

    results_dataframe = pd.DataFrame(results)

    return results_dataframe.sort_values(
        by=["coverage_scope", "f1_macro", "accuracy"],
        ascending=[False, False, False],
    )


# Sélectionne le meilleur candidat V6 à couverture complète pour la décision principale.
def select_best_full_scope_candidate(results_dataframe: pd.DataFrame) -> pd.Series:
    eligible_dataframe = results_dataframe[
        (results_dataframe["coverage_scope"] == "full_market_ready_test_scope")
        & (results_dataframe["strategy"].str.startswith("v6_"))
    ].copy()

    if eligible_dataframe.empty:
        raise RuntimeError("Aucun candidat V6 a couverture complete trouve dans les resultats.")

    return eligible_dataframe.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    ).iloc[0]


# Récupère une ligne de résultats par nom de stratégie.
def get_strategy_row(results_dataframe: pd.DataFrame, strategy_name: str) -> pd.Series | None:
    strategy_rows = results_dataframe[results_dataframe["strategy"] == strategy_name]

    if strategy_rows.empty:
        return None

    return strategy_rows.iloc[0]


# Détermine le statut final V6 selon les critères définis avant l'expérience.
def determine_v6_status(best_v6_row: pd.Series, market_coverage_rate: float) -> str:
    if market_coverage_rate < MIN_MARKET_COVERAGE_RATE:
        return "V6_STOPPED_INSUFFICIENT_MARKET_COVERAGE"

    if (
        best_v6_row["accuracy"] >= SERIOUS_ACCURACY
        and best_v6_row["f1_macro"] >= SERIOUS_F1_MACRO
        and best_v6_row["draw_recall"] >= SERIOUS_DRAW_RECALL
    ):
        return "V6_SERIOUS_EXPERIMENTAL_SIGNAL"

    if (
        best_v6_row["accuracy"] > INTERESTING_ACCURACY
        and best_v6_row["f1_macro"] > INTERESTING_F1_MACRO
        and best_v6_row["draw_recall"] > INTERESTING_DRAW_RECALL
        and best_v6_row["draw_precision"] >= INTERESTING_DRAW_PRECISION
    ):
        return "V6_INTERESTING_EXPERIMENTAL_SIGNAL"

    return "V6_NOT_RETAINED_AS_GLOBAL_CANDIDATE"


# Construit la synthèse texte de l'expérience V6 Market prior.
def build_summary(
    clean_matches: list[dict],
    feature_dataframe: pd.DataFrame,
    market_ready_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
) -> str:
    market_coverage_rate = rounded(len(market_ready_dataframe) / len(feature_dataframe) if len(feature_dataframe) else 0.0)
    best_v6_row = select_best_full_scope_candidate(results_dataframe)
    v2_row = get_strategy_row(results_dataframe, V2_REFERENCE_FEATURE_SET_NAME)
    v5_row = get_strategy_row(results_dataframe, V5_REFERENCE_FEATURE_SET_NAME)
    direct_market_row = get_strategy_row(results_dataframe, MARKET_DIRECT_STRATEGY_NAME)
    agreement_row = get_strategy_row(results_dataframe, AGREEMENT_STRATEGY_NAME)
    v6_status = determine_v6_status(best_v6_row, market_coverage_rate)

    lines = [
        "RubyBets - ML 1X2 V6 Market prior baseline",
        "76 - Synthese de l'experimentation Market prior",
        "",
        "Objectif :",
        "Tester si les cotes B365 pre-match transformees en probabilites implicites normalisees apportent un saut mesurable par rapport aux candidats V2/V5.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Les cotes restent un benchmark ML experimental interne, non affiche dans RubyBets.",
        "",
        "Point de depart avant V6 :",
        f"- V2 reference accuracy : {V2_REFERENCE_ACCURACY:.4f}",
        f"- V2 reference F1 macro : {V2_REFERENCE_F1_MACRO:.4f}",
        f"- V2 reference DRAW precision : {V2_REFERENCE_DRAW_PRECISION:.4f}",
        f"- V2 reference DRAW recall : {V2_REFERENCE_DRAW_RECALL:.4f}",
        "- V5 reste experimental uniquement car son gain observe etait trop faible.",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features V5 construites : {len(feature_dataframe)}",
        f"- Lignes avec B365H/B365D/B365A exploitables : {len(market_ready_dataframe)}",
        f"- Couverture B365 sur les features construites : {market_coverage_rate:.4f}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Meilleur candidat V6 a couverture complete :",
        f"- Strategy : {best_v6_row['strategy']}",
        f"- Model : {best_v6_row['model']}",
        f"- Accuracy : {best_v6_row['accuracy']}",
        f"- F1 macro : {best_v6_row['f1_macro']}",
        f"- F1 weighted : {best_v6_row['f1_weighted']}",
        f"- DRAW precision : {best_v6_row['draw_precision']}",
        f"- DRAW recall : {best_v6_row['draw_recall']}",
        f"- Predicted DRAW rows : {best_v6_row['predicted_draw_rows']}",
        "",
        "Comparaison rapide :",
    ]

    for label, row in [
        ("V2 reference recalculee", v2_row),
        ("V5 reference recalculee", v5_row),
        ("Market favorite direct", direct_market_row),
        ("V6 best full scope", best_v6_row),
        ("Agreement V5 + market", agreement_row),
    ]:
        if row is None:
            continue

        lines.append(
            f"- {label} : strategy={row['strategy']}, coverage={row['coverage']}, accuracy={row['accuracy']}, f1_macro={row['f1_macro']}, draw_precision={row['draw_precision']}, draw_recall={row['draw_recall']}"
        )

    lines.extend(
        [
            "",
            "Decision experimentale :",
            f"- Status : {v6_status}",
            "- La V6 ne remplace pas le scoring explicable V1.",
            "- La V6 ne modifie pas le modele officiel sauvegarde.",
            "- Les resultats doivent etre interpretes comme benchmark interne sur donnees historiques.",
            "",
            "Criteres V6 :",
            f"- V6 interessante : accuracy > {INTERESTING_ACCURACY:.4f}, f1_macro > {INTERESTING_F1_MACRO:.4f}, draw_recall > {INTERESTING_DRAW_RECALL:.4f}, draw_precision >= {INTERESTING_DRAW_PRECISION:.4f}",
            f"- V6 serieuse : accuracy >= {SERIOUS_ACCURACY:.4f}, f1_macro >= {SERIOUS_F1_MACRO:.4f}, draw_recall >= {SERIOUS_DRAW_RECALL:.4f}",
            "",
            "Tableau des strategies testees :",
            results_dataframe[
                [
                    "strategy",
                    "model",
                    "coverage_scope",
                    "coverage",
                    "train_rows",
                    "test_rows",
                    "accuracy",
                    "f1_macro",
                    "f1_weighted",
                    "draw_precision",
                    "draw_recall",
                    "predicted_draw_rows",
                ]
            ].to_string(index=False),
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V6 Market prior si les fichiers 76, 77 et 78 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour les fichiers reports/evidence/ml_training/76, 77 et 78.",
            "",
        ]
    )

    return "\n".join(lines)


# Construit le fichier de décision final V6.
def build_decision(
    feature_dataframe: pd.DataFrame,
    market_ready_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
) -> str:
    market_coverage_rate = rounded(len(market_ready_dataframe) / len(feature_dataframe) if len(feature_dataframe) else 0.0)
    best_v6_row = select_best_full_scope_candidate(results_dataframe)
    v2_row = get_strategy_row(results_dataframe, V2_REFERENCE_FEATURE_SET_NAME)
    v5_row = get_strategy_row(results_dataframe, V5_REFERENCE_FEATURE_SET_NAME)
    agreement_row = get_strategy_row(results_dataframe, AGREEMENT_STRATEGY_NAME)
    v6_status = determine_v6_status(best_v6_row, market_coverage_rate)

    v2_accuracy_delta = None if v2_row is None else rounded(best_v6_row["accuracy"] - v2_row["accuracy"])
    v5_accuracy_delta = None if v5_row is None else rounded(best_v6_row["accuracy"] - v5_row["accuracy"])
    v2_f1_delta = None if v2_row is None else rounded(best_v6_row["f1_macro"] - v2_row["f1_macro"])
    v5_f1_delta = None if v5_row is None else rounded(best_v6_row["f1_macro"] - v5_row["f1_macro"])

    lines = [
        "RubyBets - ML 1X2 V6 Market prior decision",
        "78 - Decision finale de l'experimentation V6",
        "",
        f"Status : {v6_status}",
        "",
        "Meilleur candidat V6 a couverture complete :",
        f"- Strategy : {best_v6_row['strategy']}",
        f"- Model : {best_v6_row['model']}",
        f"- Accuracy : {best_v6_row['accuracy']}",
        f"- F1 macro : {best_v6_row['f1_macro']}",
        f"- DRAW precision : {best_v6_row['draw_precision']}",
        f"- DRAW recall : {best_v6_row['draw_recall']}",
        "",
        "Delta avec les references recalculees sur le meme perimetre market-ready :",
        f"- Accuracy delta vs V2 : {v2_accuracy_delta}",
        f"- F1 macro delta vs V2 : {v2_f1_delta}",
        f"- Accuracy delta vs V5 : {v5_accuracy_delta}",
        f"- F1 macro delta vs V5 : {v5_f1_delta}",
        "",
    ]

    if agreement_row is not None:
        lines.extend(
            [
                "Strategie d'accord V5 + marche :",
                f"- Coverage : {agreement_row['coverage']}",
                f"- Accuracy : {agreement_row['accuracy']}",
                f"- F1 macro : {agreement_row['f1_macro']}",
                f"- DRAW precision : {agreement_row['draw_precision']}",
                f"- DRAW recall : {agreement_row['draw_recall']}",
                "",
            ]
        )

    if v6_status == "V6_SERIOUS_EXPERIMENTAL_SIGNAL":
        lines.extend(
            [
                "Decision :",
                "La V6 montre un signal experimental fort. Elle merite une analyse de stabilite dediee avant toute sauvegarde candidate.",
                "Prochaine etape recommandee : analyser la stabilite par ligue, saison, classe et segments d'erreurs.",
            ]
        )
    elif v6_status == "V6_INTERESTING_EXPERIMENTAL_SIGNAL":
        lines.extend(
            [
                "Decision :",
                "La V6 montre un signal experimental interessant mais pas encore suffisant pour integration.",
                "Prochaine etape recommandee : analyser les segments ou le Market prior corrige vraiment V2/V5.",
            ]
        )
    else:
        lines.extend(
            [
                "Decision :",
                "La V6 ne doit pas etre retenue comme candidat global a ce stade.",
                "Prochaine etape recommandee : conserver les resultats comme benchmark et ne pas modifier le modele sauvegarde.",
            ]
        )

    lines.extend(
        [
            "",
            "Garde-fous maintenus :",
            "- Aucun changement API/frontend/base/scoring V1.",
            "- Aucun remplacement du modele officiel sauvegarde.",
            "- Aucune exposition des cotes dans RubyBets.",
            "- Usage des cotes limite a un benchmark ML interne.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les preuves texte et CSV de l'expérience V6.
def save_reports(results_dataframe: pd.DataFrame, summary: str, decision: str) -> None:
    ensure_report_dir()
    results_dataframe.to_csv(CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérimentation V6 Market prior.
def main() -> None:
    try:
        database_url = get_database_url()

        print("Chargement des matchs nettoyes depuis ml.clean_matches...", flush=True)
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features V2 de reference en memoire...", flush=True)
        v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

        print("Ajout des features V5 d'equilibre de match...", flush=True)
        v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

        print("Chargement des cotes B365 depuis ml.raw_matches.raw_data...", flush=True)
        market_raw_rows = fetch_market_raw_data(database_url)
        market_dataframe = build_market_prior_dataframe(market_raw_rows)

        print("Transformation des cotes en probabilites implicites normalisees...", flush=True)
        v6_feature_dataframe = merge_market_prior_features(v5_feature_dataframe, market_dataframe)
        market_ready_dataframe = filter_market_ready_scope(v6_feature_dataframe)

        market_coverage_rate = rounded(
            len(market_ready_dataframe) / len(v6_feature_dataframe) if len(v6_feature_dataframe) else 0.0
        )

        if market_coverage_rate < MIN_MARKET_COVERAGE_RATE:
            raise RuntimeError(
                "Couverture B365 insuffisante pour lancer V6 : "
                f"{market_coverage_rate:.4f} < {MIN_MARKET_COVERAGE_RATE:.4f}"
            )

        print(f"Lignes avec cotes B365 exploitables : {len(market_ready_dataframe)}", flush=True)
        print(f"Couverture B365 exploitable : {market_coverage_rate:.4f}", flush=True)
        print("Evaluation des strategies V6 Market prior...", flush=True)

        results_dataframe = run_v6_market_prior_comparison(market_ready_dataframe)
        summary = build_summary(
            clean_matches=clean_matches,
            feature_dataframe=v6_feature_dataframe,
            market_ready_dataframe=market_ready_dataframe,
            results_dataframe=results_dataframe,
        )
        decision = build_decision(
            feature_dataframe=v6_feature_dataframe,
            market_ready_dataframe=market_ready_dataframe,
            results_dataframe=results_dataframe,
        )
        save_reports(results_dataframe, summary, decision)

        best_v6_row = select_best_full_scope_candidate(results_dataframe)
        v6_status = determine_v6_status(best_v6_row, market_coverage_rate)

        print("OK - Experimentation V6 Market prior terminee.", flush=True)
        print(f"Status: {v6_status}", flush=True)
        print(f"Best V6 strategy: {best_v6_row['strategy']}", flush=True)
        print(f"Accuracy: {best_v6_row['accuracy']}", flush=True)
        print(f"F1 macro: {best_v6_row['f1_macro']}", flush=True)
        print(f"DRAW precision: {best_v6_row['draw_precision']}", flush=True)
        print(f"DRAW recall: {best_v6_row['draw_recall']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experimentation V6 Market prior.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication :
# experiment_1x2_v6_market_prior.py
#   -> lit backend/.env pour recuperer DATABASE_URL
#   -> lit PostgreSQL : ml.clean_matches
#   -> lit PostgreSQL : ml.raw_matches.raw_data via raw_match_id pour recuperer B365H/B365D/B365A
#   -> construit V2 + V5 en memoire sans modifier ml.features
#   -> transforme les cotes B365 en probabilites implicites normalisees
#   -> compare V2, V5, market only, V5 + market prior et agreement V5/marche
#   -> genere reports/evidence/ml_training/76_1x2_v6_market_prior_summary.txt
#   -> genere reports/evidence/ml_training/77_1x2_v6_market_prior_results.csv
#   -> genere reports/evidence/ml_training/78_1x2_v6_market_prior_decision.txt
#   -> ne modifie pas PostgreSQL, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
