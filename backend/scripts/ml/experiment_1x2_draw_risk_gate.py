# Rôle du fichier : tester des filtres de risque de match nul sur les prédictions ML 1X2 V3 à forte confiance, sans réentraîner de modèle ni modifier le projet produit.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


# Retrouve la racine du projet RubyBets, même si le script est lancé depuis backend ou déplacé temporairement.
def resolve_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for parent in [current_path.parent, *current_path.parents]:
        if (parent / "reports" / "evidence" / "ml_training").exists():
            return parent

        if parent.name.lower() == "rubybets":
            return parent

    if len(current_path.parents) > 3:
        return current_path.parents[3]

    return current_path.parent


PROJECT_ROOT = resolve_project_root()
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
INPUT_CSV_PATH = REPORT_DIR / "53_1x2_v3_high_confidence_predictions.csv"
SUMMARY_OUTPUT_PATH = REPORT_DIR / "57_1x2_draw_risk_gate_summary.txt"
RESULTS_OUTPUT_PATH = REPORT_DIR / "58_1x2_draw_risk_gate_results.csv"
DECISION_OUTPUT_PATH = REPORT_DIR / "59_1x2_draw_risk_gate_decision.txt"

TEST_ROWS_REFERENCE = 5300
BASELINE_ACCURACY_REFERENCE = 0.7006
BASELINE_SELECTED_ROWS_REFERENCE = 1386
BASELINE_MISSED_DRAW_REFERENCE = 267
MIN_ROWS_FOR_USABLE_GATE = 500
MIN_RETENTION_FOR_USABLE_GATE = 0.40

EXPECTED_COLUMNS = [
    "clean_match_id",
    "match_date",
    "league_code",
    "season",
    "match",
    "actual_result",
    "predicted_result",
    "prob_home_win",
    "prob_draw",
    "prob_away_win",
    "max_probability",
    "correct",
]


@dataclass
class GateDefinition:
    name: str
    description: str
    risk_mask_builder: Callable[[pd.DataFrame], pd.Series]


# Vérifie que le fichier 53 existe avant d'appliquer des filtres de risque de nul.
def validate_input_file() -> None:
    if not INPUT_CSV_PATH.exists():
        raise FileNotFoundError(
            "Le fichier 53 est introuvable. Lance d'abord export_1x2_v3_high_confidence_predictions.py. "
            f"Chemin attendu : {INPUT_CSV_PATH}"
        )


# Charge les prédictions forte confiance V3 et prépare les colonnes nécessaires aux filtres DRAW.
def load_high_confidence_predictions() -> pd.DataFrame:
    validate_input_file()
    dataframe = pd.read_csv(INPUT_CSV_PATH, encoding="utf-8-sig")
    missing_columns = [column for column in EXPECTED_COLUMNS if column not in dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le fichier 53 : {missing_columns}")

    dataframe = dataframe.copy()
    dataframe["match_date"] = pd.to_datetime(dataframe["match_date"], errors="coerce")

    numeric_columns = [
        "prob_home_win",
        "prob_draw",
        "prob_away_win",
        "max_probability",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "abs_team_strength_diff",
        "draw_profile_score_with_strength",
        "home_away_context_diff",
        "home_home_context_strength",
        "away_away_context_strength",
    ]

    for column in numeric_columns:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe["correct"] = dataframe["correct"].astype(str).str.lower().isin(["true", "1", "yes"])
    dataframe["error"] = ~dataframe["correct"]
    dataframe["is_actual_draw"] = dataframe["actual_result"] == "DRAW"
    dataframe["is_predicted_draw"] = dataframe["predicted_result"] == "DRAW"
    dataframe["draw_missed"] = dataframe["is_actual_draw"] & ~dataframe["is_predicted_draw"]
    dataframe["top_probability_gap_vs_draw"] = dataframe["max_probability"] - dataframe["prob_draw"]

    if "home_away_context_diff" in dataframe.columns:
        dataframe["abs_home_away_context_diff"] = dataframe["home_away_context_diff"].abs()
    else:
        dataframe["abs_home_away_context_diff"] = pd.NA

    return dataframe


# Calcule un seuil quantile utilisable même si la colonne contient peu de valeurs valides.
def safe_quantile(dataframe: pd.DataFrame, column: str, quantile: float, fallback: float) -> float:
    if column not in dataframe.columns:
        return fallback

    values = pd.to_numeric(dataframe[column], errors="coerce").dropna()

    if values.empty:
        return fallback

    return float(values.quantile(quantile))


# Crée les filtres candidats à tester à partir des seuils observés dans les données du fichier 53.
def build_gate_definitions(dataframe: pd.DataFrame) -> list[GateDefinition]:
    high_draw_profile_threshold = safe_quantile(
        dataframe=dataframe,
        column="draw_profile_score_with_strength",
        quantile=0.67,
        fallback=0.18,
    )
    very_high_draw_profile_threshold = safe_quantile(
        dataframe=dataframe,
        column="draw_profile_score_with_strength",
        quantile=0.80,
        fallback=0.22,
    )
    low_strength_gap_threshold = safe_quantile(
        dataframe=dataframe,
        column="abs_team_strength_diff",
        quantile=0.33,
        fallback=70.0,
    )
    medium_strength_gap_threshold = safe_quantile(
        dataframe=dataframe,
        column="abs_team_strength_diff",
        quantile=0.67,
        fallback=150.0,
    )
    low_context_gap_threshold = safe_quantile(
        dataframe=dataframe,
        column="abs_home_away_context_diff",
        quantile=0.33,
        fallback=25.0,
    )
    medium_context_gap_threshold = safe_quantile(
        dataframe=dataframe,
        column="abs_home_away_context_diff",
        quantile=0.67,
        fallback=60.0,
    )

    return [
        GateDefinition(
            name="baseline_keep_all",
            description="Reference sans filtre DRAW : garde toutes les predictions forte confiance V3.",
            risk_mask_builder=lambda df: pd.Series(False, index=df.index),
        ),
        GateDefinition(
            name="remove_prob_draw_ge_0_20",
            description="Exclut les matchs ou la probabilite DRAW est superieure ou egale a 0.20.",
            risk_mask_builder=lambda df: df["prob_draw"] >= 0.20,
        ),
        GateDefinition(
            name="remove_prob_draw_ge_0_18",
            description="Exclut les matchs ou la probabilite DRAW est superieure ou egale a 0.18.",
            risk_mask_builder=lambda df: df["prob_draw"] >= 0.18,
        ),
        GateDefinition(
            name="remove_prob_draw_ge_0_15",
            description="Exclut les matchs ou la probabilite DRAW est superieure ou egale a 0.15.",
            risk_mask_builder=lambda df: df["prob_draw"] >= 0.15,
        ),
        GateDefinition(
            name="remove_gap_vs_draw_le_0_45",
            description="Exclut les matchs ou le favori du modele est trop proche de la probabilite DRAW.",
            risk_mask_builder=lambda df: df["top_probability_gap_vs_draw"] <= 0.45,
        ),
        GateDefinition(
            name="remove_gap_vs_draw_le_0_50",
            description="Version plus prudente : exclut si l'ecart entre le top choix et DRAW est <= 0.50.",
            risk_mask_builder=lambda df: df["top_probability_gap_vs_draw"] <= 0.50,
        ),
        GateDefinition(
            name="remove_confidence_between_0_62_and_0_70",
            description="Exclut la bande de confiance la plus fragile observee dans le diagnostic.",
            risk_mask_builder=lambda df: (df["max_probability"] >= 0.62) & (df["max_probability"] < 0.70),
        ),
        GateDefinition(
            name="remove_high_draw_profile_top_33pct",
            description="Exclut le tiers des matchs avec le profil DRAW le plus eleve.",
            risk_mask_builder=lambda df: df["draw_profile_score_with_strength"] >= high_draw_profile_threshold,
        ),
        GateDefinition(
            name="remove_very_high_draw_profile_top_20pct",
            description="Exclut seulement les 20% de matchs avec le profil DRAW le plus fort.",
            risk_mask_builder=lambda df: df["draw_profile_score_with_strength"] >= very_high_draw_profile_threshold,
        ),
        GateDefinition(
            name="remove_low_strength_gap_bottom_33pct",
            description="Exclut les matchs ou l'ecart de force entre equipes est faible.",
            risk_mask_builder=lambda df: df["abs_team_strength_diff"] <= low_strength_gap_threshold,
        ),
        GateDefinition(
            name="remove_low_or_medium_strength_gap_bottom_67pct",
            description="Exclut les matchs ou l'ecart de force est faible ou moyen.",
            risk_mask_builder=lambda df: df["abs_team_strength_diff"] <= medium_strength_gap_threshold,
        ),
        GateDefinition(
            name="remove_low_context_gap_bottom_33pct",
            description="Exclut les matchs avec faible ecart domicile/exterieur.",
            risk_mask_builder=lambda df: df["abs_home_away_context_diff"] <= low_context_gap_threshold,
        ),
        GateDefinition(
            name="remove_low_or_medium_context_gap_bottom_67pct",
            description="Exclut les matchs avec ecart domicile/exterieur faible ou moyen.",
            risk_mask_builder=lambda df: df["abs_home_away_context_diff"] <= medium_context_gap_threshold,
        ),
        GateDefinition(
            name="draw_prob_or_gap_gate",
            description="Exclut si prob_draw >= 0.20 OU si l'ecart top choix vs DRAW est <= 0.45.",
            risk_mask_builder=lambda df: (df["prob_draw"] >= 0.20) | (df["top_probability_gap_vs_draw"] <= 0.45),
        ),
        GateDefinition(
            name="draw_prob_or_high_profile_gate",
            description="Exclut si prob_draw >= 0.20 OU profil DRAW dans le tiers haut.",
            risk_mask_builder=lambda df: (df["prob_draw"] >= 0.20) | (df["draw_profile_score_with_strength"] >= high_draw_profile_threshold),
        ),
        GateDefinition(
            name="gap_or_high_profile_gate",
            description="Exclut si ecart top choix vs DRAW <= 0.45 OU profil DRAW dans le tiers haut.",
            risk_mask_builder=lambda df: (df["top_probability_gap_vs_draw"] <= 0.45)
            | (df["draw_profile_score_with_strength"] >= high_draw_profile_threshold),
        ),
        GateDefinition(
            name="balanced_draw_risk_gate",
            description="Filtre equilibre : prob_draw >= 0.20, ecart vs DRAW <= 0.45, ou profil DRAW eleve avec ecart de force faible/moyen.",
            risk_mask_builder=lambda df: (df["prob_draw"] >= 0.20)
            | (df["top_probability_gap_vs_draw"] <= 0.45)
            | (
                (df["draw_profile_score_with_strength"] >= high_draw_profile_threshold)
                & (df["abs_team_strength_diff"] <= medium_strength_gap_threshold)
            ),
        ),
        GateDefinition(
            name="context_draw_risk_gate",
            description="Filtre contexte : prob_draw >= 0.20, ecart vs DRAW <= 0.45, ou faible ecart domicile/exterieur.",
            risk_mask_builder=lambda df: (df["prob_draw"] >= 0.20)
            | (df["top_probability_gap_vs_draw"] <= 0.45)
            | (df["abs_home_away_context_diff"] <= low_context_gap_threshold),
        ),
        GateDefinition(
            name="aggressive_draw_risk_gate",
            description="Filtre tres prudent : retire la plupart des profils de nul ou de match equilibre.",
            risk_mask_builder=lambda df: (df["prob_draw"] >= 0.18)
            | (df["top_probability_gap_vs_draw"] <= 0.50)
            | (df["draw_profile_score_with_strength"] >= high_draw_profile_threshold)
            | (df["abs_team_strength_diff"] <= low_strength_gap_threshold)
            | (df["abs_home_away_context_diff"] <= low_context_gap_threshold),
        ),
    ]


# Calcule les indicateurs principaux d'un filtre DRAW : accuracy, coverage, nuls retires et lignes conservees.
def evaluate_gate(dataframe: pd.DataFrame, gate: GateDefinition) -> dict:
    risk_mask = gate.risk_mask_builder(dataframe).fillna(False).astype(bool)
    kept_dataframe = dataframe.loc[~risk_mask].copy()
    removed_dataframe = dataframe.loc[risk_mask].copy()

    total_rows = len(dataframe)
    kept_rows = len(kept_dataframe)
    removed_rows = len(removed_dataframe)
    correct_rows = int(kept_dataframe["correct"].sum()) if kept_rows else 0
    error_rows = kept_rows - correct_rows
    accuracy = correct_rows / kept_rows if kept_rows else 0.0
    retained_coverage = kept_rows / total_rows if total_rows else 0.0
    test_coverage = kept_rows / TEST_ROWS_REFERENCE if TEST_ROWS_REFERENCE else 0.0

    actual_draw_kept = int(kept_dataframe["is_actual_draw"].sum()) if kept_rows else 0
    actual_draw_removed = int(removed_dataframe["is_actual_draw"].sum()) if removed_rows else 0
    errors_removed = int(removed_dataframe["error"].sum()) if removed_rows else 0

    return {
        "gate_name": gate.name,
        "description": gate.description,
        "input_rows": total_rows,
        "kept_rows": kept_rows,
        "removed_rows": removed_rows,
        "correct_rows": correct_rows,
        "error_rows": error_rows,
        "accuracy": round(accuracy, 4),
        "accuracy_gain_vs_baseline": round(accuracy - BASELINE_ACCURACY_REFERENCE, 4),
        "retention_on_high_confidence": round(retained_coverage, 4),
        "test_coverage": round(test_coverage, 4),
        "test_coverage_loss_vs_v3_high_confidence": round((total_rows / TEST_ROWS_REFERENCE) - test_coverage, 4),
        "actual_draw_kept_rows": actual_draw_kept,
        "actual_draw_removed_rows": actual_draw_removed,
        "actual_draw_removed_ratio": round(actual_draw_removed / BASELINE_MISSED_DRAW_REFERENCE, 4)
        if BASELINE_MISSED_DRAW_REFERENCE
        else 0.0,
        "actual_draw_rate_kept": round(actual_draw_kept / kept_rows, 4) if kept_rows else 0.0,
        "errors_removed_rows": errors_removed,
        "errors_removed_ratio": round(errors_removed / (total_rows - int(dataframe["correct"].sum())), 4)
        if total_rows > int(dataframe["correct"].sum())
        else 0.0,
        "avg_max_probability_kept": safe_mean(kept_dataframe, "max_probability"),
        "avg_prob_draw_kept": safe_mean(kept_dataframe, "prob_draw"),
        "avg_gap_vs_draw_kept": safe_mean(kept_dataframe, "top_probability_gap_vs_draw"),
        "avg_abs_team_strength_diff_kept": safe_mean(kept_dataframe, "abs_team_strength_diff"),
        "avg_abs_home_away_context_diff_kept": safe_mean(kept_dataframe, "abs_home_away_context_diff"),
        "usable_gate": kept_rows >= MIN_ROWS_FOR_USABLE_GATE and retained_coverage >= MIN_RETENTION_FOR_USABLE_GATE,
    }


# Calcule une moyenne arrondie quand la colonne existe, sinon retourne une valeur vide lisible.
def safe_mean(dataframe: pd.DataFrame, column: str):
    if column not in dataframe.columns or dataframe.empty:
        return ""

    value = pd.to_numeric(dataframe[column], errors="coerce").mean()

    if pd.isna(value):
        return ""

    return round(float(value), 4)


# Évalue tous les filtres candidats et classe les résultats selon précision puis couverture conservée.
def evaluate_all_gates(dataframe: pd.DataFrame) -> pd.DataFrame:
    gates = build_gate_definitions(dataframe)
    results = [evaluate_gate(dataframe, gate) for gate in gates]
    results_dataframe = pd.DataFrame(results)

    return results_dataframe.sort_values(
        by=["usable_gate", "accuracy", "retention_on_high_confidence", "actual_draw_removed_ratio"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


# Sélectionne le meilleur filtre utilisable selon une logique réaliste : améliorer l'accuracy sans tuer toute la couverture.
def select_best_usable_gate(results_dataframe: pd.DataFrame) -> pd.Series:
    usable = results_dataframe[
        (results_dataframe["usable_gate"])
        & (results_dataframe["gate_name"] != "baseline_keep_all")
        & (results_dataframe["accuracy"] > BASELINE_ACCURACY_REFERENCE)
    ].copy()

    if usable.empty:
        baseline = results_dataframe[results_dataframe["gate_name"] == "baseline_keep_all"]
        return baseline.iloc[0] if not baseline.empty else results_dataframe.iloc[0]

    usable = usable.sort_values(
        by=["accuracy", "retention_on_high_confidence", "actual_draw_removed_ratio"],
        ascending=[False, False, False],
    )
    return usable.iloc[0]


# Crée une matrice de confusion lisible sur les lignes conservées par le meilleur filtre.
def build_best_gate_confusion_matrix(dataframe: pd.DataFrame, best_gate_name: str) -> pd.DataFrame:
    gate = next(gate for gate in build_gate_definitions(dataframe) if gate.name == best_gate_name)
    risk_mask = gate.risk_mask_builder(dataframe).fillna(False).astype(bool)
    kept_dataframe = dataframe.loc[~risk_mask].copy()

    return pd.crosstab(
        kept_dataframe["actual_result"],
        kept_dataframe["predicted_result"],
        rownames=["actual_result"],
        colnames=["predicted_result"],
        dropna=False,
    )


# Rédige une synthèse claire des résultats pour lecture rapide en preuve RNCP/ML.
def write_summary(dataframe: pd.DataFrame, results_dataframe: pd.DataFrame, best_gate: pd.Series) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_row = results_dataframe[results_dataframe["gate_name"] == "baseline_keep_all"].iloc[0]
    top_usable = results_dataframe[results_dataframe["usable_gate"]].head(8)
    best_confusion = build_best_gate_confusion_matrix(dataframe, str(best_gate["gate_name"]))

    lines = [
        "RubyBets - ML 1X2 draw risk gate experiment",
        "57 - Synthese du filtre de risque DRAW",
        "",
        "Positionnement :",
        "Cette experimentation applique des filtres de risque de match nul sur les predictions forte confiance V3.",
        "Elle ne reentraine aucun modele, ne modifie pas PostgreSQL, ne modifie pas l'API, ne touche pas au frontend et ne remplace aucun modele sauvegarde.",
        "Le scoring explicable V1 reste le socle produit.",
        "",
        "Fichier analyse :",
        f"- Input : {INPUT_CSV_PATH.relative_to(PROJECT_ROOT)}",
        f"- Output summary : {SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)}",
        f"- Output CSV : {RESULTS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}",
        f"- Output decision : {DECISION_OUTPUT_PATH.relative_to(PROJECT_ROOT)}",
        "",
        "Reference forte confiance V3 avant filtre :",
        f"- Selected rows : {int(baseline_row['kept_rows'])}",
        f"- Accuracy : {baseline_row['accuracy']:.4f}",
        f"- Coverage test : {baseline_row['test_coverage']:.4f}",
        f"- Actual DRAW kept/missed rows : {int(baseline_row['actual_draw_kept_rows'])}",
        "",
        "Meilleur filtre utilisable observe :",
        f"- Gate : {best_gate['gate_name']}",
        f"- Description : {best_gate['description']}",
        f"- Kept rows : {int(best_gate['kept_rows'])}",
        f"- Removed rows : {int(best_gate['removed_rows'])}",
        f"- Accuracy : {best_gate['accuracy']:.4f}",
        f"- Accuracy gain vs baseline forte confiance : {best_gate['accuracy_gain_vs_baseline']:.4f}",
        f"- Retention on high-confidence rows : {best_gate['retention_on_high_confidence']:.4f}",
        f"- Coverage test : {best_gate['test_coverage']:.4f}",
        f"- Actual DRAW removed rows : {int(best_gate['actual_draw_removed_rows'])}",
        f"- Actual DRAW removed ratio : {best_gate['actual_draw_removed_ratio']:.4f}",
        f"- Errors removed rows : {int(best_gate['errors_removed_rows'])}",
        f"- Errors removed ratio : {best_gate['errors_removed_ratio']:.4f}",
        "",
        "Top filtres utilisables :",
    ]

    if top_usable.empty:
        lines.append("- Aucun filtre utilisable selon les contraintes minimales.")
    else:
        for _, row in top_usable.iterrows():
            lines.append(
                "- "
                f"gate={row['gate_name']} | kept={int(row['kept_rows'])} | removed={int(row['removed_rows'])} | "
                f"accuracy={row['accuracy']:.4f} | gain={row['accuracy_gain_vs_baseline']:.4f} | "
                f"retention={row['retention_on_high_confidence']:.4f} | test_coverage={row['test_coverage']:.4f} | "
                f"draw_removed={int(row['actual_draw_removed_rows'])}"
            )

    lines.extend(
        [
            "",
            "Matrice de confusion apres meilleur filtre :",
            best_confusion.to_string(),
            "",
            "Lecture metier :",
            "- Le filtre DRAW ne cherche pas a predire les matchs nuls directement.",
            "- Il sert a retirer les matchs ou le risque de nul rend la forte confiance moins fiable.",
            "- Si l'accuracy augmente fortement mais que la couverture devient trop faible, le filtre doit rester experimental.",
            "- Un filtre utile pour RubyBets doit ameliorer la precision tout en conservant assez de matchs exploitables.",
            "",
            "Generated files :",
            str(SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
            str(RESULTS_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        ]
    )

    SUMMARY_OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


# Rédige une décision courte indiquant si le filtre DRAW mérite d'être conservé comme prochaine piste expérimentale.
def write_decision(best_gate: pd.Series) -> None:
    improves_accuracy = float(best_gate["accuracy"]) > BASELINE_ACCURACY_REFERENCE
    keeps_enough_rows = bool(best_gate["usable_gate"])
    removes_draws = int(best_gate["actual_draw_removed_rows"]) > 0

    if improves_accuracy and keeps_enough_rows:
        decision = (
            "Decision : piste utile. Le filtre de risque DRAW ameliore la precision de la forte confiance "
            "tout en conservant une couverture encore exploitable. Il peut devenir la prochaine brique experimentale : "
            "V2 globale + selection forte confiance V3 + filtre risque DRAW."
        )
    elif improves_accuracy and not keeps_enough_rows:
        decision = (
            "Decision : piste trop restrictive. Le filtre ameliore la precision mais retire trop de matchs pour etre utile "
            "dans l'etat actuel. Il peut servir d'indicateur de risque mais pas de gate principal."
        )
    else:
        decision = (
            "Decision : ne pas retenir comme gate principal. Les filtres testes ne battent pas clairement la reference "
            "forte confiance V3 avec une couverture suffisante."
        )

    lines = [
        "RubyBets - ML 1X2 draw risk gate decision",
        "59 - Decision apres test du filtre de risque DRAW",
        "",
        "Decision de perimetre :",
        "- Aucun modele officiel n'est remplace.",
        "- Aucun modele candidat n'est sauvegarde automatiquement.",
        "- PostgreSQL, ml.features, l'API et le frontend ne sont pas modifies.",
        "- Les resultats restent des preuves experimentales dans reports/evidence/ml_training/.",
        "",
        "Reference forte confiance V3 avant filtre :",
        f"- Accuracy : {BASELINE_ACCURACY_REFERENCE:.4f}",
        f"- Selected rows : {BASELINE_SELECTED_ROWS_REFERENCE}",
        f"- Coverage test : {BASELINE_SELECTED_ROWS_REFERENCE / TEST_ROWS_REFERENCE:.4f}",
        f"- Missed DRAW rows : {BASELINE_MISSED_DRAW_REFERENCE}",
        "",
        "Meilleur filtre observe :",
        f"- Gate : {best_gate['gate_name']}",
        f"- Description : {best_gate['description']}",
        f"- Kept rows : {int(best_gate['kept_rows'])}",
        f"- Removed rows : {int(best_gate['removed_rows'])}",
        f"- Accuracy : {best_gate['accuracy']:.4f}",
        f"- Accuracy gain : {best_gate['accuracy_gain_vs_baseline']:.4f}",
        f"- Retention on high-confidence rows : {best_gate['retention_on_high_confidence']:.4f}",
        f"- Coverage test : {best_gate['test_coverage']:.4f}",
        f"- Actual DRAW removed rows : {int(best_gate['actual_draw_removed_rows'])}",
        f"- Actual DRAW removed ratio : {best_gate['actual_draw_removed_ratio']:.4f}",
        f"- Errors removed rows : {int(best_gate['errors_removed_rows'])}",
        f"- Errors removed ratio : {best_gate['errors_removed_ratio']:.4f}",
        f"- Ameliore accuracy : {improves_accuracy}",
        f"- Couverture suffisante : {keeps_enough_rows}",
        f"- Retire des vrais DRAW : {removes_draws}",
        "",
        "Decision finale :",
        decision,
        "",
        "Formulation soutenance :",
        "RubyBets a teste un filtre de risque de match nul pour securiser la selection forte confiance V3.",
        "L'objectif n'est pas de promettre une prediction parfaite, mais d'identifier les matchs trop equilibres a exclure de la forte confiance.",
        "Cette approche reste experimentale et separee du scoring explicable V1.",
        "",
        "Statut de suivi :",
        "- Tache realisee : experimentation du filtre de risque DRAW sur les predictions forte confiance V3.",
        "- Statut source a mettre a jour : realise si les fichiers 57, 58 et 59 sont generes.",
        "- Fichiers concernes : reports/evidence/ml_training/57, 58 et 59.",
    ]

    DECISION_OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


# Lance l'expérimentation complète : chargement, test des gates, export CSV, synthèse et décision.
def main() -> None:
    print("Chargement des predictions forte confiance V3...")
    dataframe = load_high_confidence_predictions()
    print(f"Predictions chargees : {len(dataframe)}")

    print("Evaluation des filtres de risque DRAW...")
    results_dataframe = evaluate_all_gates(dataframe)
    best_gate = select_best_usable_gate(results_dataframe)

    print("Generation des fichiers de synthese et de decision...")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results_dataframe.to_csv(RESULTS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    write_summary(dataframe, results_dataframe, best_gate)
    write_decision(best_gate)

    print("OK - Experimentation du filtre de risque DRAW terminee.")
    print(f"Best gate: {best_gate['gate_name']}")
    print(f"Kept rows: {int(best_gate['kept_rows'])}")
    print(f"Removed rows: {int(best_gate['removed_rows'])}")
    print(f"Accuracy: {best_gate['accuracy']:.4f}")
    print(f"Accuracy gain: {best_gate['accuracy_gain_vs_baseline']:.4f}")
    print(f"Retention: {best_gate['retention_on_high_confidence']:.4f}")
    print(f"Test coverage: {best_gate['test_coverage']:.4f}")
    print(f"Actual DRAW removed rows: {int(best_gate['actual_draw_removed_rows'])}")
    print(f"Summary saved: {SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"CSV saved: {RESULTS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Decision saved: {DECISION_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
#
# reports/evidence/ml_training/53_1x2_v3_high_confidence_predictions.csv
#        ↓ lecture
# experiment_1x2_draw_risk_gate.py
#        ↓ écrit
# reports/evidence/ml_training/57_1x2_draw_risk_gate_summary.txt
# reports/evidence/ml_training/58_1x2_draw_risk_gate_results.csv
# reports/evidence/ml_training/59_1x2_draw_risk_gate_decision.txt
#
# Aucun échange avec PostgreSQL, models/ml/1x2/, backend/app/api/ ou frontend/.
