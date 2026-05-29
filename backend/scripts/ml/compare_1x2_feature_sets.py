# Rôle du fichier : comparer plusieurs familles de features 1X2 en mémoire, sans modifier la base ni remplacer la baseline ML validée.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import os
import sys

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "32_1x2_feature_sets_comparison.txt"
CSV_PATH = REPORT_DIR / "33_1x2_feature_sets_comparison.csv"

TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TARGET_COLUMN = "target_result"

OFFICIAL_BASELINE_ACCURACY = 0.4669
OFFICIAL_BASELINE_F1_MACRO = 0.4266


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_backend_env() -> None:
    if not BACKEND_ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {BACKEND_ENV_PATH}")

    for line in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
        clean_line = line.strip()

        if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
            continue

        key, value = clean_line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l’URL PostgreSQL depuis l’environnement local.
def get_database_url() -> str:
    load_backend_env()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable dans backend/.env")

    return database_url


# Crée le dossier de preuves ML si nécessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Charge les matchs nettoyés depuis PostgreSQL.
def fetch_clean_matches(database_url: str) -> list[dict]:
    query = """
        SELECT
            id,
            match_date,
            league_code,
            season,
            home_team,
            away_team,
            home_goals,
            away_goals,
            result
        FROM ml.clean_matches
        WHERE is_valid = TRUE
        ORDER BY match_date ASC, id ASC;
    """

    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())


# Calcule les points obtenus par une équipe sur un match passé.
def calculate_points_for_team(match: dict, team_name: str) -> int:
    if match["result"] == "DRAW":
        return 1

    if match["home_team"] == team_name and match["result"] == "HOME_WIN":
        return 3

    if match["away_team"] == team_name and match["result"] == "AWAY_WIN":
        return 3

    return 0


# Récupère les buts marqués et encaissés par une équipe dans un match.
def get_goals_for_team(match: dict, team_name: str) -> tuple[int, int]:
    if match["home_team"] == team_name:
        return match["home_goals"], match["away_goals"]

    return match["away_goals"], match["home_goals"]


# Calcule les statistiques globales récentes d’une équipe.
def calculate_overall_stats(matches: list[dict], team_name: str) -> tuple[float | None, float | None, float | None]:
    if not matches:
        return None, None, None

    points = []
    goals_scored = []
    goals_conceded = []

    for match in matches:
        team_points = calculate_points_for_team(match, team_name)
        scored, conceded = get_goals_for_team(match, team_name)

        points.append(team_points)
        goals_scored.append(scored)
        goals_conceded.append(conceded)

    form_points = float(sum(points))
    goals_scored_avg = round(sum(goals_scored) / len(goals_scored), 2)
    goals_conceded_avg = round(sum(goals_conceded) / len(goals_conceded), 2)

    return form_points, goals_scored_avg, goals_conceded_avg


# Calcule les statistiques domicile ou extérieur d’une équipe.
def calculate_venue_stats(matches: list[dict], team_name: str) -> tuple[float | None, float | None, float | None]:
    if not matches:
        return None, None, None

    points = []
    goals_scored = []
    goals_conceded = []

    for match in matches:
        team_points = calculate_points_for_team(match, team_name)
        scored, conceded = get_goals_for_team(match, team_name)

        points.append(team_points)
        goals_scored.append(scored)
        goals_conceded.append(conceded)

    points_avg = round(sum(points) / len(points), 2)
    goals_scored_avg = round(sum(goals_scored) / len(goals_scored), 2)
    goals_conceded_avg = round(sum(goals_conceded) / len(goals_conceded), 2)

    return points_avg, goals_scored_avg, goals_conceded_avg


# Calcule les points moyens d’une équipe sur la saison avant le match.
def calculate_season_points_per_match(matches: list[dict], team_name: str) -> float | None:
    if not matches:
        return None

    total_points = sum(calculate_points_for_team(match, team_name) for match in matches)

    return round(total_points / len(matches), 2)


# Calcule une différence simple si les deux valeurs existent.
def safe_diff(left_value: float | None, right_value: float | None) -> float | None:
    if left_value is None or right_value is None:
        return None

    return round(left_value - right_value, 2)


# Calcule une différence absolue si les deux valeurs existent.
def safe_abs_diff(left_value: float | None, right_value: float | None) -> float | None:
    difference = safe_diff(left_value, right_value)

    if difference is None:
        return None

    return abs(difference)


# Construit les features d’un match avec uniquement les matchs passés.
def build_features_for_match(
    match: dict,
    overall_history: dict,
    home_venue_history: dict,
    away_venue_history: dict,
    season_history: dict,
) -> dict:
    league_code = match["league_code"]
    season = match["season"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    home_last_5_home = home_venue_history[(league_code, home_team)][-5:]
    away_last_5_away = away_venue_history[(league_code, away_team)][-5:]

    home_last_10_overall = overall_history[(league_code, home_team)][-10:]
    away_last_10_overall = overall_history[(league_code, away_team)][-10:]

    home_last_10_home = home_venue_history[(league_code, home_team)][-10:]
    away_last_10_away = away_venue_history[(league_code, away_team)][-10:]

    home_season_history = season_history[(league_code, season, home_team)]
    away_season_history = season_history[(league_code, season, away_team)]

    home_form_5, home_scored_5, home_conceded_5 = calculate_overall_stats(
        home_last_5_home,
        home_team,
    )
    away_form_5, away_scored_5, away_conceded_5 = calculate_overall_stats(
        away_last_5_away,
        away_team,
    )

    home_form_10, home_scored_10, home_conceded_10 = calculate_overall_stats(
        home_last_10_overall,
        home_team,
    )
    away_form_10, away_scored_10, away_conceded_10 = calculate_overall_stats(
        away_last_10_overall,
        away_team,
    )

    home_home_points_avg, home_home_scored_avg, home_home_conceded_avg = calculate_venue_stats(
        home_last_10_home,
        home_team,
    )
    away_away_points_avg, away_away_scored_avg, away_away_conceded_avg = calculate_venue_stats(
        away_last_10_away,
        away_team,
    )

    home_season_ppm = calculate_season_points_per_match(home_season_history, home_team)
    away_season_ppm = calculate_season_points_per_match(away_season_history, away_team)

    return {
        "clean_match_id": match["id"],
        "match_date": match["match_date"],
        "league_code": league_code,
        "season": season,
        "home_team": home_team,
        "away_team": away_team,
        "target_result": match["result"],

        "home_form_points_last_5": home_form_5,
        "away_form_points_last_5": away_form_5,
        "home_goals_scored_avg_last_5": home_scored_5,
        "away_goals_scored_avg_last_5": away_scored_5,
        "home_goals_conceded_avg_last_5": home_conceded_5,
        "away_goals_conceded_avg_last_5": away_conceded_5,

        "home_form_points_last_10": home_form_10,
        "away_form_points_last_10": away_form_10,
        "home_goals_scored_avg_last_10": home_scored_10,
        "away_goals_scored_avg_last_10": away_scored_10,
        "home_goals_conceded_avg_last_10": home_conceded_10,
        "away_goals_conceded_avg_last_10": away_conceded_10,

        "form_points_diff": safe_diff(home_form_10, away_form_10),
        "goals_scored_diff": safe_diff(home_scored_10, away_scored_10),
        "goals_conceded_diff": safe_diff(home_conceded_10, away_conceded_10),

        "abs_form_points_diff": safe_abs_diff(home_form_10, away_form_10),
        "abs_goals_scored_diff": safe_abs_diff(home_scored_10, away_scored_10),
        "abs_goals_conceded_diff": safe_abs_diff(home_conceded_10, away_conceded_10),

        "home_home_points_avg_last_10": home_home_points_avg,
        "away_away_points_avg_last_10": away_away_points_avg,
        "home_home_goals_scored_avg_last_10": home_home_scored_avg,
        "away_away_goals_scored_avg_last_10": away_away_scored_avg,
        "home_home_goals_conceded_avg_last_10": home_home_conceded_avg,
        "away_away_goals_conceded_avg_last_10": away_away_conceded_avg,

        "home_season_points_per_match_before_match": home_season_ppm,
        "away_season_points_per_match_before_match": away_season_ppm,
        "season_points_diff": safe_diff(home_season_ppm, away_season_ppm),
    }


# Ajoute les matchs traités à l’historique après calcul des features du jour.
def update_histories(
    matches_for_date: list[dict],
    overall_history: dict,
    home_venue_history: dict,
    away_venue_history: dict,
    season_history: dict,
) -> None:
    for match in matches_for_date:
        league_code = match["league_code"]
        season = match["season"]
        home_team = match["home_team"]
        away_team = match["away_team"]

        overall_history[(league_code, home_team)].append(match)
        overall_history[(league_code, away_team)].append(match)

        home_venue_history[(league_code, home_team)].append(match)
        away_venue_history[(league_code, away_team)].append(match)

        season_history[(league_code, season, home_team)].append(match)
        season_history[(league_code, season, away_team)].append(match)


# Construit toutes les features candidates en mémoire.
def build_feature_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    rows = []

    overall_history = defaultdict(list)
    home_venue_history = defaultdict(list)
    away_venue_history = defaultdict(list)
    season_history = defaultdict(list)

    for _, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            rows.append(
                build_features_for_match(
                    match=match,
                    overall_history=overall_history,
                    home_venue_history=home_venue_history,
                    away_venue_history=away_venue_history,
                    season_history=season_history,
                )
            )

        update_histories(
            matches_for_date=matches_for_date,
            overall_history=overall_history,
            home_venue_history=home_venue_history,
            away_venue_history=away_venue_history,
            season_history=season_history,
        )

    return pd.DataFrame(rows)


FEATURE_SETS = {
    "v1_last5_venue_baseline_like": [
        "home_form_points_last_5",
        "away_form_points_last_5",
        "home_goals_scored_avg_last_5",
        "away_goals_scored_avg_last_5",
        "home_goals_conceded_avg_last_5",
        "away_goals_conceded_avg_last_5",
    ],
    "v2_last10_overall": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
    ],
    "v2_last10_overall_with_diff": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "form_points_diff",
        "goals_scored_diff",
        "goals_conceded_diff",
    ],
    "v2_last10_overall_with_diff_and_abs": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "form_points_diff",
        "goals_scored_diff",
        "goals_conceded_diff",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
    ],
    "v2_last10_overall_plus_venue_strength": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "home_home_points_avg_last_10",
        "away_away_points_avg_last_10",
        "home_home_goals_scored_avg_last_10",
        "away_away_goals_scored_avg_last_10",
        "home_home_goals_conceded_avg_last_10",
        "away_away_goals_conceded_avg_last_10",
    ],
    "v2_last10_diff_abs_venue_strength": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "form_points_diff",
        "goals_scored_diff",
        "goals_conceded_diff",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "home_home_points_avg_last_10",
        "away_away_points_avg_last_10",
        "home_home_goals_scored_avg_last_10",
        "away_away_goals_scored_avg_last_10",
        "home_home_goals_conceded_avg_last_10",
        "away_away_goals_conceded_avg_last_10",
    ],
    "v2_complete_with_season_level": [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "form_points_diff",
        "goals_scored_diff",
        "goals_conceded_diff",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "home_home_points_avg_last_10",
        "away_away_points_avg_last_10",
        "home_home_goals_scored_avg_last_10",
        "away_away_goals_scored_avg_last_10",
        "home_home_goals_conceded_avg_last_10",
        "away_away_goals_conceded_avg_last_10",
        "home_season_points_per_match_before_match",
        "away_season_points_per_match_before_match",
        "season_points_diff",
    ],
}


# Crée le modèle fixe utilisé pour comparer uniquement l’effet des features.
def build_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )


# Évalue un set de features avec le même modèle pour garder une comparaison propre.
def evaluate_feature_set(feature_dataframe: pd.DataFrame, feature_set_name: str, columns: list[str]) -> dict:
    working_dataframe = feature_dataframe.dropna(subset=columns + [TARGET_COLUMN]).copy()

    for column in columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError(f"Train ou test vide pour le set : {feature_set_name}")

    x_train = train_dataframe[columns]
    y_train = train_dataframe[TARGET_COLUMN]

    x_test = test_dataframe[columns]
    y_test = test_dataframe[TARGET_COLUMN]

    model = build_model()
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)

    report = classification_report(
        y_test,
        predictions,
        labels=["HOME_WIN", "DRAW", "AWAY_WIN"],
        output_dict=True,
        zero_division=0,
    )

    return {
        "feature_set": feature_set_name,
        "feature_count": len(columns),
        "rows_after_cleaning": len(working_dataframe),
        "train_rows": len(train_dataframe),
        "test_rows": len(test_dataframe),
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "home_win_precision": round(report["HOME_WIN"]["precision"], 4),
        "home_win_recall": round(report["HOME_WIN"]["recall"], 4),
        "draw_precision": round(report["DRAW"]["precision"], 4),
        "draw_recall": round(report["DRAW"]["recall"], 4),
        "away_win_precision": round(report["AWAY_WIN"]["precision"], 4),
        "away_win_recall": round(report["AWAY_WIN"]["recall"], 4),
        "features": ", ".join(columns),
    }


# Compare tous les sets de features définis.
def compare_feature_sets(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []

    for feature_set_name, columns in FEATURE_SETS.items():
        print(f"Evaluation feature set : {feature_set_name}", flush=True)
        results.append(evaluate_feature_set(feature_dataframe, feature_set_name, columns))

    result_dataframe = pd.DataFrame(results)
    result_dataframe = result_dataframe.sort_values(
        by=["accuracy", "f1_macro"],
        ascending=False,
    )

    return result_dataframe


# Construit la synthèse texte de comparaison.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, comparison: pd.DataFrame) -> str:
    best_row = comparison.iloc[0]

    lines = [
        "RubyBets - ML 1X2 feature sets comparison",
        "32 - Experimentation en memoire sans modification de la base",
        "",
        "Positionnement :",
        "Cette experimentation sert a identifier les familles de features utiles pour ameliorer la baseline ML 1X2.",
        "Elle ne remplace pas le scoring explicable V1 et ne modifie pas la baseline ML deja validee.",
        "",
        "Regle anti-redondance :",
        "- Les features last_5 et last_10 sont comparees, mais ne doivent pas etre empilees automatiquement.",
        "- Une famille de features est retenue seulement si elle ameliore les scores de maniere mesurable.",
        "- Aucune table ml.features_v2 n'est creee pendant cette experimentation.",
        "",
        "Baseline officielle actuelle :",
        f"- Accuracy officielle : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- F1 macro officiel : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features candidates construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Best experimental feature set:",
        f"- Nom : {best_row['feature_set']}",
        f"- Nombre de features : {best_row['feature_count']}",
        f"- Accuracy : {best_row['accuracy']}",
        f"- F1 macro : {best_row['f1_macro']}",
        f"- F1 weighted : {best_row['f1_weighted']}",
        f"- DRAW precision : {best_row['draw_precision']}",
        f"- DRAW recall : {best_row['draw_recall']}",
        "",
        "Comparison table:",
        comparison[
            [
                "feature_set",
                "feature_count",
                "train_rows",
                "test_rows",
                "accuracy",
                "f1_macro",
                "f1_weighted",
                "home_win_recall",
                "draw_recall",
                "away_win_recall",
            ]
        ].to_string(index=False),
        "",
        "Decision rules:",
        "- Si aucun set ne depasse clairement la baseline officielle, on ne remplace pas le modele sauvegarde.",
        "- Si un set ameliore accuracy et F1 macro, il pourra servir a entrainer une V2 separee.",
        "- Si l'accuracy reste loin de 0.70, le modele doit rester experimental.",
        "- Si la V2 est retenue, elle devra etre sauvegardee sous un nom separe : best_1x2_model_v2.joblib.",
        "",
        "Generated files:",
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        str(CSV_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde les résultats CSV et TXT.
def save_reports(comparison: pd.DataFrame, summary: str) -> None:
    comparison.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre l’expérimentation complète.
def main() -> None:
    try:
        ensure_report_dir()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features candidates en memoire...", flush=True)

        feature_dataframe = build_feature_dataframe(clean_matches)

        print(f"Lignes de features candidates : {len(feature_dataframe)}", flush=True)
        print("Comparaison des sets de features...", flush=True)

        comparison = compare_feature_sets(feature_dataframe)
        summary = build_summary(clean_matches, feature_dataframe, comparison)

        save_reports(comparison, summary)

        best_row = comparison.iloc[0]

        print("OK - Comparaison des feature sets terminee.")
        print(f"Best feature set: {best_row['feature_set']}")
        print(f"Accuracy: {best_row['accuracy']}")
        print(f"F1 macro: {best_row['f1_macro']}")
        print(f"DRAW recall: {best_row['draw_recall']}")
        print("Summary saved: reports/evidence/ml_training/32_1x2_feature_sets_comparison.txt")
        print("CSV saved: reports/evidence/ml_training/33_1x2_feature_sets_comparison.csv")

    except Exception as error:
        print("Erreur pendant la comparaison des feature sets.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# compare_1x2_feature_sets.py
#   -> lit backend/.env pour DATABASE_URL
#   -> lit PostgreSQL : ml.clean_matches
#   -> construit des features candidates en mémoire
#   -> compare plusieurs familles de features sans modifier ml.features
#   -> entraîne un modèle fixe LogisticRegression_balanced
#   -> écrit reports/evidence/ml_training/32_1x2_feature_sets_comparison.txt
#   -> écrit reports/evidence/ml_training/33_1x2_feature_sets_comparison.csv