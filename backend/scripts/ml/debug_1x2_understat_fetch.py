# Ce script diagnostique la récupération Understat avant toute intégration xG dans RubyBets.
# Il teste une page Understat, sauvegarde le HTML brut et explique pourquoi l'extraction xG échoue ou réussit.

from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
SUMMARY_PATH = REPORT_DIR / "89_1x2_understat_fetch_debug_summary.txt"
RAW_HTML_PATH = REPORT_DIR / "90_1x2_understat_fetch_debug_raw_response.html"
EXTRACT_PATH = REPORT_DIR / "91_1x2_understat_fetch_debug_extract_sample.txt"

DEFAULT_LEAGUE = "EPL"
DEFAULT_SEASON = "2024"
DEFAULT_URL = f"https://understat.com/league/{DEFAULT_LEAGUE}/{DEFAULT_SEASON}"


@dataclass
class FetchResult:
    """Résultat brut d'un appel HTTP vers Understat."""

    url: str
    ok: bool
    status_code: Optional[int]
    content_type: str
    body: str
    error_type: str = ""
    error_message: str = ""


# Prépare le dossier de sortie des preuves ML.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Récupère une page Understat avec des headers réalistes pour diagnostiquer un blocage éventuel.
def fetch_understat_page(url: str) -> FetchResult:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://understat.com/",
    }

    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            return FetchResult(
                url=url,
                ok=True,
                status_code=response.status,
                content_type=response.headers.get("Content-Type", ""),
                body=body,
            )
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return FetchResult(
            url=url,
            ok=False,
            status_code=exc.code,
            content_type=getattr(exc, "headers", {}).get("Content-Type", "") if exc.headers else "",
            body=body,
            error_type="HTTPError",
            error_message=str(exc),
        )
    except URLError as exc:
        return FetchResult(
            url=url,
            ok=False,
            status_code=None,
            content_type="",
            body="",
            error_type="URLError",
            error_message=str(exc.reason),
        )
    except Exception as exc:
        return FetchResult(
            url=url,
            ok=False,
            status_code=None,
            content_type="",
            body="",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


# Détecte les signes fréquents de blocage ou de réponse inutilisable.
def detect_blockers(body: str) -> Dict[str, bool]:
    lowered = body.lower()
    return {
        "empty_body": len(body.strip()) == 0,
        "cloudflare_detected": "cloudflare" in lowered or "cf-ray" in lowered,
        "captcha_detected": "captcha" in lowered or "verify you are human" in lowered,
        "access_denied_detected": "access denied" in lowered or "forbidden" in lowered,
        "understat_marker_detected": "understat" in lowered,
        "javascript_json_parse_detected": "json.parse" in lowered,
        "dates_data_marker_detected": "datesdata" in lowered,
        "teams_data_marker_detected": "teamsdata" in lowered,
        "players_data_marker_detected": "playersdata" in lowered,
    }


# Extrait le titre HTML pour vérifier rapidement quel type de page a été reçu.
def extract_title(body: str) -> str:
    match = re.search(r"<title>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())


# Extrait une variable JSON embarquée dans Understat si elle est présente.
def extract_understat_json_variable(body: str, variable_name: str) -> Tuple[bool, int, str]:
    pattern = rf"var\s+{re.escape(variable_name)}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, body, flags=re.DOTALL)
    if not match:
        return False, 0, ""

    encoded_payload = match.group(1)
    try:
        decoded_payload = encoded_payload.encode("utf-8").decode("unicode_escape")
        parsed = json.loads(decoded_payload)
        if isinstance(parsed, list):
            sample = json.dumps(parsed[:2], ensure_ascii=False, indent=2)
            return True, len(parsed), sample
        if isinstance(parsed, dict):
            sample_keys = list(parsed.keys())[:5]
            sample = json.dumps({key: parsed[key] for key in sample_keys}, ensure_ascii=False, indent=2)
            return True, len(parsed), sample
        return True, 1, json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception as exc:
        return True, 0, f"Extraction trouvee mais parsing JSON impossible : {type(exc).__name__} - {exc}"


# Analyse le HTML brut pour dire quelle méthode de récupération semble nécessaire.
def diagnose_fetch_result(result: FetchResult) -> Dict[str, object]:
    blockers = detect_blockers(result.body)
    title = extract_title(result.body)

    dates_found, dates_count, dates_sample = extract_understat_json_variable(result.body, "datesData")
    teams_found, teams_count, teams_sample = extract_understat_json_variable(result.body, "teamsData")

    if not result.ok:
        recommendation = "La requete HTTP echoue. Tester connexion, proxy, DNS, blocage distant ou headers/session."
    elif blockers["empty_body"]:
        recommendation = "La page recue est vide. Tester Playwright/Selenium ou verifier un blocage HTTP."
    elif blockers["cloudflare_detected"] or blockers["captcha_detected"] or blockers["access_denied_detected"]:
        recommendation = "La page semble bloquee. Utiliser une session navigateur Playwright/Selenium ou une source alternative."
    elif dates_found and dates_count > 0:
        recommendation = "La variable datesData est accessible. Le parser peut etre corrige/reutilise pour integrer Understat."
    elif blockers["understat_marker_detected"] and blockers["javascript_json_parse_detected"]:
        recommendation = "Le site repond, mais le nom ou format des variables a peut-etre change. Inspecter le HTML brut."
    elif blockers["understat_marker_detected"]:
        recommendation = "La page Understat est recue, mais les donnees semblent chargees autrement. Tester export JSON/CSV ou rendu navigateur."
    else:
        recommendation = "La reponse ne ressemble pas a une page Understat exploitable. Verifier le fichier HTML brut."

    return {
        "title": title,
        "body_length": len(result.body),
        "blockers": blockers,
        "dates_found": dates_found,
        "dates_count": dates_count,
        "dates_sample": dates_sample,
        "teams_found": teams_found,
        "teams_count": teams_count,
        "teams_sample": teams_sample,
        "recommendation": recommendation,
    }


# Sauvegarde le HTML brut et un extrait JSON éventuel pour faciliter le diagnostic manuel.
def write_debug_files(result: FetchResult, diagnosis: Dict[str, object]) -> None:
    RAW_HTML_PATH.write_text(result.body, encoding="utf-8")

    extract_lines = [
        "RubyBets - Understat debug extract sample",
        "",
        f"URL testee : {result.url}",
        f"datesData trouve : {diagnosis['dates_found']}",
        f"datesData lignes : {diagnosis['dates_count']}",
        "",
        "Echantillon datesData :",
        str(diagnosis.get("dates_sample") or "Aucun echantillon datesData disponible."),
        "",
        f"teamsData trouve : {diagnosis['teams_found']}",
        f"teamsData lignes : {diagnosis['teams_count']}",
        "",
        "Echantillon teamsData :",
        str(diagnosis.get("teams_sample") or "Aucun echantillon teamsData disponible."),
    ]
    EXTRACT_PATH.write_text("\n".join(extract_lines), encoding="utf-8")


# Rédige la synthèse de diagnostic qui servira de preuve pour décider si Understat est réparable.
def write_summary(result: FetchResult, diagnosis: Dict[str, object]) -> None:
    blockers = diagnosis["blockers"]

    lines = [
        "RubyBets - ML 1X2 V8 Understat fetch debug",
        "89 - Diagnostic technique de recuperation Understat",
        "",
        "Objectif :",
        "Comprendre pourquoi l'audit V8 xG n'a recupere aucune ligne Understat avant toute integration ML.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Diagnostic limite a une recuperation HTTP et a des fichiers de preuve locaux.",
        "",
        "Page testee :",
        f"- URL : {result.url}",
        f"- HTTP OK : {result.ok}",
        f"- Status code : {result.status_code}",
        f"- Content-Type : {result.content_type}",
        f"- Error type : {result.error_type or 'none'}",
        f"- Error message : {result.error_message or 'none'}",
        f"- Title : {diagnosis['title'] or 'non detecte'}",
        f"- Body length : {diagnosis['body_length']}",
        "",
        "Signaux detectes :",
    ]

    for key, value in blockers.items():
        lines.append(f"- {key} : {value}")

    lines.extend(
        [
            "",
            "Extraction JSON Understat :",
            f"- datesData trouve : {diagnosis['dates_found']}",
            f"- datesData lignes : {diagnosis['dates_count']}",
            f"- teamsData trouve : {diagnosis['teams_found']}",
            f"- teamsData lignes : {diagnosis['teams_count']}",
            "",
            "Diagnostic :",
            f"- Recommendation : {diagnosis['recommendation']}",
            "",
            "Fichiers generes :",
            f"{SUMMARY_PATH.relative_to(PROJECT_ROOT)}",
            f"{RAW_HTML_PATH.relative_to(PROJECT_ROOT)}",
            f"{EXTRACT_PATH.relative_to(PROJECT_ROOT)}",
            "",
            "Decision attendue :",
            "- Si datesData est trouve avec des lignes : corriger le parser Understat et relancer l'audit V8 xG.",
            "- Si la page est bloquee ou vide : tester Playwright/Selenium ou abandonner Understat pour une source xG plus stable.",
            "- Si le HTML existe mais le format a change : inspecter 90_1x2_understat_fetch_debug_raw_response.html.",
            "",
            "Statut de suivi :",
            "- Tache realisee : diagnostic technique de recuperation Understat.",
            "- Statut source a mettre a jour : a produire -> realise pour les fichiers 89, 90 et 91.",
        ]
    )

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


# Lance le diagnostic complet sur une page Understat unique.
def main() -> None:
    ensure_report_dir()

    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    print("Diagnostic Understat V8 - recuperation brute...")
    print(f"URL testee : {url}")

    result = fetch_understat_page(url)
    diagnosis = diagnose_fetch_result(result)

    write_debug_files(result, diagnosis)
    write_summary(result, diagnosis)

    print("OK - Diagnostic Understat termine.")
    print(f"HTTP OK: {result.ok}")
    print(f"Status code: {result.status_code}")
    print(f"Body length: {diagnosis['body_length']}")
    print(f"datesData found: {diagnosis['dates_found']}")
    print(f"datesData rows: {diagnosis['dates_count']}")
    print(f"Recommendation: {diagnosis['recommendation']}")
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Raw HTML saved: {RAW_HTML_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Extract saved: {EXTRACT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# debug_1x2_understat_fetch.py
#   -> Internet / Understat page HTML
#   -> reports/evidence/ml_training/89_1x2_understat_fetch_debug_summary.txt
#   -> reports/evidence/ml_training/90_1x2_understat_fetch_debug_raw_response.html
#   -> reports/evidence/ml_training/91_1x2_understat_fetch_debug_extract_sample.txt
#   -> Ne modifie ni PostgreSQL, ni ml.features, ni API, ni frontend, ni modele sauvegarde.
