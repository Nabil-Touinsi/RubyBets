# Role du fichier :
# Ce script evalue le selecteur V18.3 global multi-market de RubyBets.
# Il choisit, pour chaque match de test, entre STRICT_1X2, DOUBLE_CHANCE,
# OVER_1_5, OVER_2_5, BTTS ou ABSTAIN a partir des probabilites deja produites.

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


PREDICTIONS_FILENAME = "348_v18_3_global_multimarket_test_predictions.csv"
SUMMARY_FILENAME = "351_v18_3_global_selector_summary.txt"
RESULTS_FILENAME = "352_v18_3_global_selector_results.csv"
BREAKDOWN_FILENAME = "353_v18_3_global_selector_market_breakdown.csv"

# Seuils conservateurs issus du diagnostic V18.3 349/350.
STRICT_1X2_MIN_CONFIDENCE = 0.80
OVER_1_5_YES_MIN_CONFIDENCE = 0.80
OVER_2_5_MIN_CONFIDENCE = 0.70
BTTS_NO_MIN_CONFIDENCE = 0.70
DOUBLE_CHANCE_MAX_EXCLUDED_PROBABILITY = 0.15

# Ordre volontairement prudent : marche direct tres fiable, marches buts filtres,
# puis double chance si le risque exclu par le 1X2 est suffisamment faible.
SELECTOR_PRIORITY = [
    "STRICT_1X2",
    "OVER_1_5",
    "OVER_2_5",
    "BTTS",
    "DOUBLE_CHANCE",
    "ABSTAIN",
]


# Retrouve la racine du projet RubyBets a partir de l'emplacement du script.
def find_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for candidate in [current_path.parent, *current_path.parents]:
        if (candidate / "backend").exists() and (candidate / "reports").exists():
            return candidate

    return Path.cwd().resolve()


# Construit les chemins d'entree et de sortie utilises par cette evaluation.
def build_paths(project_root: Path) -> Dict[str, Path]:
    evidence_dir = project_root / "reports" / "evidence" / "ml_training"
    return {
        "evidence_dir": evidence_dir,
        "predictions_csv": evidence_dir / PREDICTIONS_FILENAME,
        "summary_txt": evidence_dir / SUMMARY_FILENAME,
        "results_csv": evidence_dir / RESULTS_FILENAME,
        "breakdown_csv": evidence_dir / BREAKDOWN_FILENAME,
    }


# Verifie que le fichier de predictions V18.3 existe avant evaluation.
def validate_input_file(predictions_csv: Path) -> None:
    if not predictions_csv.exists():
        raise FileNotFoundError(
            "Fichier de predictions introuvable : "
            f"{predictions_csv}\n"
            "Relancer d'abord train_v18_3_global_multimarket_models.py."
        )


# Charge les predictions de test produites par l'etape 348.
def load_predictions(predictions_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(predictions_csv)

    required_columns = [
        "clean_match_id",
        "match_date_utc",
        "season",
        "competition_code",
        "team_a_name",
        "team_b_name",
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
        "over_1_5_prob_NO",
        "over_1_5_max_probability",
        "over_2_5_prediction",
        "over_2_5_prob_YES",
        "over_2_5_prob_NO",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_prob_YES",
        "btts_prob_NO",
        "btts_max_probability",
    ]

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le fichier 348 : " + ", ".join(missing_columns)
        )

    return df


# Convertit une confiance numerique en niveau de risque simple et lisible.
def compute_risk_level(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Derive la double chance a partir de la probabilite 1X2 la moins probable.
def derive_double_chance(row: pd.Series) -> Dict[str, Any]:
    probabilities = {
        "TEAM_A_WIN": float(row["1x2_prob_TEAM_A_WIN"]),
        "DRAW": float(row["1x2_prob_DRAW"]),
        "TEAM_B_WIN": float(row["1x2_prob_TEAM_B_WIN"]),
    }

    excluded_outcome = min(probabilities, key=probabilities.get)
    excluded_probability = probabilities[excluded_outcome]
    selected_confidence = 1.0 - excluded_probability

    if excluded_outcome == "TEAM_A_WIN":
        prediction = "DRAW_OR_TEAM_B"
    elif excluded_outcome == "DRAW":
        prediction = "TEAM_A_OR_TEAM_B"
    else:
        prediction = "TEAM_A_OR_DRAW"

    is_correct = row["target_1x2"] != excluded_outcome

    return {
        "prediction": prediction,
        "confidence": selected_confidence,
        "excluded_outcome": excluded_outcome,
        "excluded_probability": excluded_probability,
        "is_correct": bool(is_correct),
    }


# Selectionne le marche final pour une ligne de match selon les regles V18.3.
def select_market_for_row(row: pd.Series) -> Dict[str, Any]:
    if (
        row["1x2_prediction"] != "DRAW"
        and float(row["1x2_max_probability"]) >= STRICT_1X2_MIN_CONFIDENCE
    ):
        confidence = float(row["1x2_max_probability"])
        prediction = row["1x2_prediction"]
        return {
            "selected_market": "STRICT_1X2",
            "selected_prediction": prediction,
            "selected_confidence": confidence,
            "risk_level": compute_risk_level(confidence),
            "actual_value": row["target_1x2"],
            "is_correct": bool(prediction == row["target_1x2"]),
            "selector_rule": "1X2 non-DRAW avec confiance >= 0.80",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if (
        row["over_1_5_prediction"] == "YES"
        and float(row["over_1_5_prob_YES"]) >= OVER_1_5_YES_MIN_CONFIDENCE
    ):
        confidence = float(row["over_1_5_prob_YES"])
        return {
            "selected_market": "OVER_1_5",
            "selected_prediction": "YES",
            "selected_confidence": confidence,
            "risk_level": compute_risk_level(confidence),
            "actual_value": row["target_over_1_5"],
            "is_correct": bool(row["target_over_1_5"] == "YES"),
            "selector_rule": "OVER_1_5 YES uniquement avec confiance >= 0.80",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if float(row["over_2_5_max_probability"]) >= OVER_2_5_MIN_CONFIDENCE:
        confidence = float(row["over_2_5_max_probability"])
        prediction = row["over_2_5_prediction"]
        return {
            "selected_market": "OVER_2_5",
            "selected_prediction": prediction,
            "selected_confidence": confidence,
            "risk_level": compute_risk_level(confidence),
            "actual_value": row["target_over_2_5"],
            "is_correct": bool(prediction == row["target_over_2_5"]),
            "selector_rule": "OVER_2_5 avec confiance >= 0.70",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if (
        row["btts_prediction"] == "NO"
        and float(row["btts_max_probability"]) >= BTTS_NO_MIN_CONFIDENCE
    ):
        confidence = float(row["btts_max_probability"])
        return {
            "selected_market": "BTTS",
            "selected_prediction": "NO",
            "selected_confidence": confidence,
            "risk_level": compute_risk_level(confidence),
            "actual_value": row["target_btts"],
            "is_correct": bool(row["target_btts"] == "NO"),
            "selector_rule": "BTTS NO uniquement avec confiance >= 0.70",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    double_chance = derive_double_chance(row)
    if double_chance["excluded_probability"] <= DOUBLE_CHANCE_MAX_EXCLUDED_PROBABILITY:
        confidence = float(double_chance["confidence"])
        return {
            "selected_market": "DOUBLE_CHANCE",
            "selected_prediction": double_chance["prediction"],
            "selected_confidence": confidence,
            "risk_level": compute_risk_level(confidence),
            "actual_value": row["target_1x2"],
            "is_correct": bool(double_chance["is_correct"]),
            "selector_rule": "Double chance si probabilite de l'issue exclue <= 0.15",
            "excluded_outcome": double_chance["excluded_outcome"],
            "excluded_probability": double_chance["excluded_probability"],
        }

    return {
        "selected_market": "ABSTAIN",
        "selected_prediction": "ABSTAIN",
        "selected_confidence": None,
        "risk_level": "none",
        "actual_value": "",
        "is_correct": None,
        "selector_rule": "Aucun signal ne respecte les seuils V18.3",
        "excluded_outcome": "",
        "excluded_probability": None,
    }


# Applique le selecteur V18.3 a toutes les lignes du test.
def build_selector_results(predictions_df: pd.DataFrame) -> pd.DataFrame:
    selections: List[Dict[str, Any]] = []

    for _, row in predictions_df.iterrows():
        selection = select_market_for_row(row)
        selections.append(selection)

    selection_df = pd.DataFrame(selections)
    result_columns = [
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
    available_result_columns = [column for column in result_columns if column in predictions_df.columns]

    return pd.concat(
        [predictions_df[available_result_columns].reset_index(drop=True), selection_df],
        axis=1,
    )


# Calcule les indicateurs globaux du selecteur.
def compute_global_metrics(results_df: pd.DataFrame) -> Dict[str, Any]:
    total_rows = len(results_df)
    selected_mask = results_df["selected_market"] != "ABSTAIN"
    selected_rows = int(selected_mask.sum())
    abstain_rows = total_rows - selected_rows

    if selected_rows > 0:
        reliability = float(results_df.loc[selected_mask, "is_correct"].astype(bool).mean())
        avg_confidence = float(results_df.loc[selected_mask, "selected_confidence"].mean())
    else:
        reliability = 0.0
        avg_confidence = 0.0

    return {
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstain_rows": abstain_rows,
        "coverage": selected_rows / total_rows if total_rows else 0.0,
        "abstention_rate": abstain_rows / total_rows if total_rows else 0.0,
        "reliability": reliability,
        "avg_confidence": avg_confidence,
    }


# Produit la repartition des marches selectionnes et leur fiabilite.
def compute_market_breakdown(results_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    total_rows = len(results_df)
    selected_total = int((results_df["selected_market"] != "ABSTAIN").sum())

    for market, market_df in results_df.groupby("selected_market", dropna=False):
        market_rows = len(market_df)
        selected_market = market != "ABSTAIN"

        if selected_market and market_rows > 0:
            correct_rows = int(market_df["is_correct"].astype(bool).sum())
            accuracy = correct_rows / market_rows
            avg_confidence = float(market_df["selected_confidence"].mean())
        else:
            correct_rows = 0
            accuracy = None
            avg_confidence = None

        rows.append(
            {
                "selected_market": market,
                "rows": market_rows,
                "share_total": market_rows / total_rows if total_rows else 0.0,
                "share_selected": (
                    market_rows / selected_total
                    if selected_market and selected_total
                    else 0.0
                ),
                "correct_rows": correct_rows,
                "error_rows": market_rows - correct_rows if selected_market else 0,
                "accuracy": accuracy,
                "avg_confidence": avg_confidence,
            }
        )

    breakdown_df = pd.DataFrame(rows)
    breakdown_df = breakdown_df.sort_values(
        by=["selected_market"],
        key=lambda column: column.map(
            {
                "STRICT_1X2": "1",
                "DOUBLE_CHANCE": "2",
                "OVER_1_5": "3",
                "OVER_2_5": "4",
                "BTTS": "5",
                "ABSTAIN": "6",
            }
        ).fillna("9"),
    )

    return breakdown_df


# Formate un pourcentage avec quatre decimales pour les preuves texte.
def format_ratio(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value:.4f}"


# Construit la synthese texte lisible du selecteur V18.3.
def build_summary(
    paths: Dict[str, Path],
    predictions_df: pd.DataFrame,
    results_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    metrics: Dict[str, Any],
) -> str:
    lines: List[str] = []

    lines.extend(
        [
            "OK - Evaluation selecteur V18.3 global multi-market terminee.",
            "",
            "Contexte :",
            "- Phase : V18.3 national global multi-market.",
            "- Objectif : choisir un marche final par match entre STRICT_1X2, DOUBLE_CHANCE, OVER_1_5, OVER_2_5, BTTS ou ABSTAIN.",
            "- StatsBomb : non utilise dans le selecteur global.",
            "- DOUBLE_CHANCE : derivee des probabilites 1X2, non entrainee comme target separee.",
            "- ABSTAIN : produit par le selecteur lorsque les seuils de confiance ne sont pas respectes.",
            "",
            "Fichier utilise :",
            f"- Predictions test : {paths['predictions_csv']}",
            "",
            "Volume :",
            f"- Lignes test analysees : {metrics['total_rows']}",
            f"- Lignes selectionnees : {metrics['selected_rows']}",
            f"- Lignes abstention : {metrics['abstain_rows']}",
            f"- Coverage : {format_ratio(metrics['coverage'])}",
            f"- Abstention rate : {format_ratio(metrics['abstention_rate'])}",
            f"- Reliability : {format_ratio(metrics['reliability'])}",
            f"- Confidence moyenne selectionnee : {format_ratio(metrics['avg_confidence'])}",
            "",
            "Seuils du selecteur :",
            f"- STRICT_1X2 : prediction non DRAW et confiance >= {STRICT_1X2_MIN_CONFIDENCE}",
            f"- OVER_1_5 : YES uniquement et confiance >= {OVER_1_5_YES_MIN_CONFIDENCE}",
            f"- OVER_2_5 : prediction YES/NO avec confiance >= {OVER_2_5_MIN_CONFIDENCE}",
            f"- BTTS : NO uniquement et confiance >= {BTTS_NO_MIN_CONFIDENCE}",
            f"- DOUBLE_CHANCE : probabilite de l'issue exclue <= {DOUBLE_CHANCE_MAX_EXCLUDED_PROBABILITY}",
            f"- Priorite : {' > '.join(SELECTOR_PRIORITY)}",
            "",
            "Repartition par marche :",
        ]
    )

    for _, row in breakdown_df.iterrows():
        lines.append(
            "- {market} : rows={rows}, accuracy={accuracy}, avg_conf={avg_conf}, share_total={share_total}".format(
                market=row["selected_market"],
                rows=int(row["rows"]),
                accuracy=format_ratio(row["accuracy"]),
                avg_conf=format_ratio(row["avg_confidence"]),
                share_total=format_ratio(row["share_total"]),
            )
        )

    competitions = predictions_df["competition_code"].value_counts(dropna=False).to_dict()
    lines.extend(["", "Repartition competitions test :"])
    for competition_code, count in competitions.items():
        lines.append(f"- {competition_code} : {count}")

    lines.extend(
        [
            "",
            "Fichiers generes :",
            f"- Synthese : {paths['summary_txt']}",
            f"- Resultats selecteur : {paths['results_csv']}",
            f"- Repartition marches : {paths['breakdown_csv']}",
            "",
            "Decision technique :",
            "- Cette evaluation produit le premier selecteur V18.3 global multi-market.",
            "- Les marches faibles sont filtres avant selection pour eviter une recommandation brute trop risquee.",
            "- OVER_1_5 NO n'est pas recommande dans cette version, car le diagnostic V18.3 l'a identifie comme faible.",
            "- BTTS YES n'est pas recommande dans cette version, car le diagnostic V18.3 l'a identifie comme fragile.",
            "- Les resultats restent experimentaux et ne promettent aucun resultat sportif.",
        ]
    )

    return "\n".join(lines)


# Orchestre l'evaluation complete et l'ecriture des preuves 351, 352 et 353.
def main() -> None:
    project_root = find_project_root()
    paths = build_paths(project_root)
    paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    validate_input_file(paths["predictions_csv"])

    predictions_df = load_predictions(paths["predictions_csv"])
    results_df = build_selector_results(predictions_df)
    breakdown_df = compute_market_breakdown(results_df)
    metrics = compute_global_metrics(results_df)
    summary_text = build_summary(paths, predictions_df, results_df, breakdown_df, metrics)

    results_df.to_csv(paths["results_csv"], index=False, encoding="utf-8")
    breakdown_df.to_csv(paths["breakdown_csv"], index=False, encoding="utf-8")
    paths["summary_txt"].write_text(summary_text, encoding="utf-8")

    print("OK - Evaluation selecteur V18.3 global multi-market terminee.")
    print(f"Lignes test analysees : {metrics['total_rows']}")
    print(f"Selected rows : {metrics['selected_rows']}")
    print(f"Coverage : {metrics['coverage']:.4f}")
    print(f"Reliability : {metrics['reliability']:.4f}")
    print(f"Abstention rate : {metrics['abstention_rate']:.4f}")
    print(f"Summary saved: {paths['summary_txt']}")
    print(f"Results CSV saved: {paths['results_csv']}")
    print(f"Breakdown CSV saved: {paths['breakdown_csv']}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# 348_v18_3_global_multimarket_test_predictions.csv
#        -> evaluate_v18_3_global_selector.py
#        -> 351_v18_3_global_selector_summary.txt
#        -> 352_v18_3_global_selector_results.csv
#        -> 353_v18_3_global_selector_market_breakdown.csv
