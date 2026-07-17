# Rôle du fichier :
# Ces tests vérifient que le contrat public des archives masque les métriques et versions internes.

from app.services.archives_service import (
    build_archive_justification,
    map_archive_row,
)


# Ce test vérifie qu’une nouvelle justification n’expose aucune probabilité interne.
def test_build_archive_justification_hides_probability() -> None:
    justification = build_archive_justification(
        "BTTS",
        {"max_probability": 0.521},
    )

    lowered = justification.lower()

    assert "52.1" not in justification
    assert "probabilité" not in lowered
    assert "probability" not in lowered
    assert "max_probability" not in lowered


# Ce test vérifie que les anciennes archives sont assainies avant exposition publique.
def test_map_archive_row_hides_legacy_probability_and_engine_version() -> None:
    row = (
        1,
        "123",
        "source-123",
        "Competition",
        "Home",
        "Away",
        None,
        None,
        None,
        None,
        None,
        None,
        "BTTS",
        "NO",
        "low",
        "high",
        "Prédiction BTTS générée avec une probabilité maximale de 52.1 %.",
        "rubybets_ml_national_v18_3_4_dynamic_inference",
        None,
        None,
        "SCHEDULED",
        "pending",
        None,
    )

    archive = map_archive_row(row)
    public_json = str(archive).lower()

    assert "engine_version" not in archive
    assert "52.1" not in public_json
    assert "probabilité" not in public_json
    assert "rubybets_ml_national_v18_3_4_dynamic_inference" not in public_json


# Schéma de communication :
# test_archives_public_contract.py
# └── archives_service.py
#     ├── map_archive_row()
#     └── build_archive_justification()
