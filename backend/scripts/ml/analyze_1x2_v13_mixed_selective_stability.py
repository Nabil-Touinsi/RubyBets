# Rôle du fichier : analyser la stabilité de V13.1 mixed selective par ligue, saison, type de recommandation et segments de risque, sans intégrer le résultat au produit.

from __future__ import annotations

import importlib.util
import math
import sys
import warnings
from pathlib import Path
from types import ModuleType

import pandas as pd


RECOMMEND_STATUS = "RECOMMEND"
STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"
TARGET_COLUMN = "target_result"

OUTPUT_SUMMARY = "199_1x2_v13_mixed_stability_summary.txt"
OUTPUT_BY_LEAGUE = "200_1x2_v13_mixed_stability_by_league.csv"
OUTPUT_BY_SEASON = "201_1x2_v13_mixed_stability_by_season.csv"
OUTPUT_BY_TYPE_MARKET = "202_1x2_v13_mixed_stability_by_type_market.csv"
OUTPUT_RISK_SEGMENTS = "203_1x2_v13_mixed_stability_risk_segments.csv"
OUTPUT_DECISION = "204_1x2_v13_mixed_stability_decision.txt"

ACCEPT_MIN_MIXED_ACCURACY = 0.82
ACCEPT_MIN_COVERAGE = 0.50
ACCEPT_MIN_SELECTED_ROWS = 2500
ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY = 0.75
ACCEPT_MIN_LEAGUE_ACCURACY = 0.82
ACCEPT_MIN_SEASON_ACCURACY = 0.82
ACCEPT_MIN_MAJOR_TYPE_MARKET_ACCURACY = 0.75

MAJOR_LEAGUE_SEASON_MIN_ROWS = 100
MAJOR_TYPE_MARKET_MIN_ROWS = 100
LOW_VOLUME_WARNING_MIN_ROWS = 100

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


# Charge le script V13.1 mixed selective comme module technique réutilisable.
def load_v13_mixed_module() -> ModuleType:
    mixed_script = Path(__file__).resolve().parent / "train_1x2_v13_mixed_selective.py"
    if not mixed_script.exists():
        raise FileNotFoundError(
            "Le script V13.1 mixed selective est requis pour reconstruire la stratégie stable : "
            f"{mixed_script}"
        )

    spec = importlib.util.spec_from_file_location("rubybets_v13_mixed_selective", mixed_script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module V13.1 mixed selective : {mixed_script}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["rubybets_v13_mixed_selective"] = module
    spec.loader.exec_module(module)
    return module


# Arrondit une valeur numérique pour stabiliser les preuves CSV et TXT.
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


# Reconstruit la meilleure sélection V13.1 sur le test final, sans modifier de donnée source.
def rebuild_best_v13_mixed_predictions(mixed: ModuleType) -> tuple[pd.DataFrame, dict[str, object], dict[str, object], dict[str, object]]:
    base = mixed.load_v13_base_module()
    project_root = base.find_project_root()

    dataset, _, metadata = base.build_v13_dataset(project_root)
    _, validation, test, split_metadata = base.prepare_temporal_splits(dataset)

    results, policies_by_name = mixed.evaluate_policies(validation, test)
    best_strategy = mixed.select_best_policy(results)
    best_policy = policies_by_name[best_strategy]
    best_predictions = mixed.build_best_predictions(test, best_policy)

    best_metrics = results[(results["scope"] == "test") & (results["strategy"] == best_strategy)].iloc[0].to_dict()
    return best_predictions, best_metrics, metadata, split_metadata


# Filtre uniquement les recommandations retenues par la stratégie V13.1.
def get_selected_predictions(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = best_predictions[best_predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS].copy()
    selected["v13_mixed_is_correct"] = selected["v13_mixed_is_correct"].astype(bool)
    return selected


# Calcule des métriques stables sur un groupe de lignes sélectionnées.
def compute_group_metrics(group: pd.DataFrame) -> dict[str, object]:
    strict_group = group[group["v13_mixed_recommendation_type"] == STRICT_TYPE]
    double_group = group[group["v13_mixed_recommendation_type"] == DOUBLE_CHANCE_TYPE]

    selected_rows = len(group)
    strict_rows = len(strict_group)
    double_rows = len(double_group)

    return {
        "selected_rows": selected_rows,
        "mixed_accuracy": rounded(group["v13_mixed_is_correct"].mean()),
        "errors": int((~group["v13_mixed_is_correct"]).sum()),
        "strict_1x2_rows": strict_rows,
        "strict_1x2_accuracy": rounded(strict_group["v13_mixed_is_correct"].mean()) if strict_rows else 0.0,
        "double_chance_rows": double_rows,
        "double_chance_accuracy": rounded(double_group["v13_mixed_is_correct"].mean()) if double_rows else 0.0,
        "double_1x_rows": int((double_group["v13_mixed_recommendation_value"] == "1X").sum()),
        "double_x2_rows": int((double_group["v13_mixed_recommendation_value"] == "X2").sum()),
        "double_12_rows": int((double_group["v13_mixed_recommendation_value"] == "12").sum()),
        "average_market_favorite_prob": rounded(group["market_favorite_prob"].mean()),
        "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
        "average_market_entropy": rounded(group["market_entropy"].mean()),
    }


# Construit la stabilité globale par ligue.
def build_by_league(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for league_code, group in selected.groupby("__league_code", dropna=False):
        metrics = compute_group_metrics(group)
        segment_status = "OK"
        if metrics["mixed_accuracy"] < ACCEPT_MIN_LEAGUE_ACCURACY:
            segment_status = "BELOW_LEAGUE_GATE"
        rows.append({"league_code": league_code, **metrics, "segment_status": segment_status})

    return pd.DataFrame(rows).sort_values("league_code")


# Construit la stabilité globale par saison de test.
def build_by_season(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for season, group in selected.groupby("__season", dropna=False):
        metrics = compute_group_metrics(group)
        segment_status = "OK"
        if metrics["mixed_accuracy"] < ACCEPT_MIN_SEASON_ACCURACY:
            segment_status = "BELOW_SEASON_GATE"
        rows.append({"season": season, **metrics, "segment_status": segment_status})

    return pd.DataFrame(rows).sort_values("season")


# Construit la stabilité par type de recommandation et marché affiché.
def build_by_type_market(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v13_mixed_recommendation_type", "v13_mixed_recommendation_value"], dropna=False)

    for (recommendation_type, recommendation_value), group in grouped:
        metrics = compute_group_metrics(group)
        segment_status = "OK"
        if metrics["selected_rows"] < LOW_VOLUME_WARNING_MIN_ROWS:
            segment_status = "LOW_VOLUME"
        elif metrics["mixed_accuracy"] < ACCEPT_MIN_MAJOR_TYPE_MARKET_ACCURACY:
            segment_status = "BELOW_TYPE_MARKET_GATE"

        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": metrics["selected_rows"],
                "accuracy": metrics["mixed_accuracy"],
                "errors": metrics["errors"],
                "actual_home_win_rows": int((group[TARGET_COLUMN] == "HOME_WIN").sum()),
                "actual_draw_rows": int((group[TARGET_COLUMN] == "DRAW").sum()),
                "actual_away_win_rows": int((group[TARGET_COLUMN] == "AWAY_WIN").sum()),
                "average_market_favorite_prob": metrics["average_market_favorite_prob"],
                "average_market_top2_sum": metrics["average_market_top2_sum"],
                "average_market_entropy": metrics["average_market_entropy"],
                "segment_status": segment_status,
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Ajoute des segments lisibles pour analyser les zones de risque restantes.
def add_risk_segments(selected: pd.DataFrame) -> pd.DataFrame:
    output = selected.copy()

    output["favorite_strength_segment"] = pd.cut(
        output["market_favorite_prob"],
        bins=[-0.01, 0.58, 0.70, 1.01],
        labels=["FAVORITE_LOW", "FAVORITE_MEDIUM", "FAVORITE_HIGH"],
    ).astype(str)

    output["top2_strength_segment"] = pd.cut(
        output["market_top2_sum"],
        bins=[-0.01, 0.78, 0.85, 1.01],
        labels=["TOP2_BORDERLINE", "TOP2_SOLID", "TOP2_STRONG"],
    ).astype(str)

    output["entropy_segment"] = pd.cut(
        output["market_entropy"],
        bins=[-0.01, 0.75, 0.95, 2.00],
        labels=["ENTROPY_LOW", "ENTROPY_MEDIUM", "ENTROPY_HIGH"],
    ).astype(str)

    return output


# Construit les segments de risque pour comprendre les erreurs persistantes.
def build_risk_segments(selected: pd.DataFrame) -> pd.DataFrame:
    segmented = add_risk_segments(selected)
    rows: list[dict[str, object]] = []
    grouped = segmented.groupby(
        [
            "v13_mixed_recommendation_type",
            "v13_mixed_recommendation_value",
            "favorite_strength_segment",
            "top2_strength_segment",
            "entropy_segment",
        ],
        dropna=False,
    )

    for keys, group in grouped:
        recommendation_type, recommendation_value, favorite_segment, top2_segment, entropy_segment = keys
        selected_rows = len(group)
        if selected_rows == 0:
            continue

        accuracy = rounded(group["v13_mixed_is_correct"].mean())
        segment_status = "OK"
        if selected_rows < LOW_VOLUME_WARNING_MIN_ROWS:
            segment_status = "LOW_VOLUME"
        elif accuracy < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_RISK_GATE"

        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "favorite_strength_segment": favorite_segment,
                "top2_strength_segment": top2_segment,
                "entropy_segment": entropy_segment,
                "selected_rows": selected_rows,
                "accuracy": accuracy,
                "errors": int((~group["v13_mixed_is_correct"]).sum()),
                "actual_home_win_rows": int((group[TARGET_COLUMN] == "HOME_WIN").sum()),
                "actual_draw_rows": int((group[TARGET_COLUMN] == "DRAW").sum()),
                "actual_away_win_rows": int((group[TARGET_COLUMN] == "AWAY_WIN").sum()),
                "average_market_favorite_prob": rounded(group["market_favorite_prob"].mean()),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
                "segment_status": segment_status,
            }
        )

    return pd.DataFrame(rows).sort_values(["segment_status", "selected_rows"], ascending=[True, False])


# Identifie les segments ligue/saison majeurs à surveiller à partir de la preuve 196 reconstruite.
def build_league_season_stability(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["__league_code", "__season"], dropna=False)

    for (league_code, season), group in grouped:
        metrics = compute_group_metrics(group)
        segment_status = "OK"
        if metrics["selected_rows"] < MAJOR_LEAGUE_SEASON_MIN_ROWS:
            segment_status = "LOW_VOLUME"
        elif metrics["mixed_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_GATE"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                **metrics,
                "segment_status": segment_status,
            }
        )

    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Prend une décision de stabilité sans autoriser d'intégration produit.
def decide_stability(
    best_metrics: dict[str, object],
    by_league: pd.DataFrame,
    by_season: pd.DataFrame,
    by_type_market: pd.DataFrame,
    by_league_season: pd.DataFrame,
    risk_segments: pd.DataFrame,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings_list: list[str] = []

    mixed_accuracy = float(best_metrics.get("mixed_accuracy", 0.0))
    coverage = float(best_metrics.get("coverage", 0.0))
    selected_rows = int(best_metrics.get("selected_rows", 0))

    if mixed_accuracy < ACCEPT_MIN_MIXED_ACCURACY:
        blockers.append(f"Mixed accuracy sous le gate fort : {mixed_accuracy} < {ACCEPT_MIN_MIXED_ACCURACY}.")
    if coverage < ACCEPT_MIN_COVERAGE:
        blockers.append(f"Coverage sous le gate fort : {coverage} < {ACCEPT_MIN_COVERAGE}.")
    if selected_rows < ACCEPT_MIN_SELECTED_ROWS:
        blockers.append(f"Volume sélectionné sous le gate fort : {selected_rows} < {ACCEPT_MIN_SELECTED_ROWS}.")

    weak_leagues = by_league[by_league["mixed_accuracy"] < ACCEPT_MIN_LEAGUE_ACCURACY]
    weak_seasons = by_season[by_season["mixed_accuracy"] < ACCEPT_MIN_SEASON_ACCURACY]
    major_weak_league_seasons = by_league_season[
        (by_league_season["selected_rows"] >= MAJOR_LEAGUE_SEASON_MIN_ROWS)
        & (by_league_season["mixed_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]
    major_weak_type_markets = by_type_market[
        (by_type_market["selected_rows"] >= MAJOR_TYPE_MARKET_MIN_ROWS)
        & (by_type_market["accuracy"] < ACCEPT_MIN_MAJOR_TYPE_MARKET_ACCURACY)
    ]
    major_weak_risk_segments = risk_segments[
        (risk_segments["selected_rows"] >= LOW_VOLUME_WARNING_MIN_ROWS)
        & (risk_segments["accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]
    low_volume_fragile_type_markets = by_type_market[
        (by_type_market["selected_rows"] < LOW_VOLUME_WARNING_MIN_ROWS)
        & (by_type_market["accuracy"] < ACCEPT_MIN_MIXED_ACCURACY)
    ]

    if not weak_leagues.empty:
        warnings_list.append(f"{len(weak_leagues)} ligue(s) sous le gate indicatif {ACCEPT_MIN_LEAGUE_ACCURACY}.")
    if not weak_seasons.empty:
        warnings_list.append(f"{len(weak_seasons)} saison(s) sous le gate indicatif {ACCEPT_MIN_SEASON_ACCURACY}.")
    if not major_weak_league_seasons.empty:
        blockers.append(f"{len(major_weak_league_seasons)} segment(s) ligue/saison majeur(s) sous {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY}.")
    if not major_weak_type_markets.empty:
        blockers.append(f"{len(major_weak_type_markets)} segment(s) type/marché majeur(s) sous {ACCEPT_MIN_MAJOR_TYPE_MARKET_ACCURACY}.")
    if not major_weak_risk_segments.empty:
        warnings_list.append(f"{len(major_weak_risk_segments)} segment(s) de risque majeur(s) sous {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY}.")
    if not low_volume_fragile_type_markets.empty:
        warnings_list.append(
            f"{len(low_volume_fragile_type_markets)} segment(s) type/marché fragile(s) mais à faible volume."
        )

    if blockers:
        return "V13_MIXED_STABILITY_REVIEW", blockers, warnings_list

    return "V13_MIXED_STABILITY_STRONG_REVIEW", blockers, warnings_list


# Écrit la synthèse de stabilité V13.1.
def write_summary(
    output_path: Path,
    best_metrics: dict[str, object],
    metadata: dict[str, object],
    split_metadata: dict[str, object],
    by_league: pd.DataFrame,
    by_season: pd.DataFrame,
    by_type_market: pd.DataFrame,
    by_league_season: pd.DataFrame,
    risk_segments: pd.DataFrame,
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    min_league = by_league.sort_values("mixed_accuracy").iloc[0].to_dict()
    min_season = by_season.sort_values("mixed_accuracy").iloc[0].to_dict()
    min_league_season = by_league_season.sort_values("mixed_accuracy").iloc[0].to_dict()

    major_fragile_segments = by_league_season[
        (by_league_season["selected_rows"] >= MAJOR_LEAGUE_SEASON_MIN_ROWS)
        & (by_league_season["mixed_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]
    low_volume_type_warnings = by_type_market[
        (by_type_market["selected_rows"] < LOW_VOLUME_WARNING_MIN_ROWS)
        & (by_type_market["accuracy"] < ACCEPT_MIN_MIXED_ACCURACY)
    ]

    lines = [
        "RubyBets - ML 1X2 V13.1 mixed selective",
        "199 - Analyse de stabilité V13.1",
        "",
        "Objectif :",
        "Vérifier si la stratégie mixte V13.1 reste stable par ligue, saison, type de recommandation, marché et segment de risque.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw via les scripts V13/V13.1.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {metadata.get('csv_files')}",
        f"- Lignes dataset V13.1 : {metadata.get('dataset_rows')}",
        f"- Ligues : {metadata.get('leagues')}",
        f"- Saisons : {metadata.get('first_season')} -> {metadata.get('last_season')}",
        f"- Validation seasons : {split_metadata.get('validation_seasons')}",
        f"- Test seasons : {split_metadata.get('test_seasons')}",
        "",
        "Stratégie analysée :",
        f"- Strategy : {best_metrics.get('strategy')}",
        f"- Status stabilité : {status}",
        "",
        "Résultat global rappelé :",
        f"- Mixed accuracy : {best_metrics.get('mixed_accuracy')}",
        f"- Coverage : {best_metrics.get('coverage')}",
        f"- Abstention rate : {best_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {best_metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {best_metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {best_metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {best_metrics.get('double_chance_accuracy')}",
        "",
        "Stabilité par ligue :",
        f"- Nombre de ligues testées : {len(by_league)}",
        f"- Ligue la plus basse : {min_league.get('league_code')} avec accuracy {min_league.get('mixed_accuracy')} sur {min_league.get('selected_rows')} matchs sélectionnés.",
        "",
        "Stabilité par saison :",
        f"- Nombre de saisons testées : {len(by_season)}",
        f"- Saison la plus basse : {min_season.get('season')} avec accuracy {min_season.get('mixed_accuracy')} sur {min_season.get('selected_rows')} matchs sélectionnés.",
        "",
        "Stabilité ligue/saison :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {min_league_season.get('league_code')} {min_league_season.get('season')} avec accuracy {min_league_season.get('mixed_accuracy')} sur {min_league_season.get('selected_rows')} matchs sélectionnés.",
        f"- Segments majeurs sous {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY} : {len(major_fragile_segments)}",
        "",
        "Stabilité type/marché :",
        f"- Segments type/marché analysés : {len(by_type_market)}",
        f"- Segments type/marché fragiles à faible volume : {len(low_volume_type_warnings)}",
        "",
        "Segments de risque :",
        f"- Segments de risque analysés : {len(risk_segments)}",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision produit :",
        "Ne pas intégrer V13.1 au produit à ce stade. L'analyse de stabilité permet de documenter une expérimentation ML/RNCP solide, mais le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- V13.1 mixed selective : réalisée.",
        "- Stabilité V13.1 mixed selective : réalisée si les fichiers 199 à 204 sont générés.",
        "- Prochaine étape : formaliser la comparaison finale V9/V11/V13/V13.1 et la décision ML globale.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision courte de stabilité V13.1.
def write_decision(
    output_path: Path,
    best_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision stabilité V13.1 mixed selective",
        "204 - Décision stabilité V13.1",
        "",
        f"Status : {status}",
        "",
        "Métriques globales rappelées :",
        f"- Strategy : {best_metrics.get('strategy')}",
        f"- Mixed accuracy : {best_metrics.get('mixed_accuracy')}",
        f"- Coverage : {best_metrics.get('coverage')}",
        f"- Abstention rate : {best_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {best_metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {best_metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {best_metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {best_metrics.get('double_chance_accuracy')}",
        "",
        "Gates de stabilité appliqués :",
        f"- Mixed accuracy >= {ACCEPT_MIN_MIXED_ACCURACY}",
        f"- Coverage >= {ACCEPT_MIN_COVERAGE}",
        f"- Selected rows >= {ACCEPT_MIN_SELECTED_ROWS}",
        f"- Segment ligue/saison majeur >= {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY}",
        f"- Segment type/marché majeur >= {ACCEPT_MIN_MAJOR_TYPE_MARKET_ACCURACY}",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision opérationnelle :",
        "- V13.1 peut être conservée comme expérimentation mixed selective forte si le statut reste STRONG_REVIEW.",
        "- V13.1 ne remplace pas le scoring explicable V1.",
        "- V13.1 ne doit pas être intégrée au produit sans arbitrage explicite, documentation et validation produit séparée.",
        "",
        "Statut de suivi à mettre à jour :",
        "- Stabilité V13.1 mixed selective : réalisée.",
        "- Fichiers concernés : 199, 200, 201, 202, 203, 204.",
        "- Prochaine tâche : comparaison finale et décision globale de la phase ML.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Orchestre l'analyse de stabilité V13.1 sans modifier RubyBets.
def main() -> None:
    mixed = load_v13_mixed_module()
    base = mixed.load_v13_base_module()
    project_root = base.find_project_root()
    evidence_dir = base.get_evidence_dir(project_root)

    print("Reconstruction de la meilleure stratégie V13.1 mixed selective...")
    best_predictions, best_metrics, metadata, split_metadata = rebuild_best_v13_mixed_predictions(mixed)
    selected = get_selected_predictions(best_predictions)

    print("Analyse de stabilité par ligue, saison, type/marché et segments de risque...")
    by_league = build_by_league(selected)
    by_season = build_by_season(selected)
    by_type_market = build_by_type_market(selected)
    by_league_season = build_league_season_stability(selected)
    risk_segments = build_risk_segments(selected)

    status, blockers, warnings_list = decide_stability(
        best_metrics,
        by_league,
        by_season,
        by_type_market,
        by_league_season,
        risk_segments,
    )

    by_league.to_csv(evidence_dir / OUTPUT_BY_LEAGUE, index=False, encoding="utf-8")
    by_season.to_csv(evidence_dir / OUTPUT_BY_SEASON, index=False, encoding="utf-8")
    by_type_market.to_csv(evidence_dir / OUTPUT_BY_TYPE_MARKET, index=False, encoding="utf-8")
    risk_segments.to_csv(evidence_dir / OUTPUT_RISK_SEGMENTS, index=False, encoding="utf-8")
    write_summary(
        evidence_dir / OUTPUT_SUMMARY,
        best_metrics,
        metadata,
        split_metadata,
        by_league,
        by_season,
        by_type_market,
        by_league_season,
        risk_segments,
        status,
        blockers,
        warnings_list,
    )
    write_decision(evidence_dir / OUTPUT_DECISION, best_metrics, status, blockers, warnings_list)

    major_fragile_segments = by_league_season[
        (by_league_season["selected_rows"] >= MAJOR_LEAGUE_SEASON_MIN_ROWS)
        & (by_league_season["mixed_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]
    low_volume_fragile_type_markets = by_type_market[
        (by_type_market["selected_rows"] < LOW_VOLUME_WARNING_MIN_ROWS)
        & (by_type_market["accuracy"] < ACCEPT_MIN_MIXED_ACCURACY)
    ]

    print("OK - Analyse stabilité V13.1 mixed selective terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_metrics.get('strategy')}")
    print(f"Overall mixed accuracy: {best_metrics.get('mixed_accuracy')}")
    print(f"Coverage: {best_metrics.get('coverage')}")
    print(f"Selected rows: {best_metrics.get('selected_rows')}")
    print(f"Strict 1X2 rows: {best_metrics.get('strict_1x2_rows')}")
    print(f"Double chance rows: {best_metrics.get('double_chance_rows')}")
    print(f"League segments: {len(by_league)}")
    print(f"Season segments: {len(by_season)}")
    print(f"Major fragile league/season segments: {len(major_fragile_segments)}")
    print(f"Low-volume fragile type/market segments: {len(low_volume_fragile_type_markets)}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"By league CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE}")
    print(f"By season CSV saved: {evidence_dir / OUTPUT_BY_SEASON}")
    print(f"By type/market CSV saved: {evidence_dir / OUTPUT_BY_TYPE_MARKET}")
    print(f"Risk segments CSV saved: {evidence_dir / OUTPUT_RISK_SEGMENTS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# analyze_1x2_v13_mixed_selective_stability.py
#   -> réutilise backend/scripts/ml/train_1x2_v13_mixed_selective.py
#   -> réutilise indirectement backend/scripts/ml/train_1x2_v13_double_chance_selective.py
#   -> lit data/ml/raw/*.csv en lecture seule
#   -> écrit reports/evidence/ml_training/199 à 204
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
