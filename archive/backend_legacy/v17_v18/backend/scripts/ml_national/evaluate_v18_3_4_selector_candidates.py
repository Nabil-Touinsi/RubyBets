# Role du fichier :
# Ce script compare des variantes experimentales V18.3.4 du selecteur national.
# Il ne reentraine aucun modele : il rejoue seulement differents seuils sur le CSV historique V18.3.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PREDICTIONS_FILENAME = "348_v18_3_global_multimarket_test_predictions.csv"
SUMMARY_FILENAME = "372_v18_3_4_selector_candidates_summary.txt"
COMPARISON_FILENAME = "373_v18_3_4_selector_candidates_comparison.csv"
BEST_RESULTS_FILENAME = "374_v18_3_4_selector_best_candidate_results.csv"
BREAKDOWN_FILENAME = "375_v18_3_4_selector_best_candidate_breakdown.csv"
DECISION_FILENAME = "376_v18_3_4_selector_candidates_decision.txt"

REFERENCE_RELIABILITY_FLOOR = 0.89
MIN_COVERAGE_GAIN = 0.05
MAX_RELIABILITY_LOSS = 0.012


@dataclass(frozen=True)
class SelectorCandidateConfig:
    name: str
    strict_1x2_min_confidence: float
    over_1_5_yes_min_confidence: float
    over_2_5_min_confidence: float
    btts_no_min_confidence: float
    double_chance_max_excluded_probability: float
    priority: tuple[str, ...]


# Retrouve la racine du projet RubyBets depuis l'emplacement du script.
def find_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for candidate in [current_path.parent, *current_path.parents, Path.cwd()]:
        if (candidate / "backend").exists() and (candidate / "reports").exists():
            return candidate.resolve()

    return Path.cwd().resolve()


# Construit les chemins d'entree et de sortie de l'evaluation.
def build_paths(project_root: Path) -> dict[str, Path]:
    evidence_dir = project_root / "reports" / "evidence" / "ml_training"
    return {
        "evidence_dir": evidence_dir,
        "predictions_csv": evidence_dir / PREDICTIONS_FILENAME,
        "summary_txt": evidence_dir / SUMMARY_FILENAME,
        "comparison_csv": evidence_dir / COMPARISON_FILENAME,
        "best_results_csv": evidence_dir / BEST_RESULTS_FILENAME,
        "breakdown_csv": evidence_dir / BREAKDOWN_FILENAME,
        "decision_txt": evidence_dir / DECISION_FILENAME,
    }


# Charge le CSV historique V18.3 contenant les predictions multi-marches deja calculees.
def load_predictions(predictions_csv: Path) -> pd.DataFrame:
    if not predictions_csv.exists():
        raise FileNotFoundError(
            "Fichier de predictions introuvable : "
            f"{predictions_csv}\n"
            "Relancer d'abord la generation V18.3 globale si ce fichier manque."
        )

    df = pd.read_csv(predictions_csv)
    required_columns = [
        "clean_match_id",
        "match_date_utc",
        "season",
        "competition_code",
        "competition_name",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_1x2",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "1x2_prediction",
        "1x2_prob_TEAM_A_WIN",
        "1x2_prob_DRAW",
        "1x2_prob_TEAM_B_WIN",
        "1x2_max_probability",
        "over_1_5_prediction",
        "over_1_5_prob_YES",
        "over_1_5_max_probability",
        "over_2_5_prediction",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_prob_NO",
        "btts_max_probability",
    ]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError("Colonnes manquantes : " + ", ".join(missing_columns))

    return df


# Cree les variantes V18.3.4 a comparer sans toucher a V18.3.3.
def build_candidate_configs() -> list[SelectorCandidateConfig]:
    base_priority = (
        "STRICT_1X2",
        "OVER_1_5",
        "OVER_2_5",
        "BTTS",
        "DOUBLE_CHANCE",
    )
    return [
        SelectorCandidateConfig(
            name="v18_3_3_reference_dc015",
            strict_1x2_min_confidence=0.76,
            over_1_5_yes_min_confidence=0.78,
            over_2_5_min_confidence=0.70,
            btts_no_min_confidence=0.75,
            double_chance_max_excluded_probability=0.15,
            priority=base_priority,
        ),
        SelectorCandidateConfig(
            name="v18_3_4_candidate_dc018",
            strict_1x2_min_confidence=0.76,
            over_1_5_yes_min_confidence=0.78,
            over_2_5_min_confidence=0.70,
            btts_no_min_confidence=0.75,
            double_chance_max_excluded_probability=0.18,
            priority=base_priority,
        ),
        SelectorCandidateConfig(
            name="v18_3_4_candidate_dc020",
            strict_1x2_min_confidence=0.76,
            over_1_5_yes_min_confidence=0.78,
            over_2_5_min_confidence=0.70,
            btts_no_min_confidence=0.75,
            double_chance_max_excluded_probability=0.20,
            priority=base_priority,
        ),
        SelectorCandidateConfig(
            name="v18_3_4_candidate_dc022",
            strict_1x2_min_confidence=0.76,
            over_1_5_yes_min_confidence=0.78,
            over_2_5_min_confidence=0.70,
            btts_no_min_confidence=0.75,
            double_chance_max_excluded_probability=0.22,
            priority=base_priority,
        ),
    ]


# Prepare les tableaux utilises pour evaluer rapidement toutes les variantes.
def prepare_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    one_x_two_probabilities = np.vstack(
        [
            df["1x2_prob_TEAM_A_WIN"].to_numpy(dtype=float),
            df["1x2_prob_DRAW"].to_numpy(dtype=float),
            df["1x2_prob_TEAM_B_WIN"].to_numpy(dtype=float),
        ]
    ).T
    labels = np.array(["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"], dtype=object)
    excluded_index = np.argmin(one_x_two_probabilities, axis=1)
    excluded_outcome = labels[excluded_index]
    excluded_probability = one_x_two_probabilities[np.arange(len(df)), excluded_index]
    double_chance_prediction = np.where(
        excluded_outcome == "TEAM_A_WIN",
        "DRAW_OR_TEAM_B",
        np.where(
            excluded_outcome == "DRAW",
            "TEAM_A_OR_TEAM_B",
            "TEAM_A_OR_DRAW",
        ),
    )

    return {
        "target_1x2": df["target_1x2"].to_numpy(dtype=object),
        "target_over_1_5": df["target_over_1_5"].to_numpy(dtype=object),
        "target_over_2_5": df["target_over_2_5"].to_numpy(dtype=object),
        "target_btts": df["target_btts"].to_numpy(dtype=object),
        "1x2_prediction": df["1x2_prediction"].to_numpy(dtype=object),
        "1x2_max_probability": df["1x2_max_probability"].to_numpy(dtype=float),
        "over_1_5_prediction": df["over_1_5_prediction"].to_numpy(dtype=object),
        "over_1_5_prob_YES": df["over_1_5_prob_YES"].to_numpy(dtype=float),
        "over_2_5_prediction": df["over_2_5_prediction"].to_numpy(dtype=object),
        "over_2_5_max_probability": df["over_2_5_max_probability"].to_numpy(dtype=float),
        "btts_prediction": df["btts_prediction"].to_numpy(dtype=object),
        "btts_prob_NO": df["btts_prob_NO"].to_numpy(dtype=float),
        "double_chance_prediction": double_chance_prediction.astype(object),
        "double_chance_excluded_outcome": excluded_outcome.astype(object),
        "double_chance_excluded_probability": excluded_probability.astype(float),
        "double_chance_confidence": (1.0 - excluded_probability).astype(float),
    }


# Convertit une confiance numerique en niveau de risque lisible.
def compute_risk_level(confidence: float | None) -> str:
    if confidence is None or pd.isna(confidence):
        return "none"
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Applique une variante de selecteur aux predictions historiques.
def evaluate_config(arrays: dict[str, np.ndarray], config: SelectorCandidateConfig) -> dict[str, np.ndarray]:
    row_count = len(arrays["target_1x2"])
    selected_market = np.full(row_count, "ABSTAIN", dtype=object)
    selected_prediction = np.full(row_count, "ABSTAIN", dtype=object)
    selected_confidence = np.full(row_count, np.nan, dtype=float)
    actual_value = np.full(row_count, "", dtype=object)
    is_correct = np.full(row_count, False, dtype=bool)
    selector_rule = np.full(
        row_count,
        "Aucun signal ne respecte les seuils experimentaux.",
        dtype=object,
    )

    strict_valid = (
        (arrays["1x2_prediction"] != "DRAW")
        & (arrays["1x2_max_probability"] >= config.strict_1x2_min_confidence)
    )
    over_1_5_valid = (
        (arrays["over_1_5_prediction"] == "YES")
        & (arrays["over_1_5_prob_YES"] >= config.over_1_5_yes_min_confidence)
    )
    over_2_5_valid = arrays["over_2_5_max_probability"] >= config.over_2_5_min_confidence
    btts_valid = (
        (arrays["btts_prediction"] == "NO")
        & (arrays["btts_prob_NO"] >= config.btts_no_min_confidence)
    )
    double_chance_valid = (
        arrays["double_chance_excluded_probability"]
        <= config.double_chance_max_excluded_probability
    )

    market_definitions = {
        "STRICT_1X2": {
            "valid": strict_valid,
            "prediction": arrays["1x2_prediction"],
            "confidence": arrays["1x2_max_probability"],
            "actual": arrays["target_1x2"],
            "correct": arrays["1x2_prediction"] == arrays["target_1x2"],
            "rule": f"1X2 non-DRAW avec confiance >= {config.strict_1x2_min_confidence}",
        },
        "OVER_1_5": {
            "valid": over_1_5_valid,
            "prediction": np.full(row_count, "YES", dtype=object),
            "confidence": arrays["over_1_5_prob_YES"],
            "actual": arrays["target_over_1_5"],
            "correct": arrays["target_over_1_5"] == "YES",
            "rule": f"OVER_1_5 YES avec confiance >= {config.over_1_5_yes_min_confidence}",
        },
        "OVER_2_5": {
            "valid": over_2_5_valid,
            "prediction": arrays["over_2_5_prediction"],
            "confidence": arrays["over_2_5_max_probability"],
            "actual": arrays["target_over_2_5"],
            "correct": arrays["over_2_5_prediction"] == arrays["target_over_2_5"],
            "rule": f"OVER_2_5 avec confiance >= {config.over_2_5_min_confidence}",
        },
        "BTTS": {
            "valid": btts_valid,
            "prediction": np.full(row_count, "NO", dtype=object),
            "confidence": arrays["btts_prob_NO"],
            "actual": arrays["target_btts"],
            "correct": arrays["target_btts"] == "NO",
            "rule": f"BTTS NO avec confiance >= {config.btts_no_min_confidence}",
        },
        "DOUBLE_CHANCE": {
            "valid": double_chance_valid,
            "prediction": arrays["double_chance_prediction"],
            "confidence": arrays["double_chance_confidence"],
            "actual": arrays["target_1x2"],
            "correct": arrays["target_1x2"] != arrays["double_chance_excluded_outcome"],
            "rule": (
                "DOUBLE_CHANCE si probabilite de l'issue exclue <= "
                f"{config.double_chance_max_excluded_probability}"
            ),
        },
    }

    for market in config.priority:
        definition = market_definitions[market]
        select_mask = (selected_market == "ABSTAIN") & definition["valid"]
        selected_market[select_mask] = market
        selected_prediction[select_mask] = definition["prediction"][select_mask]
        selected_confidence[select_mask] = definition["confidence"][select_mask]
        actual_value[select_mask] = definition["actual"][select_mask]
        is_correct[select_mask] = definition["correct"][select_mask]
        selector_rule[select_mask] = definition["rule"]

    selected_mask = selected_market != "ABSTAIN"
    is_correct = is_correct & selected_mask

    return {
        "selected_market": selected_market,
        "selected_prediction": selected_prediction,
        "selected_confidence": selected_confidence,
        "actual_value": actual_value,
        "is_correct": is_correct,
        "selector_rule": selector_rule,
    }


# Calcule les indicateurs principaux pour une variante testee.
def compute_metrics(result: dict[str, np.ndarray], config: SelectorCandidateConfig) -> dict[str, Any]:
    selected_market = result["selected_market"]
    selected_confidence = result["selected_confidence"]
    is_correct = result["is_correct"]
    total_rows = len(selected_market)
    selected_mask = selected_market != "ABSTAIN"
    selected_rows = int(selected_mask.sum())
    abstain_rows = total_rows - selected_rows
    double_chance_rows = int((selected_market == "DOUBLE_CHANCE").sum())
    strict_1x2_rows = int((selected_market == "STRICT_1X2").sum())
    over_1_5_rows = int((selected_market == "OVER_1_5").sum())
    over_2_5_rows = int((selected_market == "OVER_2_5").sum())
    btts_rows = int((selected_market == "BTTS").sum())

    reliability = float(is_correct[selected_mask].mean()) if selected_rows else 0.0
    coverage = selected_rows / total_rows if total_rows else 0.0
    abstention_rate = abstain_rows / total_rows if total_rows else 0.0
    avg_confidence = float(np.nanmean(selected_confidence[selected_mask])) if selected_rows else 0.0
    double_chance_share = double_chance_rows / selected_rows if selected_rows else 0.0

    return {
        "selector_variant": config.name,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstain_rows": abstain_rows,
        "coverage": round(coverage, 6),
        "abstention_rate": round(abstention_rate, 6),
        "reliability": round(reliability, 6),
        "avg_confidence": round(avg_confidence, 6),
        "strict_1x2_rows": strict_1x2_rows,
        "over_1_5_rows": over_1_5_rows,
        "over_2_5_rows": over_2_5_rows,
        "btts_rows": btts_rows,
        "double_chance_rows": double_chance_rows,
        "double_chance_share_selected": round(double_chance_share, 6),
        "strict_1x2_min_confidence": config.strict_1x2_min_confidence,
        "over_1_5_yes_min_confidence": config.over_1_5_yes_min_confidence,
        "over_2_5_min_confidence": config.over_2_5_min_confidence,
        "btts_no_min_confidence": config.btts_no_min_confidence,
        "double_chance_max_excluded_probability": config.double_chance_max_excluded_probability,
        "priority": " > ".join(config.priority),
    }


# Construit un CSV detaille pour la meilleure variante candidate.
def build_detailed_results(
    df: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    result: dict[str, np.ndarray],
    config: SelectorCandidateConfig,
) -> pd.DataFrame:
    base_columns = [
        "clean_match_id",
        "match_date_utc",
        "season",
        "competition_code",
        "competition_name",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_1x2",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "1x2_prediction",
        "1x2_max_probability",
        "over_1_5_prediction",
        "over_1_5_max_probability",
        "over_2_5_prediction",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_max_probability",
    ]
    available_columns = [column for column in base_columns if column in df.columns]
    result_df = df[available_columns].copy().reset_index(drop=True)
    result_df.insert(0, "selector_variant", config.name)
    result_df["selected_market"] = result["selected_market"]
    result_df["selected_prediction"] = result["selected_prediction"]
    result_df["selected_confidence"] = np.round(result["selected_confidence"], 6)
    result_df["risk_level"] = [compute_risk_level(value) for value in result["selected_confidence"]]
    result_df["actual_value"] = result["actual_value"]
    result_df["is_correct"] = np.where(result["selected_market"] == "ABSTAIN", None, result["is_correct"])
    result_df["selector_rule"] = result["selector_rule"]
    result_df["excluded_outcome"] = arrays["double_chance_excluded_outcome"]
    result_df["excluded_probability"] = np.round(arrays["double_chance_excluded_probability"], 6)
    return result_df


# Resume la performance de la meilleure variante par marche selectionne.
def build_market_breakdown(results_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total_rows = len(results_df)
    selected_total = int((results_df["selected_market"] != "ABSTAIN").sum())

    for market in ["STRICT_1X2", "OVER_1_5", "OVER_2_5", "BTTS", "DOUBLE_CHANCE", "ABSTAIN"]:
        market_df = results_df[results_df["selected_market"] == market]
        rows_count = len(market_df)
        selected_market_df = market_df[market_df["selected_market"] != "ABSTAIN"]
        correct_values = selected_market_df["is_correct"].dropna()
        reliability = float(correct_values.mean()) if len(correct_values) else None
        rows.append(
            {
                "selected_market": market,
                "rows": rows_count,
                "share_total": round(rows_count / total_rows, 6) if total_rows else 0.0,
                "share_selected": round(rows_count / selected_total, 6) if selected_total and market != "ABSTAIN" else None,
                "reliability": round(reliability, 6) if reliability is not None else None,
            }
        )

    return pd.DataFrame(rows)


# Choisit le meilleur candidat en gardant V18.3.3 comme reference de prudence.
def choose_best_candidate(comparison_df: pd.DataFrame) -> tuple[str, str]:
    reference_row = comparison_df[comparison_df["selector_variant"] == "v18_3_3_reference_dc015"].iloc[0]
    reference_reliability = float(reference_row["reliability"])
    reference_coverage = float(reference_row["coverage"])

    candidates = comparison_df[
        comparison_df["selector_variant"] != "v18_3_3_reference_dc015"
    ].copy()
    candidates["coverage_gain"] = candidates["coverage"] - reference_coverage
    candidates["reliability_loss"] = reference_reliability - candidates["reliability"]
    candidates["accepted"] = (
        (candidates["reliability"] >= REFERENCE_RELIABILITY_FLOOR)
        & (candidates["coverage_gain"] >= MIN_COVERAGE_GAIN)
        & (candidates["reliability_loss"] <= MAX_RELIABILITY_LOSS)
    )

    accepted_candidates = candidates[candidates["accepted"] == True].copy()
    if accepted_candidates.empty:
        fallback = candidates.sort_values(
            by=["reliability", "coverage"],
            ascending=False,
        ).iloc[0]
        return (
            str(fallback["selector_variant"]),
            "Aucune variante ne respecte tous les garde-fous. "
            "La variante indiquee est seulement la meilleure piste a analyser, pas une decision produit.",
        )

    best = accepted_candidates.sort_values(
        by=["coverage", "reliability"],
        ascending=False,
    ).iloc[0]
    return (
        str(best["selector_variant"]),
        "Variante candidate acceptee par les garde-fous experimentaux. "
        "Elle reste a valider sur l'audit dynamique WC avant integration produit.",
    )


# Ecrit les fichiers de synthese et de decision pour la trace RNCP.
def write_text_outputs(
    paths: dict[str, Path],
    comparison_df: pd.DataFrame,
    best_variant: str,
    decision_note: str,
) -> None:
    reference = comparison_df[comparison_df["selector_variant"] == "v18_3_3_reference_dc015"].iloc[0]
    best = comparison_df[comparison_df["selector_variant"] == best_variant].iloc[0]

    summary_lines = [
        "Evaluation V18.3.4 - candidats de reduction d'abstention",
        "========================================================",
        f"CSV historique analyse : {paths['predictions_csv']}",
        f"Lignes historiques : {int(reference['total_rows'])}",
        "",
        "Reference V18.3.3 :",
        f"- coverage : {reference['coverage']}",
        f"- reliability : {reference['reliability']}",
        f"- abstention_rate : {reference['abstention_rate']}",
        f"- double_chance_rows : {int(reference['double_chance_rows'])}",
        "",
        "Meilleur candidat retenu pour analyse :",
        f"- selector_variant : {best_variant}",
        f"- coverage : {best['coverage']}",
        f"- reliability : {best['reliability']}",
        f"- abstention_rate : {best['abstention_rate']}",
        f"- double_chance_rows : {int(best['double_chance_rows'])}",
        f"- double_chance_share_selected : {best['double_chance_share_selected']}",
        "",
        "Decision :",
        decision_note,
        "",
        f"Comparaison CSV : {paths['comparison_csv']}",
        f"Resultats detailles meilleur candidat : {paths['best_results_csv']}",
        f"Breakdown meilleur candidat : {paths['breakdown_csv']}",
    ]

    decision_lines = [
        "Decision V18.3.4 - reduction d'abstention",
        "=========================================",
        f"Best variant analyse : {best_variant}",
        decision_note,
        "",
        "Regle de prudence : ne pas remplacer V18.3.3 directement.",
        "La variante V18.3.4 doit rester experimentale tant qu'elle n'est pas testee sur les matchs dynamiques WC actuels.",
        "Aucune garantie de resultat sportif ne doit etre formulee.",
    ]

    paths["summary_txt"].write_text("\n".join(summary_lines), encoding="utf-8")
    paths["decision_txt"].write_text("\n".join(decision_lines), encoding="utf-8")


# Execute toute l'evaluation V18.3.4 et genere les preuves CSV/TXT.
def main() -> None:
    project_root = find_project_root()
    paths = build_paths(project_root)
    paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    predictions_df = load_predictions(paths["predictions_csv"])
    arrays = prepare_arrays(predictions_df)
    configs = build_candidate_configs()

    metrics_rows: list[dict[str, Any]] = []
    detailed_results_by_variant: dict[str, pd.DataFrame] = {}

    for config in configs:
        result = evaluate_config(arrays, config)
        metrics_rows.append(compute_metrics(result, config))
        detailed_results_by_variant[config.name] = build_detailed_results(
            predictions_df,
            arrays,
            result,
            config,
        )

    comparison_df = pd.DataFrame(metrics_rows)
    comparison_df.to_csv(paths["comparison_csv"], index=False, encoding="utf-8")

    best_variant, decision_note = choose_best_candidate(comparison_df)
    best_results_df = detailed_results_by_variant[best_variant]
    best_results_df.to_csv(paths["best_results_csv"], index=False, encoding="utf-8")

    breakdown_df = build_market_breakdown(best_results_df)
    breakdown_df.to_csv(paths["breakdown_csv"], index=False, encoding="utf-8")

    write_text_outputs(paths, comparison_df, best_variant, decision_note)

    print("OK - Evaluation V18.3.4 candidats terminee.")
    print(f"Configurations testees : {len(configs)}")
    print(f"Best variant analyse : {best_variant}")
    print(f"Summary saved: {paths['summary_txt']}")
    print(f"Comparison CSV saved: {paths['comparison_csv']}")
    print(f"Best results CSV saved: {paths['best_results_csv']}")
    print(f"Breakdown CSV saved: {paths['breakdown_csv']}")
    print(f"Decision saved: {paths['decision_txt']}")


if __name__ == "__main__":
    main()


# Schema de communication :
# evaluate_v18_3_4_selector_candidates.py
#   -> lit reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv
#   -> rejoue les seuils V18.3.3 et les candidats V18.3.4 sans reentrainer de modele
#   -> genere les preuves 372/373/374/375/376 dans reports/evidence/ml_training/
#   -> alimente la decision avant toute integration backend/frontend
