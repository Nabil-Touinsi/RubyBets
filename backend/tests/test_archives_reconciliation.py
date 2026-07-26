# Rôle du fichier :
# Ces tests vérifient le résumé global et l'actualisation des résultats archivés.

from datetime import datetime

from app.services.archives_service import (
    build_archive_reconciliation_update,
    compute_archive_verdict,
    normalize_archive_summary_row,
)


# Ce test vérifie que les indicateurs globaux utilisent toutes les archives agrégées.
def test_normalize_archive_summary_row_computes_success_rate() -> None:
    summary = normalize_archive_summary_row((20, 10, 7, 3, 8, 2))

    assert summary == {
        "total": 20,
        "evaluated": 10,
        "successful": 7,
        "unsuccessful": 3,
        "pending": 8,
        "not_verifiable": 2,
        "success_rate": 70.0,
    }


# Ce test vérifie qu'un résultat terminé actualise le score et le verdict 1X2.
def test_build_archive_reconciliation_update_resolves_finished_match() -> None:
    checked_at = datetime(2026, 7, 25, 12, 0, 0)
    archive = {
        "id": 42,
        "market_type": "1X2",
        "predicted_value": "TEAM_A_WIN",
    }
    source_match = {
        "status": "FINISHED",
        "score": {
            "fullTime": {
                "home": 2,
                "away": 1,
            }
        },
    }

    update = build_archive_reconciliation_update(
        archive=archive,
        source_match=source_match,
        checked_at=checked_at,
    )

    assert update == {
        "id": 42,
        "final_home_score": 2,
        "final_away_score": 1,
        "match_status": "FINISHED",
        "verdict": "correct",
        "checked_at": checked_at,
    }


# Ce test vérifie qu'un match annulé sans score ne reste pas indéfiniment en attente.
def test_compute_archive_verdict_marks_cancelled_match_not_verifiable() -> None:
    verdict = compute_archive_verdict(
        market_type="BTTS",
        predicted_value="YES",
        final_home_score=None,
        final_away_score=None,
        match_status="CANCELLED",
    )

    assert verdict == "not_verifiable"


# Schéma de communication :
# test_archives_reconciliation.py
# └── archives_service.py
#     ├── normalize_archive_summary_row()
#     ├── build_archive_reconciliation_update()
#     └── compute_archive_verdict()
