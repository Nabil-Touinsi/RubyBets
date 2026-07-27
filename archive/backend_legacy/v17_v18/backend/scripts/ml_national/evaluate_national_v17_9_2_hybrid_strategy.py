# Rôle du fichier :
# Ce script évalue une stratégie hybride V17.9.2 pour RubyBets national.
# Il combine prédictions strictes 1X2, double chance et abstention pour augmenter la couverture.

from pathlib import Path
import argparse
import csv
import os
import sys
from decimal import Decimal

import pandas as pd
import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_PREDICTIONS_FILE = EVIDENCE_DIR / "306_national_v17_9_predictions.csv"
DEFAULT_MIN_COVERAGE = 0.65

SUMMARY_FILENAME = "315_national_v17_9_2_hybrid_strategy_summary.txt"
RESULTS_FILENAME = "316_national_v17_9_2_hybrid_strategy_results.csv"
BEST_SELECTION_FILENAME = "317_national_v17_9_2_best_hybrid_predictions.csv"

STRICT_MARKET = "STRICT_1X2"
DOUBLE_CHANCE_MARKET = "DOUBLE_CHANCE"
ABSTAIN_MARKET = "ABSTAIN"

TARGET_LABELS = [
    "TEAM_A_WIN",
    "DRAW",
    "TEAM_B_WIN",
]


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_env_file() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {ENV_PATH}")

    with ENV_PATH.open("r", encoding="utf-8") as env_file:
        for line in env_file:
            clean_line = line.strip()

            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue

            key, value = clean_line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis backend/.env.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Évaluer la stratégie hybride nationale RubyBets V17.9.2."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features utilisée pour l'évaluation.",
    )

    parser.add_argument(
        "--predictions-file",
        default=str(DEFAULT_PREDICTIONS_FILE),
        help="Chemin du CSV 306_national_v17_9_predictions.csv.",
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help="Couverture minimale recherchée pour choisir une stratégie hybride.",
    )

    return parser.parse_args()


# Crée le dossier de preuves ML si nécessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Convertit les valeurs PostgreSQL numériques en float.
def normalize_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)

    return value


# Charge les prédictions produites par la baseline V17.9.
def load_predictions(predictions_file: str) -> pd.DataFrame:
    predictions_path = Path(predictions_file)

    if not predictions_path.exists():
        raise FileNotFoundError(f"Fichier de prédictions introuvable : {predictions_path}")

    dataframe = pd.read_csv(predictions_path)

    required_columns = {
        "clean_match_id",
        "target_result",
        "predicted_result",
        "is_correct",
    }

    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans le CSV prédictions : {missing_columns}")

    dataframe["clean_match_id"] = dataframe["clean_match_id"].astype(int)
    dataframe["is_correct"] = dataframe["is_correct"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )

    return dataframe


# Récupère le contexte des features nécessaire à la stratégie hybride.
def fetch_feature_context(
    connection: psycopg.Connection,
    feature_version: str,
) -> pd.DataFrame:
    query = """
        SELECT
            f.clean_match_id,
            f.feature_version,
            cm.match_date_utc,
            cm.competition_code,
            cm.season,
            cm.home_team_name AS team_a_name,
            cm.away_team_name AS team_b_name,
            f.elo_gap,
            f.is_neutral_venue,
            f.team_a_is_host,
            f.team_b_is_host,
            f.host_advantage_side,
            f.is_group_stage,
            f.is_knockout_stage,
            f.target_result
        FROM ml_national.features f
        JOIN ml_national.clean_matches cm
            ON cm.id = f.clean_match_id
        WHERE f.feature_version = %s
        ORDER BY cm.match_date_utc ASC, f.clean_match_id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (feature_version,))
        rows = cursor.fetchall()

    normalized_rows = [
        {key: normalize_value(value) for key, value in row.items()}
        for row in rows
    ]

    return pd.DataFrame(normalized_rows)


# Fusionne les prédictions avec les features utiles.
def build_evaluation_dataframe(
    predictions_dataframe: pd.DataFrame,
    feature_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    prediction_columns_to_drop = [
        "match_date_utc",
        "competition_code",
        "season",
        "team_a_name",
        "team_b_name",
    ]

    clean_predictions_dataframe = predictions_dataframe.drop(
        columns=prediction_columns_to_drop,
        errors="ignore",
    )

    evaluation_dataframe = clean_predictions_dataframe.merge(
        feature_dataframe.drop(columns=["target_result"], errors="ignore"),
        on="clean_match_id",
        how="left",
    )

    evaluation_dataframe["match_date_utc"] = pd.to_datetime(
        evaluation_dataframe["match_date_utc"],
        utc=True,
    )

    evaluation_dataframe["elo_gap"] = pd.to_numeric(
        evaluation_dataframe["elo_gap"],
        errors="coerce",
    )

    evaluation_dataframe["abs_elo_gap"] = evaluation_dataframe["elo_gap"].abs()

    evaluation_dataframe["host_advantage_side"] = evaluation_dataframe[
        "host_advantage_side"
    ].fillna("NONE")

    boolean_columns = [
        "is_neutral_venue",
        "team_a_is_host",
        "team_b_is_host",
        "is_group_stage",
        "is_knockout_stage",
    ]

    for column in boolean_columns:
        evaluation_dataframe[column] = evaluation_dataframe[column].fillna(False)

    return evaluation_dataframe


# Retourne une double chance selon l'équipe favorisée par l'écart Elo.
def build_favorite_double_chance(row: pd.Series) -> str:
    if row["elo_gap"] < 0:
        return "TEAM_B_OR_DRAW"

    return "TEAM_A_OR_DRAW"


# Retourne une double chance selon la prédiction stricte du modèle.
def build_predicted_side_double_chance(row: pd.Series) -> str:
    if row["predicted_result"] == "TEAM_B_WIN":
        return "TEAM_B_OR_DRAW"

    if row["predicted_result"] == "TEAM_A_WIN":
        return "TEAM_A_OR_DRAW"

    return build_favorite_double_chance(row)


# Vérifie si une recommandation est correcte selon le résultat réel.
def is_recommendation_correct(target_result: str, recommendation: str) -> bool | None:
    if recommendation == "ABSTAIN":
        return None

    if recommendation == "TEAM_A_WIN":
        return target_result == "TEAM_A_WIN"

    if recommendation == "DRAW":
        return target_result == "DRAW"

    if recommendation == "TEAM_B_WIN":
        return target_result == "TEAM_B_WIN"

    if recommendation == "TEAM_A_OR_DRAW":
        return target_result in ["TEAM_A_WIN", "DRAW"]

    if recommendation == "TEAM_B_OR_DRAW":
        return target_result in ["TEAM_B_WIN", "DRAW"]

    if recommendation == "TEAM_A_OR_TEAM_B":
        return target_result in ["TEAM_A_WIN", "TEAM_B_WIN"]

    raise ValueError(f"Recommandation inconnue : {recommendation}")


# Applique la stratégie stricte brute V17.9 sans abstention.
def apply_strict_all_strategy(row: pd.Series) -> dict[str, object]:
    return {
        "market_type": STRICT_MARKET,
        "recommendation": row["predicted_result"],
        "risk_level": "standard",
        "selection_reason": "baseline_strict_prediction",
    }


# Applique la stratégie sélective V17.9.1 retenue.
def apply_v17_9_1_abs_150_strategy(row: pd.Series) -> dict[str, object]:
    if row["abs_elo_gap"] >= 150:
        return {
            "market_type": STRICT_MARKET,
            "recommendation": row["predicted_result"],
            "risk_level": "medium",
            "selection_reason": "strict_selected_abs_elo_gap_150_plus",
        }

    return {
        "market_type": ABSTAIN_MARKET,
        "recommendation": "ABSTAIN",
        "risk_level": "high",
        "selection_reason": "abstain_abs_elo_gap_below_150",
    }


# Applique une stratégie hybride prudente.
def apply_hybrid_safe_strategy(row: pd.Series) -> dict[str, object]:
    if row["abs_elo_gap"] >= 200 and row["predicted_result"] != "DRAW":
        return {
            "market_type": STRICT_MARKET,
            "recommendation": row["predicted_result"],
            "risk_level": "medium",
            "selection_reason": "strict_non_draw_abs_elo_gap_200_plus",
        }

    if row["abs_elo_gap"] >= 100:
        return {
            "market_type": DOUBLE_CHANCE_MARKET,
            "recommendation": build_favorite_double_chance(row),
            "risk_level": "medium",
            "selection_reason": "double_chance_favorite_abs_elo_gap_100_plus",
        }

    return {
        "market_type": ABSTAIN_MARKET,
        "recommendation": "ABSTAIN",
        "risk_level": "high",
        "selection_reason": "abstain_abs_elo_gap_below_100",
    }


# Applique une stratégie hybride équilibrée.
def apply_hybrid_balanced_strategy(row: pd.Series) -> dict[str, object]:
    if row["abs_elo_gap"] >= 200 and row["predicted_result"] != "DRAW":
        return {
            "market_type": STRICT_MARKET,
            "recommendation": row["predicted_result"],
            "risk_level": "medium",
            "selection_reason": "strict_non_draw_abs_elo_gap_200_plus",
        }

    if row["abs_elo_gap"] >= 100:
        return {
            "market_type": DOUBLE_CHANCE_MARKET,
            "recommendation": build_favorite_double_chance(row),
            "risk_level": "medium",
            "selection_reason": "double_chance_favorite_abs_elo_gap_100_plus",
        }

    if row["abs_elo_gap"] >= 50 and row["predicted_result"] != "DRAW":
        return {
            "market_type": DOUBLE_CHANCE_MARKET,
            "recommendation": build_predicted_side_double_chance(row),
            "risk_level": "high",
            "selection_reason": "double_chance_predicted_side_abs_elo_gap_50_plus",
        }

    return {
        "market_type": ABSTAIN_MARKET,
        "recommendation": "ABSTAIN",
        "risk_level": "high",
        "selection_reason": "abstain_too_balanced_or_predicted_draw",
    }


# Applique une stratégie hybride orientée couverture.
def apply_hybrid_coverage_strategy(row: pd.Series) -> dict[str, object]:
    if row["abs_elo_gap"] >= 150 and row["predicted_result"] != "DRAW":
        return {
            "market_type": STRICT_MARKET,
            "recommendation": row["predicted_result"],
            "risk_level": "medium",
            "selection_reason": "strict_non_draw_abs_elo_gap_150_plus",
        }

    if row["abs_elo_gap"] >= 50:
        return {
            "market_type": DOUBLE_CHANCE_MARKET,
            "recommendation": build_favorite_double_chance(row),
            "risk_level": "medium",
            "selection_reason": "double_chance_favorite_abs_elo_gap_50_plus",
        }

    return {
        "market_type": ABSTAIN_MARKET,
        "recommendation": "ABSTAIN",
        "risk_level": "high",
        "selection_reason": "abstain_abs_elo_gap_below_50",
    }


# Applique une stratégie hybride très couvrante.
def apply_hybrid_max_coverage_strategy(row: pd.Series) -> dict[str, object]:
    if row["abs_elo_gap"] >= 200 and row["predicted_result"] != "DRAW":
        return {
            "market_type": STRICT_MARKET,
            "recommendation": row["predicted_result"],
            "risk_level": "medium",
            "selection_reason": "strict_non_draw_abs_elo_gap_200_plus",
        }

    return {
        "market_type": DOUBLE_CHANCE_MARKET,
        "recommendation": build_favorite_double_chance(row),
        "risk_level": "medium",
        "selection_reason": "double_chance_favorite_max_coverage",
    }


# Applique une stratégie nommée à tout le dataframe.
def apply_strategy(dataframe: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    strategy_functions = {
        "strict_all_predictions": apply_strict_all_strategy,
        "v17_9_1_abs_150_plus": apply_v17_9_1_abs_150_strategy,
        "v17_9_2_hybrid_safe": apply_hybrid_safe_strategy,
        "v17_9_2_hybrid_balanced": apply_hybrid_balanced_strategy,
        "v17_9_2_hybrid_coverage": apply_hybrid_coverage_strategy,
        "v17_9_2_hybrid_max_coverage": apply_hybrid_max_coverage_strategy,
    }

    if strategy_name not in strategy_functions:
        raise ValueError(f"Stratégie inconnue : {strategy_name}")

    strategy_function = strategy_functions[strategy_name]

    evaluated_dataframe = dataframe.copy()

    recommendations = evaluated_dataframe.apply(strategy_function, axis=1)

    evaluated_dataframe["strategy_name"] = strategy_name
    evaluated_dataframe["market_type"] = recommendations.apply(lambda item: item["market_type"])
    evaluated_dataframe["recommendation"] = recommendations.apply(lambda item: item["recommendation"])
    evaluated_dataframe["risk_level"] = recommendations.apply(lambda item: item["risk_level"])
    evaluated_dataframe["selection_reason"] = recommendations.apply(lambda item: item["selection_reason"])

    evaluated_dataframe["is_selected"] = evaluated_dataframe["recommendation"] != "ABSTAIN"

    evaluated_dataframe["is_recommendation_correct"] = evaluated_dataframe.apply(
        lambda row: is_recommendation_correct(
            target_result=row["target_result"],
            recommendation=row["recommendation"],
        ),
        axis=1,
    )

    return evaluated_dataframe


# Évalue une stratégie hybride avec ses métriques principales.
def evaluate_strategy(
    dataframe: pd.DataFrame,
    strategy_name: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    evaluated_dataframe = apply_strategy(dataframe, strategy_name)

    selected_dataframe = evaluated_dataframe[evaluated_dataframe["is_selected"]].copy()
    strict_dataframe = selected_dataframe[selected_dataframe["market_type"] == STRICT_MARKET]
    double_chance_dataframe = selected_dataframe[
        selected_dataframe["market_type"] == DOUBLE_CHANCE_MARKET
    ]

    total_rows = len(evaluated_dataframe)
    selected_rows = len(selected_dataframe)
    coverage = selected_rows / total_rows if total_rows else 0
    abstention_rate = 1 - coverage

    reliability = None
    if selected_rows > 0:
        reliability = selected_dataframe["is_recommendation_correct"].mean()

    strict_reliability = None
    if not strict_dataframe.empty:
        strict_reliability = strict_dataframe["is_recommendation_correct"].mean()

    double_chance_reliability = None
    if not double_chance_dataframe.empty:
        double_chance_reliability = double_chance_dataframe[
            "is_recommendation_correct"
        ].mean()

    wc_dataframe = selected_dataframe[selected_dataframe["competition_code"] == "WC"]
    wcq_dataframe = selected_dataframe[selected_dataframe["competition_code"] == "WCQ"]

    wc_reliability = None
    if not wc_dataframe.empty:
        wc_reliability = wc_dataframe["is_recommendation_correct"].mean()

    wcq_reliability = None
    if not wcq_dataframe.empty:
        wcq_reliability = wcq_dataframe["is_recommendation_correct"].mean()

    draw_dataframe = selected_dataframe[selected_dataframe["target_result"] == "DRAW"]

    draw_reliability = None
    if not draw_dataframe.empty:
        draw_reliability = draw_dataframe["is_recommendation_correct"].mean()

    result = {
        "strategy_name": strategy_name,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "coverage": round(coverage, 4),
        "abstention_rate": round(abstention_rate, 4),
        "reliability": round(reliability, 4) if reliability is not None else None,
        "strict_rows": int(len(strict_dataframe)),
        "strict_reliability": round(strict_reliability, 4) if strict_reliability is not None else None,
        "double_chance_rows": int(len(double_chance_dataframe)),
        "double_chance_reliability": round(double_chance_reliability, 4)
        if double_chance_reliability is not None
        else None,
        "draw_rows": int(len(draw_dataframe)),
        "draw_reliability": round(draw_reliability, 4) if draw_reliability is not None else None,
        "wc_rows": int(len(wc_dataframe)),
        "wc_reliability": round(wc_reliability, 4) if wc_reliability is not None else None,
        "wcq_rows": int(len(wcq_dataframe)),
        "wcq_reliability": round(wcq_reliability, 4) if wcq_reliability is not None else None,
    }

    return result, evaluated_dataframe


# Évalue toutes les stratégies définies.
def evaluate_all_strategies(dataframe: pd.DataFrame) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame]]:
    strategy_names = [
        "strict_all_predictions",
        "v17_9_1_abs_150_plus",
        "v17_9_2_hybrid_safe",
        "v17_9_2_hybrid_balanced",
        "v17_9_2_hybrid_coverage",
        "v17_9_2_hybrid_max_coverage",
    ]

    results = []
    evaluated_dataframes = {}

    for strategy_name in strategy_names:
        result, evaluated_dataframe = evaluate_strategy(
            dataframe=dataframe,
            strategy_name=strategy_name,
        )

        results.append(result)
        evaluated_dataframes[strategy_name] = evaluated_dataframe

    return results, evaluated_dataframes


# Sélectionne la meilleure stratégie selon couverture minimale puis fiabilité.
def select_best_strategy(
    strategy_results: list[dict[str, object]],
    min_coverage: float,
) -> dict[str, object]:
    eligible_results = [
        result
        for result in strategy_results
        if result["strategy_name"] != "strict_all_predictions"
        and result["reliability"] is not None
        and result["coverage"] >= min_coverage
    ]

    if not eligible_results:
        eligible_results = [
            result
            for result in strategy_results
            if result["reliability"] is not None
        ]

    return max(
        eligible_results,
        key=lambda result: (
            result["reliability"],
            result["coverage"],
            result["selected_rows"],
        ),
    )


# Exporte le tableau comparatif des stratégies hybrides.
def export_results_csv(strategy_results: list[dict[str, object]]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / RESULTS_FILENAME

    fieldnames = [
        "strategy_name",
        "total_rows",
        "selected_rows",
        "coverage",
        "abstention_rate",
        "reliability",
        "strict_rows",
        "strict_reliability",
        "double_chance_rows",
        "double_chance_reliability",
        "draw_rows",
        "draw_reliability",
        "wc_rows",
        "wc_reliability",
        "wcq_rows",
        "wcq_reliability",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(strategy_results)

    return output_path


# Exporte les prédictions retenues par la meilleure stratégie.
def export_best_selection_csv(
    best_strategy: dict[str, object],
    evaluated_dataframes: dict[str, pd.DataFrame],
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / BEST_SELECTION_FILENAME

    strategy_name = best_strategy["strategy_name"]
    selected_dataframe = evaluated_dataframes[strategy_name].copy()
    selected_dataframe = selected_dataframe[selected_dataframe["is_selected"]].copy()

    export_columns = [
        "clean_match_id",
        "match_date_utc",
        "competition_code",
        "season",
        "team_a_name",
        "team_b_name",
        "target_result",
        "predicted_result",
        "market_type",
        "recommendation",
        "risk_level",
        "selection_reason",
        "is_recommendation_correct",
        "elo_gap",
        "abs_elo_gap",
        "is_neutral_venue",
        "host_advantage_side",
    ]

    selected_dataframe[export_columns].to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    return output_path


# Exporte le résumé de décision V17.9.2.
def export_summary_txt(
    strategy_results: list[dict[str, object]],
    best_strategy: dict[str, object],
    results_path: Path,
    best_selection_path: Path,
    args: argparse.Namespace,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    strict_reference = next(
        result
        for result in strategy_results
        if result["strategy_name"] == "strict_all_predictions"
    )

    v17_9_1_reference = next(
        result
        for result in strategy_results
        if result["strategy_name"] == "v17_9_1_abs_150_plus"
    )

    sorted_results = sorted(
        [
            result
            for result in strategy_results
            if result["reliability"] is not None
        ],
        key=lambda result: (
            result["reliability"],
            result["coverage"],
        ),
        reverse=True,
    )

    lines = [
        "OK - Évaluation stratégie hybride V17.9.2 terminée.",
        f"Feature version : {args.feature_version}",
        f"Fichier prédictions : {args.predictions_file}",
        f"Couverture minimale recherchée : {args.min_coverage}",
        "",
        "Référence V17.9 stricte brute :",
        f"- strategy_name : {strict_reference['strategy_name']}",
        f"- reliability / accuracy stricte : {strict_reference['reliability']}",
        f"- coverage : {strict_reference['coverage']}",
        "",
        "Référence V17.9.1 stricte sélective :",
        f"- strategy_name : {v17_9_1_reference['strategy_name']}",
        f"- reliability : {v17_9_1_reference['reliability']}",
        f"- coverage : {v17_9_1_reference['coverage']}",
        f"- abstention_rate : {v17_9_1_reference['abstention_rate']}",
        "",
        "Meilleure stratégie hybride retenue automatiquement :",
        f"- strategy_name : {best_strategy['strategy_name']}",
        f"- selected_rows : {best_strategy['selected_rows']}",
        f"- coverage : {best_strategy['coverage']}",
        f"- abstention_rate : {best_strategy['abstention_rate']}",
        f"- reliability : {best_strategy['reliability']}",
        f"- strict_rows : {best_strategy['strict_rows']}",
        f"- strict_reliability : {best_strategy['strict_reliability']}",
        f"- double_chance_rows : {best_strategy['double_chance_rows']}",
        f"- double_chance_reliability : {best_strategy['double_chance_reliability']}",
        f"- draw_rows : {best_strategy['draw_rows']}",
        f"- draw_reliability : {best_strategy['draw_reliability']}",
        f"- wc_rows : {best_strategy['wc_rows']}",
        f"- wc_reliability : {best_strategy['wc_reliability']}",
        f"- wcq_rows : {best_strategy['wcq_rows']}",
        f"- wcq_reliability : {best_strategy['wcq_reliability']}",
        "",
        "Comparaison des stratégies :",
    ]

    for result in sorted_results:
        lines.append(
            f"- {result['strategy_name']} | "
            f"reliability={result['reliability']} | "
            f"coverage={result['coverage']} | "
            f"abstention={result['abstention_rate']} | "
            f"strict_rows={result['strict_rows']} | "
            f"double_chance_rows={result['double_chance_rows']}"
        )

    lines.extend(
        [
            "",
            f"CSV comparaison stratégies : {results_path}",
            f"CSV meilleure sélection : {best_selection_path}",
            "",
            "Lecture importante :",
            "- La reliability hybride n'est pas directement comparable à l'accuracy 1X2 stricte.",
            "- La double chance est un marché plus large, donc mécaniquement moins risqué.",
            "- Cette stratégie sert à augmenter la couverture tout en restant responsable.",
            "",
            "Décision technique :",
            "- V17.9.2 teste une logique produit plus réaliste : strict 1X2 quand le signal est fort, double chance quand le match est plus incertain, abstention quand le signal est trop faible.",
            "- Cette étape ne modifie pas le modèle ML entraîné.",
            "- Cette étape ne remplace pas V17.8 club.",
            "- StatsBomb reste reporté tant que la stratégie hybride n'a pas été analysée.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


# Affiche un résumé court dans le terminal.
def print_summary(
    strict_reference: dict[str, object],
    v17_9_1_reference: dict[str, object],
    best_strategy: dict[str, object],
    summary_path: Path,
    results_path: Path,
) -> None:
    print("OK - Évaluation stratégie hybride V17.9.2 terminée.")
    print(
        f"Référence V17.9 stricte : "
        f"reliability={strict_reference['reliability']} | "
        f"coverage={strict_reference['coverage']}"
    )
    print(
        f"Référence V17.9.1 : "
        f"reliability={v17_9_1_reference['reliability']} | "
        f"coverage={v17_9_1_reference['coverage']}"
    )
    print(f"Meilleure stratégie hybride : {best_strategy['strategy_name']}")
    print(f"Reliability : {best_strategy['reliability']}")
    print(f"Coverage : {best_strategy['coverage']}")
    print(f"Abstention rate : {best_strategy['abstention_rate']}")
    print(f"Strict rows : {best_strategy['strict_rows']}")
    print(f"Double chance rows : {best_strategy['double_chance_rows']}")
    print(f"Résumé sauvegardé : {summary_path}")
    print(f"Résultats sauvegardés : {results_path}")


# Exécute l'évaluation complète de la stratégie hybride V17.9.2.
def main() -> None:
    try:
        args = parse_arguments()
        ensure_evidence_directory()

        predictions_dataframe = load_predictions(args.predictions_file)

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            feature_dataframe = fetch_feature_context(
                connection=connection,
                feature_version=args.feature_version,
            )

        evaluation_dataframe = build_evaluation_dataframe(
            predictions_dataframe=predictions_dataframe,
            feature_dataframe=feature_dataframe,
        )

        strategy_results, evaluated_dataframes = evaluate_all_strategies(
            dataframe=evaluation_dataframe
        )

        best_strategy = select_best_strategy(
            strategy_results=strategy_results,
            min_coverage=args.min_coverage,
        )

        results_path = export_results_csv(strategy_results)
        best_selection_path = export_best_selection_csv(
            best_strategy=best_strategy,
            evaluated_dataframes=evaluated_dataframes,
        )

        summary_path = export_summary_txt(
            strategy_results=strategy_results,
            best_strategy=best_strategy,
            results_path=results_path,
            best_selection_path=best_selection_path,
            args=args,
        )

        strict_reference = next(
            result
            for result in strategy_results
            if result["strategy_name"] == "strict_all_predictions"
        )

        v17_9_1_reference = next(
            result
            for result in strategy_results
            if result["strategy_name"] == "v17_9_1_abs_150_plus"
        )

        print_summary(
            strict_reference=strict_reference,
            v17_9_1_reference=v17_9_1_reference,
            best_strategy=best_strategy,
            summary_path=summary_path,
            results_path=results_path,
        )

    except Exception as error:
        print("Erreur pendant l'évaluation stratégie hybride V17.9.2.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# 306_national_v17_9_predictions.csv
#        ↓
# ml_national.features + ml_national.clean_matches
#        ↓
# backend/scripts/ml_national/evaluate_national_v17_9_2_hybrid_strategy.py
#        ↓
# reports/evidence/ml_training/
#        ↓
# décision : conserver V17.9.2 hybride, ajuster les règles ou enrichir avec StatsBomb