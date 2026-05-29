# Rôle du fichier : construire le sélecteur multi-marchés V17.5 enrichi en combinant V13.1 avec le signal OVER_1_5 V17.2, sans intégration produit.

from __future__ import annotations

import importlib.util
import math
import sys
import warnings
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd


RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"
STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"
GOALS_OVER_15_TYPE = "GOALS_OVER_1_5"
OVER_15_VALUE = "OVER_1_5"
UNDER_15_VALUE = "UNDER_1_5"

OUTPUT_SUMMARY = "256_multimarket_v17_5_selector_enriched_summary.txt"
OUTPUT_RESULTS = "257_multimarket_v17_5_selector_results.csv"
OUTPUT_BY_MARKET = "258_multimarket_v17_5_selector_by_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "259_multimarket_v17_5_selector_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "260_multimarket_v17_5_selector_error_patterns.csv"
OUTPUT_DECISION = "261_multimarket_v17_5_selector_decision.txt"
OUTPUT_V17_0_REFERENCE_RESULTS = "228_multimarket_v17_selector_results.csv"

V13_STRATEGY_NAME = "v13_mixed_sp080_sm010_top2076_ent107_trip1_agr000"
V17_2_EXPECTED_STRATEGY_NAME = "v17_2_logistic_enriched_over_t0745_under_none"
V17_5_STRATEGY_NAME = "v17_5_controlled_v13_mixed_plus_v17_2_over15_only"
V17_5_WARNING_UNDER_STRATEGY_NAME = "v17_5_warning_add_v17_2_under15"

V17_0_REFERENCE_ACCURACY = 0.8382
V17_0_REFERENCE_COVERAGE = 0.7651
V17_0_REFERENCE_SELECTED_ROWS = 4078
V17_0_REFERENCE_OVER_15_ROWS = 1193
V17_0_REFERENCE_OVER_15_ACCURACY = 0.7921
V13_REFERENCE_SELECTED_ROWS = 2885
V13_REFERENCE_COVERAGE = 0.5413
V13_REFERENCE_ACCURACY = 0.8572

STRONG_MIN_ACCURACY = 0.83
STRONG_MIN_COVERAGE = 0.78
STRONG_MIN_SELECTED_ROWS = 4079
STRONG_MIN_MAJOR_SEGMENT_ACCURACY = 0.75
REVIEW_MIN_ACCURACY = 0.82
REVIEW_MIN_COVERAGE = 0.76
REVIEW_MIN_SELECTED_ROWS = 4000
LOW_VOLUME_SEGMENT_ROWS = 80

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


# Charge un script ML voisin comme module réutilisable, sans modifier son contenu.
def load_module(module_name: str, filename: str) -> ModuleType:
    script_path = Path(__file__).resolve().parent / filename
    if not script_path.exists():
        raise FileNotFoundError(f"Script requis introuvable : {script_path}")

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module : {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Arrondit une valeur numérique pour stabiliser les exports et les logs.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio en évitant les divisions par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Construit une clé stable pour relier les sorties V13.1 et V17.2 sur les mêmes matchs.
def build_join_key(dataframe: pd.DataFrame, columns: list[str]) -> pd.Series:
    output = dataframe[columns].astype(str).fillna("")
    return output.apply(lambda row: "|".join(row.values.tolist()), axis=1)


# Charge les sorties détaillées V17.0 déjà produites pour récupérer rapidement le socle V13.1, si elles existent.
def load_v17_0_reference_predictions(evidence_dir: Path) -> pd.DataFrame | None:
    reference_path = evidence_dir / OUTPUT_V17_0_REFERENCE_RESULTS
    if not reference_path.exists():
        return None

    reference = pd.read_csv(reference_path)
    required_columns = {
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "v13_mixed_recommendation_type",
        "v13_mixed_recommendation_value",
        "v13_mixed_is_correct",
    }
    missing_columns = required_columns - set(reference.columns)
    if missing_columns:
        return None

    reference = reference.copy()
    reference["v13_mixed_recommendation_status"] = np.where(
        reference["v13_mixed_recommendation_type"].astype(str) != "ABSTAIN",
        RECOMMEND_STATUS,
        ABSTAIN_STATUS,
    )
    reference["join_key"] = build_join_key(reference, ["__league_code", "__season", "Date", "HomeTeam", "AwayTeam"])
    return reference


# Reconstruit les prédictions V13.1 retenues à partir des CSV bruts et du script V13.1.
def build_v13_predictions(project_root: Path, v13_module: ModuleType) -> pd.DataFrame:
    base_module = v13_module.load_v13_base_module()
    dataset, _, _ = base_module.build_v13_dataset(project_root)
    _, _, test, _ = base_module.prepare_temporal_splits(dataset)

    policy = v13_module.MixedPolicy(
        strict_probability_threshold=0.80,
        strict_margin_threshold=0.10,
        double_chance_top2_threshold=0.76,
        max_entropy_threshold=1.07,
        min_available_triplets=1,
        min_agreement_threshold=0.00,
    )
    predictions = v13_module.build_best_predictions(test, policy).copy()
    predictions["join_key"] = build_join_key(predictions, ["__league_code", "__season", "Date", "HomeTeam", "AwayTeam"])
    return predictions


# Reconstruit les prédictions V17.2 enrichies à partir des features goals/BTTS en mémoire.
def build_v17_2_predictions(project_root: Path, v17_2_module: ModuleType) -> tuple[pd.DataFrame, str]:
    dataset, _ = v17_2_module.build_v17_2_dataset(project_root)
    train, validation, test = v17_2_module.split_dataset(dataset)
    _, validation_scored, test_scored = v17_2_module.attach_scores(train, validation, test)
    strategies = v17_2_module.build_strategies()

    validation_results = pd.DataFrame(
        [v17_2_module.evaluate_strategy(validation_scored, strategy, "validation") for strategy in strategies]
    )
    best_strategy = v17_2_module.select_best_strategy(validation_results, strategies)
    predictions = v17_2_module.apply_strategy(test_scored, best_strategy).copy()
    predictions["join_key"] = build_join_key(predictions, ["league_code", "season", "match_date", "home_team", "away_team"])
    return predictions, best_strategy.name


# Fusionne les prédictions V13.1 et V17.2 sur le périmètre de test final.
def merge_candidate_predictions(v13_predictions: pd.DataFrame, v17_2_predictions: pd.DataFrame) -> pd.DataFrame:
    v17_2_keep_columns = [
        "join_key",
        "target_over_under_15",
        "total_goals",
        "v17_2_strategy",
        "v17_2_family",
        "v17_2_score",
        "v17_2_recommendation_status",
        "v17_2_recommendation",
        "v17_2_is_correct",
        "v17_2_signal_strength",
        "combined_over_1_5_rate_last_10",
        "combined_over_2_5_rate_last_10",
        "combined_btts_rate_last_10",
        "expected_total_goals_proxy",
        "prob_over_1_5_proxy",
        "prob_over_2_5_proxy",
        "prob_btts_proxy",
        "min_history_count_last_10",
    ]
    available_columns = [column for column in v17_2_keep_columns if column in v17_2_predictions.columns]
    merged = v13_predictions.merge(v17_2_predictions[available_columns], on="join_key", how="left")

    if merged["v17_2_recommendation_status"].isna().any():
        missing_count = int(merged["v17_2_recommendation_status"].isna().sum())
        raise RuntimeError(f"Fusion V13.1/V17.2 incomplète : {missing_count} match(s) sans signal V17.2.")
    return merged


# Applique le sélecteur V17.5 contrôlé : V13.1 d'abord, puis uniquement OVER_1_5 enrichi V17.2.
def apply_v17_5_selector(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()

    v13_selected = output["v13_mixed_recommendation_status"] == RECOMMEND_STATUS
    v17_2_over_selected = (
        (output["v17_2_recommendation_status"] == RECOMMEND_STATUS)
        & (output["v17_2_recommendation"] == OVER_15_VALUE)
    )
    add_over_15 = (~v13_selected) & v17_2_over_selected
    selected = v13_selected | add_over_15

    output["v17_5_strategy"] = V17_5_STRATEGY_NAME
    output["v17_5_recommendation_status"] = np.where(selected, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_5_recommendation_type"] = "ABSTAIN"
    output.loc[v13_selected, "v17_5_recommendation_type"] = output.loc[
        v13_selected, "v13_mixed_recommendation_type"
    ]
    output.loc[add_over_15, "v17_5_recommendation_type"] = GOALS_OVER_15_TYPE

    output["v17_5_recommendation_value"] = "ABSTAIN"
    output.loc[v13_selected, "v17_5_recommendation_value"] = output.loc[
        v13_selected, "v13_mixed_recommendation_value"
    ]
    output.loc[add_over_15, "v17_5_recommendation_value"] = OVER_15_VALUE

    output["v17_5_source"] = "ABSTAIN"
    output.loc[v13_selected, "v17_5_source"] = "V13_1_MIXED"
    output.loc[add_over_15, "v17_5_source"] = "V17_2_OVER_1_5_ENRICHED"

    output["v17_5_is_correct"] = False
    output.loc[v13_selected, "v17_5_is_correct"] = output.loc[v13_selected, "v13_mixed_is_correct"].astype(bool)
    output.loc[add_over_15, "v17_5_is_correct"] = output.loc[add_over_15, "v17_2_is_correct"].astype(bool)

    output["v17_5_is_added_over_15"] = add_over_15
    output["v17_5_excluded_reason"] = ""
    output.loc[(~v13_selected) & (output["v17_2_recommendation"] == UNDER_15_VALUE), "v17_5_excluded_reason"] = (
        "UNDER_1_5_EXCLUDED_REJECTED_IN_V17_2"
    )
    output.loc[(~selected) & (output["v17_5_excluded_reason"] == ""), "v17_5_excluded_reason"] = "NO_VALIDATED_SIGNAL"
    return output


# Calcule une variante volontairement rejetée qui ajouterait aussi UNDER_1_5 si V17.2 le proposait.
def compute_under_warning_variant(dataframe: pd.DataFrame) -> dict[str, object]:
    v13_selected = dataframe["v13_mixed_recommendation_status"] == RECOMMEND_STATUS
    v17_2_selected = dataframe["v17_2_recommendation_status"] == RECOMMEND_STATUS
    additional_v17_2 = (~v13_selected) & v17_2_selected
    selected = v13_selected | additional_v17_2

    correct = pd.Series(False, index=dataframe.index)
    correct.loc[v13_selected] = dataframe.loc[v13_selected, "v13_mixed_is_correct"].astype(bool)
    correct.loc[additional_v17_2] = dataframe.loc[additional_v17_2, "v17_2_is_correct"].astype(bool)

    under_added = additional_v17_2 & (dataframe["v17_2_recommendation"] == UNDER_15_VALUE)
    return {
        "strategy": V17_5_WARNING_UNDER_STRATEGY_NAME,
        "selected_rows": int(selected.sum()),
        "coverage": rounded(safe_rate(int(selected.sum()), len(dataframe))),
        "accuracy": rounded(safe_rate(int(correct.loc[selected].sum()), int(selected.sum()))),
        "added_under_15_rows": int(under_added.sum()),
        "added_under_15_accuracy": rounded(
            safe_rate(int(dataframe.loc[under_added, "v17_2_is_correct"].astype(bool).sum()), int(under_added.sum()))
        ),
        "decision": "REJECTED_VARIANT",
    }


# Calcule les métriques principales du sélecteur V17.5.
def compute_v17_5_metrics(predictions: pd.DataFrame) -> dict[str, object]:
    selected = predictions[predictions["v17_5_recommendation_status"] == RECOMMEND_STATUS]
    total_rows = len(predictions)
    selected_rows = len(selected)

    strict = selected[selected["v17_5_recommendation_type"] == STRICT_TYPE]
    double = selected[selected["v17_5_recommendation_type"] == DOUBLE_CHANCE_TYPE]
    over_15 = selected[selected["v17_5_recommendation_type"] == GOALS_OVER_15_TYPE]
    added_over_15 = predictions[predictions["v17_5_is_added_over_15"]]

    return {
        "strategy": V17_5_STRATEGY_NAME,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "accuracy": rounded(safe_rate(int(selected["v17_5_is_correct"].sum()), selected_rows)),
        "correct_rows": int(selected["v17_5_is_correct"].sum()),
        "strict_1x2_rows": len(strict),
        "strict_1x2_accuracy": rounded(safe_rate(int(strict["v17_5_is_correct"].sum()), len(strict))),
        "double_chance_rows": len(double),
        "double_chance_accuracy": rounded(safe_rate(int(double["v17_5_is_correct"].sum()), len(double))),
        "over_15_rows": len(over_15),
        "over_15_accuracy": rounded(safe_rate(int(over_15["v17_5_is_correct"].sum()), len(over_15))),
        "added_over_15_rows": len(added_over_15),
        "added_over_15_accuracy": rounded(safe_rate(int(added_over_15["v17_5_is_correct"].sum()), len(added_over_15))),
        "selected_rows_delta_vs_v13_1": selected_rows - int((predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS).sum()),
        "coverage_delta_vs_v13_1": rounded(
            safe_rate(selected_rows, total_rows)
            - safe_rate(int((predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS).sum()), total_rows)
        ),
        "selected_rows_delta_vs_v17_0": selected_rows - V17_0_REFERENCE_SELECTED_ROWS,
        "coverage_delta_vs_v17_0": rounded(safe_rate(selected_rows, total_rows) - V17_0_REFERENCE_COVERAGE),
        "accuracy_delta_vs_v17_0": rounded(safe_rate(int(selected["v17_5_is_correct"].sum()), selected_rows) - V17_0_REFERENCE_ACCURACY),
    }


# Construit le tableau de comparaison des stratégies V13.1, V17.0 et V17.5.
def build_results_table(predictions: pd.DataFrame, metrics: dict[str, object], under_variant: dict[str, object]) -> pd.DataFrame:
    v13_selected = predictions[predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS]

    rows = [
        {
            "strategy": V13_STRATEGY_NAME,
            "scope": "test_reference",
            "accuracy": rounded(safe_rate(int(v13_selected["v13_mixed_is_correct"].sum()), len(v13_selected))),
            "coverage": rounded(safe_rate(len(v13_selected), len(predictions))),
            "selected_rows": len(v13_selected),
            "strict_1x2_rows": int((v13_selected["v13_mixed_recommendation_type"] == STRICT_TYPE).sum()),
            "double_chance_rows": int((v13_selected["v13_mixed_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
            "over_15_rows": 0,
            "decision": "REFERENCE_V13_1",
        },
        {
            "strategy": "v17_0_controlled_v13_mixed_plus_v15_over15_only",
            "scope": "test_reference_static",
            "accuracy": V17_0_REFERENCE_ACCURACY,
            "coverage": V17_0_REFERENCE_COVERAGE,
            "selected_rows": V17_0_REFERENCE_SELECTED_ROWS,
            "strict_1x2_rows": 147,
            "double_chance_rows": 2738,
            "over_15_rows": V17_0_REFERENCE_OVER_15_ROWS,
            "decision": "REFERENCE_CURRENT_V17_0",
        },
        {
            "strategy": V17_5_STRATEGY_NAME,
            "scope": "test_final",
            "accuracy": metrics["accuracy"],
            "coverage": metrics["coverage"],
            "selected_rows": metrics["selected_rows"],
            "strict_1x2_rows": metrics["strict_1x2_rows"],
            "double_chance_rows": metrics["double_chance_rows"],
            "over_15_rows": metrics["over_15_rows"],
            "decision": "SELECTED_CONTROLLED_ENRICHED_VARIANT",
        },
        {
            "strategy": under_variant["strategy"],
            "scope": "test_warning",
            "accuracy": under_variant["accuracy"],
            "coverage": under_variant["coverage"],
            "selected_rows": under_variant["selected_rows"],
            "strict_1x2_rows": metrics["strict_1x2_rows"],
            "double_chance_rows": metrics["double_chance_rows"],
            "over_15_rows": metrics["over_15_rows"],
            "decision": under_variant["decision"],
        },
    ]
    return pd.DataFrame(rows)


# Agrège les performances V17.5 par marché retenu.
def build_by_market(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_5_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_5_recommendation_type", "v17_5_recommendation_value"], dropna=False)

    for (recommendation_type, recommendation_value), group in grouped:
        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_5_is_correct"].sum()), len(group))),
                "source": ",".join(sorted(group["v17_5_source"].astype(str).unique())),
                "avg_market_favorite_prob": rounded(group["market_favorite_prob"].mean()) if "market_favorite_prob" in group else 0.0,
                "avg_market_top2_sum": rounded(group["market_top2_sum"].mean()) if "market_top2_sum" in group else 0.0,
                "avg_v17_2_over_score": rounded(group["v17_2_score"].mean()) if "v17_2_score" in group else 0.0,
                "avg_prob_over_1_5_proxy": rounded(group["prob_over_1_5_proxy"].mean()) if "prob_over_1_5_proxy" in group else 0.0,
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()) if "expected_total_goals_proxy" in group else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Agrège les performances V17.5 par ligue et saison pour détecter les segments fragiles.
def build_by_league_season(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_5_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["__league_code", "__season"], dropna=False)

    for (league_code, season), group in grouped:
        selected_rows = len(group)
        accuracy = rounded(safe_rate(int(group["v17_5_is_correct"].sum()), selected_rows))
        segment_status = "OK"
        if selected_rows < LOW_VOLUME_SEGMENT_ROWS:
            segment_status = "LOW_VOLUME"
        elif accuracy < STRONG_MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_GATE"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "selected_rows": selected_rows,
                "accuracy": accuracy,
                "strict_1x2_rows": int((group["v17_5_recommendation_type"] == STRICT_TYPE).sum()),
                "double_chance_rows": int((group["v17_5_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
                "over_15_rows": int((group["v17_5_recommendation_type"] == GOALS_OVER_15_TYPE).sum()),
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Exporte un extrait des erreurs V17.5 pour comprendre les échecs restants.
def build_error_patterns(predictions: pd.DataFrame) -> pd.DataFrame:
    errors = predictions[
        (predictions["v17_5_recommendation_status"] == RECOMMEND_STATUS)
        & (~predictions["v17_5_is_correct"])
    ].copy()
    if errors.empty:
        return pd.DataFrame()

    keep_columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "target_over_under_15",
        "total_goals",
        "v17_5_recommendation_type",
        "v17_5_recommendation_value",
        "v17_5_source",
        "v13_mixed_recommendation_type",
        "v13_mixed_recommendation_value",
        "v17_2_recommendation",
        "v17_2_score",
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_top2_sum",
        "combined_over_1_5_rate_last_10",
        "expected_total_goals_proxy",
        "prob_over_1_5_proxy",
    ]
    available_columns = [column for column in keep_columns if column in errors.columns]
    return errors[available_columns].sort_values(["__season", "__league_code", "Date"]).head(800)


# Détermine le statut V17.5 selon les métriques globales et les segments majeurs.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame, v17_2_strategy_name: str) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))

    major_fragile_segments = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["selected_rows"] >= LOW_VOLUME_SEGMENT_ROWS]
        major_fragile_segments = len(major_segments[major_segments["accuracy"] < STRONG_MIN_MAJOR_SEGMENT_ACCURACY])

    blockers: list[str] = []
    warnings_list: list[str] = []

    if v17_2_strategy_name != V17_2_EXPECTED_STRATEGY_NAME:
        warnings_list.append(
            f"La stratégie V17.2 reconstruite est {v17_2_strategy_name}, différente de la stratégie attendue {V17_2_EXPECTED_STRATEGY_NAME}."
        )
    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {STRONG_MIN_MAJOR_SEGMENT_ACCURACY}.")
    if accuracy < V17_0_REFERENCE_ACCURACY:
        warnings_list.append("Accuracy inférieure à la référence V17.0.")
    if selected_rows <= V17_0_REFERENCE_SELECTED_ROWS:
        warnings_list.append("Selected rows ne dépasse pas la référence V17.0.")

    if (
        accuracy >= STRONG_MIN_ACCURACY
        and coverage >= STRONG_MIN_COVERAGE
        and selected_rows >= STRONG_MIN_SELECTED_ROWS
        and major_fragile_segments == 0
    ):
        return "V17_5_SELECTOR_ENRICHED_STRONG_REVIEW", blockers, warnings_list

    if accuracy >= REVIEW_MIN_ACCURACY and coverage >= REVIEW_MIN_COVERAGE and selected_rows >= REVIEW_MIN_SELECTED_ROWS:
        return "V17_5_SELECTOR_ENRICHED_REVIEW", blockers, warnings_list

    blockers.append("Compromis accuracy / coverage insuffisant pour remplacer V17.0 comme meilleur sélecteur expérimental.")
    return "V17_5_SELECTOR_ENRICHED_LIMITED_REVIEW", blockers, warnings_list


# Prépare les colonnes détaillées à exporter dans le CSV de prédictions V17.5.
def build_predictions_export(predictions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "target_over_under_15",
        "total_goals",
        "v17_5_strategy",
        "v17_5_recommendation_status",
        "v17_5_recommendation_type",
        "v17_5_recommendation_value",
        "v17_5_source",
        "v17_5_is_correct",
        "v17_5_is_added_over_15",
        "v17_5_excluded_reason",
        "v13_mixed_recommendation_type",
        "v13_mixed_recommendation_value",
        "v13_mixed_is_correct",
        "v17_2_strategy",
        "v17_2_recommendation",
        "v17_2_score",
        "v17_2_is_correct",
        "v17_2_signal_strength",
        "combined_over_1_5_rate_last_10",
        "expected_total_goals_proxy",
        "prob_over_1_5_proxy",
        "prob_over_2_5_proxy",
        "prob_btts_proxy",
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_top2_sum",
    ]
    available_columns = [column for column in columns if column in predictions.columns]
    return predictions[available_columns].copy()


# Écrit la synthèse V17.5 dans le dossier de preuves ML.
def write_summary(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
    by_league_season: pd.DataFrame,
    under_variant: dict[str, object],
    v17_2_strategy_name: str,
) -> None:
    lowest_segment = "Aucun"
    major_fragile_segments = 0
    if not by_league_season.empty:
        first = by_league_season.sort_values(["accuracy", "selected_rows"], ascending=[True, False]).iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"
        major_segments = by_league_season[by_league_season["selected_rows"] >= LOW_VOLUME_SEGMENT_ROWS]
        major_fragile_segments = len(major_segments[major_segments["accuracy"] < STRONG_MIN_MAJOR_SEGMENT_ACCURACY])

    lines = [
        "RubyBets - ML V17.5 multi-market selector enrichi final",
        "256 - Synthèse expérience V17.5",
        "",
        "Objectif :",
        "Reconstruire le sélecteur multi-marchés V17 avec uniquement les signaux validés ou défendables : V13.1 1X2/double chance et OVER_1_5 enrichi V17.2. UNDER_1_5, O/U 2.5 et BTTS restent exclus.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data via les scripts V13.1 et V17.2.",
        "- Construction des signaux enrichis en mémoire.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Logique du sélecteur V17.5 :",
        "1. Si V13.1 recommande un 1X2 strict, conserver le 1X2 strict.",
        "2. Sinon, si V13.1 recommande une double chance, conserver 1X / X2 / 12.",
        "3. Sinon, si V17.2 recommande OVER_1_5, ajouter OVER_1_5 comme complément enrichi prudent.",
        "4. Exclure UNDER_1_5, O/U 2.5 et BTTS.",
        "5. S'abstenir si aucun signal validé n'est disponible.",
        "",
        "Signal V17.2 utilisé :",
        f"- Strategy : {v17_2_strategy_name}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Strategy : {metrics.get('strategy')}",
        f"- Accuracy : {metrics.get('accuracy')}",
        f"- Coverage : {metrics.get('coverage')}",
        f"- Abstention rate : {metrics.get('abstention_rate')}",
        f"- Selected rows : {metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {metrics.get('double_chance_accuracy')}",
        f"- OVER_1_5 rows : {metrics.get('over_15_rows')}",
        f"- OVER_1_5 accuracy : {metrics.get('over_15_accuracy')}",
        f"- Added OVER_1_5 rows vs V13.1 : {metrics.get('added_over_15_rows')}",
        f"- Added OVER_1_5 accuracy : {metrics.get('added_over_15_accuracy')}",
        "",
        "Comparaison avec V17.0 :",
        f"- V17.0 accuracy : {V17_0_REFERENCE_ACCURACY}",
        f"- V17.5 accuracy delta : {metrics.get('accuracy_delta_vs_v17_0')}",
        f"- V17.0 coverage : {V17_0_REFERENCE_COVERAGE}",
        f"- V17.5 coverage delta : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- V17.0 selected rows : {V17_0_REFERENCE_SELECTED_ROWS}",
        f"- V17.5 selected rows delta : {metrics.get('selected_rows_delta_vs_v17_0')}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        f"- Segments majeurs sous {STRONG_MIN_MAJOR_SEGMENT_ACCURACY} : {major_fragile_segments}",
        "",
        "Variante rejetée :",
        f"- Strategy : {under_variant.get('strategy')}",
        f"- Selected rows : {under_variant.get('selected_rows')}",
        f"- Accuracy : {under_variant.get('accuracy')}",
        f"- Added UNDER_1_5 rows : {under_variant.get('added_under_15_rows')}",
        f"- Added UNDER_1_5 accuracy : {under_variant.get('added_under_15_accuracy')}",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision produit :",
        "Ne pas intégrer V17.5 au produit à ce stade. V17.5 reste une expérimentation ML multi-marchés séparée ; le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision opérationnelle V17.5.
def write_decision(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17.5 multi-market selector enrichi final",
        "261 - Décision expérience V17.5",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {metrics.get('strategy')}",
        f"- Accuracy : {metrics.get('accuracy')}",
        f"- Coverage : {metrics.get('coverage')}",
        f"- Abstention rate : {metrics.get('abstention_rate')}",
        f"- Selected rows : {metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {metrics.get('double_chance_accuracy')}",
        f"- OVER_1_5 rows : {metrics.get('over_15_rows')}",
        f"- OVER_1_5 accuracy : {metrics.get('over_15_accuracy')}",
        f"- Selected rows delta vs V17.0 : {metrics.get('selected_rows_delta_vs_v17_0')}",
        f"- Coverage delta vs V17.0 : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- Accuracy delta vs V17.0 : {metrics.get('accuracy_delta_vs_v17_0')}",
        "",
        "Gates V17.5 :",
        f"- Accuracy cible >= {STRONG_MIN_ACCURACY}",
        f"- Coverage cible >= {STRONG_MIN_COVERAGE}",
        f"- Selected rows > {V17_0_REFERENCE_SELECTED_ROWS}",
        f"- Aucun segment majeur sous {STRONG_MIN_MAJOR_SEGMENT_ACCURACY}",
        "- Aucun marché ne doit entrer automatiquement sans validation préalable.",
        "- Aucun modèle officiel sauvegardé.",
        "- Aucune intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision opérationnelle :",
    ]

    if status == "V17_5_SELECTOR_ENRICHED_STRONG_REVIEW":
        lines.extend(
            [
                "- V17.5 devient le meilleur candidat expérimental multi-marchés enrichi.",
                "- V17.5 améliore V17.0 tout en conservant une logique contrôlée.",
                "- V17.5 peut être conservée comme référence expérimentale finale V17.x.",
            ]
        )
    elif status == "V17_5_SELECTOR_ENRICHED_REVIEW":
        lines.extend(
            [
                "- V17.5 est exploitable comme comparaison expérimentale, mais ne remplace pas clairement V17.0.",
                "- V17.0 reste la référence prudente tant qu'aucun arbitrage produit n'est fait.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.5 ne remplace pas V17.0 comme meilleur sélecteur expérimental.",
                "- V17.0 reste la référence multi-marchés contrôlée.",
            ]
        )

    lines.extend(
        [
            "- UNDER_1_5 reste exclu.",
            "- O/U 2.5 reste exclu.",
            "- BTTS reste exclu.",
            "- V17.5 ne remplace pas le scoring explicable V1.",
            "- V17.5 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.5 sélecteur multi-marchés enrichi final : réalisée si les fichiers 256 à 261 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_multimarket_v17_5_selector_enriched.py et reports/evidence/ml_training/256-261.",
        ]
    )
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Orchestre V17.5 sans modifier RubyBets produit.
def main() -> None:
    print("Reconstruction des signaux V13.1 et V17.2 pour V17.5 selector enrichi...")
    v17_2_module = load_module("rubybets_v17_2_over15_enriched", "train_goals_v17_2_over_under_15_enriched.py")
    project_root = v17_2_module.find_project_root()
    evidence_dir = v17_2_module.get_evidence_dir(project_root)

    v13_predictions = load_v17_0_reference_predictions(evidence_dir)
    if v13_predictions is None:
        v13_module = load_module("rubybets_v13_mixed", "train_1x2_v13_mixed_selective.py")
        v13_predictions = build_v13_predictions(project_root, v13_module)
    v17_2_predictions, v17_2_strategy_name = build_v17_2_predictions(project_root, v17_2_module)

    print("Application du sélecteur enrichi : V13.1 puis OVER_1_5 V17.2 uniquement...")
    merged = merge_candidate_predictions(v13_predictions, v17_2_predictions)
    v17_5_predictions = apply_v17_5_selector(merged)
    metrics = compute_v17_5_metrics(v17_5_predictions)
    under_variant = compute_under_warning_variant(merged)
    by_market = build_by_market(v17_5_predictions)
    by_league_season = build_by_league_season(v17_5_predictions)
    error_patterns = build_error_patterns(v17_5_predictions)
    results_table = build_results_table(v17_5_predictions, metrics, under_variant)
    status, blockers, warnings_list = determine_status(metrics, by_league_season, v17_2_strategy_name)

    write_summary(
        evidence_dir / OUTPUT_SUMMARY,
        metrics,
        status,
        blockers,
        warnings_list,
        by_league_season,
        under_variant,
        v17_2_strategy_name,
    )
    build_predictions_export(v17_5_predictions).to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_market.to_csv(evidence_dir / OUTPUT_BY_MARKET, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")
    write_decision(evidence_dir / OUTPUT_DECISION, metrics, status, blockers, warnings_list)

    print("OK - Expérience V17.5 multi-market selector enrichi terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {metrics.get('strategy')}")
    print(f"V17.2 strategy used: {v17_2_strategy_name}")
    print(f"Test accuracy: {metrics.get('accuracy')}")
    print(f"Test coverage: {metrics.get('coverage')}")
    print(f"Test abstention rate: {metrics.get('abstention_rate')}")
    print(f"Selected rows: {metrics.get('selected_rows')}")
    print(f"Strict 1X2 rows: {metrics.get('strict_1x2_rows')}")
    print(f"Strict 1X2 accuracy: {metrics.get('strict_1x2_accuracy')}")
    print(f"Double chance rows: {metrics.get('double_chance_rows')}")
    print(f"Double chance accuracy: {metrics.get('double_chance_accuracy')}")
    print(f"OVER_1_5 rows: {metrics.get('over_15_rows')}")
    print(f"OVER_1_5 accuracy: {metrics.get('over_15_accuracy')}")
    print(f"Selected rows delta vs V17.0: {metrics.get('selected_rows_delta_vs_v17_0')}")
    print(f"Coverage delta vs V17.0: {metrics.get('coverage_delta_vs_v17_0')}")
    print(f"Accuracy delta vs V17.0: {metrics.get('accuracy_delta_vs_v17_0')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By market CSV saved: {evidence_dir / OUTPUT_BY_MARKET}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# train_multimarket_v17_5_selector_enriched.py
#   -> réutilise backend/scripts/ml/train_1x2_v13_mixed_selective.py
#   -> réutilise backend/scripts/ml/train_goals_v17_2_over_under_15_enriched.py
#   -> réutilise backend/scripts/ml/build_multimarket_v17_1_enriched_features.py via V17.2
#   -> lit data/ml/raw/*.csv en lecture seule via les scripts réutilisés
#   -> écrit reports/evidence/ml_training/256 à 261
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
