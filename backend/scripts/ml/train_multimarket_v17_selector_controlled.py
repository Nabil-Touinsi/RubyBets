# Rôle du fichier : tester V17 multi-market selector contrôlé, en combinant V13.1 1X2/double chance avec le signal OVER_1_5 V15, sans intégrer le résultat au produit.

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

OUTPUT_SUMMARY = "227_multimarket_v17_selector_summary.txt"
OUTPUT_RESULTS = "228_multimarket_v17_selector_results.csv"
OUTPUT_BY_MARKET = "229_multimarket_v17_selector_by_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "230_multimarket_v17_selector_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "231_multimarket_v17_selector_error_patterns.csv"
OUTPUT_DECISION = "232_multimarket_v17_selector_decision.txt"

V13_STRATEGY_NAME = "v13_mixed_sp080_sm010_top2076_ent107_trip1_agr000"
V15_STRATEGY_NAME = "v15_ou15_labels_ot080_ut050_mh10_ognone_ugnone"
V17_STRATEGY_NAME = "v17_controlled_v13_mixed_plus_over15_only"
V17_UNSAFE_STRATEGY_NAME = "v17_warning_v13_mixed_plus_over15_under15"

STRONG_MIN_ACCURACY = 0.82
STRONG_MIN_COVERAGE = 0.70
STRONG_MIN_SELECTED_ROWS = 3500
STRONG_MIN_MAJOR_SEGMENT_ACCURACY = 0.75
REVIEW_MIN_ACCURACY = 0.78
REVIEW_MIN_COVERAGE = 0.55
REVIEW_MIN_SELECTED_ROWS = 2800
LOW_VOLUME_SEGMENT_ROWS = 80

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


# Charge un script Python voisin comme module réutilisable.
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


# Arrondit une valeur numérique pour stabiliser les exports.
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


# Crée une clé stable pour relier les sorties V13.1 et V15 sur les mêmes matchs.
def build_join_key(dataframe: pd.DataFrame, columns: list[str]) -> pd.Series:
    output = dataframe[columns].astype(str).fillna("")
    return output.apply(lambda row: "|".join(row.values.tolist()), axis=1)


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


# Reconstruit les signaux V15 Over/Under 1.5 à partir des scores et features rolling en mémoire.
def build_v15_predictions(project_root: Path, v15_module: ModuleType) -> pd.DataFrame:
    dataset, _ = v15_module.build_v15_dataset(project_root)
    test = dataset[dataset["season"].astype(str).isin(v15_module.TEST_SEASONS)].copy()

    policy = v15_module.V15Policy(
        over_rate_threshold=0.80,
        under_rate_threshold=0.50,
        min_history_count=10,
        min_over_goals_avg=None,
        max_under_goals_avg=None,
    )
    predictions = v15_module.apply_policy(test, policy).copy()
    predictions["join_key"] = build_join_key(predictions, ["league_code", "season", "match_date", "home_team", "away_team"])
    return predictions


# Fusionne les prédictions V13.1 et V15 sur le périmètre de test final.
def merge_candidate_predictions(v13_predictions: pd.DataFrame, v15_predictions: pd.DataFrame) -> pd.DataFrame:
    v15_keep_columns = [
        "join_key",
        "target_over_under_15",
        "total_goals",
        "v15_recommendation_status",
        "v15_recommendation",
        "v15_is_correct",
        "v15_signal_strength",
        "combined_over_15_rate_last10",
        "combined_total_goals_avg_last10",
        "combined_over_25_rate_last10",
        "combined_btts_rate_last10",
        "min_history_count_last10",
    ]
    available_v15_columns = [column for column in v15_keep_columns if column in v15_predictions.columns]
    merged = v13_predictions.merge(v15_predictions[available_v15_columns], on="join_key", how="left")

    if merged["v15_recommendation_status"].isna().any():
        missing_count = int(merged["v15_recommendation_status"].isna().sum())
        raise RuntimeError(f"Fusion V13/V15 incomplète : {missing_count} match(s) sans signal V15.")
    return merged


# Applique le sélecteur V17 contrôlé : V13.1 d'abord, puis seulement OVER_1_5 V15 si V13.1 s'abstient.
def apply_v17_controlled_selector(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()

    v13_selected = output["v13_mixed_recommendation_status"] == RECOMMEND_STATUS
    v15_over_selected = (
        (output["v15_recommendation_status"] == RECOMMEND_STATUS)
        & (output["v15_recommendation"] == OVER_15_VALUE)
    )
    add_over_15 = (~v13_selected) & v15_over_selected
    selected = v13_selected | add_over_15

    output["v17_strategy"] = V17_STRATEGY_NAME
    output["v17_recommendation_status"] = np.where(selected, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_recommendation_type"] = "ABSTAIN"
    output.loc[v13_selected, "v17_recommendation_type"] = output.loc[
        v13_selected, "v13_mixed_recommendation_type"
    ]
    output.loc[add_over_15, "v17_recommendation_type"] = GOALS_OVER_15_TYPE

    output["v17_recommendation_value"] = "ABSTAIN"
    output.loc[v13_selected, "v17_recommendation_value"] = output.loc[
        v13_selected, "v13_mixed_recommendation_value"
    ]
    output.loc[add_over_15, "v17_recommendation_value"] = OVER_15_VALUE

    output["v17_source"] = "ABSTAIN"
    output.loc[v13_selected, "v17_source"] = "V13_1_MIXED"
    output.loc[add_over_15, "v17_source"] = "V15_OVER_1_5_ONLY"

    output["v17_is_correct"] = False
    output.loc[v13_selected, "v17_is_correct"] = output.loc[v13_selected, "v13_mixed_is_correct"].astype(bool)
    output.loc[add_over_15, "v17_is_correct"] = output.loc[add_over_15, "v15_is_correct"].astype(bool)

    output["v17_is_added_over_15"] = add_over_15
    output["v17_excluded_reason"] = ""
    output.loc[(~v13_selected) & (output["v15_recommendation"] == "UNDER_1_5"), "v17_excluded_reason"] = (
        "UNDER_1_5_EXCLUDED_LOW_ACCURACY_IN_V15"
    )
    return output


# Calcule une variante volontairement non retenue qui ajoute aussi UNDER_1_5 pour prouver le risque.
def compute_unsafe_under_variant(dataframe: pd.DataFrame) -> dict[str, object]:
    v13_selected = dataframe["v13_mixed_recommendation_status"] == RECOMMEND_STATUS
    v15_selected = dataframe["v15_recommendation_status"] == RECOMMEND_STATUS
    v15_additional = (~v13_selected) & v15_selected
    selected = v13_selected | v15_additional

    correct = pd.Series(False, index=dataframe.index)
    correct.loc[v13_selected] = dataframe.loc[v13_selected, "v13_mixed_is_correct"].astype(bool)
    correct.loc[v15_additional] = dataframe.loc[v15_additional, "v15_is_correct"].astype(bool)

    under_added = v15_additional & (dataframe["v15_recommendation"] == "UNDER_1_5")
    return {
        "strategy": V17_UNSAFE_STRATEGY_NAME,
        "selected_rows": int(selected.sum()),
        "coverage": rounded(safe_rate(int(selected.sum()), len(dataframe))),
        "accuracy": rounded(safe_rate(int(correct.loc[selected].sum()), int(selected.sum()))),
        "added_under_15_rows": int(under_added.sum()),
        "added_under_15_accuracy": rounded(
            safe_rate(int(dataframe.loc[under_added, "v15_is_correct"].astype(bool).sum()), int(under_added.sum()))
        ),
        "decision": "REJECTED_VARIANT",
    }


# Calcule les métriques principales du sélecteur V17.
def compute_v17_metrics(predictions: pd.DataFrame) -> dict[str, object]:
    selected = predictions[predictions["v17_recommendation_status"] == RECOMMEND_STATUS]
    total_rows = len(predictions)
    selected_rows = len(selected)

    strict = selected[selected["v17_recommendation_type"] == STRICT_TYPE]
    double = selected[selected["v17_recommendation_type"] == DOUBLE_CHANCE_TYPE]
    over_15 = selected[selected["v17_recommendation_type"] == GOALS_OVER_15_TYPE]

    return {
        "strategy": V17_STRATEGY_NAME,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "accuracy": rounded(safe_rate(int(selected["v17_is_correct"].sum()), selected_rows)),
        "correct_rows": int(selected["v17_is_correct"].sum()),
        "strict_1x2_rows": len(strict),
        "strict_1x2_accuracy": rounded(safe_rate(int(strict["v17_is_correct"].sum()), len(strict))),
        "double_chance_rows": len(double),
        "double_chance_accuracy": rounded(safe_rate(int(double["v17_is_correct"].sum()), len(double))),
        "over_15_rows": len(over_15),
        "over_15_accuracy": rounded(safe_rate(int(over_15["v17_is_correct"].sum()), len(over_15))),
        "added_over_15_rows": int(predictions["v17_is_added_over_15"].sum()),
        "added_over_15_accuracy": rounded(
            safe_rate(
                int(predictions.loc[predictions["v17_is_added_over_15"], "v17_is_correct"].sum()),
                int(predictions["v17_is_added_over_15"].sum()),
            )
        ),
        "selected_rows_delta_vs_v13_1": selected_rows - int((predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS).sum()),
        "coverage_delta_vs_v13_1": rounded(
            safe_rate(selected_rows, total_rows)
            - safe_rate(int((predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS).sum()), total_rows)
        ),
    }


# Construit le tableau de comparaison des stratégies V13.1, V17 contrôlée et variante rejetée.
def build_results_table(predictions: pd.DataFrame, unsafe_variant: dict[str, object]) -> pd.DataFrame:
    v13_selected = predictions[predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS]
    v17_metrics = compute_v17_metrics(predictions)

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
            "decision": "REFERENCE_CURRENT_BEST",
        },
        {
            "strategy": V17_STRATEGY_NAME,
            "scope": "test_final",
            "accuracy": v17_metrics["accuracy"],
            "coverage": v17_metrics["coverage"],
            "selected_rows": v17_metrics["selected_rows"],
            "strict_1x2_rows": v17_metrics["strict_1x2_rows"],
            "double_chance_rows": v17_metrics["double_chance_rows"],
            "over_15_rows": v17_metrics["over_15_rows"],
            "decision": "SELECTED_CONTROLLED_VARIANT",
        },
        {
            "strategy": unsafe_variant["strategy"],
            "scope": "test_warning",
            "accuracy": unsafe_variant["accuracy"],
            "coverage": unsafe_variant["coverage"],
            "selected_rows": unsafe_variant["selected_rows"],
            "strict_1x2_rows": v17_metrics["strict_1x2_rows"],
            "double_chance_rows": v17_metrics["double_chance_rows"],
            "over_15_rows": v17_metrics["over_15_rows"],
            "decision": unsafe_variant["decision"],
        },
    ]
    return pd.DataFrame(rows)


# Agrège les performances V17 par type de marché recommandé.
def build_by_market(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_recommendation_type", "v17_recommendation_value"], dropna=False)

    for (recommendation_type, recommendation_value), group in grouped:
        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_is_correct"].sum()), len(group))),
                "source": ",".join(sorted(group["v17_source"].astype(str).unique())),
                "avg_market_favorite_prob": rounded(group["market_favorite_prob"].mean()) if "market_favorite_prob" in group else 0.0,
                "avg_market_top2_sum": rounded(group["market_top2_sum"].mean()) if "market_top2_sum" in group else 0.0,
                "avg_over_15_rate": rounded(group["combined_over_15_rate_last10"].mean()) if "combined_over_15_rate_last10" in group else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Agrège les performances V17 par ligue et saison pour détecter les segments fragiles.
def build_by_league_season(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["__league_code", "__season"], dropna=False)

    for (league_code, season), group in grouped:
        selected_rows = len(group)
        accuracy = rounded(safe_rate(int(group["v17_is_correct"].sum()), selected_rows))
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
                "strict_1x2_rows": int((group["v17_recommendation_type"] == STRICT_TYPE).sum()),
                "double_chance_rows": int((group["v17_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
                "over_15_rows": int((group["v17_recommendation_type"] == GOALS_OVER_15_TYPE).sum()),
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Exporte un extrait des erreurs V17 pour comprendre les échecs restants.
def build_error_patterns(predictions: pd.DataFrame) -> pd.DataFrame:
    errors = predictions[
        (predictions["v17_recommendation_status"] == RECOMMEND_STATUS)
        & (~predictions["v17_is_correct"])
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
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_source",
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_top2_sum",
        "combined_over_15_rate_last10",
        "combined_total_goals_avg_last10",
    ]
    available_columns = [column for column in keep_columns if column in errors.columns]
    return errors[available_columns].sort_values(["__season", "__league_code", "Date"]).head(600)


# Détermine le statut V17 selon les métriques et les segments majeurs.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame, unsafe_variant: dict[str, object]) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))

    major_fragile_segments = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["selected_rows"] >= LOW_VOLUME_SEGMENT_ROWS]
        major_fragile_segments = len(major_segments[major_segments["accuracy"] < STRONG_MIN_MAJOR_SEGMENT_ACCURACY])

    blockers: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {STRONG_MIN_MAJOR_SEGMENT_ACCURACY}.")
    if int(unsafe_variant.get("added_under_15_rows", 0)) > 0:
        warnings_list.append(
            "La variante qui ajoute UNDER_1_5 est rejetée : son accuracy additionnelle est trop faible."
        )

    if accuracy >= STRONG_MIN_ACCURACY and coverage >= STRONG_MIN_COVERAGE and selected_rows >= STRONG_MIN_SELECTED_ROWS and major_fragile_segments == 0:
        return "V17_MULTI_MARKET_CONTROLLED_STRONG_REVIEW", blockers, warnings_list
    if accuracy >= REVIEW_MIN_ACCURACY and coverage >= REVIEW_MIN_COVERAGE and selected_rows >= REVIEW_MIN_SELECTED_ROWS:
        return "V17_MULTI_MARKET_CONTROLLED_REVIEW", blockers, warnings_list

    blockers.append("Accuracy, couverture ou volume insuffisant pour conserver V17 comme candidat multi-marchés expérimental.")
    return "V17_MULTI_MARKET_CONTROLLED_REJECTED", blockers, warnings_list


# Écrit la synthèse V17 dans le dossier de preuves ML.
def write_summary(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
    by_league_season: pd.DataFrame,
    unsafe_variant: dict[str, object],
) -> None:
    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.sort_values(["accuracy", "selected_rows"], ascending=[True, False]).iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML V17 multi-market selector contrôlé",
        "227 - Synthèse expérience V17",
        "",
        "Objectif :",
        "Tester un sélecteur multi-marchés contrôlé qui combine V13.1 1X2/double chance avec le signal OVER_1_5 V15, sans intégrer les signaux faibles V14 O/U 2.5, V15 UNDER_1_5 ou V16 BTTS.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data via les scripts V13.1 et V15.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Logique du sélecteur :",
        "1. Si V13.1 recommande un 1X2 strict, conserver le 1X2 strict.",
        "2. Sinon, si V13.1 recommande une double chance, conserver 1X / X2 / 12.",
        "3. Sinon, si V15 recommande OVER_1_5, ajouter OVER_1_5 comme complément prudent.",
        "4. Exclure UNDER_1_5, O/U 2.5 et BTTS dans cette version contrôlée.",
        "5. S'abstenir si aucun signal contrôlé n'est disponible.",
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
        f"- Selected rows delta vs V13.1 : {metrics.get('selected_rows_delta_vs_v13_1')}",
        f"- Coverage delta vs V13.1 : {metrics.get('coverage_delta_vs_v13_1')}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        f"- Segments majeurs sous {STRONG_MIN_MAJOR_SEGMENT_ACCURACY} : {len(by_league_season[(by_league_season['selected_rows'] >= LOW_VOLUME_SEGMENT_ROWS) & (by_league_season['accuracy'] < STRONG_MIN_MAJOR_SEGMENT_ACCURACY)]) if not by_league_season.empty else 0}",
        "",
        "Variante rejetée :",
        f"- Strategy : {unsafe_variant.get('strategy')}",
        f"- Selected rows : {unsafe_variant.get('selected_rows')}",
        f"- Accuracy : {unsafe_variant.get('accuracy')}",
        f"- Added UNDER_1_5 rows : {unsafe_variant.get('added_under_15_rows')}",
        f"- Added UNDER_1_5 accuracy : {unsafe_variant.get('added_under_15_accuracy')}",
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
        "Ne pas intégrer V17 au produit à ce stade. V17 est une expérimentation multi-marchés forte, mais le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- V17 multi-market selector contrôlé : réalisée si les fichiers 227 à 232 sont générés.",
        "- Prochaine étape : comparaison finale V13.1 / V14 / V15 / V16 / V17 et décision globale multi-marchés.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision opérationnelle V17.
def write_decision(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17 multi-market selector contrôlé",
        "232 - Décision expérience V17",
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
        f"- Double chance rows : {metrics.get('double_chance_rows')}",
        f"- OVER_1_5 rows : {metrics.get('over_15_rows')}",
        f"- OVER_1_5 accuracy : {metrics.get('over_15_accuracy')}",
        f"- Selected rows delta vs V13.1 : {metrics.get('selected_rows_delta_vs_v13_1')}",
        f"- Coverage delta vs V13.1 : {metrics.get('coverage_delta_vs_v13_1')}",
        "",
        "Gates appliqués :",
        f"- Accuracy >= {STRONG_MIN_ACCURACY}",
        f"- Coverage >= {STRONG_MIN_COVERAGE}",
        f"- Selected rows >= {STRONG_MIN_SELECTED_ROWS}",
        f"- Segment majeur >= {STRONG_MIN_MAJOR_SEGMENT_ACCURACY}",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
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
        "- V17 peut être conservée comme expérimentation multi-marchés contrôlée en STRONG_REVIEW si les gates restent validés.",
        "- V17 ne doit pas intégrer UNDER_1_5, O/U 2.5 ou BTTS tant que leurs signaux restent faibles ou instables.",
        "- V17 ne remplace pas le scoring explicable V1.",
        "- V17 ne doit pas être intégrée au produit sans arbitrage explicite, documentation et validation produit séparée.",
        "",
        "Statut de suivi à mettre à jour :",
        "- V17 multi-market selector contrôlé : réalisée.",
        "- Fichiers concernés : 227, 228, 229, 230, 231, 232.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Prépare les colonnes à exporter dans le CSV de prédictions V17.
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
        "v17_strategy",
        "v17_recommendation_status",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_source",
        "v17_is_correct",
        "v13_mixed_recommendation_type",
        "v13_mixed_recommendation_value",
        "v13_mixed_is_correct",
        "v15_recommendation",
        "v15_is_correct",
        "combined_over_15_rate_last10",
        "combined_total_goals_avg_last10",
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_top2_sum",
    ]
    available_columns = [column for column in columns if column in predictions.columns]
    return predictions[available_columns].copy()


# Orchestre V17 sans modifier RubyBets produit.
def main() -> None:
    print("Reconstruction des signaux V13.1 et V15 pour V17 multi-market selector contrôlé...")
    v13_module = load_module("rubybets_v13_mixed", "train_1x2_v13_mixed_selective.py")
    v15_module = load_module("rubybets_v15_over15", "train_goals_v15_over_under_15_labels_selective.py")

    base_module = v13_module.load_v13_base_module()
    project_root = base_module.find_project_root()
    evidence_dir = base_module.get_evidence_dir(project_root)

    v13_predictions = build_v13_predictions(project_root, v13_module)
    v15_predictions = build_v15_predictions(project_root, v15_module)

    print("Application du sélecteur contrôlé : V13.1 puis OVER_1_5 uniquement...")
    merged = merge_candidate_predictions(v13_predictions, v15_predictions)
    v17_predictions = apply_v17_controlled_selector(merged)
    metrics = compute_v17_metrics(v17_predictions)
    unsafe_variant = compute_unsafe_under_variant(merged)
    by_market = build_by_market(v17_predictions)
    by_league_season = build_by_league_season(v17_predictions)
    error_patterns = build_error_patterns(v17_predictions)
    results_table = build_results_table(v17_predictions, unsafe_variant)
    status, blockers, warnings_list = determine_status(metrics, by_league_season, unsafe_variant)

    build_predictions_export(v17_predictions).to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8")
    by_market.to_csv(evidence_dir / OUTPUT_BY_MARKET, index=False, encoding="utf-8")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8")
    write_summary(evidence_dir / OUTPUT_SUMMARY, metrics, status, blockers, warnings_list, by_league_season, unsafe_variant)
    write_decision(evidence_dir / OUTPUT_DECISION, metrics, status, blockers, warnings_list)

    print("OK - Expérience V17 multi-market selector contrôlé terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {metrics.get('strategy')}")
    print(f"Test accuracy: {metrics.get('accuracy')}")
    print(f"Test coverage: {metrics.get('coverage')}")
    print(f"Test abstention rate: {metrics.get('abstention_rate')}")
    print(f"Selected rows: {metrics.get('selected_rows')}")
    print(f"Strict 1X2 rows: {metrics.get('strict_1x2_rows')}")
    print(f"Double chance rows: {metrics.get('double_chance_rows')}")
    print(f"OVER_1_5 rows: {metrics.get('over_15_rows')}")
    print(f"OVER_1_5 accuracy: {metrics.get('over_15_accuracy')}")
    print(f"Selected rows delta vs V13.1: {metrics.get('selected_rows_delta_vs_v13_1')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By market CSV saved: {evidence_dir / OUTPUT_BY_MARKET}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# train_multimarket_v17_selector_controlled.py
#   -> réutilise backend/scripts/ml/train_1x2_v13_mixed_selective.py
#   -> réutilise backend/scripts/ml/train_goals_v15_over_under_15_labels_selective.py
#   -> lit data/ml/raw/*.csv en lecture seule via les scripts réutilisés
#   -> écrit reports/evidence/ml_training/227 à 232
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
