# Ce fichier analyse la stabilite de la selection V3 forte confiance apres filtre DRAW.
# Il lit le fichier 60, calcule les performances par segments, puis genere les preuves 62 et 63.

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ML_EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

INPUT_FILTERED_PREDICTIONS_PATH = ML_EVIDENCE_DIR / "60_1x2_v3_filtered_high_confidence_predictions.csv"
OUTPUT_SUMMARY_PATH = ML_EVIDENCE_DIR / "62_1x2_v3_filtered_stability_summary.txt"
OUTPUT_CSV_PATH = ML_EVIDENCE_DIR / "63_1x2_v3_filtered_stability.csv"

REFERENCE_HIGH_CONFIDENCE_ACCURACY = 0.7006
REFERENCE_FILTERED_ACCURACY = 0.7455
REFERENCE_TEST_ROWS = 5300
MIN_SEGMENT_ROWS = 30
TARGET_STABILITY_ACCURACY = 0.70


# Verifie que les colonnes obligatoires existent dans le fichier analyse.
def require_columns(dataframe: pd.DataFrame, columns: Iterable[str]) -> None:
    missing_columns = [column for column in columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le fichier 60 : " + ", ".join(missing_columns)
        )


# Convertit proprement une colonne de booleens meme si elle est lue comme texte depuis le CSV.
def normalize_boolean_column(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes", "oui"])


# Formate un nombre decimal pour les fichiers de synthese.
def format_float(value: float, digits: int = 4) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


# Charge la selection V3 filtree produite par le script precedent.
def load_filtered_predictions() -> pd.DataFrame:
    if not INPUT_FILTERED_PREDICTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {INPUT_FILTERED_PREDICTIONS_PATH}. "
            "Lance d'abord export_1x2_v3_filtered_high_confidence_predictions.py."
        )

    dataframe = pd.read_csv(INPUT_FILTERED_PREDICTIONS_PATH)
    require_columns(
        dataframe,
        [
            "league_code",
            "season",
            "actual_result",
            "predicted_result",
            "max_probability",
            "prob_draw",
            "prob_home_win",
            "prob_away_win",
            "correct",
        ],
    )
    dataframe["correct"] = normalize_boolean_column(dataframe["correct"])
    return dataframe


# Cree une bande de valeurs a partir de seuils fixes.
def create_fixed_band(series: pd.Series, bins: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(series, bins=bins, labels=labels, include_lowest=True, right=False).astype(str)


# Cree trois bandes low / medium / high a partir des quantiles observes.
def create_quantile_band(series: pd.Series, prefix: str) -> pd.Series:
    clean_series = pd.to_numeric(series, errors="coerce")
    first_quantile = clean_series.quantile(1 / 3)
    second_quantile = clean_series.quantile(2 / 3)

    if pd.isna(first_quantile) or pd.isna(second_quantile) or first_quantile == second_quantile:
        return pd.Series([f"{prefix}_flat"] * len(series), index=series.index)

    return pd.Series(
        [
            f"low_{prefix}" if value <= first_quantile else f"medium_{prefix}" if value <= second_quantile else f"high_{prefix}"
            for value in clean_series
        ],
        index=series.index,
    )


# Ajoute les colonnes de segmentation utiles pour analyser la stabilite de la selection filtree.
def add_stability_segments(dataframe: pd.DataFrame) -> pd.DataFrame:
    enriched = dataframe.copy()

    enriched["confidence_band"] = create_fixed_band(
        enriched["max_probability"],
        bins=[0.0, 0.70, 0.80, 0.90, 1.01],
        labels=["below_0_70", "0_70_0_80", "0_80_0_90", "0_90_1_00"],
    )
    enriched["prob_draw_band"] = create_fixed_band(
        enriched["prob_draw"],
        bins=[0.0, 0.05, 0.10, 0.15, 0.20, 0.31, 1.01],
        labels=["0_00_0_05", "0_05_0_10", "0_10_0_15", "0_15_0_20", "0_20_0_30", "0_30_plus"],
    )

    if "home_away_context_diff" in enriched.columns:
        enriched["abs_home_away_context_diff"] = enriched["home_away_context_diff"].abs()
        enriched["home_away_context_gap_band"] = create_quantile_band(
            enriched["abs_home_away_context_diff"],
            "context_gap",
        )

    if "team_strength_diff" in enriched.columns:
        enriched["abs_team_strength_diff"] = enriched["team_strength_diff"].abs()
        enriched["team_strength_gap_band"] = create_quantile_band(
            enriched["abs_team_strength_diff"],
            "strength_gap",
        )

    if "draw_profile_score_with_strength" in enriched.columns:
        enriched["draw_profile_score_band"] = create_quantile_band(
            enriched["draw_profile_score_with_strength"],
            "draw_profile",
        )

    enriched["league_season"] = enriched["league_code"].astype(str) + "_" + enriched["season"].astype(str)
    enriched["prediction_side"] = enriched["predicted_result"].replace(
        {
            "HOME_WIN": "home_prediction",
            "AWAY_WIN": "away_prediction",
            "DRAW": "draw_prediction",
        }
    )

    return enriched


# Calcule les indicateurs de performance pour un sous-ensemble donne.
def compute_segment_metrics(segment: pd.DataFrame) -> dict[str, float | int]:
    rows = len(segment)
    correct_rows = int(segment["correct"].sum()) if rows else 0
    error_rows = rows - correct_rows
    accuracy = correct_rows / rows if rows else 0.0

    actual_home_rows = int((segment["actual_result"] == "HOME_WIN").sum())
    actual_draw_rows = int((segment["actual_result"] == "DRAW").sum())
    actual_away_rows = int((segment["actual_result"] == "AWAY_WIN").sum())
    predicted_home_rows = int((segment["predicted_result"] == "HOME_WIN").sum())
    predicted_draw_rows = int((segment["predicted_result"] == "DRAW").sum())
    predicted_away_rows = int((segment["predicted_result"] == "AWAY_WIN").sum())

    return {
        "rows": rows,
        "correct_rows": correct_rows,
        "error_rows": error_rows,
        "accuracy": accuracy,
        "error_rate": error_rows / rows if rows else 0.0,
        "actual_home_rows": actual_home_rows,
        "actual_draw_rows": actual_draw_rows,
        "actual_away_rows": actual_away_rows,
        "actual_draw_rate": actual_draw_rows / rows if rows else 0.0,
        "predicted_home_rows": predicted_home_rows,
        "predicted_draw_rows": predicted_draw_rows,
        "predicted_away_rows": predicted_away_rows,
        "avg_max_probability": float(segment["max_probability"].mean()) if rows else 0.0,
        "avg_prob_draw": float(segment["prob_draw"].mean()) if rows else 0.0,
        "avg_prob_home_win": float(segment["prob_home_win"].mean()) if rows else 0.0,
        "avg_prob_away_win": float(segment["prob_away_win"].mean()) if rows else 0.0,
    }


# Construit les lignes du CSV de stabilite pour un type de segment.
def build_segment_rows(dataframe: pd.DataFrame, segment_column: str, segment_type: str) -> list[dict[str, object]]:
    if segment_column not in dataframe.columns:
        return []

    rows: list[dict[str, object]] = []
    for segment_value, segment in dataframe.groupby(segment_column, dropna=False):
        metrics = compute_segment_metrics(segment)
        metrics.update(
            {
                "segment_type": segment_type,
                "segment_value": str(segment_value),
            }
        )
        rows.append(metrics)

    return rows


# Construit le tableau complet des performances par segment.
def build_stability_table(dataframe: pd.DataFrame) -> pd.DataFrame:
    segment_definitions = [
        ("league_code", "by_league"),
        ("season", "by_season"),
        ("league_season", "by_league_season"),
        ("actual_result", "by_actual_result"),
        ("predicted_result", "by_predicted_result"),
        ("prediction_side", "by_prediction_side"),
        ("confidence_band", "by_confidence_band"),
        ("prob_draw_band", "by_prob_draw_band"),
        ("home_away_context_gap_band", "by_home_away_context_gap"),
        ("team_strength_gap_band", "by_team_strength_gap"),
        ("draw_profile_score_band", "by_draw_profile_score"),
    ]

    segment_rows: list[dict[str, object]] = []
    for column, segment_type in segment_definitions:
        segment_rows.extend(build_segment_rows(dataframe, column, segment_type))

    stability_table = pd.DataFrame(segment_rows)
    if not stability_table.empty:
        ordered_columns = [
            "segment_type",
            "segment_value",
            "rows",
            "correct_rows",
            "error_rows",
            "accuracy",
            "error_rate",
            "actual_home_rows",
            "actual_draw_rows",
            "actual_away_rows",
            "actual_draw_rate",
            "predicted_home_rows",
            "predicted_draw_rows",
            "predicted_away_rows",
            "avg_max_probability",
            "avg_prob_draw",
            "avg_prob_home_win",
            "avg_prob_away_win",
        ]
        stability_table = stability_table[ordered_columns]
        stability_table = stability_table.sort_values(
            by=["segment_type", "accuracy", "rows"],
            ascending=[True, True, False],
        )

    return stability_table


# Formate un petit tableau texte pour la synthese.
def format_table(dataframe: pd.DataFrame, max_rows: int = 20) -> str:
    if dataframe.empty:
        return "Aucun segment disponible."
    return dataframe.head(max_rows).to_string(index=False)


# Extrait les segments les plus utiles a commenter dans le resume.
def extract_key_segments(stability_table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    reliable_segments = stability_table[stability_table["rows"] >= MIN_SEGMENT_ROWS].copy()

    league_rows = stability_table[stability_table["segment_type"] == "by_league"].copy()
    season_rows = stability_table[stability_table["segment_type"] == "by_season"].copy()
    league_season_rows = stability_table[stability_table["segment_type"] == "by_league_season"].copy()

    weakest_segments = reliable_segments.sort_values(
        by=["accuracy", "rows"],
        ascending=[True, False],
    )
    strongest_segments = reliable_segments.sort_values(
        by=["accuracy", "rows"],
        ascending=[False, False],
    )
    draw_heavy_segments = reliable_segments.sort_values(
        by=["actual_draw_rate", "actual_draw_rows", "rows"],
        ascending=[False, False, False],
    )

    return {
        "league_rows": league_rows,
        "season_rows": season_rows,
        "league_season_rows": league_season_rows,
        "weakest_segments": weakest_segments,
        "strongest_segments": strongest_segments,
        "draw_heavy_segments": draw_heavy_segments,
    }


# Genere le contenu texte du fichier de synthese 62.
def build_summary(dataframe: pd.DataFrame, stability_table: pd.DataFrame) -> str:
    metrics = compute_segment_metrics(dataframe)
    test_coverage = metrics["rows"] / REFERENCE_TEST_ROWS if REFERENCE_TEST_ROWS else 0.0
    accuracy_gain_vs_v3_high_confidence = metrics["accuracy"] - REFERENCE_HIGH_CONFIDENCE_ACCURACY
    accuracy_gap_vs_filtered_reference = metrics["accuracy"] - REFERENCE_FILTERED_ACCURACY
    key_segments = extract_key_segments(stability_table)

    league_rows = key_segments["league_rows"]
    season_rows = key_segments["season_rows"]

    min_league_accuracy = float(league_rows["accuracy"].min()) if not league_rows.empty else 0.0
    min_season_accuracy = float(season_rows["accuracy"].min()) if not season_rows.empty else 0.0
    stable_by_league = min_league_accuracy >= TARGET_STABILITY_ACCURACY
    stable_by_season = min_season_accuracy >= TARGET_STABILITY_ACCURACY

    if stable_by_league and stable_by_season:
        decision = "Decision : selection stable par ligue et par saison au seuil de 70%."
    else:
        decision = "Decision : selection utile, mais certaines zones doivent rester surveillees avant sauvegarde d'un candidat."

    return f"""RubyBets - ML 1X2 V3 filtered stability analysis
62 - Synthese de stabilite de la selection forte confiance filtree

Positionnement :
Cette analyse verifie la stabilite de la selection forte confiance V3 apres filtre DRAW.
Elle ne reentraine aucun modele, ne modifie pas PostgreSQL, ne modifie pas l'API,
ne touche pas au frontend et ne remplace aucun modele sauvegarde.
Le scoring explicable V1 reste le socle produit.

Fichier analyse :
- Input : {INPUT_FILTERED_PREDICTIONS_PATH}
- Output summary : {OUTPUT_SUMMARY_PATH}
- Output CSV : {OUTPUT_CSV_PATH}

Reference avant filtre DRAW :
- Accuracy forte confiance V3 non filtree : {format_float(REFERENCE_HIGH_CONFIDENCE_ACCURACY)}

Resultat global selection filtree :
- Rows analysed : {metrics['rows']}
- Correct rows : {metrics['correct_rows']}
- Error rows : {metrics['error_rows']}
- Accuracy : {format_float(metrics['accuracy'])}
- Accuracy gain vs V3 forte confiance non filtree : {format_float(accuracy_gain_vs_v3_high_confidence)}
- Accuracy gap vs reference filtree attendue : {format_float(accuracy_gap_vs_filtered_reference)}
- Coverage test : {format_float(test_coverage)}
- Actual DRAW rows kept : {metrics['actual_draw_rows']}
- Actual DRAW rate kept : {format_float(metrics['actual_draw_rate'])}
- Predicted DRAW rows kept : {metrics['predicted_draw_rows']}

Stabilite par ligue :
{format_table(league_rows[['segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_max_probability']] if not league_rows.empty else league_rows)}

Stabilite par saison :
{format_table(season_rows[['segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_max_probability']] if not season_rows.empty else season_rows)}

Stabilite par couple ligue/saison :
{format_table(key_segments['league_season_rows'][['segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_max_probability']] if not key_segments['league_season_rows'].empty else key_segments['league_season_rows'], max_rows=15)}

Segments les plus fragiles avec au moins {MIN_SEGMENT_ROWS} lignes :
{format_table(key_segments['weakest_segments'][['segment_type', 'segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_max_probability']], max_rows=12)}

Segments les plus solides avec au moins {MIN_SEGMENT_ROWS} lignes :
{format_table(key_segments['strongest_segments'][['segment_type', 'segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_max_probability']], max_rows=12)}

Segments qui conservent le plus de profils DRAW :
{format_table(key_segments['draw_heavy_segments'][['segment_type', 'segment_value', 'rows', 'accuracy', 'actual_draw_rows', 'actual_draw_rate', 'avg_prob_draw']], max_rows=12)}

Lecture metier :
- La selection filtree doit etre jugee sur sa stabilite, pas seulement sur son accuracy globale.
- Une performance stable par ligue et par saison est un meilleur signal qu'un gain global isole.
- Les vrais matchs nuls restent la principale source d'erreur car la selection ne predit toujours pas DRAW.
- Si certaines ligues restent sous 70%, il faudra garder une limite explicite ou ajouter un filtre par segment.

Decision recommandee :
{decision}

Statut de suivi :
- Tache realisee : analyse de stabilite de la selection forte confiance V3 filtree.
- Statut source a mettre a jour : realise si les fichiers 62 et 63 sont generes.
- Fichiers concernes : reports/evidence/ml_training/62 et 63.
"""


# Sauvegarde le CSV de stabilite et la synthese lisible.
def save_outputs(dataframe: pd.DataFrame, stability_table: pd.DataFrame) -> None:
    ML_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stability_table.to_csv(OUTPUT_CSV_PATH, index=False, encoding="utf-8")
    OUTPUT_SUMMARY_PATH.write_text(
        build_summary(dataframe, stability_table),
        encoding="utf-8",
    )


# Orchestre l'analyse complete de stabilite.
def main() -> None:
    print("Chargement de la selection forte confiance V3 filtree...")
    dataframe = load_filtered_predictions()
    print(f"Predictions filtrees chargees : {len(dataframe)}")

    print("Construction des segments de stabilite...")
    enriched_dataframe = add_stability_segments(dataframe)
    stability_table = build_stability_table(enriched_dataframe)

    print("Generation du CSV de stabilite et de la synthese...")
    save_outputs(enriched_dataframe, stability_table)

    global_metrics = compute_segment_metrics(enriched_dataframe)
    print("OK - Analyse de stabilite V3 filtree terminee.")
    print(f"Rows analysed: {global_metrics['rows']}")
    print(f"Correct rows: {global_metrics['correct_rows']}")
    print(f"Error rows: {global_metrics['error_rows']}")
    print(f"Accuracy: {global_metrics['accuracy']:.4f}")
    print(f"Actual DRAW rows kept: {global_metrics['actual_draw_rows']}")
    print(f"CSV saved: {OUTPUT_CSV_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Summary saved: {OUTPUT_SUMMARY_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# 60_1x2_v3_filtered_high_confidence_predictions.csv
#        -> analyze_1x2_v3_filtered_stability.py
#        -> 62_1x2_v3_filtered_stability_summary.txt
#        -> 63_1x2_v3_filtered_stability.csv
# Aucun acces PostgreSQL / aucune modification API / aucune modification frontend / aucun modele sauvegarde remplace.
