# Rôle du fichier : tester V17.7, un sélecteur multi-marchés contrôlé qui ajoute BTTS_YES ultra-sélectif V17.6 uniquement en fallback, sans intégration produit.

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
BTTS_TYPE = "BTTS"
BTTS_YES_VALUE = "BTTS_YES"
BTTS_NO_VALUE = "BTTS_NO"

OUTPUT_SUMMARY = "268_multimarket_v17_7_selector_with_btts_summary.txt"
OUTPUT_RESULTS = "269_multimarket_v17_7_selector_with_btts_results.csv"
OUTPUT_BY_MARKET = "270_multimarket_v17_7_selector_with_btts_by_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "271_multimarket_v17_7_selector_with_btts_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "272_multimarket_v17_7_selector_with_btts_error_patterns.csv"
OUTPUT_DECISION = "273_multimarket_v17_7_selector_with_btts_decision.txt"
OUTPUT_V17_REFERENCE_RESULTS = "228_multimarket_v17_selector_results.csv"

V17_REFERENCE_STRATEGY = "v17_controlled_v13_mixed_plus_over15_only"
V17_7_STRATEGY = "v17_7_v17_0_plus_btts_yes_ultra_selective_fallback"
V17_6_STRATEGY_NAME = "v17_6_logisticbalanced_yes_t0580_no_t0400_mh8_eg0900_bt0500"

V17_REFERENCE_ACCURACY = 0.8382
V17_REFERENCE_COVERAGE = 0.7651
V17_REFERENCE_SELECTED_ROWS = 4078
V17_REFERENCE_STRICT_ROWS = 147
V17_REFERENCE_DOUBLE_ROWS = 2738
V17_REFERENCE_OVER_15_ROWS = 1193

MIN_GLOBAL_ACCURACY_USER_GATE = 0.70
MIN_GLOBAL_ACCURACY_PRO_GATE = 0.80
MIN_ADDED_BTTS_ROWS_REVIEW = 20
MIN_BTTS_ADDED_ACCURACY_REVIEW = 0.60
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.70
STRONG_SEGMENT_ACCURACY = 0.75

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


# Construit une clé stable pour relier les sorties V17.0 et BTTS V17.6 sur les mêmes matchs.
def build_join_key(dataframe: pd.DataFrame, columns: list[str]) -> pd.Series:
    output = dataframe[columns].astype(str).fillna("")
    return output.apply(lambda row: "|".join(row.values.tolist()), axis=1)


# Lit le fichier 228 de V17.0 quand il existe, afin de repartir de la vraie référence contrôlée.
def load_v17_reference_predictions(evidence_dir: Path) -> pd.DataFrame | None:
    reference_path = evidence_dir / OUTPUT_V17_REFERENCE_RESULTS
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
        "v17_recommendation_status",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_source",
        "v17_is_correct",
    }
    missing_columns = required_columns - set(reference.columns)
    if missing_columns:
        return None

    output = reference.copy()
    output["join_key"] = build_join_key(output, ["__league_code", "__season", "Date", "HomeTeam", "AwayTeam"])
    return output


# Reconstruit V17.0 depuis les scripts V13.1/V15/V17 si le fichier 228 n'est pas disponible.
def rebuild_v17_reference_predictions(project_root: Path, v17_module: ModuleType) -> pd.DataFrame:
    v13_module = v17_module.load_module("rubybets_v13_mixed_for_v17_7", "train_1x2_v13_mixed_selective.py")
    v15_module = v17_module.load_module("rubybets_v15_over15_for_v17_7", "train_goals_v15_over_under_15_labels_selective.py")
    v13_predictions = v17_module.build_v13_predictions(project_root, v13_module)
    v15_predictions = v17_module.build_v15_predictions(project_root, v15_module)
    merged = v17_module.merge_candidate_predictions(v13_predictions, v15_predictions)
    reference = v17_module.apply_v17_controlled_selector(merged)
    reference["join_key"] = build_join_key(reference, ["__league_code", "__season", "Date", "HomeTeam", "AwayTeam"])
    return reference


# Crée explicitement la stratégie BTTS V17.6 retenue, sans relancer les 864 000 combinaisons.
def build_fixed_v17_6_strategy(v17_6_module: ModuleType):
    return v17_6_module.StrategySpec(
        name=V17_6_STRATEGY_NAME,
        family="btts_mixed_ultra",
        score_column="score_logistic_balanced_btts_yes",
        yes_threshold=0.58,
        no_threshold=0.40,
        min_history_count=8,
        min_expected_team_goals=0.90,
        min_expected_total_goals=2.00,
        min_combined_btts_rate=0.50,
        max_failed_to_score_rate=0.45,
        min_over_15_rate=0.55,
        no_min_failed_or_clean_rate=0.50,
        notes="Stratégie V17.6 retenue, utilisée seulement pour ajouter BTTS_YES en fallback.",
    )


# Reconstruit uniquement les prédictions BTTS V17.6 nécessaires au sélecteur V17.7, sans grille complète.
def build_v17_6_btts_predictions(project_root: Path, v17_6_module: ModuleType) -> tuple[pd.DataFrame, str]:
    dataset, _ = v17_6_module.build_v17_6_dataset(project_root)
    train, validation, test = v17_6_module.split_dataset(dataset)
    _, _, test_scored = v17_6_module.attach_scores(train, validation, test)
    fixed_strategy = build_fixed_v17_6_strategy(v17_6_module)
    predictions = v17_6_module.apply_strategy(test_scored, fixed_strategy).copy()
    predictions["join_key"] = build_join_key(predictions, ["league_code", "season", "match_date", "home_team", "away_team"])
    return predictions, fixed_strategy.name


# Fusionne V17.0 et BTTS V17.6 sur le périmètre de test final.
def merge_v17_and_btts(v17_reference: pd.DataFrame, btts_predictions: pd.DataFrame) -> pd.DataFrame:
    btts_keep_columns = [
        "join_key",
        "target_btts",
        "v17_6_strategy",
        "v17_6_family",
        "v17_6_score_column",
        "v17_6_score",
        "v17_6_recommendation_status",
        "v17_6_recommendation",
        "v17_6_is_correct",
        "v17_6_signal_strength",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "combined_over_1_5_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "min_history_count_last_10",
    ]
    available_columns = [column for column in btts_keep_columns if column in btts_predictions.columns]
    merged = v17_reference.merge(btts_predictions[available_columns], on="join_key", how="left")

    if merged["v17_6_recommendation_status"].isna().any():
        missing_count = int(merged["v17_6_recommendation_status"].isna().sum())
        raise RuntimeError(f"Fusion V17.0/V17.6 incomplète : {missing_count} match(s) sans signal BTTS V17.6.")
    return merged


# Applique V17.7 : V17.0 d'abord, puis BTTS_YES ultra-sélectif uniquement si V17.0 s'abstient.
def apply_v17_7_selector(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()

    v17_selected = output["v17_recommendation_status"] == RECOMMEND_STATUS
    btts_yes_selected = (
        (output["v17_6_recommendation_status"] == RECOMMEND_STATUS)
        & (output["v17_6_recommendation"] == BTTS_YES_VALUE)
    )
    add_btts_yes = (~v17_selected) & btts_yes_selected
    selected = v17_selected | add_btts_yes

    output["v17_7_strategy"] = V17_7_STRATEGY
    output["v17_7_recommendation_status"] = np.where(selected, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_7_recommendation_type"] = "ABSTAIN"
    output.loc[v17_selected, "v17_7_recommendation_type"] = output.loc[v17_selected, "v17_recommendation_type"]
    output.loc[add_btts_yes, "v17_7_recommendation_type"] = BTTS_TYPE

    output["v17_7_recommendation_value"] = "ABSTAIN"
    output.loc[v17_selected, "v17_7_recommendation_value"] = output.loc[v17_selected, "v17_recommendation_value"]
    output.loc[add_btts_yes, "v17_7_recommendation_value"] = BTTS_YES_VALUE

    output["v17_7_source"] = "ABSTAIN"
    output.loc[v17_selected, "v17_7_source"] = output.loc[v17_selected, "v17_source"].astype(str)
    output.loc[add_btts_yes, "v17_7_source"] = "V17_6_BTTS_YES_ULTRA_SELECTIVE"

    output["v17_7_is_correct"] = False
    output.loc[v17_selected, "v17_7_is_correct"] = output.loc[v17_selected, "v17_is_correct"].astype(bool)
    output.loc[add_btts_yes, "v17_7_is_correct"] = output.loc[add_btts_yes, "v17_6_is_correct"].astype(bool)

    output["v17_7_is_added_btts_yes"] = add_btts_yes
    output["v17_7_excluded_reason"] = ""
    output.loc[(~v17_selected) & (output["v17_6_recommendation"] == BTTS_NO_VALUE), "v17_7_excluded_reason"] = (
        "BTTS_NO_EXCLUDED_LOW_VOLUME_IN_V17_6"
    )
    output.loc[(~selected) & (output["v17_7_excluded_reason"] == ""), "v17_7_excluded_reason"] = "NO_VALIDATED_SIGNAL"
    return output


# Calcule les métriques principales de V17.7.
def compute_v17_7_metrics(predictions: pd.DataFrame) -> dict[str, object]:
    selected = predictions[predictions["v17_7_recommendation_status"] == RECOMMEND_STATUS]
    total_rows = len(predictions)
    selected_rows = len(selected)

    strict = selected[selected["v17_7_recommendation_type"] == STRICT_TYPE]
    double = selected[selected["v17_7_recommendation_type"] == DOUBLE_CHANCE_TYPE]
    over_15 = selected[selected["v17_7_recommendation_type"] == GOALS_OVER_15_TYPE]
    btts = selected[selected["v17_7_recommendation_type"] == BTTS_TYPE]
    added_btts = predictions[predictions["v17_7_is_added_btts_yes"]]
    v17_selected = predictions[predictions["v17_recommendation_status"] == RECOMMEND_STATUS]

    return {
        "strategy": V17_7_STRATEGY,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "accuracy": rounded(safe_rate(int(selected["v17_7_is_correct"].sum()), selected_rows)),
        "correct_rows": int(selected["v17_7_is_correct"].sum()),
        "strict_1x2_rows": len(strict),
        "strict_1x2_accuracy": rounded(safe_rate(int(strict["v17_7_is_correct"].sum()), len(strict))),
        "double_chance_rows": len(double),
        "double_chance_accuracy": rounded(safe_rate(int(double["v17_7_is_correct"].sum()), len(double))),
        "over_15_rows": len(over_15),
        "over_15_accuracy": rounded(safe_rate(int(over_15["v17_7_is_correct"].sum()), len(over_15))),
        "btts_rows": len(btts),
        "btts_accuracy": rounded(safe_rate(int(btts["v17_7_is_correct"].sum()), len(btts))),
        "added_btts_yes_rows": len(added_btts),
        "added_btts_yes_accuracy": rounded(safe_rate(int(added_btts["v17_7_is_correct"].sum()), len(added_btts))),
        "v17_reference_selected_rows": len(v17_selected),
        "v17_reference_accuracy_recomputed": rounded(safe_rate(int(v17_selected["v17_is_correct"].sum()), len(v17_selected))),
        "selected_rows_delta_vs_v17_0": selected_rows - len(v17_selected),
        "coverage_delta_vs_v17_0": rounded(safe_rate(selected_rows, total_rows) - safe_rate(len(v17_selected), total_rows)),
        "accuracy_delta_vs_v17_0": rounded(
            safe_rate(int(selected["v17_7_is_correct"].sum()), selected_rows)
            - safe_rate(int(v17_selected["v17_is_correct"].sum()), len(v17_selected))
        ),
    }


# Construit le tableau comparatif V17.0 / V17.6 / V17.7.
def build_results_table(predictions: pd.DataFrame, metrics: dict[str, object]) -> pd.DataFrame:
    v17_selected = predictions[predictions["v17_recommendation_status"] == RECOMMEND_STATUS]
    btts_candidate = predictions[
        (predictions["v17_6_recommendation_status"] == RECOMMEND_STATUS)
        & (predictions["v17_6_recommendation"] == BTTS_YES_VALUE)
    ]
    added_btts = predictions[predictions["v17_7_is_added_btts_yes"]]

    rows = [
        {
            "strategy": V17_REFERENCE_STRATEGY,
            "scope": "test_reference_v17_0",
            "accuracy": rounded(safe_rate(int(v17_selected["v17_is_correct"].sum()), len(v17_selected))),
            "coverage": rounded(safe_rate(len(v17_selected), len(predictions))),
            "selected_rows": len(v17_selected),
            "strict_1x2_rows": int((v17_selected["v17_recommendation_type"] == STRICT_TYPE).sum()),
            "double_chance_rows": int((v17_selected["v17_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
            "over_15_rows": int((v17_selected["v17_recommendation_type"] == GOALS_OVER_15_TYPE).sum()),
            "btts_rows": 0,
            "decision": "REFERENCE_V17_0",
        },
        {
            "strategy": V17_6_STRATEGY_NAME,
            "scope": "test_btts_candidate_before_fallback",
            "accuracy": rounded(safe_rate(int(btts_candidate["v17_6_is_correct"].sum()), len(btts_candidate))),
            "coverage": rounded(safe_rate(len(btts_candidate), len(predictions))),
            "selected_rows": len(btts_candidate),
            "strict_1x2_rows": 0,
            "double_chance_rows": 0,
            "over_15_rows": 0,
            "btts_rows": len(btts_candidate),
            "decision": "BTTS_CANDIDATE_ONLY",
        },
        {
            "strategy": "v17_6_btts_yes_added_only_after_v17_0_abstention",
            "scope": "test_incremental_btts_fallback_only",
            "accuracy": metrics["added_btts_yes_accuracy"],
            "coverage": rounded(safe_rate(len(added_btts), len(predictions))),
            "selected_rows": len(added_btts),
            "strict_1x2_rows": 0,
            "double_chance_rows": 0,
            "over_15_rows": 0,
            "btts_rows": len(added_btts),
            "decision": "INCREMENTAL_BTTS_FALLBACK",
        },
        {
            "strategy": V17_7_STRATEGY,
            "scope": "test_final",
            "accuracy": metrics["accuracy"],
            "coverage": metrics["coverage"],
            "selected_rows": metrics["selected_rows"],
            "strict_1x2_rows": metrics["strict_1x2_rows"],
            "double_chance_rows": metrics["double_chance_rows"],
            "over_15_rows": metrics["over_15_rows"],
            "btts_rows": metrics["btts_rows"],
            "decision": "SELECTOR_WITH_BTTS_FALLBACK",
        },
    ]
    return pd.DataFrame(rows)


# Agrège les performances V17.7 par marché retenu.
def build_by_market(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_7_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_7_recommendation_type", "v17_7_recommendation_value"], dropna=False)

    for (recommendation_type, recommendation_value), group in grouped:
        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_7_is_correct"].sum()), len(group))),
                "source": ",".join(sorted(group["v17_7_source"].astype(str).unique())),
                "avg_v17_6_btts_score": rounded(group["v17_6_score"].mean()) if "v17_6_score" in group else 0.0,
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()) if "prob_btts_proxy" in group else 0.0,
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()) if "combined_btts_rate_last_10" in group else 0.0,
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()) if "expected_total_goals_proxy" in group else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Agrège les performances V17.7 par ligue et saison pour contrôler la stabilité.
def build_by_league_season(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_7_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["__league_code", "__season"], dropna=False)

    for (league_code, season), group in grouped:
        selected_rows = len(group)
        accuracy = rounded(safe_rate(int(group["v17_7_is_correct"].sum()), selected_rows))
        segment_status = "OK"
        if selected_rows < MIN_MAJOR_SEGMENT_ROWS:
            segment_status = "LOW_VOLUME"
        elif accuracy < MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_0_70"
        elif accuracy < STRONG_SEGMENT_ACCURACY:
            segment_status = "UNDER_STRONG_0_75"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "selected_rows": selected_rows,
                "accuracy": accuracy,
                "strict_1x2_rows": int((group["v17_7_recommendation_type"] == STRICT_TYPE).sum()),
                "double_chance_rows": int((group["v17_7_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
                "over_15_rows": int((group["v17_7_recommendation_type"] == GOALS_OVER_15_TYPE).sum()),
                "btts_rows": int((group["v17_7_recommendation_type"] == BTTS_TYPE).sum()),
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Exporte un extrait des erreurs V17.7 pour analyser les limites restantes.
def build_error_patterns(predictions: pd.DataFrame) -> pd.DataFrame:
    errors = predictions[
        (predictions["v17_7_recommendation_status"] == RECOMMEND_STATUS)
        & (~predictions["v17_7_is_correct"])
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
        "target_btts",
        "v17_7_recommendation_type",
        "v17_7_recommendation_value",
        "v17_7_source",
        "v17_7_is_correct",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_is_correct",
        "v17_6_recommendation",
        "v17_6_score",
        "v17_6_signal_strength",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "min_history_count_last_10",
    ]
    available_columns = [column for column in keep_columns if column in errors.columns]
    return errors[available_columns].sort_values(["__season", "__league_code", "Date"]).head(800)


# Détermine le statut V17.7 selon l'objectif utilisateur et les exigences de stabilité.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))
    added_btts_rows = int(metrics.get("added_btts_yes_rows", 0))
    added_btts_accuracy = float(metrics.get("added_btts_yes_accuracy", 0.0))

    major_under_70 = 0
    major_under_75 = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["selected_rows"] >= MIN_MAJOR_SEGMENT_ROWS]
        major_under_70 = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])
        major_under_75 = len(major_segments[major_segments["accuracy"] < STRONG_SEGMENT_ACCURACY])

    blockers: list[str] = []
    warnings_list: list[str] = []

    if added_btts_rows == 0:
        blockers.append("Aucun BTTS_YES additionnel après abstention V17.0 : l'intégration BTTS n'apporte pas de couverture.")
    if accuracy < MIN_GLOBAL_ACCURACY_USER_GATE:
        blockers.append("Accuracy globale sous le seuil utilisateur minimal de 0.70.")
    if added_btts_rows < MIN_ADDED_BTTS_ROWS_REVIEW:
        warnings_list.append(f"Volume BTTS additionnel faible : {added_btts_rows} lignes ajoutées.")
    if added_btts_accuracy < MIN_BTTS_ADDED_ACCURACY_REVIEW and added_btts_rows > 0:
        warnings_list.append(f"Accuracy du BTTS ajouté sous {MIN_BTTS_ADDED_ACCURACY_REVIEW}.")
    if major_under_70 > 0:
        warnings_list.append(f"{major_under_70} segment(s) majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if major_under_75 > 0:
        warnings_list.append(f"{major_under_75} segment(s) majeur(s) sous {STRONG_SEGMENT_ACCURACY}.")
    if accuracy < V17_REFERENCE_ACCURACY:
        warnings_list.append("Accuracy globale inférieure à V17.0 : le gain de couverture BTTS a un coût.")
    if selected_rows <= V17_REFERENCE_SELECTED_ROWS:
        warnings_list.append("Selected rows ne dépasse pas V17.0.")

    if blockers:
        return "V17_7_SELECTOR_WITH_BTTS_REJECTED", blockers, warnings_list

    if (
        accuracy >= V17_REFERENCE_ACCURACY
        and selected_rows > V17_REFERENCE_SELECTED_ROWS
        and added_btts_rows >= MIN_ADDED_BTTS_ROWS_REVIEW
        and added_btts_accuracy >= MIN_BTTS_ADDED_ACCURACY_REVIEW
        and major_under_75 == 0
    ):
        return "V17_7_SELECTOR_WITH_BTTS_STRONG_REVIEW", blockers, warnings_list

    if accuracy >= MIN_GLOBAL_ACCURACY_PRO_GATE and selected_rows > V17_REFERENCE_SELECTED_ROWS and added_btts_rows > 0:
        return "V17_7_SELECTOR_WITH_BTTS_REVIEW", blockers, warnings_list

    return "V17_7_SELECTOR_WITH_BTTS_LIMITED_REVIEW", blockers, warnings_list


# Prépare les colonnes détaillées à exporter dans le CSV de prédictions V17.7.
def build_predictions_export(predictions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "target_over_under_15",
        "target_btts",
        "v17_7_strategy",
        "v17_7_recommendation_status",
        "v17_7_recommendation_type",
        "v17_7_recommendation_value",
        "v17_7_source",
        "v17_7_is_correct",
        "v17_7_is_added_btts_yes",
        "v17_7_excluded_reason",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_source",
        "v17_is_correct",
        "v17_6_strategy",
        "v17_6_recommendation",
        "v17_6_score",
        "v17_6_is_correct",
        "v17_6_signal_strength",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "combined_over_1_5_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "min_history_count_last_10",
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_top2_sum",
    ]
    available_columns = [column for column in columns if column in predictions.columns]
    return predictions[available_columns].copy()


# Écrit la synthèse V17.7 dans le dossier de preuves ML.
def write_summary(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
    by_league_season: pd.DataFrame,
    btts_strategy_name: str,
) -> None:
    lowest_segment = "Aucun"
    major_under_70 = 0
    if not by_league_season.empty:
        first = by_league_season.sort_values(["accuracy", "selected_rows"], ascending=[True, False]).iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"
        major_segments = by_league_season[by_league_season["selected_rows"] >= MIN_MAJOR_SEGMENT_ROWS]
        major_under_70 = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])

    lines = [
        "RubyBets - ML V17.7 sélecteur multi-marchés avec BTTS ultra-sélectif",
        "268 - Synthèse expérience V17.7",
        "",
        "Objectif :",
        "Tester une intégration propre de BTTS dans le sélecteur multi-marchés, sans forcer le marché : V17.0 reste prioritaire et BTTS_YES V17.6 n'est ajouté qu'en fallback sur les matchs sans signal V17.0.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data via les scripts existants.",
        "- Construction des signaux en mémoire.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Logique du sélecteur V17.7 :",
        "1. Si V17.0 recommande un 1X2 strict, une double chance ou OVER_1_5, conserver V17.0.",
        "2. Sinon, si V17.6 recommande BTTS_YES ultra-sélectif, ajouter BTTS_YES.",
        "3. Exclure BTTS_NO pour volume insuffisant.",
        "4. Exclure UNDER_1_5 et O/U 2.5.",
        "5. S'abstenir si aucun signal validé n'est disponible.",
        "",
        "Signal BTTS utilisé :",
        f"- Strategy : {btts_strategy_name}",
        "- BTTS_NO n'est pas intégré dans V17.7.",
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
        f"- BTTS rows : {metrics.get('btts_rows')}",
        f"- BTTS accuracy : {metrics.get('btts_accuracy')}",
        f"- Added BTTS_YES rows vs V17.0 : {metrics.get('added_btts_yes_rows')}",
        f"- Added BTTS_YES accuracy : {metrics.get('added_btts_yes_accuracy')}",
        "",
        "Comparaison avec V17.0 :",
        f"- V17.0 selected rows recalculées : {metrics.get('v17_reference_selected_rows')}",
        f"- V17.0 accuracy recalculée : {metrics.get('v17_reference_accuracy_recomputed')}",
        f"- Selected rows delta vs V17.0 : {metrics.get('selected_rows_delta_vs_v17_0')}",
        f"- Coverage delta vs V17.0 : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- Accuracy delta vs V17.0 : {metrics.get('accuracy_delta_vs_v17_0')}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        f"- Segments majeurs sous {MIN_MAJOR_SEGMENT_ACCURACY} : {major_under_70}",
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
        "Ne pas intégrer V17.7 au produit à ce stade. V17.7 sert uniquement à vérifier si BTTS peut être ajouté sans casser le compromis global.",
        "Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision opérationnelle V17.7.
def write_decision(output_path: Path, metrics: dict[str, object], status: str, blockers: list[str], warnings_list: list[str]) -> None:
    lines = [
        "RubyBets - Décision V17.7 sélecteur avec BTTS ultra-sélectif",
        "273 - Décision expérience V17.7",
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
        f"- BTTS rows : {metrics.get('btts_rows')}",
        f"- BTTS accuracy : {metrics.get('btts_accuracy')}",
        f"- Added BTTS_YES rows : {metrics.get('added_btts_yes_rows')}",
        f"- Added BTTS_YES accuracy : {metrics.get('added_btts_yes_accuracy')}",
        f"- Selected rows delta vs V17.0 : {metrics.get('selected_rows_delta_vs_v17_0')}",
        f"- Coverage delta vs V17.0 : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- Accuracy delta vs V17.0 : {metrics.get('accuracy_delta_vs_v17_0')}",
        "",
        "Gates V17.7 :",
        f"- Accuracy globale minimale utilisateur >= {MIN_GLOBAL_ACCURACY_USER_GATE}",
        f"- Accuracy globale professionnelle cible >= {MIN_GLOBAL_ACCURACY_PRO_GATE}",
        f"- Added BTTS rows review >= {MIN_ADDED_BTTS_ROWS_REVIEW}",
        f"- Added BTTS accuracy review >= {MIN_BTTS_ADDED_ACCURACY_REVIEW}",
        f"- Aucun segment majeur sous {MIN_MAJOR_SEGMENT_ACCURACY}",
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

    if status == "V17_7_SELECTOR_WITH_BTTS_STRONG_REVIEW":
        lines.extend(
            [
                "- V17.7 devient un candidat expérimental fort avec BTTS intégré proprement.",
                "- BTTS_YES peut être conservé comme signal rare de fallback expérimental.",
            ]
        )
    elif status == "V17_7_SELECTOR_WITH_BTTS_REVIEW":
        lines.extend(
            [
                "- V17.7 atteint un niveau global acceptable avec BTTS intégré, mais nécessite encore un arbitrage produit.",
                "- BTTS_YES reste un signal rare de fallback, pas un marché prioritaire.",
            ]
        )
    elif status == "V17_7_SELECTOR_WITH_BTTS_LIMITED_REVIEW":
        lines.extend(
            [
                "- V17.7 montre une intégration BTTS possible, mais pas assez forte pour remplacer V17.0.",
                "- BTTS peut rester une piste expérimentale documentée.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.7 ne valide pas l'intégration BTTS.",
                "- V17.0 reste la référence expérimentale multi-marchés contrôlée.",
            ]
        )

    lines.extend(
        [
            "- BTTS_NO reste exclu.",
            "- UNDER_1_5 reste exclu.",
            "- O/U 2.5 reste exclu.",
            "- V17.7 ne remplace pas le scoring explicable V1.",
            "- V17.7 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.7 sélecteur multi-marchés avec BTTS : réalisée si les fichiers 268 à 273 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_multimarket_v17_7_selector_with_btts.py et reports/evidence/ml_training/268-273.",
        ]
    )
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Orchestre V17.7 sans modifier RubyBets produit.
def main() -> None:
    print("Chargement de V17.0 référence et reconstruction BTTS V17.6 pour V17.7...")
    v17_6_module = load_module("rubybets_v17_6_btts_ultra", "train_goals_v17_6_btts_ultra_selective.py")
    project_root = v17_6_module.find_project_root()
    evidence_dir = v17_6_module.get_evidence_dir(project_root)

    v17_reference = load_v17_reference_predictions(evidence_dir)
    if v17_reference is None:
        print("Fichier 228 introuvable ou incomplet : reconstruction de V17.0 depuis les scripts V13.1/V15...")
        v17_module = load_module("rubybets_v17_controlled", "train_multimarket_v17_selector_controlled.py")
        v17_reference = rebuild_v17_reference_predictions(project_root, v17_module)
    else:
        print("Référence V17.0 chargée depuis 228_multimarket_v17_selector_results.csv.")

    print("Reconstruction rapide du signal BTTS V17.6 retenu, sans relancer les 864 000 combinaisons...")
    btts_predictions, btts_strategy_name = build_v17_6_btts_predictions(project_root, v17_6_module)

    print("Application du sélecteur V17.7 : V17.0 puis BTTS_YES ultra-sélectif en fallback...")
    merged = merge_v17_and_btts(v17_reference, btts_predictions)
    v17_7_predictions = apply_v17_7_selector(merged)
    metrics = compute_v17_7_metrics(v17_7_predictions)
    by_market = build_by_market(v17_7_predictions)
    by_league_season = build_by_league_season(v17_7_predictions)
    error_patterns = build_error_patterns(v17_7_predictions)
    results_table = build_results_table(v17_7_predictions, metrics)
    status, blockers, warnings_list = determine_status(metrics, by_league_season)

    write_summary(evidence_dir / OUTPUT_SUMMARY, metrics, status, blockers, warnings_list, by_league_season, btts_strategy_name)
    build_predictions_export(v17_7_predictions).to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_market.to_csv(evidence_dir / OUTPUT_BY_MARKET, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")
    write_decision(evidence_dir / OUTPUT_DECISION, metrics, status, blockers, warnings_list)

    print("OK - Expérience V17.7 multi-market selector avec BTTS terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {metrics.get('strategy')}")
    print(f"BTTS strategy used: {btts_strategy_name}")
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
    print(f"BTTS rows: {metrics.get('btts_rows')}")
    print(f"BTTS accuracy: {metrics.get('btts_accuracy')}")
    print(f"Added BTTS_YES rows vs V17.0: {metrics.get('added_btts_yes_rows')}")
    print(f"Added BTTS_YES accuracy: {metrics.get('added_btts_yes_accuracy')}")
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
# train_multimarket_v17_7_selector_with_btts.py
#   -> réutilise reports/evidence/ml_training/228_multimarket_v17_selector_results.csv si disponible
#   -> réutilise backend/scripts/ml/train_multimarket_v17_selector_controlled.py si la référence V17.0 doit être reconstruite
#   -> réutilise backend/scripts/ml/train_goals_v17_6_btts_ultra_selective.py pour reconstruire le signal BTTS V17.6 retenu
#   -> lit data/ml/raw/*.csv en lecture seule via les scripts réutilisés
#   -> écrit reports/evidence/ml_training/268 à 273
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
