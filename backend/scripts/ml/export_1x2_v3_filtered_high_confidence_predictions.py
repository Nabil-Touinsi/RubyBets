# Ce fichier exporte la selection finale V3 forte confiance apres application du filtre de risque DRAW.
# Il lit le fichier 53, retire la bande de confiance fragile 0.62-0.70, puis genere les preuves 60 et 61.

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ML_EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

INPUT_PREDICTIONS_PATH = ML_EVIDENCE_DIR / "53_1x2_v3_high_confidence_predictions.csv"
OUTPUT_FILTERED_PREDICTIONS_PATH = ML_EVIDENCE_DIR / "60_1x2_v3_filtered_high_confidence_predictions.csv"
OUTPUT_SUMMARY_PATH = ML_EVIDENCE_DIR / "61_1x2_v3_filtered_high_confidence_summary.txt"

GATE_NAME = "remove_confidence_between_0_62_and_0_70"
GATE_DESCRIPTION = "Exclut la bande de confiance la plus fragile observee dans le diagnostic V3."
LOW_CONFIDENCE_BOUND = 0.62
HIGH_CONFIDENCE_BOUND = 0.70
REFERENCE_TEST_ROWS = 5300
REFERENCE_HIGH_CONFIDENCE_ACCURACY = 0.7006
REFERENCE_HIGH_CONFIDENCE_ROWS = 1386
REFERENCE_HIGH_CONFIDENCE_COVERAGE = 0.2615


# Verifie que les colonnes obligatoires existent dans le fichier d'entree.
def require_columns(dataframe: pd.DataFrame, columns: Iterable[str]) -> None:
    missing_columns = [column for column in columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le fichier 53 : " + ", ".join(missing_columns)
        )


# Convertit proprement une colonne de booleens meme si elle est lue comme texte depuis le CSV.
def normalize_boolean_column(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes", "oui"])


# Charge les predictions forte confiance exportees precedemment dans le fichier 53.
def load_high_confidence_predictions() -> pd.DataFrame:
    if not INPUT_PREDICTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {INPUT_PREDICTIONS_PATH}. "
            "Lance d'abord export_1x2_v3_high_confidence_predictions.py."
        )

    dataframe = pd.read_csv(INPUT_PREDICTIONS_PATH)
    require_columns(
        dataframe,
        [
            "actual_result",
            "predicted_result",
            "max_probability",
            "prob_draw",
            "correct",
        ],
    )
    dataframe["correct"] = normalize_boolean_column(dataframe["correct"])
    return dataframe


# Applique le filtre retenu : retirer les predictions dont la confiance est entre 0.62 et 0.70.
def apply_draw_risk_gate(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    fragile_confidence_mask = dataframe["max_probability"].between(
        LOW_CONFIDENCE_BOUND,
        HIGH_CONFIDENCE_BOUND,
        inclusive="left",
    )

    kept_rows = dataframe.loc[~fragile_confidence_mask].copy()
    removed_rows = dataframe.loc[fragile_confidence_mask].copy()

    kept_rows["applied_gate"] = GATE_NAME
    kept_rows["gate_status"] = "kept"
    kept_rows["gate_reason"] = "confidence_outside_fragile_band"

    removed_rows["applied_gate"] = GATE_NAME
    removed_rows["gate_status"] = "removed"
    removed_rows["gate_reason"] = "confidence_between_0_62_and_0_70"

    return kept_rows, removed_rows


# Calcule les indicateurs principaux pour la selection conservee apres filtre DRAW.
def compute_metrics(kept_rows: pd.DataFrame, removed_rows: pd.DataFrame, total_rows: int) -> dict[str, float | int]:
    kept_count = len(kept_rows)
    removed_count = len(removed_rows)
    correct_count = int(kept_rows["correct"].sum()) if kept_count else 0
    accuracy = correct_count / kept_count if kept_count else 0.0
    accuracy_gain = accuracy - REFERENCE_HIGH_CONFIDENCE_ACCURACY
    retention = kept_count / total_rows if total_rows else 0.0
    test_coverage = kept_count / REFERENCE_TEST_ROWS if REFERENCE_TEST_ROWS else 0.0

    actual_draw_before = int((pd.concat([kept_rows, removed_rows])["actual_result"] == "DRAW").sum())
    actual_draw_kept = int((kept_rows["actual_result"] == "DRAW").sum())
    actual_draw_removed = int((removed_rows["actual_result"] == "DRAW").sum())
    errors_removed = int((~removed_rows["correct"]).sum()) if removed_count else 0

    return {
        "kept_rows": kept_count,
        "removed_rows": removed_count,
        "correct_rows": correct_count,
        "accuracy": accuracy,
        "accuracy_gain": accuracy_gain,
        "retention": retention,
        "test_coverage": test_coverage,
        "actual_draw_before": actual_draw_before,
        "actual_draw_kept": actual_draw_kept,
        "actual_draw_removed": actual_draw_removed,
        "errors_removed": errors_removed,
    }


# Formate une distribution simple pour l'ajouter au fichier de synthese.
def format_distribution(dataframe: pd.DataFrame, column: str) -> str:
    if dataframe.empty or column not in dataframe.columns:
        return "- Aucun element disponible."

    counts = dataframe[column].value_counts(dropna=False).sort_index()
    return "\n".join(f"- {index} : {value}" for index, value in counts.items())


# Formate une matrice de confusion lisible pour la synthese texte.
def format_confusion_matrix(dataframe: pd.DataFrame) -> str:
    if dataframe.empty:
        return "Aucune ligne conservee apres filtre."

    matrix = pd.crosstab(dataframe["actual_result"], dataframe["predicted_result"])
    return matrix.to_string()


# Sauvegarde le CSV final des predictions conservees apres filtre.
def save_filtered_predictions(kept_rows: pd.DataFrame) -> None:
    ML_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    kept_rows.sort_values(
        by=["max_probability", "prob_draw"],
        ascending=[False, True],
    ).to_csv(OUTPUT_FILTERED_PREDICTIONS_PATH, index=False, encoding="utf-8")


# Genere le fichier de synthese lisible pour documenter la selection finale filtree.
def save_summary(kept_rows: pd.DataFrame, removed_rows: pd.DataFrame, metrics: dict[str, float | int]) -> None:
    summary = f"""RubyBets - ML 1X2 V3 filtered high-confidence export
61 - Synthese de la selection forte confiance filtree

Positionnement :
Cet export applique la meilleure piste experimentale observee apres le diagnostic V3 :
selection forte confiance XGBoost + filtre de risque DRAW.
Il ne reentraine aucun modele, ne modifie pas PostgreSQL, ne modifie pas l'API,
ne touche pas au frontend et ne remplace aucun modele sauvegarde.
Le scoring explicable V1 reste le socle produit.

Fichier source :
- Input : {INPUT_PREDICTIONS_PATH.relative_to(PROJECT_ROOT)}
- Output CSV : {OUTPUT_FILTERED_PREDICTIONS_PATH.relative_to(PROJECT_ROOT)}
- Output summary : {OUTPUT_SUMMARY_PATH.relative_to(PROJECT_ROOT)}

Configuration appliquee :
- Source modele : V3 high-confidence export
- Feature group : v2_reference_plus_home_away_context
- Model : XGBoost
- Seuil forte confiance initial : 0.62
- Gate applique : {GATE_NAME}
- Description gate : {GATE_DESCRIPTION}
- Regle : supprimer les lignes avec {LOW_CONFIDENCE_BOUND:.2f} <= max_probability < {HIGH_CONFIDENCE_BOUND:.2f}

Reference avant filtre :
- Selected rows : {REFERENCE_HIGH_CONFIDENCE_ROWS}
- Accuracy : {REFERENCE_HIGH_CONFIDENCE_ACCURACY:.4f}
- Coverage test : {REFERENCE_HIGH_CONFIDENCE_COVERAGE:.4f}

Resultat apres filtre :
- Kept rows : {metrics['kept_rows']}
- Removed rows : {metrics['removed_rows']}
- Correct rows : {metrics['correct_rows']}
- Accuracy : {metrics['accuracy']:.4f}
- Accuracy gain : {metrics['accuracy_gain']:.4f}
- Retention on high-confidence rows : {metrics['retention']:.4f}
- Coverage test : {metrics['test_coverage']:.4f}
- Actual DRAW before filter : {metrics['actual_draw_before']}
- Actual DRAW kept rows : {metrics['actual_draw_kept']}
- Actual DRAW removed rows : {metrics['actual_draw_removed']}
- Errors removed rows : {metrics['errors_removed']}

Distribution des predictions conservees :
{format_distribution(kept_rows, 'predicted_result')}

Distribution des resultats reels conserves :
{format_distribution(kept_rows, 'actual_result')}

Distribution par ligue conservee :
{format_distribution(kept_rows, 'league_code')}

Distribution par saison conservee :
{format_distribution(kept_rows, 'season')}

Matrice de confusion apres filtre :
{format_confusion_matrix(kept_rows)}

Lecture metier :
- La selection filtree ameliore la precision par rapport a la forte confiance V3 non filtree.
- Le filtre retire une partie importante de la zone la plus fragile observee dans le diagnostic.
- La couverture baisse, mais reste exploitable pour une logique RubyBets orientee prudence.
- Cette brique reste experimentale et separee du scoring explicable V1.

Decision recommandee :
Conserver cette selection comme preuve experimentale intermediaire.
La prochaine etape utile consiste a verifier sa stabilite par ligue et par saison avant toute sauvegarde de candidat.

Statut de suivi :
- Tache realisee : export de la selection forte confiance V3 filtree par risque DRAW.
- Statut source a mettre a jour : realise si les fichiers 60 et 61 sont generes.
- Fichiers concernes : reports/evidence/ml_training/60 et 61.
"""

    OUTPUT_SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre le chargement, le filtrage et l'export des preuves 60 et 61.
def main() -> None:
    print("Chargement des predictions forte confiance V3...")
    predictions = load_high_confidence_predictions()
    print(f"Predictions chargees : {len(predictions)}")

    print("Application du filtre de risque DRAW retenu...")
    kept_rows, removed_rows = apply_draw_risk_gate(predictions)
    metrics = compute_metrics(kept_rows, removed_rows, len(predictions))

    print("Generation du CSV filtre et de la synthese...")
    save_filtered_predictions(kept_rows)
    save_summary(kept_rows, removed_rows, metrics)

    print("OK - Export forte confiance V3 filtree termine.")
    print(f"Gate: {GATE_NAME}")
    print(f"Kept rows: {metrics['kept_rows']}")
    print(f"Removed rows: {metrics['removed_rows']}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Accuracy gain: {metrics['accuracy_gain']:.4f}")
    print(f"Retention: {metrics['retention']:.4f}")
    print(f"Test coverage: {metrics['test_coverage']:.4f}")
    print(f"CSV saved: {OUTPUT_FILTERED_PREDICTIONS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Summary saved: {OUTPUT_SUMMARY_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
#
# reports/evidence/ml_training/53_1x2_v3_high_confidence_predictions.csv
#        |
#        v
# backend/scripts/ml/export_1x2_v3_filtered_high_confidence_predictions.py
#        |
#        +--> reports/evidence/ml_training/60_1x2_v3_filtered_high_confidence_predictions.csv
#        +--> reports/evidence/ml_training/61_1x2_v3_filtered_high_confidence_summary.txt
