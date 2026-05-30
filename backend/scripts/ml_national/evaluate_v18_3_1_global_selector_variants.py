# Role du fichier :
# Ce script evalue plusieurs variantes V18.3.1 du selecteur national global RubyBets.
# Il cherche a reduire la dependance a DOUBLE_CHANCE tout en conservant une fiabilite elevee.
# Les variantes restent experimentales et ne doivent pas etre presentees comme une garantie sportive.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


PREDICTIONS_FILENAME = "348_v18_3_global_multimarket_test_predictions.csv"
SUMMARY_FILENAME = "355_v18_3_1_global_selector_variants_summary.txt"
COMPARISON_FILENAME = "356_v18_3_1_global_selector_variants_comparison.csv"
BEST_RESULTS_FILENAME = "357_v18_3_1_global_selector_best_results.csv"
BEST_BREAKDOWN_FILENAME = "358_v18_3_1_global_selector_best_market_breakdown.csv"

TARGET_RELIABILITY_FLOOR = 0.90
TARGET_COVERAGE_FLOOR = 0.35
TARGET_MAX_DOUBLE_CHANCE_SHARE = 0.70


@dataclass(frozen=True)
class SelectorVariant:
    name: str
    description: str
    strict_1x2_min_confidence: float = 0.80
    over_1_5_yes_min_confidence: float = 0.80
    over_2_5_min_confidence: float = 0.70
    btts_no_min_confidence: float = 0.70
    double_chance_max_excluded_probability: Optional[float] = 0.15
    allow_btts: bool = True
    priority: tuple[str, ...] = (
        "STRICT_1X2",
        "OVER_1_5",
        "OVER_2_5",
        "BTTS",
        "DOUBLE_CHANCE",
    )


SELECTOR_VARIANTS = [
    SelectorVariant(
        name="v18_3_baseline_reference",
        description="Reference V18.3 taguee : tres fiable, mais fortement dependante de DOUBLE_CHANCE.",
    ),
    SelectorVariant(
        name="v18_3_1_dc_strict_p010",
        description="Resserre DOUBLE_CHANCE avec issue exclue <= 0.10 pour reduire sa place sans changer les autres seuils.",
        double_chance_max_excluded_probability=0.10,
    ),
    SelectorVariant(
        name="v18_3_1_dc_strict_p012",
        description="Compromis intermediaire : DOUBLE_CHANCE autorisee si issue exclue <= 0.12.",
        double_chance_max_excluded_probability=0.12,
    ),
    SelectorVariant(
        name="v18_3_1_market_balanced",
        description="Variante plus equilibree : leger assouplissement 1X2/OVER_2_5 et priorite a OVER_2_5 avant OVER_1_5.",
        strict_1x2_min_confidence=0.78,
        over_1_5_yes_min_confidence=0.78,
        over_2_5_min_confidence=0.68,
        btts_no_min_confidence=0.72,
        double_chance_max_excluded_probability=0.10,
        priority=("STRICT_1X2", "OVER_2_5", "OVER_1_5", "BTTS", "DOUBLE_CHANCE"),
    ),
    SelectorVariant(
        name="v18_3_1_market_balanced_p012",
        description="Variante equilibree avec un peu plus de couverture via DOUBLE_CHANCE <= 0.12.",
        strict_1x2_min_confidence=0.78,
        over_1_5_yes_min_confidence=0.78,
        over_2_5_min_confidence=0.68,
        btts_no_min_confidence=0.72,
        double_chance_max_excluded_probability=0.12,
        priority=("STRICT_1X2", "OVER_2_5", "OVER_1_5", "BTTS", "DOUBLE_CHANCE"),
    ),
    SelectorVariant(
        name="v18_3_1_no_dc_reference",
        description="Reference sans DOUBLE_CHANCE pour mesurer la fiabilite des marches directs seuls.",
        double_chance_max_excluded_probability=None,
        priority=("STRICT_1X2", "OVER_1_5", "OVER_2_5", "BTTS"),
    ),
    SelectorVariant(
        name="v18_3_1_conservative_no_btts_dc_p010",
        description="Variante prudente sans BTTS : seuils directs durcis et DOUBLE_CHANCE <= 0.10.",
        strict_1x2_min_confidence=0.82,
        over_1_5_yes_min_confidence=0.82,
        over_2_5_min_confidence=0.72,
        double_chance_max_excluded_probability=0.10,
        allow_btts=False,
        priority=("STRICT_1X2", "OVER_1_5", "OVER_2_5", "DOUBLE_CHANCE"),
    ),
]


# Retrouve la racine du projet RubyBets a partir de l'emplacement du script.
def find_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for candidate in [current_path.parent, *current_path.parents]:
        if (candidate / "backend").exists() and (candidate / "reports").exists():
            return candidate

    return Path.cwd().resolve()


# Construit les chemins d'entree et de sortie de l'experience V18.3.1.
def build_paths(project_root: Path) -> Dict[str, Path]:
    evidence_dir = project_root / "reports" / "evidence" / "ml_training"
    return {
        "evidence_dir": evidence_dir,
        "predictions_csv": evidence_dir / PREDICTIONS_FILENAME,
        "summary_txt": evidence_dir / SUMMARY_FILENAME,
        "comparison_csv": evidence_dir / COMPARISON_FILENAME,
        "best_results_csv": evidence_dir / BEST_RESULTS_FILENAME,
        "best_breakdown_csv": evidence_dir / BEST_BREAKDOWN_FILENAME,
    }


# Verifie que le fichier de predictions 348 existe avant de lancer les variantes.
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
        "over_2_5_prediction",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_max_probability",
    ]

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le fichier 348 : " + ", ".join(missing_columns)
        )

    return df


# Convertit une confiance numerique en niveau de risque simple pour les preuves CSV.
def compute_risk_level(confidence: Optional[float]) -> str:
    if confidence is None:
        return "none"
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Derive une double chance a partir de l'issue 1X2 la moins probable.
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

    return {
        "prediction": prediction,
        "confidence": selected_confidence,
        "excluded_outcome": excluded_outcome,
        "excluded_probability": excluded_probability,
        "is_correct": bool(row["target_1x2"] != excluded_outcome),
    }


# Construit les candidats valides pour une ligne selon les seuils d'une variante.
def build_candidates_for_row(row: pd.Series, variant: SelectorVariant) -> Dict[str, Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}

    if (
        row["1x2_prediction"] != "DRAW"
        and float(row["1x2_max_probability"]) >= variant.strict_1x2_min_confidence
    ):
        prediction = row["1x2_prediction"]
        confidence = float(row["1x2_max_probability"])
        candidates["STRICT_1X2"] = {
            "selected_prediction": prediction,
            "selected_confidence": confidence,
            "actual_value": row["target_1x2"],
            "is_correct": bool(prediction == row["target_1x2"]),
            "selector_rule": f"1X2 non-DRAW avec confiance >= {variant.strict_1x2_min_confidence}",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if (
        row["over_1_5_prediction"] == "YES"
        and float(row["over_1_5_prob_YES"]) >= variant.over_1_5_yes_min_confidence
    ):
        confidence = float(row["over_1_5_prob_YES"])
        candidates["OVER_1_5"] = {
            "selected_prediction": "YES",
            "selected_confidence": confidence,
            "actual_value": row["target_over_1_5"],
            "is_correct": bool(row["target_over_1_5"] == "YES"),
            "selector_rule": f"OVER_1_5 YES avec confiance >= {variant.over_1_5_yes_min_confidence}",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if float(row["over_2_5_max_probability"]) >= variant.over_2_5_min_confidence:
        prediction = row["over_2_5_prediction"]
        confidence = float(row["over_2_5_max_probability"])
        candidates["OVER_2_5"] = {
            "selected_prediction": prediction,
            "selected_confidence": confidence,
            "actual_value": row["target_over_2_5"],
            "is_correct": bool(prediction == row["target_over_2_5"]),
            "selector_rule": f"OVER_2_5 avec confiance >= {variant.over_2_5_min_confidence}",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if (
        variant.allow_btts
        and row["btts_prediction"] == "NO"
        and float(row["btts_max_probability"]) >= variant.btts_no_min_confidence
    ):
        confidence = float(row["btts_max_probability"])
        candidates["BTTS"] = {
            "selected_prediction": "NO",
            "selected_confidence": confidence,
            "actual_value": row["target_btts"],
            "is_correct": bool(row["target_btts"] == "NO"),
            "selector_rule": f"BTTS NO avec confiance >= {variant.btts_no_min_confidence}",
            "excluded_outcome": "",
            "excluded_probability": None,
        }

    if variant.double_chance_max_excluded_probability is not None:
        double_chance = derive_double_chance(row)
        if double_chance["excluded_probability"] <= variant.double_chance_max_excluded_probability:
            candidates["DOUBLE_CHANCE"] = {
                "selected_prediction": double_chance["prediction"],
                "selected_confidence": float(double_chance["confidence"]),
                "actual_value": row["target_1x2"],
                "is_correct": bool(double_chance["is_correct"]),
                "selector_rule": "DOUBLE_CHANCE si probabilite de l'issue exclue <= "
                f"{variant.double_chance_max_excluded_probability}",
                "excluded_outcome": double_chance["excluded_outcome"],
                "excluded_probability": double_chance["excluded_probability"],
            }

    return candidates


# Selectionne le marche final d'une ligne pour une variante donnee.
def select_market_for_row(row: pd.Series, variant: SelectorVariant) -> Dict[str, Any]:
    candidates = build_candidates_for_row(row, variant)

    for market in variant.priority:
        if market in candidates:
            selected = candidates[market]
            selected_confidence = selected["selected_confidence"]
            return {
                "selected_market": market,
                "risk_level": compute_risk_level(selected_confidence),
                **selected,
            }

    return {
        "selected_market": "ABSTAIN",
        "selected_prediction": "ABSTAIN",
        "selected_confidence": None,
        "risk_level": "none",
        "actual_value": "",
        "is_correct": None,
        "selector_rule": "Aucun signal ne respecte les seuils de la variante.",
        "excluded_outcome": "",
        "excluded_probability": None,
    }


# Applique une variante du selecteur a toutes les lignes du fichier 348.
def build_variant_results(predictions_df: pd.DataFrame, variant: SelectorVariant) -> pd.DataFrame:
    selections: List[Dict[str, Any]] = []

    for _, row in predictions_df.iterrows():
        selections.append(select_market_for_row(row, variant))

    selection_df = pd.DataFrame(selections)
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
    available_columns = [column for column in base_columns if column in predictions_df.columns]

    result_df = pd.concat(
        [predictions_df[available_columns].reset_index(drop=True), selection_df],
        axis=1,
    )
    result_df.insert(0, "selector_variant", variant.name)
    return result_df


# Calcule les indicateurs globaux d'une variante du selecteur.
def compute_variant_metrics(results_df: pd.DataFrame, variant: SelectorVariant) -> Dict[str, Any]:
    total_rows = len(results_df)
    selected_mask = results_df["selected_market"] != "ABSTAIN"
    selected_rows = int(selected_mask.sum())
    abstain_rows = total_rows - selected_rows

    if selected_rows > 0:
        reliability = float(results_df.loc[selected_mask, "is_correct"].astype(bool).mean())
        avg_confidence = float(results_df.loc[selected_mask, "selected_confidence"].mean())
        selected_markets_count = int(results_df.loc[selected_mask, "selected_market"].nunique())
    else:
        reliability = 0.0
        avg_confidence = 0.0
        selected_markets_count = 0

    double_chance_rows = int((results_df["selected_market"] == "DOUBLE_CHANCE").sum())
    strict_1x2_rows = int((results_df["selected_market"] == "STRICT_1X2").sum())
    over_1_5_rows = int((results_df["selected_market"] == "OVER_1_5").sum())
    over_2_5_rows = int((results_df["selected_market"] == "OVER_2_5").sum())
    btts_rows = int((results_df["selected_market"] == "BTTS").sum())

    coverage = selected_rows / total_rows if total_rows else 0.0
    abstention_rate = abstain_rows / total_rows if total_rows else 0.0
    double_chance_share_selected = double_chance_rows / selected_rows if selected_rows else 0.0
    direct_market_rows = selected_rows - double_chance_rows
    direct_market_share_selected = direct_market_rows / selected_rows if selected_rows else 0.0

    market_diversity_score = selected_markets_count / 5 if selected_markets_count else 0.0
    double_chance_balance_score = 1.0 - double_chance_share_selected

    quality_score = (
        reliability * 0.50
        + coverage * 0.25
        + market_diversity_score * 0.15
        + double_chance_balance_score * 0.10
    )

    meets_targets = bool(
        reliability >= TARGET_RELIABILITY_FLOOR
        and coverage >= TARGET_COVERAGE_FLOOR
        and double_chance_share_selected <= TARGET_MAX_DOUBLE_CHANCE_SHARE
    )

    return {
        "selector_variant": variant.name,
        "description": variant.description,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstain_rows": abstain_rows,
        "coverage": coverage,
        "abstention_rate": abstention_rate,
        "reliability": reliability,
        "avg_confidence": avg_confidence,
        "double_chance_rows": double_chance_rows,
        "double_chance_share_selected": double_chance_share_selected,
        "direct_market_rows": direct_market_rows,
        "direct_market_share_selected": direct_market_share_selected,
        "strict_1x2_rows": strict_1x2_rows,
        "over_1_5_rows": over_1_5_rows,
        "over_2_5_rows": over_2_5_rows,
        "btts_rows": btts_rows,
        "selected_markets_count": selected_markets_count,
        "quality_score": quality_score,
        "meets_v18_3_1_targets": meets_targets,
        "strict_1x2_min_confidence": variant.strict_1x2_min_confidence,
        "over_1_5_yes_min_confidence": variant.over_1_5_yes_min_confidence,
        "over_2_5_min_confidence": variant.over_2_5_min_confidence,
        "btts_no_min_confidence": variant.btts_no_min_confidence,
        "double_chance_max_excluded_probability": variant.double_chance_max_excluded_probability,
        "allow_btts": variant.allow_btts,
        "priority": " > ".join(variant.priority),
    }


# Produit la repartition des marches du meilleur selecteur V18.3.1.
def compute_market_breakdown(results_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    total_rows = len(results_df)
    selected_total = int((results_df["selected_market"] != "ABSTAIN").sum())

    market_order = {
        "STRICT_1X2": 1,
        "DOUBLE_CHANCE": 2,
        "OVER_1_5": 3,
        "OVER_2_5": 4,
        "BTTS": 5,
        "ABSTAIN": 6,
    }

    for market, market_df in results_df.groupby("selected_market", dropna=False):
        selected_market = market != "ABSTAIN"
        market_rows = len(market_df)

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
                "share_selected": market_rows / selected_total if selected_market and selected_total else 0.0,
                "correct_rows": correct_rows,
                "error_rows": market_rows - correct_rows if selected_market else 0,
                "accuracy": accuracy,
                "avg_confidence": avg_confidence,
            }
        )

    breakdown_df = pd.DataFrame(rows)
    breakdown_df["market_order"] = breakdown_df["selected_market"].map(market_order).fillna(99)
    breakdown_df = breakdown_df.sort_values("market_order").drop(columns=["market_order"])
    return breakdown_df


# Selectionne la meilleure variante V18.3.1 selon l'objectif de reduction de DOUBLE_CHANCE.
def select_best_variant(comparison_df: pd.DataFrame) -> str:
    candidate_df = comparison_df[
        comparison_df["selector_variant"] != "v18_3_baseline_reference"
    ].copy()

    target_df = candidate_df[candidate_df["meets_v18_3_1_targets"] == True].copy()
    if not target_df.empty:
        target_df = target_df.sort_values(
            by=["quality_score", "reliability", "coverage"], ascending=False
        )
        return str(target_df.iloc[0]["selector_variant"])

    candidate_df = candidate_df.sort_values(
        by=["quality_score", "reliability", "coverage"], ascending=False
    )
    return str(candidate_df.iloc[0]["selector_variant"])


# Formate un ratio pour les fichiers texte de preuve.
def format_ratio(value: Any) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.4f}"


# Construit le texte de synthese V18.3.1 avec comparaison et decision provisoire.
def build_summary(
    paths: Dict[str, Path],
    predictions_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    best_variant_name: str,
    best_results_df: pd.DataFrame,
    best_breakdown_df: pd.DataFrame,
) -> str:
    best_row = comparison_df.loc[
        comparison_df["selector_variant"] == best_variant_name
    ].iloc[0]
    baseline_row = comparison_df.loc[
        comparison_df["selector_variant"] == "v18_3_baseline_reference"
    ].iloc[0]

    lines: List[str] = []
    lines.extend(
        [
            "OK - Evaluation V18.3.1 global selector variants terminee.",
            "",
            "Contexte :",
            "- Phase : V18.3.1 national global multi-market.",
            "- Objectif : reduire la dependance a DOUBLE_CHANCE sans perdre la fiabilite du selecteur V18.3.",
            "- StatsBomb : non utilise dans V18.3.1 global.",
            "- DOUBLE_CHANCE : toujours derivee des probabilites 1X2, jamais entrainee comme target separee.",
            "- ABSTAIN : conserve comme mecanisme de prudence.",
            "",
            "Fichier utilise :",
            f"- Predictions test : {paths['predictions_csv']}",
            "",
            "Objectifs de decision V18.3.1 :",
            f"- Reliability cible minimale : {TARGET_RELIABILITY_FLOOR}",
            f"- Coverage cible minimale : {TARGET_COVERAGE_FLOOR}",
            f"- Part DOUBLE_CHANCE cible maximale parmi les selections : {TARGET_MAX_DOUBLE_CHANCE_SHARE}",
            "",
            "Reference V18.3 :",
            f"- Reliability : {format_ratio(baseline_row['reliability'])}",
            f"- Coverage : {format_ratio(baseline_row['coverage'])}",
            f"- Selected rows : {int(baseline_row['selected_rows'])}",
            f"- DOUBLE_CHANCE rows : {int(baseline_row['double_chance_rows'])}",
            f"- DOUBLE_CHANCE share selected : {format_ratio(baseline_row['double_chance_share_selected'])}",
            "",
            "Meilleure variante V18.3.1 selon le score de qualite :",
            f"- Variante retenue : {best_variant_name}",
            f"- Description : {best_row['description']}",
            f"- Reliability : {format_ratio(best_row['reliability'])}",
            f"- Coverage : {format_ratio(best_row['coverage'])}",
            f"- Selected rows : {int(best_row['selected_rows'])}",
            f"- Abstention rate : {format_ratio(best_row['abstention_rate'])}",
            f"- DOUBLE_CHANCE rows : {int(best_row['double_chance_rows'])}",
            f"- DOUBLE_CHANCE share selected : {format_ratio(best_row['double_chance_share_selected'])}",
            f"- Direct market share selected : {format_ratio(best_row['direct_market_share_selected'])}",
            f"- Quality score : {format_ratio(best_row['quality_score'])}",
            f"- Objectifs V18.3.1 atteints : {bool(best_row['meets_v18_3_1_targets'])}",
            "",
            "Repartition du meilleur selecteur :",
        ]
    )

    for _, row in best_breakdown_df.iterrows():
        lines.append(
            "- {market} : rows={rows}, accuracy={accuracy}, avg_conf={avg_conf}, share_selected={share_selected}".format(
                market=row["selected_market"],
                rows=int(row["rows"]),
                accuracy=format_ratio(row["accuracy"]),
                avg_conf=format_ratio(row["avg_confidence"]),
                share_selected=format_ratio(row["share_selected"]),
            )
        )

    lines.extend(["", "Comparaison des variantes :"])
    ordered_df = comparison_df.sort_values("quality_score", ascending=False)
    for _, row in ordered_df.iterrows():
        lines.append(
            "- {variant} | reliability={reliability} | coverage={coverage} | dc_share={dc_share} | selected={selected} | score={score}".format(
                variant=row["selector_variant"],
                reliability=format_ratio(row["reliability"]),
                coverage=format_ratio(row["coverage"]),
                dc_share=format_ratio(row["double_chance_share_selected"]),
                selected=int(row["selected_rows"]),
                score=format_ratio(row["quality_score"]),
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
            f"- Comparaison variantes : {paths['comparison_csv']}",
            f"- Resultats meilleur selecteur : {paths['best_results_csv']}",
            f"- Repartition meilleur selecteur : {paths['best_breakdown_csv']}",
            "",
            "Decision technique :",
            "- V18.3.1 sert a comparer des variantes, pas encore a integrer le frontend.",
            "- La meilleure variante doit etre analysee avant commit definitif comme nouvelle reference.",
            "- Si la baisse de coverage est trop forte, V18.3 peut rester la reference et V18.3.1 devenir une variante prudente.",
            "- Les resultats restent experimentaux et ne promettent aucun resultat sportif.",
        ]
    )

    return "\n".join(lines)


# Orchestre l'evaluation complete des variantes V18.3.1 et l'ecriture des preuves 355 a 358.
def main() -> None:
    project_root = find_project_root()
    paths = build_paths(project_root)
    paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    validate_input_file(paths["predictions_csv"])
    predictions_df = load_predictions(paths["predictions_csv"])

    all_results: Dict[str, pd.DataFrame] = {}
    comparison_rows: List[Dict[str, Any]] = []

    for variant in SELECTOR_VARIANTS:
        variant_results_df = build_variant_results(predictions_df, variant)
        all_results[variant.name] = variant_results_df
        comparison_rows.append(compute_variant_metrics(variant_results_df, variant))

    comparison_df = pd.DataFrame(comparison_rows)
    best_variant_name = select_best_variant(comparison_df)
    best_results_df = all_results[best_variant_name]
    best_breakdown_df = compute_market_breakdown(best_results_df)
    summary_text = build_summary(
        paths,
        predictions_df,
        comparison_df,
        best_variant_name,
        best_results_df,
        best_breakdown_df,
    )

    comparison_df.to_csv(paths["comparison_csv"], index=False, encoding="utf-8")
    best_results_df.to_csv(paths["best_results_csv"], index=False, encoding="utf-8")
    best_breakdown_df.to_csv(paths["best_breakdown_csv"], index=False, encoding="utf-8")
    paths["summary_txt"].write_text(summary_text, encoding="utf-8")

    best_metrics = comparison_df.loc[
        comparison_df["selector_variant"] == best_variant_name
    ].iloc[0]

    print("OK - Evaluation V18.3.1 global selector variants terminee.")
    print(f"Lignes test analysees : {len(predictions_df)}")
    print(f"Variantes testees : {len(SELECTOR_VARIANTS)}")
    print(f"Best variant : {best_variant_name}")
    print(f"Selected rows : {int(best_metrics['selected_rows'])}")
    print(f"Coverage : {best_metrics['coverage']:.4f}")
    print(f"Reliability : {best_metrics['reliability']:.4f}")
    print(
        "DOUBLE_CHANCE share selected : "
        f"{best_metrics['double_chance_share_selected']:.4f}"
    )
    print(f"Summary saved: {paths['summary_txt']}")
    print(f"Comparison CSV saved: {paths['comparison_csv']}")
    print(f"Best results CSV saved: {paths['best_results_csv']}")
    print(f"Best breakdown CSV saved: {paths['best_breakdown_csv']}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# 348_v18_3_global_multimarket_test_predictions.csv
#        -> evaluate_v18_3_1_global_selector_variants.py
#        -> 355_v18_3_1_global_selector_variants_summary.txt
#        -> 356_v18_3_1_global_selector_variants_comparison.csv
#        -> 357_v18_3_1_global_selector_best_results.csv
#        -> 358_v18_3_1_global_selector_best_market_breakdown.csv
