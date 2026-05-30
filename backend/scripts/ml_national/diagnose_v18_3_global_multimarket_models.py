# Role du fichier :
# Ce script analyse les performances V18.3 global multi-market par segments.
# Il utilise les predictions 348 et le dataset 345 pour produire les diagnostics 349/350 avant de construire le selecteur final.

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


CURRENT_FILE = Path(__file__).resolve()

if len(CURRENT_FILE.parents) >= 4 and CURRENT_FILE.parents[2].name == "backend":
    PROJECT_ROOT = CURRENT_FILE.parents[3]
else:
    PROJECT_ROOT = Path.cwd()

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_DATASET_PATH = EVIDENCE_DIR / "345_v18_3_global_multimarket_dataset.csv"
DEFAULT_COMPARISON_PATH = EVIDENCE_DIR / "347_v18_3_global_multimarket_model_comparison.csv"
DEFAULT_PREDICTIONS_PATH = EVIDENCE_DIR / "348_v18_3_global_multimarket_test_predictions.csv"

SEGMENT_DIAGNOSTICS_FILENAME = "349_v18_3_global_multimarket_segment_diagnostics.csv"
SUMMARY_FILENAME = "350_v18_3_global_multimarket_diagnostics_summary.txt"

MIN_SEGMENT_ROWS_FOR_SUMMARY = 30

MARKETS = {
    "1X2": {
        "target_column": "target_1x2",
        "prediction_column": "1x2_prediction",
        "confidence_column": "1x2_max_probability",
        "model_column": "1x2_model",
        "labels": ["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"],
    },
    "OVER_1_5": {
        "target_column": "target_over_1_5",
        "prediction_column": "over_1_5_prediction",
        "confidence_column": "over_1_5_max_probability",
        "model_column": "over_1_5_model",
        "labels": ["YES", "NO"],
    },
    "OVER_2_5": {
        "target_column": "target_over_2_5",
        "prediction_column": "over_2_5_prediction",
        "confidence_column": "over_2_5_max_probability",
        "model_column": "over_2_5_model",
        "labels": ["YES", "NO"],
    },
    "BTTS": {
        "target_column": "target_btts",
        "prediction_column": "btts_prediction",
        "confidence_column": "btts_max_probability",
        "model_column": "btts_model",
        "labels": ["YES", "NO"],
    },
}

CONTEXT_COLUMNS_FROM_DATASET = [
    "clean_match_id",
    "elo_gap",
    "is_neutral_venue",
    "team_a_is_host",
    "team_b_is_host",
    "host_side_team_a",
    "host_side_team_b",
    "is_group_stage",
    "is_knockout_stage",
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_form_points_last_10",
    "away_form_points_last_10",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
]

BASE_REQUIRED_PREDICTION_COLUMNS = [
    "clean_match_id",
    "match_date_utc",
    "season",
    "competition_code",
    "competition_name",
    "team_a_name",
    "team_b_name",
    "team_a_score",
    "team_b_score",
    "total_goals",
    "split_role",
]

OUTPUT_COLUMNS = [
    "market",
    "segment_family",
    "segment_value",
    "rows",
    "correct_rows",
    "error_rows",
    "accuracy",
    "avg_confidence",
    "min_confidence",
    "max_confidence",
    "target_distribution",
    "prediction_distribution",
    "main_model",
    "note",
]


# Prepare les arguments de ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnostiquer les modeles V18.3 global multi-market par segments."
    )

    parser.add_argument(
        "--dataset-path",
        default=str(DEFAULT_DATASET_PATH),
        help="Chemin du dataset 345 utilise pour recuperer les features de contexte.",
    )
    parser.add_argument(
        "--comparison-path",
        default=str(DEFAULT_COMPARISON_PATH),
        help="Chemin du CSV 347 de comparaison des modeles.",
    )
    parser.add_argument(
        "--predictions-path",
        default=str(DEFAULT_PREDICTIONS_PATH),
        help="Chemin du CSV 348 contenant les predictions du test set.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EVIDENCE_DIR),
        help="Dossier de sortie des preuves 349 et 350.",
    )

    return parser.parse_args()


# Cree le dossier de sortie si necessaire.
def ensure_output_directory(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


# Charge un CSV en controlant son existence et son contenu.
def load_csv_file(csv_path: Path, label: str) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Fichier {label} introuvable : {csv_path}")

    dataframe = pd.read_csv(csv_path)

    if dataframe.empty:
        raise ValueError(f"Le fichier {label} est vide : {csv_path}")

    return dataframe


# Verifie que les colonnes indispensables sont presentes.
def validate_input_columns(predictions: pd.DataFrame, dataset: pd.DataFrame) -> None:
    required_prediction_columns = set(BASE_REQUIRED_PREDICTION_COLUMNS)

    for market_config in MARKETS.values():
        required_prediction_columns.add(str(market_config["target_column"]))
        required_prediction_columns.add(str(market_config["prediction_column"]))
        required_prediction_columns.add(str(market_config["confidence_column"]))
        required_prediction_columns.add(str(market_config["model_column"]))

    missing_prediction_columns = sorted(
        required_prediction_columns - set(predictions.columns)
    )

    if missing_prediction_columns:
        raise ValueError(
            "Colonnes absentes du fichier 348 : "
            + ", ".join(missing_prediction_columns)
        )

    missing_dataset_columns = sorted(
        {"clean_match_id", "elo_gap", "is_group_stage", "is_knockout_stage"}
        - set(dataset.columns)
    )

    if missing_dataset_columns:
        raise ValueError(
            "Colonnes absentes du fichier 345 : " + ", ".join(missing_dataset_columns)
        )


# Fusionne les predictions de test avec les features de contexte du dataset 345.
def merge_predictions_with_context(
    predictions: pd.DataFrame, dataset: pd.DataFrame
) -> pd.DataFrame:
    context_columns = [
        column for column in CONTEXT_COLUMNS_FROM_DATASET if column in dataset.columns
    ]

    context = dataset[context_columns].drop_duplicates(subset=["clean_match_id"])

    enriched = predictions.merge(
        context,
        on="clean_match_id",
        how="left",
        validate="one_to_one",
    )

    return enriched


# Transforme une distribution de classes en texte compact pour le CSV.
def format_distribution(series: pd.Series) -> str:
    counts = series.fillna("UNKNOWN").astype(str).value_counts(dropna=False)
    return " | ".join(f"{label}:{int(count)}" for label, count in counts.items())


# Arrondit proprement les nombres pour les preuves CSV et TXT.
def rounded(value: Any, digits: int = 4) -> float | None:
    if pd.isna(value):
        return None
    return round(float(value), digits)


# Cree les segments generaux utilises pour diagnostiquer les erreurs.
def add_global_segment_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    enriched = dataframe.copy()

    enriched["season_numeric"] = pd.to_numeric(enriched["season"], errors="coerce")
    enriched["elo_gap_numeric"] = pd.to_numeric(enriched.get("elo_gap"), errors="coerce")
    enriched["abs_elo_gap"] = enriched["elo_gap_numeric"].abs()

    enriched["elo_gap_bucket"] = pd.cut(
        enriched["abs_elo_gap"],
        bins=[-0.1, 25, 75, 150, 300, float("inf")],
        labels=[
            "abs_elo_000_025_tres_equilibre",
            "abs_elo_026_075_equilibre",
            "abs_elo_076_150_ecart_moyen",
            "abs_elo_151_300_ecart_fort",
            "abs_elo_301_plus_ecart_tres_fort",
        ],
    ).astype("object")
    enriched["elo_gap_bucket"] = enriched["elo_gap_bucket"].fillna("elo_gap_unknown")

    enriched["elo_advantage_side"] = "elo_unknown_or_equal"
    enriched.loc[enriched["elo_gap_numeric"] > 0, "elo_advantage_side"] = "team_a_elo_advantage"
    enriched.loc[enriched["elo_gap_numeric"] < 0, "elo_advantage_side"] = "team_b_elo_advantage"

    enriched["stage_type"] = "unknown_or_qualification"
    if "competition_code" in enriched.columns:
        enriched.loc[
            enriched["competition_code"].astype(str).str.upper().eq("WCQ"),
            "stage_type",
        ] = "world_cup_qualification"
    if "is_group_stage" in enriched.columns:
        enriched.loc[
            pd.to_numeric(enriched["is_group_stage"], errors="coerce").fillna(0).eq(1),
            "stage_type",
        ] = "group_stage"
    if "is_knockout_stage" in enriched.columns:
        enriched.loc[
            pd.to_numeric(enriched["is_knockout_stage"], errors="coerce").fillna(0).eq(1),
            "stage_type",
        ] = "knockout_stage"

    enriched["host_context"] = "no_declared_host_side"
    for column in ["team_a_is_host", "team_b_is_host", "host_side_team_a", "host_side_team_b"]:
        if column not in enriched.columns:
            enriched[column] = 0

    team_a_host_mask = (
        pd.to_numeric(enriched["team_a_is_host"], errors="coerce").fillna(0).eq(1)
        | pd.to_numeric(enriched["host_side_team_a"], errors="coerce").fillna(0).eq(1)
    )
    team_b_host_mask = (
        pd.to_numeric(enriched["team_b_is_host"], errors="coerce").fillna(0).eq(1)
        | pd.to_numeric(enriched["host_side_team_b"], errors="coerce").fillna(0).eq(1)
    )

    enriched.loc[team_a_host_mask, "host_context"] = "team_a_host"
    enriched.loc[team_b_host_mask, "host_context"] = "team_b_host"

    if "is_neutral_venue" in enriched.columns:
        neutral_mask = pd.to_numeric(
            enriched["is_neutral_venue"], errors="coerce"
        ).fillna(0).eq(1)
        enriched.loc[neutral_mask & ~team_a_host_mask & ~team_b_host_mask, "host_context"] = "neutral_venue"

    enriched["season_period"] = pd.cut(
        enriched["season_numeric"],
        bins=[-float("inf"), 2018, 2022, float("inf")],
        labels=["test_period_2017_2018", "test_period_2019_2022", "test_period_2023_2026"],
    ).astype("object")
    enriched["season_period"] = enriched["season_period"].fillna("season_unknown")

    enriched["actual_total_goals_bucket"] = pd.cut(
        pd.to_numeric(enriched["total_goals"], errors="coerce"),
        bins=[-0.1, 1, 2, 3, float("inf")],
        labels=["goals_0_1", "goals_2", "goals_3", "goals_4_plus"],
    ).astype("object")
    enriched["actual_total_goals_bucket"] = enriched[
        "actual_total_goals_bucket"
    ].fillna("goals_unknown")

    return enriched


# Cree un nom court utilisable pour les colonnes internes de chaque marche.
def normalize_market_key(market: str) -> str:
    return market.lower().replace(".", "_").replace(" ", "_")


# Ajoute les colonnes correct/erreur et les buckets de confiance par marche.
def add_market_segment_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    enriched = dataframe.copy()

    for market, config in MARKETS.items():
        market_key = normalize_market_key(market)
        target_column = str(config["target_column"])
        prediction_column = str(config["prediction_column"])
        confidence_column = str(config["confidence_column"])

        enriched[f"is_correct_{market_key}"] = (
            enriched[prediction_column].astype(str) == enriched[target_column].astype(str)
        )

        confidence_values = pd.to_numeric(enriched[confidence_column], errors="coerce")
        enriched[f"confidence_bucket_{market_key}"] = pd.cut(
            confidence_values,
            bins=[-0.01, 0.45, 0.55, 0.65, 0.75, 0.85, 1.01],
            labels=[
                "conf_000_045_tres_faible",
                "conf_046_055_faible",
                "conf_056_065_moyenne",
                "conf_066_075_bonne",
                "conf_076_085_forte",
                "conf_086_100_tres_forte",
            ],
        ).astype("object")
        enriched[f"confidence_bucket_{market_key}"] = enriched[
            f"confidence_bucket_{market_key}"
        ].fillna("confidence_unknown")

    return enriched


# Calcule les indicateurs d'un segment pour un marche donne.
def build_segment_row(
    dataframe: pd.DataFrame,
    market: str,
    segment_family: str,
    segment_value: str,
    note: str = "",
) -> dict[str, Any]:
    config = MARKETS[market]
    market_key = normalize_market_key(market)
    target_column = str(config["target_column"])
    prediction_column = str(config["prediction_column"])
    confidence_column = str(config["confidence_column"])
    model_column = str(config["model_column"])
    correct_column = f"is_correct_{market_key}"

    rows = int(len(dataframe))
    correct_rows = int(dataframe[correct_column].sum()) if rows else 0
    error_rows = rows - correct_rows
    accuracy = correct_rows / rows if rows else None
    confidence_values = pd.to_numeric(dataframe[confidence_column], errors="coerce")

    main_model = "UNKNOWN"
    if model_column in dataframe.columns and not dataframe[model_column].dropna().empty:
        main_model = str(dataframe[model_column].mode(dropna=True).iloc[0])

    return {
        "market": market,
        "segment_family": segment_family,
        "segment_value": segment_value,
        "rows": rows,
        "correct_rows": correct_rows,
        "error_rows": error_rows,
        "accuracy": rounded(accuracy),
        "avg_confidence": rounded(confidence_values.mean()),
        "min_confidence": rounded(confidence_values.min()),
        "max_confidence": rounded(confidence_values.max()),
        "target_distribution": format_distribution(dataframe[target_column]),
        "prediction_distribution": format_distribution(dataframe[prediction_column]),
        "main_model": main_model,
        "note": note,
    }


# Genere les diagnostics par segments pour tous les marches.
def build_segment_diagnostics(dataframe: pd.DataFrame) -> pd.DataFrame:
    segment_rows: list[dict[str, Any]] = []

    common_segment_columns = [
        "competition_code",
        "stage_type",
        "elo_gap_bucket",
        "elo_advantage_side",
        "host_context",
        "season_period",
        "actual_total_goals_bucket",
    ]

    for market, config in MARKETS.items():
        market_key = normalize_market_key(market)
        target_column = str(config["target_column"])
        prediction_column = str(config["prediction_column"])
        confidence_bucket_column = f"confidence_bucket_{market_key}"

        segment_rows.append(
            build_segment_row(
                dataframe=dataframe,
                market=market,
                segment_family="overall",
                segment_value="all_test_rows",
                note="Performance globale sur le test chronologique.",
            )
        )

        market_specific_segments = common_segment_columns + [
            confidence_bucket_column,
            target_column,
            prediction_column,
        ]

        for segment_column in market_specific_segments:
            if segment_column not in dataframe.columns:
                continue

            segment_family = segment_column
            for segment_value, segment_dataframe in dataframe.groupby(
                segment_column, dropna=False
            ):
                readable_value = str(segment_value) if not pd.isna(segment_value) else "UNKNOWN"
                note = ""
                if segment_column == "actual_total_goals_bucket":
                    note = "Segment post-match utilise pour diagnostiquer les erreurs, pas pour predire."
                elif segment_column == target_column:
                    note = "Diagnostic par classe reelle."
                elif segment_column == prediction_column:
                    note = "Diagnostic par classe predite."
                elif segment_column == confidence_bucket_column:
                    note = "Diagnostic par niveau de probabilite maximale du modele."

                segment_rows.append(
                    build_segment_row(
                        dataframe=segment_dataframe,
                        market=market,
                        segment_family=segment_family,
                        segment_value=readable_value,
                        note=note,
                    )
                )

    diagnostics = pd.DataFrame(segment_rows)
    diagnostics = diagnostics[OUTPUT_COLUMNS]
    diagnostics = diagnostics.sort_values(
        by=["market", "segment_family", "rows"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    return diagnostics


# Recupere les lignes overall du diagnostic pour la synthese.
def get_overall_rows(diagnostics: pd.DataFrame) -> pd.DataFrame:
    return diagnostics[diagnostics["segment_family"].eq("overall")].copy()


# Recupere les meilleurs et pires segments exploitables d'un marche.
def get_segment_extremes(
    diagnostics: pd.DataFrame, market: str, largest: bool, limit: int = 5
) -> pd.DataFrame:
    market_rows = diagnostics[
        diagnostics["market"].eq(market)
        & ~diagnostics["segment_family"].eq("overall")
        & diagnostics["rows"].ge(MIN_SEGMENT_ROWS_FOR_SUMMARY)
        & diagnostics["accuracy"].notna()
    ].copy()

    return market_rows.sort_values(
        by=["accuracy", "rows"], ascending=[not largest, False]
    ).head(limit)


# Formate une ligne de segment pour la synthese texte.
def format_segment_for_summary(row: pd.Series) -> str:
    return (
        f"- {row['segment_family']} = {row['segment_value']} | "
        f"rows={int(row['rows'])} | accuracy={float(row['accuracy']):.4f} | "
        f"avg_conf={float(row['avg_confidence']):.4f}"
    )


# Recupere les meilleurs modeles depuis le CSV 347.
def extract_best_models(comparison: pd.DataFrame) -> dict[str, dict[str, Any]]:
    best_models: dict[str, dict[str, Any]] = {}

    if "best_model_for_market" not in comparison.columns:
        return best_models

    for market in MARKETS.keys():
        market_rows = comparison[comparison["market"].eq(market)].copy()
        if market_rows.empty:
            continue

        best_model_name = str(market_rows["best_model_for_market"].dropna().iloc[0])
        best_row = market_rows[market_rows["model_name"].eq(best_model_name)]
        if best_row.empty:
            best_row = market_rows.sort_values("f1_macro", ascending=False).head(1)

        row = best_row.iloc[0]
        best_models[market] = {
            "model_name": str(row.get("model_name", best_model_name)),
            "accuracy": rounded(row.get("accuracy")),
            "f1_macro": rounded(row.get("f1_macro")),
            "balanced_accuracy": rounded(row.get("balanced_accuracy")),
        }

    return best_models


# Ajoute des lignes de synthese dediees aux points critiques par marche.
def build_market_focus_lines(diagnostics: pd.DataFrame) -> list[str]:
    lines: list[str] = []

    focus_definitions = [
        ("1X2", "target_1x2", "DRAW", "Precision sur les vrais nuls"),
        ("OVER_1_5", "target_over_1_5", "NO", "Controle des matchs under 1.5"),
        ("OVER_2_5", "target_over_2_5", "YES", "Controle des matchs over 2.5"),
        ("BTTS", "target_btts", "YES", "Controle des matchs BTTS oui"),
    ]

    for market, segment_family, segment_value, label in focus_definitions:
        row = diagnostics[
            diagnostics["market"].eq(market)
            & diagnostics["segment_family"].eq(segment_family)
            & diagnostics["segment_value"].eq(segment_value)
        ]

        if row.empty:
            continue

        selected = row.iloc[0]
        lines.append(
            f"- {label} ({market}) : rows={int(selected['rows'])}, "
            f"accuracy={float(selected['accuracy']):.4f}, "
            f"avg_conf={float(selected['avg_confidence']):.4f}"
        )

    return lines


# Construit la synthese texte de l'etape de diagnostic V18.3.
def build_summary_text(
    enriched_predictions: pd.DataFrame,
    diagnostics: pd.DataFrame,
    comparison: pd.DataFrame,
    dataset_path: Path,
    predictions_path: Path,
    comparison_path: Path,
    output_dir: Path,
) -> str:
    best_models = extract_best_models(comparison)
    overall_rows = get_overall_rows(diagnostics)

    lines: list[str] = []
    lines.append("OK - Diagnostic V18.3 global multi-market termine.")
    lines.append("")
    lines.append("Contexte :")
    lines.append("- Phase : V18.3 national global multi-market.")
    lines.append(
        "- Objectif : diagnostiquer les performances des baselines 1X2, OVER_1_5, OVER_2_5 et BTTS par segments avant le selecteur."
    )
    lines.append("- StatsBomb : non utilise dans ce diagnostic global.")
    lines.append("- DOUBLE_CHANCE : sera derivee plus tard des probabilites 1X2.")
    lines.append("- ABSTAIN : sera produit plus tard par le selecteur selon les seuils.")
    lines.append("")
    lines.append("Fichiers utilises :")
    lines.append(f"- Dataset global : {dataset_path}")
    lines.append(f"- Comparaison modeles : {comparison_path}")
    lines.append(f"- Predictions test : {predictions_path}")
    lines.append("")
    lines.append("Volume diagnostique :")
    lines.append(f"- Lignes test analysees : {len(enriched_predictions)}")
    lines.append(
        f"- Competitions : {format_distribution(enriched_predictions['competition_code'])}"
    )
    lines.append(
        f"- Periode test : {int(pd.to_numeric(enriched_predictions['season'], errors='coerce').min())} -> {int(pd.to_numeric(enriched_predictions['season'], errors='coerce').max())}"
    )
    lines.append("")
    lines.append("Modeles retenus depuis 347 :")
    for market in MARKETS.keys():
        model = best_models.get(market, {})
        if not model:
            lines.append(f"- {market} : modele non trouve dans 347")
            continue
        lines.append(
            f"- {market} : {model['model_name']} | accuracy={model['accuracy']} | f1_macro={model['f1_macro']} | balanced_accuracy={model['balanced_accuracy']}"
        )
    lines.append("")
    lines.append("Performance globale sur le test :")
    for _, row in overall_rows.iterrows():
        lines.append(
            f"- {row['market']} : rows={int(row['rows'])}, accuracy={float(row['accuracy']):.4f}, avg_confidence={float(row['avg_confidence']):.4f}, errors={int(row['error_rows'])}"
        )
    lines.append("")
    lines.append("Points critiques a surveiller :")
    focus_lines = build_market_focus_lines(diagnostics)
    if focus_lines:
        lines.extend(focus_lines)
    else:
        lines.append("- Aucun point critique specifique calcule.")
    lines.append("")

    for market in MARKETS.keys():
        lines.append("=" * 80)
        lines.append(f"Segments forts pour {market} (minimum {MIN_SEGMENT_ROWS_FOR_SUMMARY} lignes) :")
        strong_segments = get_segment_extremes(diagnostics, market, largest=True)
        if strong_segments.empty:
            lines.append("- Aucun segment fort exploitable.")
        else:
            for _, row in strong_segments.iterrows():
                lines.append(format_segment_for_summary(row))

        lines.append("")
        lines.append(f"Segments faibles pour {market} (minimum {MIN_SEGMENT_ROWS_FOR_SUMMARY} lignes) :")
        weak_segments = get_segment_extremes(diagnostics, market, largest=False)
        if weak_segments.empty:
            lines.append("- Aucun segment faible exploitable.")
        else:
            for _, row in weak_segments.iterrows():
                lines.append(format_segment_for_summary(row))
        lines.append("")

    lines.append("Fichiers generes :")
    lines.append(f"- Diagnostics segments : {output_dir / SEGMENT_DIAGNOSTICS_FILENAME}")
    lines.append(f"- Synthese : {output_dir / SUMMARY_FILENAME}")
    lines.append("")
    lines.append("Decision technique :")
    lines.append("- Cette etape valide le diagnostic avant construction du selecteur V18.3.")
    lines.append(
        "- Le futur selecteur devra eviter de choisir un marche uniquement parce que sa classe majoritaire est frequente."
    )
    lines.append(
        "- OVER_2_5 semble utile a surveiller car il est plus equilibre que OVER_1_5 dans le test."
    )
    lines.append(
        "- BTTS reste fragile et devra etre filtre strictement si le selecteur l'utilise."
    )
    lines.append(
        "- Les segments post-match comme actual_total_goals_bucket servent uniquement au diagnostic d'erreurs, pas a la prediction."
    )
    lines.append("- Les resultats restent experimentaux et ne promettent aucun resultat sportif.")

    return "\n".join(lines) + "\n"


# Ecrit les fichiers 349 et 350 dans reports/evidence/ml_training.
def write_outputs(
    diagnostics: pd.DataFrame,
    summary_text: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    diagnostics_path = output_dir / SEGMENT_DIAGNOSTICS_FILENAME
    summary_path = output_dir / SUMMARY_FILENAME

    diagnostics.to_csv(diagnostics_path, index=False, encoding="utf-8")
    summary_path.write_text(summary_text, encoding="utf-8")

    return diagnostics_path, summary_path


# Orchestre le diagnostic complet V18.3.
def main() -> None:
    args = parse_arguments()

    dataset_path = Path(args.dataset_path)
    comparison_path = Path(args.comparison_path)
    predictions_path = Path(args.predictions_path)
    output_dir = Path(args.output_dir)

    ensure_output_directory(output_dir)

    dataset = load_csv_file(dataset_path, "dataset 345")
    comparison = load_csv_file(comparison_path, "comparaison 347")
    predictions = load_csv_file(predictions_path, "predictions 348")

    validate_input_columns(predictions=predictions, dataset=dataset)

    enriched_predictions = merge_predictions_with_context(
        predictions=predictions,
        dataset=dataset,
    )
    enriched_predictions = add_global_segment_columns(enriched_predictions)
    enriched_predictions = add_market_segment_columns(enriched_predictions)

    diagnostics = build_segment_diagnostics(enriched_predictions)

    summary_text = build_summary_text(
        enriched_predictions=enriched_predictions,
        diagnostics=diagnostics,
        comparison=comparison,
        dataset_path=dataset_path,
        predictions_path=predictions_path,
        comparison_path=comparison_path,
        output_dir=output_dir,
    )

    diagnostics_path, summary_path = write_outputs(
        diagnostics=diagnostics,
        summary_text=summary_text,
        output_dir=output_dir,
    )

    print("OK - Diagnostic V18.3 global multi-market termine.")
    print(f"Lignes test analysees : {len(enriched_predictions)}")
    print(f"Segments generes : {len(diagnostics)}")

    overall_rows = get_overall_rows(diagnostics)
    for _, row in overall_rows.iterrows():
        print(
            f"{row['market']} accuracy={float(row['accuracy']):.4f} "
            f"avg_confidence={float(row['avg_confidence']):.4f} "
            f"errors={int(row['error_rows'])}"
        )

    print(f"Diagnostics CSV saved: {diagnostics_path}")
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# 345_v18_3_global_multimarket_dataset.csv
#      +
# 347_v18_3_global_multimarket_model_comparison.csv
#      +
# 348_v18_3_global_multimarket_test_predictions.csv
#      -> diagnose_v18_3_global_multimarket_models.py
#      -> 349_v18_3_global_multimarket_segment_diagnostics.csv
#      -> 350_v18_3_global_multimarket_diagnostics_summary.txt
