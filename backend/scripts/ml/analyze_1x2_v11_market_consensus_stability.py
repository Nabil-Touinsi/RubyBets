# Analyse la stabilité de la V11 market consensus selective sans modifier le produit RubyBets.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


# Définit les chemins utilisés par le script.
@dataclass(frozen=True)
class StabilityPaths:
    project_root: Path
    ml_training_dir: Path
    v11_summary: Path
    v11_results: Path
    v11_best_strategy: Path
    v11_by_class: Path
    v11_by_league_season: Path
    v11_error_patterns: Path
    v11_decision: Path
    v9_by_league_season: Path
    v9_by_class: Path
    out_summary: Path
    out_by_league_season: Path
    out_by_class: Path
    out_error_patterns: Path
    out_decision: Path


# Retourne la racine du projet depuis backend/scripts/ml.
def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


# Construit tous les chemins d'entrée et de sortie de l'analyse.
def build_paths() -> StabilityPaths:
    project_root = resolve_project_root()
    ml_training_dir = project_root / "reports" / "evidence" / "ml_training"

    return StabilityPaths(
        project_root=project_root,
        ml_training_dir=ml_training_dir,
        v11_summary=ml_training_dir / "167_1x2_v11_market_consensus_summary.txt",
        v11_results=ml_training_dir / "168_1x2_v11_market_consensus_results.csv",
        v11_best_strategy=ml_training_dir / "169_1x2_v11_market_consensus_best_strategy.csv",
        v11_by_class=ml_training_dir / "170_1x2_v11_market_consensus_by_class.csv",
        v11_by_league_season=ml_training_dir / "171_1x2_v11_market_consensus_by_league_season.csv",
        v11_error_patterns=ml_training_dir / "172_1x2_v11_market_consensus_error_patterns.csv",
        v11_decision=ml_training_dir / "173_1x2_v11_market_consensus_decision.txt",
        v9_by_league_season=ml_training_dir / "152_1x2_v9_selective_stability_by_league_season.csv",
        v9_by_class=ml_training_dir / "153_1x2_v9_selective_stability_by_predicted_class.csv",
        out_summary=ml_training_dir / "174_1x2_v11_market_consensus_stability_summary.txt",
        out_by_league_season=ml_training_dir / "175_1x2_v11_market_consensus_stability_by_league_season.csv",
        out_by_class=ml_training_dir / "176_1x2_v11_market_consensus_stability_by_class.csv",
        out_error_patterns=ml_training_dir / "177_1x2_v11_market_consensus_stability_error_patterns.csv",
        out_decision=ml_training_dir / "178_1x2_v11_market_consensus_stability_decision.txt",
    )


# Lit un CSV de preuve avec un encodage robuste.
def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Fichier introuvable : {path}")
        return pd.DataFrame()

    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue

    raise RuntimeError(f"Lecture impossible du fichier : {path}")


# Lit un fichier texte de preuve si disponible.
def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


# Convertit des colonnes numériques quand elles existent.
def coerce_numeric_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    frame = frame.copy()
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


# Arrondit une valeur numérique pour les fichiers de preuve.
def round_float(value: float, digits: int = 4) -> float:
    try:
        return round(float(value), digits)
    except Exception:
        return 0.0


# Récupère une valeur de la stratégie V11 retenue.
def scalar_from_best(best_strategy: pd.DataFrame, column: str, default: float | str = 0) -> float | str:
    if best_strategy.empty or column not in best_strategy.columns:
        return default
    value = best_strategy.iloc[0][column]
    if pd.isna(value):
        return default
    return value


# Calcule les lignes correctes et les erreurs à partir d'une agrégation.
def add_correct_error_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["selected_correct_rows"] = (
        frame["selected_rows"].astype(float) * frame["selected_accuracy"].astype(float)
    ).round().astype(int)
    frame["selected_error_rows"] = (
        frame["selected_rows"].astype(int) - frame["selected_correct_rows"].astype(int)
    ).clip(lower=0)
    return frame


# Construit un statut de stabilité pour un segment V11.
def build_segment_status(row: pd.Series) -> str:
    selected_rows = float(row.get("selected_rows", 0))
    accuracy = float(row.get("selected_accuracy", 0))
    coverage = float(row.get("coverage", 0))
    predicted_draw_rows = float(row.get("predicted_draw_rows", 0))

    if selected_rows == 0:
        return "NO_SELECTION"
    if selected_rows < 30:
        return "LOW_SAMPLE_REVIEW"
    if accuracy < 0.68 and selected_rows >= 50:
        return "LOW_ACCURACY_REVIEW"
    if accuracy < 0.70:
        return "ACCURACY_REVIEW"
    if accuracy < 0.76:
        if coverage >= 0.20:
            base = "EXTENDED_COVERAGE_BELOW_ACCEPTANCE_ACCURACY"
        else:
            base = "STABLE_BUT_BELOW_ACCEPTANCE_ACCURACY"
    else:
        base = "STABLE_OK"

    if predicted_draw_rows == 0:
        return f"{base}_NO_DRAW_RECOMMENDATION"
    return base


# Agrège les résultats V11 par ligue, saison et couple ligue/saison.
def build_v11_stability_segments(v11_league_season: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = [
        "total_rows",
        "selected_rows",
        "coverage",
        "selected_accuracy",
        "predicted_draw_rows",
        "actual_draw_rows",
    ]
    base = coerce_numeric_columns(v11_league_season, numeric_columns)

    required_columns = {"league_code", "season", "total_rows", "selected_rows", "selected_accuracy"}
    missing_columns = required_columns.difference(base.columns)
    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans 171 : {sorted(missing_columns)}")

    if "predicted_draw_rows" not in base.columns:
        base["predicted_draw_rows"] = 0
    if "actual_draw_rows" not in base.columns:
        base["actual_draw_rows"] = 0

    base = add_correct_error_columns(base)

    by_league_season = base.copy()
    by_league_season["segment_type"] = "by_league_season"

    def aggregate(group: pd.DataFrame, segment_type: str, league_code: str, season: str) -> dict:
        total_rows = int(group["total_rows"].sum())
        selected_rows = int(group["selected_rows"].sum())
        selected_correct_rows = int(group["selected_correct_rows"].sum())
        selected_error_rows = max(selected_rows - selected_correct_rows, 0)
        accuracy = selected_correct_rows / selected_rows if selected_rows else 0.0
        coverage = selected_rows / total_rows if total_rows else 0.0

        return {
            "segment_type": segment_type,
            "league_code": league_code,
            "season": season,
            "total_rows": total_rows,
            "selected_rows": selected_rows,
            "coverage": round_float(coverage),
            "selected_accuracy": round_float(accuracy),
            "selected_correct_rows": selected_correct_rows,
            "selected_error_rows": selected_error_rows,
            "predicted_draw_rows": int(group["predicted_draw_rows"].sum()),
            "actual_draw_rows": int(group["actual_draw_rows"].sum()),
        }

    league_rows = [
        aggregate(group, "by_league", str(league_code), "ALL")
        for league_code, group in base.groupby("league_code", dropna=False)
    ]
    season_rows = [
        aggregate(group, "by_season", "ALL", str(season))
        for season, group in base.groupby("season", dropna=False)
    ]

    league_df = pd.DataFrame(league_rows)
    season_df = pd.DataFrame(season_rows)

    by_league_season = by_league_season[
        [
            "league_code",
            "season",
            "total_rows",
            "selected_rows",
            "coverage",
            "selected_accuracy",
            "selected_correct_rows",
            "selected_error_rows",
            "predicted_draw_rows",
            "actual_draw_rows",
            "segment_type",
        ]
    ]

    combined = pd.concat([league_df, season_df, by_league_season], ignore_index=True)
    combined["coverage"] = combined["coverage"].map(lambda value: round_float(value))
    combined["selected_accuracy"] = combined["selected_accuracy"].map(lambda value: round_float(value))
    combined["segment_status"] = combined.apply(build_segment_status, axis=1)

    ordered_columns = [
        "segment_type",
        "league_code",
        "season",
        "segment_status",
        "total_rows",
        "selected_rows",
        "coverage",
        "selected_accuracy",
        "selected_correct_rows",
        "selected_error_rows",
        "predicted_draw_rows",
        "actual_draw_rows",
    ]
    return combined[ordered_columns].sort_values(
        by=["segment_type", "selected_accuracy", "selected_rows"],
        ascending=[True, True, False],
    )


# Ajoute une comparaison V9 par segment quand les preuves V9 existent.
def add_v9_segment_comparison(v11_segments: pd.DataFrame, v9_segments: pd.DataFrame) -> pd.DataFrame:
    if v9_segments.empty:
        v11_segments["v9_selected_rows"] = 0
        v11_segments["v9_selected_accuracy"] = 0.0
        v11_segments["v9_coverage"] = 0.0
        v11_segments["v9_selected_correct_rows"] = 0
        v11_segments["delta_selected_rows_vs_v9"] = v11_segments["selected_rows"]
        v11_segments["delta_correct_rows_vs_v9"] = v11_segments["selected_correct_rows"]
        v11_segments["delta_accuracy_vs_v9"] = v11_segments["selected_accuracy"]
        v11_segments["delta_coverage_vs_v9"] = v11_segments["coverage"]
        return v11_segments

    v9 = v9_segments.copy()
    v9 = coerce_numeric_columns(
        v9,
        ["selected_rows", "selected_accuracy", "coverage", "selected_correct_rows"],
    )

    keep_columns = [
        "segment_type",
        "league_code",
        "season",
        "selected_rows",
        "selected_accuracy",
        "coverage",
        "selected_correct_rows",
    ]
    for column in keep_columns:
        if column not in v9.columns:
            v9[column] = 0

    v9 = v9[keep_columns].rename(
        columns={
            "selected_rows": "v9_selected_rows",
            "selected_accuracy": "v9_selected_accuracy",
            "coverage": "v9_coverage",
            "selected_correct_rows": "v9_selected_correct_rows",
        }
    )

    merged = v11_segments.merge(
        v9,
        on=["segment_type", "league_code", "season"],
        how="left",
    )
    fill_columns = [
        "v9_selected_rows",
        "v9_selected_accuracy",
        "v9_coverage",
        "v9_selected_correct_rows",
    ]
    for column in fill_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0)

    merged["delta_selected_rows_vs_v9"] = (
        merged["selected_rows"].astype(int) - merged["v9_selected_rows"].astype(int)
    )
    merged["delta_correct_rows_vs_v9"] = (
        merged["selected_correct_rows"].astype(int) - merged["v9_selected_correct_rows"].astype(int)
    )
    merged["delta_accuracy_vs_v9"] = (
        merged["selected_accuracy"].astype(float) - merged["v9_selected_accuracy"].astype(float)
    ).map(lambda value: round_float(value))
    merged["delta_coverage_vs_v9"] = (
        merged["coverage"].astype(float) - merged["v9_coverage"].astype(float)
    ).map(lambda value: round_float(value))

    return merged


# Ajoute la comparaison V9 dans l'analyse par classe prédite.
def build_class_stability(v11_by_class: pd.DataFrame, v9_by_class: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = ["selected_rows", "selected_accuracy", "actual_draw_rows"]
    frame = coerce_numeric_columns(v11_by_class, numeric_columns)

    if "predicted_class" not in frame.columns:
        raise ValueError("Colonne predicted_class manquante dans 170.")
    if "class_status" not in frame.columns:
        frame["class_status"] = ""

    frame = frame.copy()
    frame["selected_correct_rows"] = (
        frame["selected_rows"].astype(float) * frame["selected_accuracy"].astype(float)
    ).round().astype(int)
    frame["selected_error_rows"] = (
        frame["selected_rows"].astype(int) - frame["selected_correct_rows"].astype(int)
    ).clip(lower=0)

    if not v9_by_class.empty:
        v9 = coerce_numeric_columns(
            v9_by_class,
            ["selected_rows", "selected_accuracy", "selected_correct_rows"],
        )
        if "predicted_class" in v9.columns:
            v9 = v9[
                ["predicted_class", "selected_rows", "selected_accuracy", "selected_correct_rows"]
            ].rename(
                columns={
                    "selected_rows": "v9_selected_rows",
                    "selected_accuracy": "v9_selected_accuracy",
                    "selected_correct_rows": "v9_selected_correct_rows",
                }
            )
            frame = frame.merge(v9, on="predicted_class", how="left")

    for column in ["v9_selected_rows", "v9_selected_accuracy", "v9_selected_correct_rows"]:
        if column not in frame.columns:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    frame["delta_selected_rows_vs_v9"] = (
        frame["selected_rows"].astype(int) - frame["v9_selected_rows"].astype(int)
    )
    frame["delta_correct_rows_vs_v9"] = (
        frame["selected_correct_rows"].astype(int) - frame["v9_selected_correct_rows"].astype(int)
    )
    frame["delta_accuracy_vs_v9"] = (
        frame["selected_accuracy"].astype(float) - frame["v9_selected_accuracy"].astype(float)
    ).map(lambda value: round_float(value))

    ordered_columns = [
        "predicted_class",
        "class_status",
        "selected_rows",
        "selected_accuracy",
        "selected_correct_rows",
        "selected_error_rows",
        "actual_draw_rows",
        "v9_selected_rows",
        "v9_selected_accuracy",
        "v9_selected_correct_rows",
        "delta_selected_rows_vs_v9",
        "delta_correct_rows_vs_v9",
        "delta_accuracy_vs_v9",
    ]
    for column in ordered_columns:
        if column not in frame.columns:
            frame[column] = 0

    return frame[ordered_columns]


# Prépare les patterns d'erreur V11 pour identifier les risques principaux.
def build_error_stability(v11_errors: pd.DataFrame) -> pd.DataFrame:
    if v11_errors.empty:
        return pd.DataFrame(columns=["league_code", "season", "error_label", "rows", "error_share"])

    frame = coerce_numeric_columns(v11_errors, ["rows"])
    total_errors = float(frame["rows"].sum()) if "rows" in frame.columns else 0.0
    frame["error_share"] = frame["rows"].map(
        lambda value: round_float(float(value) / total_errors if total_errors else 0.0)
    )
    return frame.sort_values(by=["rows"], ascending=False)


# Détecte les segments V11 qui peuvent fragiliser la décision.
def detect_stability_flags(stability_segments: pd.DataFrame, class_stability: pd.DataFrame) -> tuple[list[str], list[str]]:
    blocking_reasons: list[str] = []
    warning_points: list[str] = []

    league_segments = stability_segments[stability_segments["segment_type"] == "by_league"]
    season_segments = stability_segments[stability_segments["segment_type"] == "by_season"]
    league_season_segments = stability_segments[stability_segments["segment_type"] == "by_league_season"]

    weak_leagues = league_segments[
        (league_segments["selected_rows"] >= 80) & (league_segments["selected_accuracy"] < 0.70)
    ]
    weak_seasons = season_segments[
        (season_segments["selected_rows"] >= 200) & (season_segments["selected_accuracy"] < 0.70)
    ]
    weak_league_seasons = league_season_segments[
        (league_season_segments["selected_rows"] >= 50) & (league_season_segments["selected_accuracy"] < 0.68)
    ]

    if not weak_leagues.empty:
        details = "; ".join(
            f"{row.league_code}: acc={row.selected_accuracy}, rows={row.selected_rows}"
            for row in weak_leagues.itertuples()
        )
        blocking_reasons.append(f"Effondrement par ligue majeure détecté : {details}")

    if not weak_seasons.empty:
        details = "; ".join(
            f"{row.season}: acc={row.selected_accuracy}, rows={row.selected_rows}"
            for row in weak_seasons.itertuples()
        )
        blocking_reasons.append(f"Effondrement par saison majeure détecté : {details}")

    if not weak_league_seasons.empty:
        details = "; ".join(
            f"{row.league_code}/{row.season}: acc={row.selected_accuracy}, rows={row.selected_rows}"
            for row in weak_league_seasons.head(5).itertuples()
        )
        warning_points.append(f"Segments ligue/saison faibles à surveiller : {details}")

    draw_row = class_stability[class_stability["predicted_class"].astype(str) == "DRAW"]
    if draw_row.empty or int(draw_row.iloc[0].get("selected_rows", 0)) == 0:
        warning_points.append("Aucun DRAW recommandé : limite acceptable uniquement si elle est documentée.")

    low_accuracy_classes = class_stability[
        (class_stability["selected_rows"] >= 100)
        & (class_stability["selected_accuracy"] < 0.70)
        & (class_stability["predicted_class"].astype(str) != "DRAW")
    ]
    if not low_accuracy_classes.empty:
        details = "; ".join(
            f"{row.predicted_class}: acc={row.selected_accuracy}, rows={row.selected_rows}"
            for row in low_accuracy_classes.itertuples()
        )
        warning_points.append(f"Classe prédite à surveiller : {details}")

    return blocking_reasons, warning_points


# Décide du statut de stabilité V11 à partir des gates et des segments.
def decide_stability_status(
    best_strategy: pd.DataFrame,
    blocking_reasons: list[str],
    warning_points: list[str],
) -> str:
    accuracy = float(scalar_from_best(best_strategy, "selected_accuracy", 0))
    coverage = float(scalar_from_best(best_strategy, "coverage", 0))
    selected_rows = int(float(scalar_from_best(best_strategy, "selected_rows", 0)))
    net_delta = int(float(scalar_from_best(best_strategy, "net_correct_delta_vs_static_v9", 0)))

    passes_extended_coverage = coverage >= 0.20 and selected_rows > 1000 and net_delta >= 1
    passes_acceptance_accuracy = accuracy >= 0.76

    if blocking_reasons:
        return "V11_STABILITY_REJECTED"

    if passes_extended_coverage and passes_acceptance_accuracy and not warning_points:
        return "V11_STABILITY_VALIDATED_AS_EXTENDED_COVERAGE"

    if passes_extended_coverage and accuracy >= 0.72:
        return "V11_STABILITY_REVIEW"

    return "V11_STABILITY_REJECTED"


# Formate une petite section de lignes pour la synthèse texte.
def format_rows(frame: pd.DataFrame, columns: list[str], limit: int = 10) -> list[str]:
    if frame.empty:
        return ["- Aucune donnée disponible."]
    lines: list[str] = []
    selected = frame.head(limit)
    for row in selected.itertuples(index=False):
        values = row._asdict()
        parts = [f"{column}={values.get(column)}" for column in columns]
        lines.append("- " + " | ".join(parts))
    return lines


# Écrit la synthèse de stabilité V11.
def write_summary(
    paths: StabilityPaths,
    status: str,
    best_strategy: pd.DataFrame,
    stability_segments: pd.DataFrame,
    class_stability: pd.DataFrame,
    error_stability: pd.DataFrame,
    blocking_reasons: list[str],
    warning_points: list[str],
) -> None:
    strategy = scalar_from_best(best_strategy, "strategy", "UNKNOWN")
    accuracy = round_float(float(scalar_from_best(best_strategy, "selected_accuracy", 0)))
    coverage = round_float(float(scalar_from_best(best_strategy, "coverage", 0)))
    abstention_rate = round_float(float(scalar_from_best(best_strategy, "abstention_rate", 0)))
    selected_rows = int(float(scalar_from_best(best_strategy, "selected_rows", 0)))
    predicted_draw_rows = int(float(scalar_from_best(best_strategy, "predicted_draw_rows", 0)))
    net_delta = int(float(scalar_from_best(best_strategy, "net_correct_delta_vs_static_v9", 0)))
    selected_correct_rows = int(float(scalar_from_best(best_strategy, "selected_correct_rows", 0)))

    low_segments = stability_segments.sort_values(
        by=["selected_accuracy", "selected_rows"],
        ascending=[True, False],
    )

    lines: list[str] = [
        "RubyBets - ML 1X2 V11 market consensus stability",
        "174 - Synthèse stabilité V11 market consensus",
        "",
        "Objectif :",
        "Analyser si la V11 market consensus selective est suffisamment stable pour être conservée comme candidat expérimental à couverture élargie.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des fichiers de preuves V11 déjà générés.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modèles sauvegardés.",
        "- Aucune intégration produit.",
        "",
        "Fichiers d'entrée utilisés :",
        f"- {paths.v11_results}",
        f"- {paths.v11_best_strategy}",
        f"- {paths.v11_by_class}",
        f"- {paths.v11_by_league_season}",
        f"- {paths.v11_error_patterns}",
        f"- {paths.v11_decision}",
        "",
        "Stratégie V11 analysée :",
        f"- Strategy : {strategy}",
        "",
        "Résultat global sur le test :",
        f"- Status : {status}",
        f"- Selected accuracy : {accuracy}",
        f"- Coverage : {coverage}",
        f"- Abstention rate : {abstention_rate}",
        f"- Selected rows : {selected_rows}",
        f"- Selected correct rows : {selected_correct_rows}",
        f"- Predicted DRAW rows : {predicted_draw_rows}",
        f"- Net correct delta vs V9 static reference : {net_delta}",
        "",
        "Lecture experte :",
        "- La V11 augmente fortement la couverture par rapport à V9, mais elle reste sous le gate d'accuracy officiel de 0.76.",
        "- Elle ne doit donc pas être intégrée au produit.",
        "- Elle peut être conservée comme candidat expérimental à couverture élargie uniquement si les segments restent défendables.",
        "",
        "Segments les plus faibles à surveiller :",
        *format_rows(
            low_segments,
            ["segment_type", "league_code", "season", "selected_rows", "selected_accuracy", "coverage", "segment_status"],
            limit=12,
        ),
        "",
        "Stabilité par classe prédite :",
        *format_rows(
            class_stability,
            ["predicted_class", "selected_rows", "selected_accuracy", "delta_selected_rows_vs_v9", "delta_correct_rows_vs_v9"],
            limit=10,
        ),
        "",
        "Top erreurs restantes :",
        *format_rows(
            error_stability,
            ["league_code", "season", "error_label", "rows", "error_share"],
            limit=10,
        ),
        "",
        "Raisons bloquantes :",
        *(["- Aucune."] if not blocking_reasons else [f"- {reason}" for reason in blocking_reasons]),
        "",
        "Points de vigilance :",
        *(["- Aucun point de vigilance majeur."] if not warning_points else [f"- {point}" for point in warning_points]),
        "",
        "Décision produit :",
        "- Ne pas intégrer V11 au produit à ce stade.",
        "- Le scoring explicable V1 reste le socle officiel.",
        "- V11 reste une preuve expérimentale ML/RNCP et une piste d'amélioration data.",
        "",
        "Fichiers produits :",
        f"- {paths.out_summary}",
        f"- {paths.out_by_league_season}",
        f"- {paths.out_by_class}",
        f"- {paths.out_error_patterns}",
        f"- {paths.out_decision}",
        "",
        "Statut de suivi :",
        "- Analyse de stabilité V11 market consensus : réalisée si les fichiers 174 à 178 sont générés.",
        "- Fichiers sources à mettre à jour ensuite : plan ML/RNCP et documents de preuves concernés.",
    ]

    paths.out_summary.write_text("\n".join(lines), encoding="utf-8")


# Écrit le fichier de décision de stabilité V11.
def write_decision(
    paths: StabilityPaths,
    status: str,
    best_strategy: pd.DataFrame,
    blocking_reasons: list[str],
    warning_points: list[str],
) -> None:
    strategy = scalar_from_best(best_strategy, "strategy", "UNKNOWN")
    accuracy = round_float(float(scalar_from_best(best_strategy, "selected_accuracy", 0)))
    coverage = round_float(float(scalar_from_best(best_strategy, "coverage", 0)))
    abstention_rate = round_float(float(scalar_from_best(best_strategy, "abstention_rate", 0)))
    selected_rows = int(float(scalar_from_best(best_strategy, "selected_rows", 0)))
    net_delta = int(float(scalar_from_best(best_strategy, "net_correct_delta_vs_static_v9", 0)))
    predicted_draw_rows = int(float(scalar_from_best(best_strategy, "predicted_draw_rows", 0)))

    lines = [
        "RubyBets - Décision stabilité V11 market consensus",
        "178 - Decision analyse stabilité V11",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {strategy}",
        f"- Selected accuracy : {accuracy}",
        f"- Coverage : {coverage}",
        f"- Abstention rate : {abstention_rate}",
        f"- Selected rows : {selected_rows}",
        f"- Net correct delta vs V9 static reference : {net_delta}",
        f"- Predicted DRAW rows : {predicted_draw_rows}",
        "",
        "Gates appliqués :",
        "- Selected accuracy >= 0.76 pour validation officielle.",
        "- Coverage >= 0.20 pour conserver l'intérêt couverture élargie.",
        "- Selected rows > 1000.",
        "- Net correct delta vs V9 >= 1.",
        "- Pas d'effondrement majeur par ligue ou saison.",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        *(["- Aucune."] if not blocking_reasons else [f"- {reason}" for reason in blocking_reasons]),
        "",
        "Points de vigilance :",
        *(["- Aucun point de vigilance majeur."] if not warning_points else [f"- {point}" for point in warning_points]),
        "",
        "Décision opérationnelle :",
    ]

    if status == "V11_STABILITY_VALIDATED_AS_EXTENDED_COVERAGE":
        lines.extend(
            [
                "- Conserver V11 comme candidat expérimental à couverture élargie.",
                "- Ne pas l'intégrer au produit sans validation complémentaire et documentation RNCP.",
            ]
        )
    elif status == "V11_STABILITY_REVIEW":
        lines.extend(
            [
                "- V11 reste intéressante pour augmenter la couverture mais elle doit rester en revue.",
                "- Comparer V11 et V9 comme deux profils expérimentaux : V9 très haute confiance, V11 couverture élargie.",
                "- Ne pas intégrer V11 au produit à ce stade.",
            ]
        )
    else:
        lines.extend(
            [
                "- Rejeter V11 comme candidat opérationnel.",
                "- Conserver uniquement la preuve expérimentale et revenir à V9 comme meilleure baseline sélective.",
            ]
        )

    lines.extend(
        [
            "",
            "Statut de suivi à mettre à jour :",
            "- Analyse de stabilité V11 market consensus : réalisée.",
            "- Fichiers concernés : 174, 175, 176, 177, 178.",
            "- Prochaine action : décider si l'on documente V11 comme profil coverage élargi ou si l'on passe à l'enrichissement Elo/calendrier.",
        ]
    )

    paths.out_decision.write_text("\n".join(lines), encoding="utf-8")


# Orchestre toute l'analyse de stabilité V11.
def main() -> None:
    paths = build_paths()
    paths.ml_training_dir.mkdir(parents=True, exist_ok=True)

    print("Chargement des preuves V11 market consensus...")
    v11_results = read_csv(paths.v11_results)
    v11_best_strategy = read_csv(paths.v11_best_strategy)
    v11_by_class = read_csv(paths.v11_by_class)
    v11_by_league_season = read_csv(paths.v11_by_league_season)
    v11_error_patterns = read_csv(paths.v11_error_patterns)
    _ = read_text(paths.v11_summary)
    _ = read_text(paths.v11_decision)

    print("Chargement des références V9 si disponibles...")
    v9_by_league_season = read_csv(paths.v9_by_league_season, required=False)
    v9_by_class = read_csv(paths.v9_by_class, required=False)

    if v11_results.empty or v11_best_strategy.empty:
        raise ValueError("Les fichiers 168 et 169 doivent contenir au moins une ligne.")

    print("Construction des segments de stabilité V11...")
    stability_segments = build_v11_stability_segments(v11_by_league_season)
    stability_segments = add_v9_segment_comparison(stability_segments, v9_by_league_season)

    print("Analyse par classe prédite...")
    class_stability = build_class_stability(v11_by_class, v9_by_class)

    print("Analyse des erreurs restantes...")
    error_stability = build_error_stability(v11_error_patterns)

    print("Application des gates de stabilité...")
    blocking_reasons, warning_points = detect_stability_flags(stability_segments, class_stability)
    status = decide_stability_status(v11_best_strategy, blocking_reasons, warning_points)

    print("Génération des fichiers de preuve V11 stabilité...")
    stability_segments.to_csv(paths.out_by_league_season, index=False, encoding="utf-8-sig")
    class_stability.to_csv(paths.out_by_class, index=False, encoding="utf-8-sig")
    error_stability.to_csv(paths.out_error_patterns, index=False, encoding="utf-8-sig")
    write_summary(
        paths=paths,
        status=status,
        best_strategy=v11_best_strategy,
        stability_segments=stability_segments,
        class_stability=class_stability,
        error_stability=error_stability,
        blocking_reasons=blocking_reasons,
        warning_points=warning_points,
    )
    write_decision(
        paths=paths,
        status=status,
        best_strategy=v11_best_strategy,
        blocking_reasons=blocking_reasons,
        warning_points=warning_points,
    )

    print("OK - Analyse de stabilité V11 market consensus terminée.")
    print(f"Status: {status}")
    print(f"Selected accuracy: {round_float(float(scalar_from_best(v11_best_strategy, 'selected_accuracy', 0)))}")
    print(f"Coverage: {round_float(float(scalar_from_best(v11_best_strategy, 'coverage', 0)))}")
    print(f"Selected rows: {int(float(scalar_from_best(v11_best_strategy, 'selected_rows', 0)))}")
    print(f"Predicted DRAW rows: {int(float(scalar_from_best(v11_best_strategy, 'predicted_draw_rows', 0)))}")
    print(f"Net correct delta vs V9: {int(float(scalar_from_best(v11_best_strategy, 'net_correct_delta_vs_static_v9', 0)))}")
    print(f"Summary saved: {paths.out_summary}")
    print(f"League/season CSV saved: {paths.out_by_league_season}")
    print(f"By class CSV saved: {paths.out_by_class}")
    print(f"Error patterns CSV saved: {paths.out_error_patterns}")
    print(f"Decision saved: {paths.out_decision}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data input  : reports/evidence/ml_training/167 à 173 + références V9 152/153 si disponibles
# traitement  : analyse segments ligue/saison, classes prédites, erreurs et gates de stabilité
# data output : reports/evidence/ml_training/174 à 178
# produit     : aucune modification API / frontend / scoring V1 / PostgreSQL / ml.features
