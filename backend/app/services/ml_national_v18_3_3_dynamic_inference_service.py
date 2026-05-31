# Role du fichier :
# Ce service construit les features nationales pour un match RubyBets selectionne
# et applique la variante experimentale V18.3.4 dc018 sans modifier le moteur officiel RubyBets.

from __future__ import annotations

import csv
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.services.ml_national_v18_3_3_selector import select_market_with_v18_3_4_dc018


SUPPORTED_DYNAMIC_COMPETITION_CODES = {"WC"}
ALLOWED_HISTORY_TOURNAMENTS = {"FIFA World Cup", "FIFA World Cup qualification"}
DEFAULT_ELO_VALUE = 1500.0

MODEL_RELATIVE_DIR = Path("models/ml_national/v18_3_global_multimarket")
RESULTS_RELATIVE_PATH = Path("data/external/national_results/results.csv")
ELO_RANKINGS_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/299_national_elo_final_rankings.csv"
)

MODEL_FILES = {
    "1x2": "1x2_best_model.joblib",
    "over_1_5": "over_1_5_best_model.joblib",
    "over_2_5": "over_2_5_best_model.joblib",
    "btts": "btts_best_model.joblib",
}

TEAM_NAME_ALIASES = {
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    "Czechia": "Czech Republic",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia-H.": "Bosnia and Herzegovina",
    "USA": "United States",
    "United States of America": "United States",
    "Türkiye": "Turkey",
    "CuraÃ§ao": "Curaçao",
    "Curacao": "Curaçao",
    "Cape Verde": "Cabo Verde",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
}

WORLD_CUP_2026_HOST_TEAMS = {"Mexico", "United States", "Canada"}


# Retourne les emplacements possibles du projet selon le dossier de lancement.
def get_project_root_candidates() -> list[Path]:
    service_file_path = Path(__file__).resolve()

    candidates = [
        service_file_path.parents[3],
        Path.cwd(),
        Path.cwd().parent,
    ]

    unique_candidates: list[Path] = []
    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        if resolved_candidate not in unique_candidates:
            unique_candidates.append(resolved_candidate)

    return unique_candidates


# Retrouve un fichier projet a partir de plusieurs racines possibles.
def find_project_file(relative_path: Path) -> Path:
    for project_root in get_project_root_candidates():
        candidate = project_root / relative_path
        if candidate.exists():
            return candidate

    return get_project_root_candidates()[0] / relative_path


# Normalise une chaine pour faire des comparaisons de noms plus robustes.
def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )

    return without_accents.lower().replace(".", "").replace("-", " ").strip()


# Convertit une valeur en float sans bloquer l'inference experimentale.
def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# Convertit une valeur en entier 0/1 pour les features binaires.
def binary_flag(value: Any) -> int:
    return 1 if bool(value) else 0


# Parse une date ISO ou simple en datetime timezone-aware.
def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        clean_value = value.replace("Z", "+00:00")
        parsed_date = datetime.fromisoformat(clean_value)
    except ValueError:
        try:
            parsed_date = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None

    if parsed_date.tzinfo is None:
        return parsed_date.replace(tzinfo=timezone.utc)

    return parsed_date.astimezone(timezone.utc)


# Arrondit une valeur numerique si elle existe.
def round_or_none(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None

    return round(value, digits)


# Calcule une moyenne si la liste contient au moins une valeur.
def average_or_none(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


# Charge les noms d'equipe disponibles dans l'historique national.
@lru_cache(maxsize=1)
def load_known_national_team_names() -> set[str]:
    results_path = find_project_file(RESULTS_RELATIVE_PATH)

    if not results_path.exists():
        return set()

    names: set[str] = set()

    with results_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if row.get("home_team"):
                names.add(str(row["home_team"]))
            if row.get("away_team"):
                names.add(str(row["away_team"]))

    return names


# Construit un index de noms normalises pour retrouver les equipes mal orthographiees.
@lru_cache(maxsize=1)
def load_normalized_team_name_index() -> dict[str, str]:
    return {
        normalize_text(team_name): team_name
        for team_name in load_known_national_team_names()
    }


# Convertit un nom Football-Data vers le nom utilise dans les donnees nationales Kaggle.
def canonicalize_team_name(team_name: str | None) -> str | None:
    if not team_name:
        return None

    clean_name = team_name.strip()
    alias = TEAM_NAME_ALIASES.get(clean_name)
    if alias:
        return alias

    known_names = load_known_national_team_names()
    if clean_name in known_names:
        return clean_name

    return load_normalized_team_name_index().get(normalize_text(clean_name), clean_name)


# Charge les matchs historiques WC/WCQ utiles a la construction des features.
@lru_cache(maxsize=1)
def load_world_cup_history_rows() -> list[dict[str, Any]]:
    results_path = find_project_file(RESULTS_RELATIVE_PATH)

    if not results_path.exists():
        return []

    rows: list[dict[str, Any]] = []

    with results_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if row.get("tournament") not in ALLOWED_HISTORY_TOURNAMENTS:
                continue

            match_date = parse_datetime(row.get("date"))
            if match_date is None:
                continue

            home_score = safe_float(row.get("home_score"))
            away_score = safe_float(row.get("away_score"))
            if home_score is None or away_score is None:
                continue

            rows.append(
                {
                    "date": match_date,
                    "home_team": canonicalize_team_name(row.get("home_team")),
                    "away_team": canonicalize_team_name(row.get("away_team")),
                    "home_score": home_score,
                    "away_score": away_score,
                    "neutral": str(row.get("neutral", "")).lower() == "true",
                    "tournament": row.get("tournament"),
                }
            )

    return sorted(rows, key=lambda item: item["date"])


# Charge les derniers ratings Elo disponibles pour les selections nationales.
@lru_cache(maxsize=1)
def load_latest_elo_ratings() -> dict[str, float]:
    rankings_path = find_project_file(ELO_RANKINGS_RELATIVE_PATH)

    if not rankings_path.exists():
        return {}

    ratings: dict[str, float] = {}

    with rankings_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            team_name = canonicalize_team_name(row.get("team_name"))
            elo_rating = safe_float(row.get("elo_rating"))

            if team_name and elo_rating is not None:
                ratings[team_name] = elo_rating

    return ratings


# Charge un modele V18.3 sauvegarde pour un marche donne.
@lru_cache(maxsize=4)
def load_v18_3_model_payload(market_key: str) -> dict[str, Any]:
    if market_key not in MODEL_FILES:
        raise ValueError(f"Marche V18.3 inconnu : {market_key}")

    model_path = find_project_file(MODEL_RELATIVE_DIR / MODEL_FILES[market_key])

    if not model_path.exists():
        raise FileNotFoundError(f"Modele V18.3 introuvable : {model_path}")

    payload = joblib.load(model_path)

    if not isinstance(payload, dict):
        raise TypeError(f"Modele V18.3 invalide : {model_path}")

    return payload


# Calcule les points obtenus par les deux equipes dans un match historique.
def compute_points_from_score(home_score: float, away_score: float) -> tuple[int, int]:
    if home_score > away_score:
        return 3, 0

    if away_score > home_score:
        return 0, 3

    return 1, 1


# Construit les historiques de forme avant le match selectionne.
def build_team_histories_before_match(match_date: datetime) -> dict[str, dict[str, list[float]]]:
    histories: dict[str, dict[str, list[float]]] = {}

    def ensure_team(team_name: str | None) -> dict[str, list[float]]:
        key = team_name or "UNKNOWN"
        if key not in histories:
            histories[key] = {
                "points": [],
                "goals_scored": [],
                "goals_conceded": [],
            }
        return histories[key]

    for row in load_world_cup_history_rows():
        if row["date"] >= match_date:
            break

        home_team = row.get("home_team")
        away_team = row.get("away_team")
        home_score = float(row["home_score"])
        away_score = float(row["away_score"])

        home_history = ensure_team(str(home_team))
        away_history = ensure_team(str(away_team))
        home_points, away_points = compute_points_from_score(home_score, away_score)

        home_history["points"].append(float(home_points))
        away_history["points"].append(float(away_points))
        home_history["goals_scored"].append(home_score)
        away_history["goals_scored"].append(away_score)
        home_history["goals_conceded"].append(away_score)
        away_history["goals_conceded"].append(home_score)

    return histories


# Repere si une equipe correspond a un pays hote connu de la Coupe du monde 2026.
def is_2026_host_team(team_name: str | None, season: str | int | None) -> bool:
    if str(season or "") != "2026":
        return False

    canonical_name = canonicalize_team_name(team_name)
    return canonical_name in WORLD_CUP_2026_HOST_TEAMS


# Detecte les indicateurs de phase a partir du stage Football-Data.
def build_stage_flags(stage: str | None) -> tuple[int, int]:
    normalized_stage = normalize_text(stage)

    is_group_stage = "group" in normalized_stage
    knockout_keywords = [
        "last 16",
        "round of 16",
        "quarter",
        "semi",
        "final",
        "third place",
    ]
    is_knockout_stage = any(keyword in normalized_stage for keyword in knockout_keywords)

    return binary_flag(is_group_stage), binary_flag(is_knockout_stage)


# Extrait l'annee de saison la plus fiable possible pour le match.
def extract_match_season(match: dict[str, Any], match_date: datetime | None) -> str | None:
    season = get_match_season_payload(match)
    start_date = season.get("startDate") or season.get("start_date")

    if start_date:
        return str(start_date)[:4]

    if match_date:
        return str(match_date.year)

    return None


# Recupere un dictionnaire equipe en acceptant les formats raw Football-Data et formate RubyBets.
def get_team_payload(match: dict[str, Any], raw_key: str, formatted_key: str) -> dict[str, Any]:
    team = match.get(raw_key)
    if isinstance(team, dict):
        return team

    formatted_team = match.get(formatted_key)
    if isinstance(formatted_team, dict):
        return formatted_team

    return {}


# Recupere une date de match en acceptant utcDate et utc_date.
def get_match_utc_date(match: dict[str, Any]) -> str | None:
    return match.get("utcDate") or match.get("utc_date")


# Recupere la date de derniere mise a jour en acceptant lastUpdated et last_updated.
def get_match_last_updated(match: dict[str, Any]) -> str | None:
    return match.get("lastUpdated") or match.get("last_updated")


# Recupere la saison en acceptant startDate et start_date.
def get_match_season_payload(match: dict[str, Any]) -> dict[str, Any]:
    season = match.get("season")
    return season if isinstance(season, dict) else {}


# Verifie que le match contient deux equipes connues et une competition compatible.
def validate_dynamic_match_scope(match: dict[str, Any]) -> tuple[bool, str]:
    competition_code = match.get("competition", {}).get("code")

    if competition_code not in SUPPORTED_DYNAMIC_COMPETITION_CODES:
        return (
            False,
            "V18.3.4 dc018 dynamique est limite aux matchs nationaux World Cup dans cette phase.",
        )

    home_team_name = get_team_payload(match, "homeTeam", "home_team").get("name")
    away_team_name = get_team_payload(match, "awayTeam", "away_team").get("name")

    if not home_team_name or not away_team_name:
        return (
            False,
            "Les equipes du match ne sont pas encore connues, inference impossible.",
        )

    match_date = parse_datetime(get_match_utc_date(match))
    if match_date is None:
        return False, "La date du match est indisponible, inference impossible."

    return True, "Match compatible avec l'inference experimentale V18.3.4 dc018."


# Construit les features nationales dynamiques a partir du match RubyBets selectionne.
def build_v18_3_3_dynamic_features(match: dict[str, Any]) -> dict[str, Any]:
    match_date = parse_datetime(get_match_utc_date(match))
    if match_date is None:
        raise ValueError("Date du match invalide pour V18.3.4 dc018 dynamique.")

    home_team_source_name = get_team_payload(match, "homeTeam", "home_team").get("name")
    away_team_source_name = get_team_payload(match, "awayTeam", "away_team").get("name")
    home_team_name = canonicalize_team_name(home_team_source_name)
    away_team_name = canonicalize_team_name(away_team_source_name)

    histories = build_team_histories_before_match(match_date)
    home_history = histories.get(home_team_name or "", {
        "points": [],
        "goals_scored": [],
        "goals_conceded": [],
    })
    away_history = histories.get(away_team_name or "", {
        "points": [],
        "goals_scored": [],
        "goals_conceded": [],
    })

    elo_ratings = load_latest_elo_ratings()
    home_elo = elo_ratings.get(home_team_name or "", DEFAULT_ELO_VALUE)
    away_elo = elo_ratings.get(away_team_name or "", DEFAULT_ELO_VALUE)
    match_season = extract_match_season(match, match_date)

    team_a_is_host = is_2026_host_team(home_team_name, match_season)
    team_b_is_host = is_2026_host_team(away_team_name, match_season)
    is_neutral_venue = not (team_a_is_host or team_b_is_host)
    is_group_stage, is_knockout_stage = build_stage_flags(match.get("stage"))

    return {
        "home_form_points_last_5": round_or_none(sum(home_history["points"][-5:])),
        "away_form_points_last_5": round_or_none(sum(away_history["points"][-5:])),
        "home_form_points_last_10": round_or_none(sum(home_history["points"][-10:])),
        "away_form_points_last_10": round_or_none(sum(away_history["points"][-10:])),
        "home_goals_scored_avg_last_10": round_or_none(
            average_or_none(home_history["goals_scored"][-10:])
        ),
        "away_goals_scored_avg_last_10": round_or_none(
            average_or_none(away_history["goals_scored"][-10:])
        ),
        "home_goals_conceded_avg_last_10": round_or_none(
            average_or_none(home_history["goals_conceded"][-10:])
        ),
        "away_goals_conceded_avg_last_10": round_or_none(
            average_or_none(away_history["goals_conceded"][-10:])
        ),
        "elo_gap": round_or_none(home_elo - away_elo),
        "is_neutral_venue": binary_flag(is_neutral_venue),
        "team_a_is_host": binary_flag(team_a_is_host),
        "team_b_is_host": binary_flag(team_b_is_host),
        "host_side_team_a": binary_flag(team_a_is_host),
        "host_side_team_b": binary_flag(team_b_is_host),
        "is_group_stage": is_group_stage,
        "is_knockout_stage": is_knockout_stage,
    }


# Construit les metadonnees du match renvoyees au frontend.
def build_dynamic_match_metadata(match: dict[str, Any]) -> dict[str, Any]:
    match_date = parse_datetime(get_match_utc_date(match))
    competition = match.get("competition") or {}
    season = extract_match_season(match, match_date)

    return {
        "clean_match_id": f"rubybets_match_{match.get('id')}",
        "rubybets_match_id": match.get("id"),
        "feature_id": "dynamic_frontend_match",
        "feature_version": "national_v1_elo_form_dynamic_v18_3_4_dc018",
        "match_date_utc": get_match_utc_date(match),
        "season": season,
        "competition_code": competition.get("code"),
        "competition_name": competition.get("name"),
        "stage": match.get("stage"),
        "group_name": match.get("group"),
        "team_a_name": get_team_payload(match, "homeTeam", "home_team").get("name"),
        "team_b_name": get_team_payload(match, "awayTeam", "away_team").get("name"),
        "inference_mode": "dynamic_selected_match",
    }


# Applique un modele sauvegarde a une ligne de features et retourne prediction + probabilites.
def predict_market_from_features(
    market_key: str,
    features: dict[str, Any],
) -> dict[str, Any]:
    payload = load_v18_3_model_payload(market_key)
    model = payload["model"]
    labels = list(payload["labels"])
    feature_columns = list(payload["feature_columns"])

    model_input = pd.DataFrame(
        [{column: features.get(column) for column in feature_columns}],
        columns=feature_columns,
    )

    prediction = str(model.predict(model_input)[0])
    probabilities = model.predict_proba(model_input)[0]
    model_classes = [str(label) for label in list(model.classes_)]

    probability_by_label = {}
    for label in labels:
        if label in model_classes:
            label_index = model_classes.index(label)
            probability_by_label[label] = round(float(probabilities[label_index]), 6)
        else:
            probability_by_label[label] = 0.0

    return {
        "model_name": str(payload.get("model_name")),
        "prediction": prediction,
        "probabilities": probability_by_label,
        "max_probability": round(float(max(probabilities)), 6),
    }


# Transforme les sorties des modeles en features compatibles avec le selecteur V18.3.4 dc018.
def build_selector_features_from_dynamic_predictions(
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    one_x_two = predictions["1x2"]
    over_1_5 = predictions["over_1_5"]
    over_2_5 = predictions["over_2_5"]
    btts = predictions["btts"]

    return {
        "1x2_prediction": one_x_two["prediction"],
        "1x2_prob_TEAM_A_WIN": one_x_two["probabilities"].get("TEAM_A_WIN"),
        "1x2_prob_DRAW": one_x_two["probabilities"].get("DRAW"),
        "1x2_prob_TEAM_B_WIN": one_x_two["probabilities"].get("TEAM_B_WIN"),
        "1x2_max_probability": one_x_two["max_probability"],
        "over_1_5_prediction": over_1_5["prediction"],
        "over_1_5_prob_YES": over_1_5["probabilities"].get("YES"),
        "over_1_5_prob_NO": over_1_5["probabilities"].get("NO"),
        "over_1_5_max_probability": over_1_5["max_probability"],
        "over_2_5_prediction": over_2_5["prediction"],
        "over_2_5_prob_YES": over_2_5["probabilities"].get("YES"),
        "over_2_5_prob_NO": over_2_5["probabilities"].get("NO"),
        "over_2_5_max_probability": over_2_5["max_probability"],
        "btts_prediction": btts["prediction"],
        "btts_prob_YES": btts["probabilities"].get("YES"),
        "btts_prob_NO": btts["probabilities"].get("NO"),
        "btts_max_probability": btts["max_probability"],
    }


# Construit une reponse indisponible lisible sans faire planter le frontend.
def build_unavailable_dynamic_response(
    match: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "source": "rubybets_ml_national_v18_3_4_dynamic_inference",
        "scope": "experimental_backend",
        "status": "unavailable",
        "data_source_file": "dynamic_selected_match_inference",
        "match": build_dynamic_match_metadata(match),
        "selector_result": None,
        "unavailable_reason": reason,
        "responsible_note": (
            "V18.3.4 dc018 reste experimental. Aucune prediction officielle RubyBets "
            "n'est remplacee et aucun resultat sportif n'est garanti."
        ),
    }


# Orchestre l'inference dynamique V18.3.4 dc018 pour un match RubyBets selectionne.
def infer_v18_3_3_for_rubybets_match(match: dict[str, Any]) -> dict[str, Any]:
    is_valid, validation_message = validate_dynamic_match_scope(match)

    if not is_valid:
        return build_unavailable_dynamic_response(match, validation_message)

    dynamic_features = build_v18_3_3_dynamic_features(match)
    predictions = {
        market_key: predict_market_from_features(market_key, dynamic_features)
        for market_key in MODEL_FILES
    }
    selector_features = build_selector_features_from_dynamic_predictions(predictions)
    selector_result = select_market_with_v18_3_4_dc018(selector_features)

    return {
        "source": "rubybets_ml_national_v18_3_4_dynamic_inference",
        "scope": "experimental_backend",
        "status": "computed",
        "data_source_file": "dynamic_selected_match_inference",
        "match": build_dynamic_match_metadata(match),
        "dynamic_features": dynamic_features,
        "market_predictions": predictions,
        "selector_result": selector_result,
        "responsible_note": (
            "Resultat experimental V18.3.4 dc018 calcule dynamiquement pour le match selectionne. "
            "Il ne remplace pas les predictions officielles RubyBets et ne garantit "
            "aucun resultat sportif."
        ),
    }


# Schema de communication :
# ml_national_v18_3_3_dynamic_inference_service.py
#   -> lit les donnees historiques data/external/national_results/results.csv
#   -> lit les ratings reports/evidence/ml_training/299_national_elo_final_rankings.csv
#   -> charge les modeles models/ml_national/v18_3_global_multimarket/*.joblib
#   -> appelle ml_national_v18_3_3_selector.py avec la variante V18.3.4 dc018
#   -> retourne une analyse experimentale au routeur experimental_ml_national_v18_3_3.py
