# Rôle du fichier : auditer les CSV historiques pour vérifier les labels Over/Under, BTTS et les colonnes de cotes disponibles avant la phase V14 multi-marchés.

from __future__ import annotations

import csv
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


OUTPUT_SUMMARY = "206_goals_btts_market_columns_audit_summary.txt"
OUTPUT_AUDIT_CSV = "207_goals_btts_market_columns_audit.csv"

RECENT_COVERAGE_START_YEAR = 2020
MIN_READY_ODDS_ROWS = 1000
MIN_READY_RECENT_COVERAGE = 0.50

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class CsvFileInfo:
    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class OddsPair:
    market_group: str
    bookmaker_prefix: str
    positive_col: str
    negative_col: str

    @property
    def key(self) -> str:
        return f"{self.market_group}_{self.bookmaker_prefix}"


# Retrouve la racine RubyBets depuis l'emplacement du script.
def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "data" / "ml" / "raw").exists():
            return parent
    raise FileNotFoundError("Impossible de trouver la racine projet : data/ml/raw est introuvable.")


# Retourne le dossier de preuves ML et le crée si nécessaire.
def get_evidence_dir(project_root: Path) -> Path:
    output_dir = project_root / "reports" / "evidence" / "ml_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Extrait la saison depuis un nom de fichier comme E0_2024_2025.csv.
def infer_season_from_filename(path: Path) -> str:
    parts = path.stem.split("_")
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}_{parts[-1]}"
    return "UNKNOWN"


# Extrait le code ligue depuis le nom du fichier CSV brut.
def infer_league_code(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        return stem.split("_")[0]
    return "UNKNOWN"


# Transforme une saison 2024_2025 en année de début 2024.
def season_start_year(season: object) -> int:
    try:
        return int(str(season).split("_")[0])
    except Exception:  # noqa: BLE001 - fallback robuste pour fichiers historiques hétérogènes
        return -1


# Indique si une saison appartient au périmètre récent utilisé pour l'audit de couverture.
def is_recent_season(season: object) -> bool:
    return season_start_year(season) >= RECENT_COVERAGE_START_YEAR


# Arrondit une valeur numérique pour stabiliser les sorties.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio sans risque de division par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Liste les fichiers CSV bruts disponibles dans data/ml/raw.
def list_raw_csv_files(project_root: Path) -> list[CsvFileInfo]:
    raw_dir = project_root / "data" / "ml" / "raw"
    return [
        CsvFileInfo(path=path, league_code=infer_league_code(path), season=infer_season_from_filename(path))
        for path in sorted(raw_dir.rglob("*.csv"))
    ]


# Lit un CSV Football-Data avec des fallbacks d'encodage et de lignes mal formées.
def read_csv_safely(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding, engine="python", on_bad_lines="skip")
        except Exception as error:  # noqa: BLE001 - fallback volontaire sur données historiques
            last_error = error

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

            return pd.DataFrame(rows, columns=[str(column).strip().replace("\ufeff", "") for column in header])
        except Exception as error:  # noqa: BLE001 - fallback volontaire sur données historiques
            last_error = error

    raise RuntimeError(f"Lecture impossible du fichier {path}: {last_error}")


# Convertit une colonne en série numérique exploitable.
def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([math.nan] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


# Nettoie les noms de colonnes pour éviter les espaces invisibles ou BOM.
def clean_columns(columns: Iterable[object]) -> list[str]:
    return [str(column).strip().replace("\ufeff", "") for column in columns]


# Prépare un fichier CSV brut en ajoutant des métadonnées sans modifier le fichier original.
def prepare_raw_frame(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = clean_columns(frame.columns)
    frame["__source_file"] = str(file_info.path)
    frame["__league_code"] = file_info.league_code
    frame["__season"] = file_info.season
    frame["__season_start_year"] = season_start_year(file_info.season)
    return frame


# Détecte les paires Over/Under pour un seuil donné, par exemple >2.5 et <2.5.
def detect_over_under_pairs(columns: Iterable[str], threshold: str) -> list[OddsPair]:
    column_set = {str(column).strip().replace("\ufeff", "") for column in columns}
    pairs: dict[str, OddsPair] = {}

    for column in column_set:
        if f">{threshold}" not in column:
            continue
        prefix = column.split(f">{threshold}", 1)[0]
        negative_col = f"{prefix}<{threshold}"
        if negative_col in column_set:
            market_group = f"OVER_UNDER_{threshold.replace('.', '_')}"
            pairs[prefix] = OddsPair(market_group, prefix, column, negative_col)

    return sorted(pairs.values(), key=lambda item: item.key)


# Détecte prudemment les paires BTTS Yes/No selon les conventions les plus fréquentes.
def detect_btts_pairs(columns: Iterable[str]) -> list[OddsPair]:
    column_set = {str(column).strip().replace("\ufeff", "") for column in columns}
    upper_to_original = {column.upper(): column for column in column_set}
    pairs: dict[str, OddsPair] = {}

    suffix_pairs = [
        ("BTTSY", "BTTSN"),
        ("BTTSYES", "BTTSNO"),
        ("BTSY", "BTSN"),
        ("BTSYES", "BTSNO"),
        ("GG", "NG"),
    ]

    for upper_column, original_column in upper_to_original.items():
        for positive_suffix, negative_suffix in suffix_pairs:
            if not upper_column.endswith(positive_suffix):
                continue
            prefix = upper_column[: -len(positive_suffix)]
            negative_upper = f"{prefix}{negative_suffix}"
            if negative_upper in upper_to_original:
                original_negative = upper_to_original[negative_upper]
                readable_prefix = re.sub(r"[^A-Z0-9_]+", "_", prefix).strip("_") or "UNKNOWN"
                pairs[f"{readable_prefix}_{positive_suffix}_{negative_suffix}"] = OddsPair(
                    "BTTS",
                    readable_prefix,
                    original_column,
                    original_negative,
                )

    return sorted(pairs.values(), key=lambda item: item.key)


# Calcule les labels Over/Under et BTTS à partir des scores finaux réels.
def build_score_labels(frame: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame(index=frame.index)
    home_goals = numeric_series(frame, "FTHG")
    away_goals = numeric_series(frame, "FTAG")
    valid_score = home_goals.notna() & away_goals.notna() & (home_goals >= 0) & (away_goals >= 0)
    total_goals = home_goals + away_goals

    output["valid_score"] = valid_score
    output["total_goals"] = total_goals.where(valid_score)
    output["over_1_5"] = (total_goals >= 2).where(valid_score)
    output["under_1_5"] = (total_goals <= 1).where(valid_score)
    output["over_2_5"] = (total_goals >= 3).where(valid_score)
    output["under_2_5"] = (total_goals <= 2).where(valid_score)
    output["btts_yes"] = ((home_goals >= 1) & (away_goals >= 1)).where(valid_score)
    output["btts_no"] = ((home_goals == 0) | (away_goals == 0)).where(valid_score)
    return output


# Calcule le nombre de lignes où une paire de cotes est exploitable.
def count_valid_odds_rows(frame: pd.DataFrame, pair: OddsPair) -> int:
    positive = numeric_series(frame, pair.positive_col)
    negative = numeric_series(frame, pair.negative_col)
    valid = (positive > 1.0) & (negative > 1.0)
    return int(valid.sum())


# Calcule si au moins une paire de cotes est exploitable sur chaque ligne.
def build_any_valid_odds_mask(frame: pd.DataFrame, pairs: list[OddsPair]) -> pd.Series:
    if not pairs:
        return pd.Series([False] * len(frame), index=frame.index)

    result = pd.Series([False] * len(frame), index=frame.index)
    for pair in pairs:
        positive = numeric_series(frame, pair.positive_col)
        negative = numeric_series(frame, pair.negative_col)
        result = result | ((positive > 1.0) & (negative > 1.0))
    return result


# Audite un fichier CSV et retourne les lignes détaillées ainsi que les compteurs globaux.
def audit_single_file(file_info: CsvFileInfo) -> tuple[list[dict[str, object]], dict[str, object]]:
    frame = prepare_raw_frame(file_info)
    labels = build_score_labels(frame)
    valid_score_rows = int(labels["valid_score"].sum())

    over_25_pairs = detect_over_under_pairs(frame.columns, "2.5")
    over_15_pairs = detect_over_under_pairs(frame.columns, "1.5")
    btts_pairs = detect_btts_pairs(frame.columns)

    any_over_25 = build_any_valid_odds_mask(frame, over_25_pairs)
    any_over_15 = build_any_valid_odds_mask(frame, over_15_pairs)
    any_btts = build_any_valid_odds_mask(frame, btts_pairs)

    base = {
        "source_file": str(file_info.path),
        "file_name": file_info.path.name,
        "league_code": file_info.league_code,
        "season": file_info.season,
        "season_start_year": season_start_year(file_info.season),
        "raw_rows": len(frame),
        "valid_score_rows": valid_score_rows,
        "is_recent_scope": is_recent_season(file_info.season),
    }

    rows: list[dict[str, object]] = [
        {
            **base,
            "audit_kind": "SCORE_LABELS",
            "market_group": "GOALS_BTTS_LABELS",
            "market_key": "score_labels_from_FTHG_FTAG",
            "positive_col": "FTHG+FTAG",
            "negative_col": "FTHG+FTAG",
            "valid_odds_rows": 0,
            "odds_coverage_rate": 0.0,
            "over_1_5_yes_rows": int(labels["over_1_5"].fillna(False).sum()),
            "under_1_5_yes_rows": int(labels["under_1_5"].fillna(False).sum()),
            "over_2_5_yes_rows": int(labels["over_2_5"].fillna(False).sum()),
            "under_2_5_yes_rows": int(labels["under_2_5"].fillna(False).sum()),
            "btts_yes_rows": int(labels["btts_yes"].fillna(False).sum()),
            "btts_no_rows": int(labels["btts_no"].fillna(False).sum()),
        }
    ]

    for pair in [*over_25_pairs, *over_15_pairs, *btts_pairs]:
        valid_odds_rows = count_valid_odds_rows(frame, pair)
        rows.append(
            {
                **base,
                "audit_kind": "ODDS_PAIR",
                "market_group": pair.market_group,
                "market_key": pair.key,
                "positive_col": pair.positive_col,
                "negative_col": pair.negative_col,
                "valid_odds_rows": valid_odds_rows,
                "odds_coverage_rate": rounded(safe_rate(valid_odds_rows, len(frame))),
                "over_1_5_yes_rows": "",
                "under_1_5_yes_rows": "",
                "over_2_5_yes_rows": "",
                "under_2_5_yes_rows": "",
                "btts_yes_rows": "",
                "btts_no_rows": "",
            }
        )

    counters = {
        "raw_rows": len(frame),
        "valid_score_rows": valid_score_rows,
        "over_1_5_yes_rows": int(labels["over_1_5"].fillna(False).sum()),
        "under_1_5_yes_rows": int(labels["under_1_5"].fillna(False).sum()),
        "over_2_5_yes_rows": int(labels["over_2_5"].fillna(False).sum()),
        "under_2_5_yes_rows": int(labels["under_2_5"].fillna(False).sum()),
        "btts_yes_rows": int(labels["btts_yes"].fillna(False).sum()),
        "btts_no_rows": int(labels["btts_no"].fillna(False).sum()),
        "over_25_pair_count": len(over_25_pairs),
        "over_15_pair_count": len(over_15_pairs),
        "btts_pair_count": len(btts_pairs),
        "over_25_any_odds_rows": int(any_over_25.sum()),
        "over_15_any_odds_rows": int(any_over_15.sum()),
        "btts_any_odds_rows": int(any_btts.sum()),
        "recent_raw_rows": len(frame) if is_recent_season(file_info.season) else 0,
        "recent_over_25_any_odds_rows": int(any_over_25.sum()) if is_recent_season(file_info.season) else 0,
        "recent_over_15_any_odds_rows": int(any_over_15.sum()) if is_recent_season(file_info.season) else 0,
        "recent_btts_any_odds_rows": int(any_btts.sum()) if is_recent_season(file_info.season) else 0,
        "over_25_unique_pairs": {pair.key for pair in over_25_pairs},
        "over_15_unique_pairs": {pair.key for pair in over_15_pairs},
        "btts_unique_pairs": {pair.key for pair in btts_pairs},
    }
    return rows, counters


# Fusionne les compteurs fichier par fichier en synthèse globale.
def merge_counters(counters: list[dict[str, object]]) -> dict[str, object]:
    numeric_keys = [
        "raw_rows",
        "valid_score_rows",
        "over_1_5_yes_rows",
        "under_1_5_yes_rows",
        "over_2_5_yes_rows",
        "under_2_5_yes_rows",
        "btts_yes_rows",
        "btts_no_rows",
        "over_25_pair_count",
        "over_15_pair_count",
        "btts_pair_count",
        "over_25_any_odds_rows",
        "over_15_any_odds_rows",
        "btts_any_odds_rows",
        "recent_raw_rows",
        "recent_over_25_any_odds_rows",
        "recent_over_15_any_odds_rows",
        "recent_btts_any_odds_rows",
    ]
    merged: dict[str, object] = {key: sum(int(counter.get(key, 0)) for counter in counters) for key in numeric_keys}

    for key in ["over_25_unique_pairs", "over_15_unique_pairs", "btts_unique_pairs"]:
        values: set[str] = set()
        for counter in counters:
            values.update(set(counter.get(key, set())))
        merged[key] = values

    return merged


# Détermine le statut d'audit selon les labels et la disponibilité des colonnes de marché.
def determine_status(summary: dict[str, object]) -> str:
    valid_score_rows = int(summary.get("valid_score_rows", 0))
    recent_rows = int(summary.get("recent_raw_rows", 0))
    recent_over_25 = int(summary.get("recent_over_25_any_odds_rows", 0))
    recent_over_15 = int(summary.get("recent_over_15_any_odds_rows", 0))
    recent_btts = int(summary.get("recent_btts_any_odds_rows", 0))

    over_25_ready = recent_over_25 >= MIN_READY_ODDS_ROWS and safe_rate(recent_over_25, recent_rows) >= MIN_READY_RECENT_COVERAGE
    over_15_ready = recent_over_15 >= MIN_READY_ODDS_ROWS and safe_rate(recent_over_15, recent_rows) >= MIN_READY_RECENT_COVERAGE
    btts_ready = recent_btts >= MIN_READY_ODDS_ROWS and safe_rate(recent_btts, recent_rows) >= MIN_READY_RECENT_COVERAGE

    if valid_score_rows == 0:
        return "GOALS_BTTS_AUDIT_BLOCKED_NO_SCORE_LABELS"
    if over_25_ready and over_15_ready and btts_ready:
        return "GOALS_BTTS_AUDIT_READY_MARKET_ODDS_FULL"
    if over_25_ready:
        return "GOALS_BTTS_AUDIT_READY_OVER25_MARKET_LABELS_ONLY_FOR_OTHERS"
    return "GOALS_BTTS_AUDIT_LABELS_READY_MARKET_ODDS_LIMITED"


# Ecrit la synthèse texte exploitable comme preuve RNCP.
def write_summary(evidence_dir: Path, files: list[CsvFileInfo], summary: dict[str, object], detail_dataframe: pd.DataFrame) -> None:
    status = determine_status(summary)
    recent_rows = int(summary.get("recent_raw_rows", 0))
    over_25_pairs = sorted(set(summary.get("over_25_unique_pairs", set())))
    over_15_pairs = sorted(set(summary.get("over_15_unique_pairs", set())))
    btts_pairs = sorted(set(summary.get("btts_unique_pairs", set())))

    lines = [
        "RubyBets - Audit V14 multi-marchés : Over/Under et BTTS",
        "206 - Synthèse audit colonnes goals / BTTS",
        "",
        "Objectif :",
        "Vérifier les labels constructibles depuis les scores réels et les colonnes de cotes disponibles avant de lancer V14 / V15 / V16.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {len(files)}",
        f"- Lignes brutes : {int(summary.get('raw_rows', 0))}",
        f"- Lignes avec score exploitable : {int(summary.get('valid_score_rows', 0))}",
        f"- Ligues : {', '.join(sorted({file.league_code for file in files}))}",
        f"- Saisons : {min(file.season for file in files)} -> {max(file.season for file in files)}",
        "",
        "Labels constructibles depuis FTHG / FTAG :",
        f"- OVER_1_5 yes rows : {int(summary.get('over_1_5_yes_rows', 0))}",
        f"- UNDER_1_5 yes rows : {int(summary.get('under_1_5_yes_rows', 0))}",
        f"- OVER_2_5 yes rows : {int(summary.get('over_2_5_yes_rows', 0))}",
        f"- UNDER_2_5 yes rows : {int(summary.get('under_2_5_yes_rows', 0))}",
        f"- BTTS_YES rows : {int(summary.get('btts_yes_rows', 0))}",
        f"- BTTS_NO rows : {int(summary.get('btts_no_rows', 0))}",
        "",
        "Colonnes de cotes détectées :",
        f"- Paires Over/Under 2.5 détectées : {len(over_25_pairs)}",
        f"- Paires Over/Under 1.5 détectées : {len(over_15_pairs)}",
        f"- Paires BTTS détectées : {len(btts_pairs)}",
        "",
        "Couverture odds globale :",
        f"- Lignes avec au moins une cote O/U 2.5 exploitable : {int(summary.get('over_25_any_odds_rows', 0))}",
        f"- Lignes avec au moins une cote O/U 1.5 exploitable : {int(summary.get('over_15_any_odds_rows', 0))}",
        f"- Lignes avec au moins une cote BTTS exploitable : {int(summary.get('btts_any_odds_rows', 0))}",
        "",
        "Couverture odds récente depuis 2020 :",
        f"- Lignes récentes : {recent_rows}",
        f"- O/U 2.5 récent exploitable : {int(summary.get('recent_over_25_any_odds_rows', 0))} ({rounded(safe_rate(int(summary.get('recent_over_25_any_odds_rows', 0)), recent_rows))})",
        f"- O/U 1.5 récent exploitable : {int(summary.get('recent_over_15_any_odds_rows', 0))} ({rounded(safe_rate(int(summary.get('recent_over_15_any_odds_rows', 0)), recent_rows))})",
        f"- BTTS récent exploitable : {int(summary.get('recent_btts_any_odds_rows', 0))} ({rounded(safe_rate(int(summary.get('recent_btts_any_odds_rows', 0)), recent_rows))})",
        "",
        "Exemples de paires O/U 2.5 :",
        f"- {', '.join(over_25_pairs[:20]) if over_25_pairs else 'Aucune'}",
        "",
        "Exemples de paires O/U 1.5 :",
        f"- {', '.join(over_15_pairs[:20]) if over_15_pairs else 'Aucune'}",
        "",
        "Exemples de paires BTTS :",
        f"- {', '.join(btts_pairs[:20]) if btts_pairs else 'Aucune'}",
        "",
        "Status :",
        f"- {status}",
        "",
        "Décision technique recommandée :",
    ]

    if "READY_OVER25_MARKET" in status:
        lines.extend(
            [
                "- Lancer V14 Over/Under 2.5 en priorité avec les cotes de marché disponibles.",
                "- Construire Over/Under 1.5 et BTTS depuis les labels de score, mais ne pas supposer de cotes exploitables si l'audit indique une couverture nulle.",
            ]
        )
    elif "LABELS_READY" in status:
        lines.extend(
            [
                "- Les labels Over/Under et BTTS sont constructibles depuis les scores réels.",
                "- Les cotes de marché sont limitées : commencer par des features statistiques en mémoire, ou limiter V14 aux marchés disposant de colonnes suffisantes.",
            ]
        )
    else:
        lines.append("- Ne pas lancer V14 avant correction du problème de labels de score.")

    lines.extend(
        [
            "",
            "Fichiers générés :",
            f"- {OUTPUT_SUMMARY}",
            f"- {OUTPUT_AUDIT_CSV}",
            "",
            "Statut de suivi :",
            "- Audit colonnes Over/Under et BTTS : réalisé si les fichiers 206 et 207 sont générés.",
            "- Prochaine étape : décider le périmètre V14 selon la disponibilité réelle des colonnes de marché.",
            "",
            f"Lignes détaillées dans le CSV : {len(detail_dataframe)}",
        ]
    )

    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Orchestre l'audit complet et génère les preuves 206 et 207.
def main() -> None:
    print("Audit des colonnes Over/Under et BTTS dans les CSV bruts...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    files = list_raw_csv_files(project_root)
    if not files:
        raise FileNotFoundError("Aucun CSV brut trouvé dans data/ml/raw.")

    all_rows: list[dict[str, object]] = []
    all_counters: list[dict[str, object]] = []

    for file_info in files:
        rows, counters = audit_single_file(file_info)
        all_rows.extend(rows)
        all_counters.append(counters)

    detail_dataframe = pd.DataFrame(all_rows)
    detail_dataframe = detail_dataframe.sort_values(
        by=["league_code", "season", "audit_kind", "market_group", "market_key"],
        ascending=[True, True, True, True, True],
    )
    detail_dataframe.to_csv(evidence_dir / OUTPUT_AUDIT_CSV, index=False, encoding="utf-8-sig")

    summary = merge_counters(all_counters)
    status = determine_status(summary)
    write_summary(evidence_dir, files, summary, detail_dataframe)

    print("OK - Audit colonnes goals / BTTS terminé.")
    print(f"Status: {status}")
    print(f"CSV analysés: {len(files)}")
    print(f"Lignes brutes: {int(summary.get('raw_rows', 0))}")
    print(f"Lignes avec score exploitable: {int(summary.get('valid_score_rows', 0))}")
    print(f"Paires O/U 2.5 détectées: {len(set(summary.get('over_25_unique_pairs', set())))}")
    print(f"Paires O/U 1.5 détectées: {len(set(summary.get('over_15_unique_pairs', set())))}")
    print(f"Paires BTTS détectées: {len(set(summary.get('btts_unique_pairs', set())))}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Audit CSV saved: {evidence_dir / OUTPUT_AUDIT_CSV}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# audit_goals_btts_market_columns.py
# ├── lit uniquement : data/ml/raw/**/*.csv
# └── écrit uniquement : reports/evidence/ml_training/206_*.txt et 207_*.csv
# Aucun accès PostgreSQL | aucune modification ml.features | aucune API/front/scoring V1 | aucun modèle sauvegardé.
