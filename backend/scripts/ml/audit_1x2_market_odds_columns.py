# Ce script audite les colonnes de cotes historiques disponibles pour préparer une V11 market consensus sélective.
# Il lit uniquement les CSV bruts déjà présents dans data/ml/raw et génère des preuves dans reports/evidence/ml_training.

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


OUTPUT_SUMMARY = "164_1x2_market_odds_columns_audit_summary.txt"
OUTPUT_COVERAGE = "165_1x2_market_odds_columns_coverage.csv"
OUTPUT_DECISION = "166_1x2_market_odds_columns_decision.txt"

RECENT_SEASON_START_YEAR = 2020
STRONG_COVERAGE_THRESHOLD = 0.80
MIN_RECENT_COMPLETE_ROWS = 1000


@dataclass(frozen=True)
class CsvFileInfo:
    """Décrit un fichier CSV historique analysé pendant l'audit."""

    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class OddsTriplet:
    """Décrit un triplet de cotes Home / Draw / Away détecté dans les CSV."""

    market_type: str
    bookmaker_prefix: str
    home_col: str
    draw_col: str
    away_col: str


# Retrouve la racine du projet RubyBets à partir de l'emplacement du script.
def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "data" / "ml" / "raw").exists():
            return parent
    raise FileNotFoundError(
        "Impossible de trouver la racine du projet : data/ml/raw est introuvable."
    )


# Retourne le dossier de preuves ML et le crée si nécessaire.
def get_output_dir(project_root: Path) -> Path:
    output_dir = project_root / "reports" / "evidence" / "ml_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Extrait la saison à partir d'un nom de fichier comme E0_2024_2025.csv.
def infer_season_from_filename(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}_{parts[-1]}"
    return "UNKNOWN"


# Extrait le code de ligue à partir d'un fichier brut Football-Data, avec fallback sur le nom du fichier.
def infer_league_code(path: Path, columns: Iterable[str] | None = None) -> str:
    stem = path.stem
    if "_" in stem:
        return stem.split("_")[0]
    if columns and "Div" in columns:
        return "FROM_DIV_COLUMN"
    return "UNKNOWN"


# Liste les fichiers CSV bruts à auditer.
def list_raw_csv_files(project_root: Path) -> list[CsvFileInfo]:
    raw_dir = project_root / "data" / "ml" / "raw"
    csv_paths = sorted(raw_dir.rglob("*.csv"))
    files: list[CsvFileInfo] = []
    for path in csv_paths:
        files.append(
            CsvFileInfo(
                path=path,
                league_code=infer_league_code(path),
                season=infer_season_from_filename(path),
            )
        )
    return files


# Lit un CSV avec une stratégie robuste pour gérer les anciens fichiers Football-Data parfois irréguliers.
def read_csv_safely(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None

    # Première tentative : moteur Python + lignes défectueuses ignorées.
    # Cela évite les erreurs du type "Expected 35 fields, saw 36".
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                engine="python",
                on_bad_lines="skip",
            )
        except Exception as error:
            last_error = error

    # Deuxième tentative : lecture manuelle ligne par ligne.
    # Les lignes avec trop de colonnes sont ignorées, les lignes trop courtes sont complétées.
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            with path.open("r", encoding=encoding, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader)
                expected_columns = len(header)
                rows: list[list[str]] = []

                for row in reader:
                    if not row or all(str(value).strip() == "" for value in row):
                        continue

                    if len(row) > expected_columns:
                        continue

                    if len(row) < expected_columns:
                        row = row + [""] * (expected_columns - len(row))

                    rows.append(row)

            cleaned_header = [
                str(column).strip().replace("\ufeff", "")
                for column in header
            ]

            return pd.DataFrame(rows, columns=cleaned_header)

        except Exception as error:
            last_error = error

    raise RuntimeError(f"Lecture impossible du fichier {path}: {last_error}")


# Normalise les colonnes utiles pour l'audit sans modifier les fichiers sources.
def prepare_raw_frame(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = [str(col).strip().replace("\ufeff", "") for col in frame.columns]
    frame["__source_file"] = str(file_info.path)
    frame["__league_code"] = file_info.league_code
    frame["__season"] = file_info.season
    return frame


# Détecte automatiquement les triplets de cotes Home / Draw / Away dans un ensemble de colonnes.
def detect_odds_triplets(columns: Iterable[str]) -> list[OddsTriplet]:
    column_set = {str(col).strip().replace("\ufeff", "") for col in columns}
    triplets: dict[tuple[str, str], OddsTriplet] = {}

    for col in column_set:
        # Colonnes de clôture : B365CH / B365CD / B365CA, MaxCH / MaxCD / MaxCA, etc.
        if col.endswith("CH"):
            prefix = col[:-2]
            draw_col = f"{prefix}CD"
            away_col = f"{prefix}CA"
            if draw_col in column_set and away_col in column_set:
                triplets[("closing", prefix)] = OddsTriplet(
                    market_type="closing",
                    bookmaker_prefix=prefix,
                    home_col=col,
                    draw_col=draw_col,
                    away_col=away_col,
                )

        # Colonnes d'ouverture / classiques : B365H / B365D / B365A, AvgH / AvgD / AvgA, etc.
        if col.endswith("H") and not col.endswith("CH"):
            prefix = col[:-1]
            draw_col = f"{prefix}D"
            away_col = f"{prefix}A"
            if draw_col in column_set and away_col in column_set:
                # On évite de confondre les marchés Asian Handicap qui n'ont pas de colonne Draw.
                if "AH" not in prefix.upper() and ">" not in prefix and "<" not in prefix:
                    triplets[("opening_or_standard", prefix)] = OddsTriplet(
                        market_type="opening_or_standard",
                        bookmaker_prefix=prefix,
                        home_col=col,
                        draw_col=draw_col,
                        away_col=away_col,
                    )

    return sorted(triplets.values(), key=lambda item: (item.market_type, item.bookmaker_prefix))


# Convertit une colonne en numérique pour calculer correctement la couverture.
def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([math.nan] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


# Indique si une saison appartient au périmètre récent utilisé pour décider de la faisabilité V11.
def is_recent_season(season: str) -> bool:
    try:
        start_year = int(str(season).split("_")[0])
        return start_year >= RECENT_SEASON_START_YEAR
    except Exception:
        return False


# Calcule la couverture globale et récente de chaque triplet de cotes.
def compute_triplet_coverage(frame: pd.DataFrame, triplets: list[OddsTriplet]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total_rows = len(frame)
    recent_mask = frame["__season"].map(is_recent_season)
    recent_rows = int(recent_mask.sum())

    for triplet in triplets:
        home = numeric_series(frame, triplet.home_col)
        draw = numeric_series(frame, triplet.draw_col)
        away = numeric_series(frame, triplet.away_col)
        complete_mask = home.notna() & draw.notna() & away.notna()
        recent_complete_mask = complete_mask & recent_mask

        complete_rows = int(complete_mask.sum())
        recent_complete_rows = int(recent_complete_mask.sum())
        coverage_rate = complete_rows / total_rows if total_rows else 0.0
        recent_coverage_rate = recent_complete_rows / recent_rows if recent_rows else 0.0

        available = frame.loc[complete_mask, ["__league_code", "__season"]]
        recent_available = frame.loc[recent_complete_mask, ["__league_code", "__season"]]

        rows.append(
            {
                "market_type": triplet.market_type,
                "bookmaker_prefix": triplet.bookmaker_prefix,
                "home_col": triplet.home_col,
                "draw_col": triplet.draw_col,
                "away_col": triplet.away_col,
                "total_rows": total_rows,
                "complete_rows": complete_rows,
                "coverage_rate": round(coverage_rate, 4),
                "recent_rows": recent_rows,
                "recent_complete_rows": recent_complete_rows,
                "recent_coverage_rate": round(recent_coverage_rate, 4),
                "league_count": int(available["__league_code"].nunique()) if not available.empty else 0,
                "season_count": int(available["__season"].nunique()) if not available.empty else 0,
                "recent_league_count": int(recent_available["__league_code"].nunique()) if not recent_available.empty else 0,
                "recent_season_count": int(recent_available["__season"].nunique()) if not recent_available.empty else 0,
                "first_available_season": str(available["__season"].min()) if not available.empty else "NONE",
                "last_available_season": str(available["__season"].max()) if not available.empty else "NONE",
            }
        )

    return pd.DataFrame(rows).sort_values(
        by=["recent_coverage_rate", "coverage_rate", "recent_complete_rows"],
        ascending=[False, False, False],
    )


# Calcule une vue par ligue/saison pour repérer les zones où les cotes sont réellement disponibles.
def compute_league_season_summary(frame: pd.DataFrame, best_triplets: list[OddsTriplet]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = frame.groupby(["__league_code", "__season"], dropna=False)

    for (league_code, season), group in grouped:
        row: dict[str, object] = {
            "league_code": league_code,
            "season": season,
            "rows": len(group),
        }
        for triplet in best_triplets:
            complete_mask = (
                numeric_series(group, triplet.home_col).notna()
                & numeric_series(group, triplet.draw_col).notna()
                & numeric_series(group, triplet.away_col).notna()
            )
            key = f"{triplet.market_type}_{triplet.bookmaker_prefix}_coverage"
            row[key] = round(float(complete_mask.mean()), 4) if len(group) else 0.0
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Choisit les triplets les plus utiles pour une future V11 market consensus.
def select_priority_triplets(coverage: pd.DataFrame) -> list[OddsTriplet]:
    if coverage.empty:
        return []

    priority_prefixes = ["Avg", "Max", "B365", "PS", "BW", "IW", "WH", "VC"]
    selected_rows = []
    for prefix in priority_prefixes:
        matches = coverage[coverage["bookmaker_prefix"].eq(prefix)]
        if not matches.empty:
            selected_rows.append(matches.iloc[0])
        closing_matches = coverage[coverage["bookmaker_prefix"].eq(f"{prefix}C")]
        if not closing_matches.empty:
            selected_rows.append(closing_matches.iloc[0])

    if not selected_rows:
        selected_rows = [row for _, row in coverage.head(5).iterrows()]

    triplets: list[OddsTriplet] = []
    seen: set[tuple[str, str]] = set()
    for row in selected_rows:
        key = (str(row["market_type"]), str(row["bookmaker_prefix"]))
        if key not in seen:
            seen.add(key)
            triplets.append(
                OddsTriplet(
                    market_type=str(row["market_type"]),
                    bookmaker_prefix=str(row["bookmaker_prefix"]),
                    home_col=str(row["home_col"]),
                    draw_col=str(row["draw_col"]),
                    away_col=str(row["away_col"]),
                )
            )
    return triplets[:8]


# Détermine si l'état des données permet de lancer V11 rapidement.
def make_decision(coverage: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    blocking_reasons: list[str] = []
    watch_points: list[str] = []

    if coverage.empty:
        return "V11_MARKET_DATA_NOT_FOUND", ["Aucun triplet de cotes 1X2 détecté."], []

    strong_recent = coverage[
        (coverage["recent_coverage_rate"] >= STRONG_COVERAGE_THRESHOLD)
        & (coverage["recent_complete_rows"] >= MIN_RECENT_COMPLETE_ROWS)
    ]
    strong_opening = strong_recent[strong_recent["market_type"].eq("opening_or_standard")]
    strong_closing = strong_recent[strong_recent["market_type"].eq("closing")]

    has_avg_or_max = not strong_recent[strong_recent["bookmaker_prefix"].isin(["Avg", "Max", "AvgC", "MaxC"])].empty
    has_bookmaker_consensus = strong_recent["bookmaker_prefix"].nunique() >= 3

    if strong_opening.empty:
        blocking_reasons.append("Aucun triplet opening/standard n'atteint le seuil de couverture récente.")
    if not has_bookmaker_consensus:
        watch_points.append("Le consensus multi-bookmakers peut être limité si moins de 3 triplets récents sont solides.")
    if not has_avg_or_max:
        watch_points.append("Les colonnes Avg/Max ne sont pas suffisamment couvertes ; V11 devra reconstruire les moyennes depuis les bookmakers disponibles.")
    if strong_closing.empty:
        watch_points.append("Aucun triplet closing solide détecté ; les mouvements ouverture/fermeture devront être reportés ou traités partiellement.")

    if blocking_reasons:
        return "V11_MARKET_DATA_REVIEW", blocking_reasons, watch_points
    if not strong_closing.empty and has_bookmaker_consensus:
        return "V11_READY_MARKET_CONSENSUS_AND_CLOSING", [], watch_points
    return "V11_READY_MARKET_CONSENSUS_OPENING_ONLY", [], watch_points


# Génère la synthèse lisible de l'audit.
def write_summary(
    output_dir: Path,
    project_root: Path,
    files: list[CsvFileInfo],
    frame: pd.DataFrame,
    triplets: list[OddsTriplet],
    coverage: pd.DataFrame,
    decision_status: str,
    blocking_reasons: list[str],
    watch_points: list[str],
) -> None:
    top_lines = []
    for _, row in coverage.head(12).iterrows():
        top_lines.append(
            f"- {row['market_type']} | {row['bookmaker_prefix']} "
            f"({row['home_col']}/{row['draw_col']}/{row['away_col']}) "
            f"| coverage={row['coverage_rate']} | recent_coverage={row['recent_coverage_rate']} "
            f"| recent_complete_rows={row['recent_complete_rows']}"
        )

    recent_rows = int(frame["__season"].map(is_recent_season).sum()) if not frame.empty else 0
    summary = f"""RubyBets - Audit colonnes de cotes historiques 1X2
164 - Synthèse audit market odds columns

Objectif :
Vérifier quelles colonnes de cotes historiques 1X2 sont disponibles dans les CSV bruts afin de décider si une V11 market consensus selective est faisable rapidement.

Garde-fous respectés :
- Lecture uniquement des fichiers CSV bruts dans data/ml/raw.
- Aucune modification de PostgreSQL.
- Aucune modification de ml.features.
- Aucune modification de l'API, du frontend ou du scoring explicable V1.
- Aucun modèle sauvegardé.

Périmètre analysé :
- Racine projet : {project_root}
- Fichiers CSV analysés : {len(files)}
- Lignes totales analysées : {len(frame)}
- Lignes récentes depuis {RECENT_SEASON_START_YEAR} : {recent_rows}
- Ligues détectées : {', '.join(sorted(map(str, frame['__league_code'].dropna().unique()))) if not frame.empty else 'NONE'}
- Saisons détectées : {frame['__season'].min() if not frame.empty else 'NONE'} -> {frame['__season'].max() if not frame.empty else 'NONE'}

Triplets de cotes 1X2 détectés : {len(triplets)}

Top colonnes candidates pour V11 :
{chr(10).join(top_lines) if top_lines else '- Aucun triplet détecté.'}

Décision :
- Status : {decision_status}

Raisons bloquantes :
{chr(10).join(f'- {reason}' for reason in blocking_reasons) if blocking_reasons else '- Aucune raison bloquante détectée.'}

Points de vigilance :
{chr(10).join(f'- {point}' for point in watch_points) if watch_points else '- Aucun point de vigilance majeur.'}

Lecture experte :
- Si le statut commence par V11_READY, les données de cotes sont assez solides pour créer une V11 market consensus selective.
- Si le statut indique OPENING_ONLY, il faut d'abord exploiter le consensus de marché sans promettre les mouvements ouverture/fermeture.
- Si le statut indique MARKET_DATA_REVIEW ou NOT_FOUND, il faut récupérer ou reconstruire des données de cotes avant de lancer V11.

Fichiers produits :
- {output_dir / OUTPUT_SUMMARY}
- {output_dir / OUTPUT_COVERAGE}
- {output_dir / OUTPUT_DECISION}

Statut de suivi :
- Audit colonnes de cotes historiques : réalisé si les fichiers 164 à 166 sont générés.
- Prochaine action si V11_READY : créer backend/scripts/ml/train_1x2_v11_market_consensus_selective.py.
"""
    (output_dir / OUTPUT_SUMMARY).write_text(summary, encoding="utf-8")


# Génère la décision opérationnelle courte de l'audit.
def write_decision(
    output_dir: Path,
    decision_status: str,
    blocking_reasons: list[str],
    watch_points: list[str],
    coverage: pd.DataFrame,
) -> None:
    best = coverage.head(8)
    best_lines = []
    for _, row in best.iterrows():
        best_lines.append(
            f"- {row['market_type']} | {row['bookmaker_prefix']} | "
            f"recent_coverage={row['recent_coverage_rate']} | recent_complete_rows={row['recent_complete_rows']}"
        )

    next_action = (
        "Créer V11 market consensus selective."
        if decision_status.startswith("V11_READY")
        else "Ne pas créer V11 avant correction ou enrichissement des données de cotes."
    )

    decision = f"""RubyBets - Décision audit market odds columns
166 - Decision audit cotes historiques

Status : {decision_status}

Meilleurs triplets détectés :
{chr(10).join(best_lines) if best_lines else '- Aucun triplet exploitable.'}

Raisons bloquantes :
{chr(10).join(f'- {reason}' for reason in blocking_reasons) if blocking_reasons else '- Aucune.'}

Points de vigilance :
{chr(10).join(f'- {point}' for point in watch_points) if watch_points else '- Aucun.'}

Décision opérationnelle :
{next_action}

Rappel :
- Ne pas modifier PostgreSQL ou ml.features à ce stade.
- Ne pas intégrer les cotes dans le produit.
- Utiliser les cotes uniquement comme enrichissement expérimental ML/RNCP.
- Ne pas sauvegarder de modèle officiel tant qu'une V11 n'est pas validée.

Statut de suivi à mettre à jour :
- Audit colonnes de cotes historiques : réalisé.
- Fichiers concernés : 164, 165, 166.
- Prochaine action : lancer V11 uniquement si le statut est V11_READY.
"""
    (output_dir / OUTPUT_DECISION).write_text(decision, encoding="utf-8")


# Lance l'audit complet et génère les fichiers de preuves.
def main() -> None:
    print("Chargement des fichiers CSV bruts pour audit des cotes...")
    project_root = find_project_root()
    output_dir = get_output_dir(project_root)
    files = list_raw_csv_files(project_root)

    if not files:
        raise FileNotFoundError("Aucun CSV trouvé dans data/ml/raw.")

    frames: list[pd.DataFrame] = []
    for file_info in files:
        frames.append(prepare_raw_frame(file_info))

    full_frame = pd.concat(frames, ignore_index=True, sort=False)
    print(f"CSV analysés : {len(files)}")
    print(f"Lignes analysées : {len(full_frame)}")

    print("Détection des triplets de cotes Home/Draw/Away...")
    triplets = detect_odds_triplets(full_frame.columns)
    print(f"Triplets détectés : {len(triplets)}")

    print("Calcul de la couverture des colonnes de cotes...")
    coverage = compute_triplet_coverage(full_frame, triplets)
    priority_triplets = select_priority_triplets(coverage)
    league_season = compute_league_season_summary(full_frame, priority_triplets)

    # Le fichier 165 contient la couverture globale et une vue compacte par colonnes candidates.
    coverage.to_csv(output_dir / OUTPUT_COVERAGE, index=False, encoding="utf-8")

    # Une vue détaillée par ligue/saison est ajoutée en suffixe dans le même dossier sans changer la séquence officielle.
    league_season_path = output_dir / "165_1x2_market_odds_columns_by_league_season.csv"
    league_season.to_csv(league_season_path, index=False, encoding="utf-8")

    decision_status, blocking_reasons, watch_points = make_decision(coverage)

    print("Génération de la synthèse et de la décision...")
    write_summary(
        output_dir=output_dir,
        project_root=project_root,
        files=files,
        frame=full_frame,
        triplets=triplets,
        coverage=coverage,
        decision_status=decision_status,
        blocking_reasons=blocking_reasons,
        watch_points=watch_points,
    )
    write_decision(
        output_dir=output_dir,
        decision_status=decision_status,
        blocking_reasons=blocking_reasons,
        watch_points=watch_points,
        coverage=coverage,
    )

    print("OK - Audit colonnes de cotes historiques terminé.")
    print(f"Status: {decision_status}")
    print(f"Summary saved: {output_dir / OUTPUT_SUMMARY}")
    print(f"Coverage CSV saved: {output_dir / OUTPUT_COVERAGE}")
    print(f"League/season CSV saved: {league_season_path}")
    print(f"Decision saved: {output_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du script :
# data/ml/raw/**/*.csv
#        ↓ lecture seule
# audit_1x2_market_odds_columns.py
#        ↓ écrit les preuves
# reports/evidence/ml_training/164_*.txt
# reports/evidence/ml_training/165_*.csv
# reports/evidence/ml_training/166_*.txt
