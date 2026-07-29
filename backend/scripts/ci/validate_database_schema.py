# Rôle du fichier :
# Ce script vérifie en lecture seule la structure PostgreSQL active de RubyBets,
# ses relations principales et le périmètre de données personnelles du MVP.

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
REPORT_PATH = (
    REPO_ROOT
    / "reports"
    / "evidence"
    / "database"
    / "database_schema_validation.json"
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


REQUIRED_PUBLIC_TABLES = {
    "competitions",
    "teams",
    "matches",
    "predictions",
    "recommendations",
    "recommendation_items",
    "archived_predictions",
}

REQUIRED_RELATIONS = {
    ("public", "matches", "public", "competitions"),
    ("public", "matches", "public", "teams"),
    ("public", "predictions", "public", "matches"),
    ("public", "recommendation_items", "public", "recommendations"),
    ("public", "recommendation_items", "public", "predictions"),
    ("public", "archived_predictions", "public", "matches"),
    ("public", "archived_predictions", "public", "predictions"),
}

PERSONAL_DATA_TABLE_NAMES = {
    "users",
    "user_accounts",
    "accounts",
    "profiles",
    "customers",
    "payments",
    "payment_methods",
    "transactions",
}

PERSONAL_DATA_COLUMN_NAMES = {
    "email",
    "phone",
    "phone_number",
    "password",
    "password_hash",
    "first_name",
    "last_name",
    "full_name",
    "birth_date",
    "date_of_birth",
    "postal_address",
    "ip_address",
    "payment_card",
    "card_number",
    "iban",
}


# Retourne une date UTC sérialisable pour dater la preuve.
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Vérifie que le fichier .gitignore exclut bien les fichiers .env.
def check_env_is_gitignored() -> bool:
    gitignore_path = REPO_ROOT / ".gitignore"
    if not gitignore_path.exists():
        return False

    ignored_lines = {
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return ".env" in ignored_lines or "**/.env" in ignored_lines


# Récupère les schémas applicatifs visibles dans PostgreSQL.
def fetch_schemas(cursor: psycopg.Cursor[Any]) -> list[str]:
    cursor.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('public', 'ml', 'ml_national')
        ORDER BY schema_name;
        """
    )
    return [row["schema_name"] for row in cursor.fetchall()]


# Récupère les tables applicatives des schémas RubyBets.
def fetch_tables(cursor: psycopg.Cursor[Any]) -> list[dict[str, str]]:
    cursor.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema IN ('public', 'ml', 'ml_national')
        ORDER BY table_schema, table_name;
        """
    )
    return [dict(row) for row in cursor.fetchall()]


# Récupère les colonnes applicatives afin de contrôler le périmètre RGPD.
def fetch_columns(cursor: psycopg.Cursor[Any]) -> list[dict[str, str]]:
    cursor.execute(
        """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema IN ('public', 'ml', 'ml_national')
        ORDER BY table_schema, table_name, ordinal_position;
        """
    )
    return [dict(row) for row in cursor.fetchall()]


# Compte les contraintes primaires, étrangères, uniques et de contrôle.
def fetch_constraint_counts(cursor: psycopg.Cursor[Any]) -> dict[str, int]:
    cursor.execute(
        """
        SELECT
            CASE constraint_type
                WHEN 'PRIMARY KEY' THEN 'primary_keys'
                WHEN 'FOREIGN KEY' THEN 'foreign_keys'
                WHEN 'UNIQUE' THEN 'unique_constraints'
                WHEN 'CHECK' THEN 'check_constraints'
            END AS constraint_group,
            COUNT(*)::INTEGER AS total
        FROM information_schema.table_constraints
        WHERE table_schema IN ('public', 'ml', 'ml_national')
          AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK')
        GROUP BY constraint_type;
        """
    )

    counts = {
        "primary_keys": 0,
        "foreign_keys": 0,
        "unique_constraints": 0,
        "check_constraints": 0,
    }

    for row in cursor.fetchall():
        group = row["constraint_group"]
        if group:
            counts[group] = row["total"]

    return counts


# Récupère les relations entre tables à partir des clés étrangères PostgreSQL.
def fetch_foreign_key_relations(
    cursor: psycopg.Cursor[Any],
) -> list[dict[str, str]]:
    cursor.execute(
        """
        SELECT DISTINCT
            source_namespace.nspname AS source_schema,
            source_table.relname AS source_table,
            target_namespace.nspname AS target_schema,
            target_table.relname AS target_table
        FROM pg_constraint AS constraint_definition
        JOIN pg_class AS source_table
          ON source_table.oid = constraint_definition.conrelid
        JOIN pg_namespace AS source_namespace
          ON source_namespace.oid = source_table.relnamespace
        JOIN pg_class AS target_table
          ON target_table.oid = constraint_definition.confrelid
        JOIN pg_namespace AS target_namespace
          ON target_namespace.oid = target_table.relnamespace
        WHERE constraint_definition.contype = 'f'
          AND source_namespace.nspname IN ('public', 'ml', 'ml_national')
        ORDER BY source_schema, source_table, target_schema, target_table;
        """
    )
    return [dict(row) for row in cursor.fetchall()]


# Compte les index applicatifs disponibles dans les schémas RubyBets.
def fetch_index_count(cursor: psycopg.Cursor[Any]) -> int:
    cursor.execute(
        """
        SELECT COUNT(*)::INTEGER AS total
        FROM pg_indexes
        WHERE schemaname IN ('public', 'ml', 'ml_national');
        """
    )
    row = cursor.fetchone()
    return int(row["total"]) if row else 0


# Identifie les tables ou colonnes correspondant à des données personnelles usuelles.
def find_personal_data_candidates(
    tables: list[dict[str, str]],
    columns: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    table_candidates = [
        table
        for table in tables
        if table["table_name"].lower() in PERSONAL_DATA_TABLE_NAMES
    ]

    column_candidates = [
        column
        for column in columns
        if column["column_name"].lower() in PERSONAL_DATA_COLUMN_NAMES
    ]

    return {
        "tables": table_candidates,
        "columns": column_candidates,
    }


# Vérifie que les relations structurantes du modèle métier sont présentes.
def find_missing_relations(
    foreign_keys: list[dict[str, str]],
) -> list[dict[str, str]]:
    actual_relations = {
        (
            relation["source_schema"],
            relation["source_table"],
            relation["target_schema"],
            relation["target_table"],
        )
        for relation in foreign_keys
    }

    missing_relations = REQUIRED_RELATIONS - actual_relations

    return [
        {
            "source_schema": relation[0],
            "source_table": relation[1],
            "target_schema": relation[2],
            "target_table": relation[3],
        }
        for relation in sorted(missing_relations)
    ]


# Construit la preuve C4 à partir des métadonnées PostgreSQL réelles.
def build_validation_report() -> dict[str, Any]:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL est absent de backend/.env. "
            "La validation C4 nécessite la base PostgreSQL active."
        )

    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    current_setting('server_version') AS server_version;
                """
            )
            database_identity = dict(cursor.fetchone() or {})

            schemas = fetch_schemas(cursor)
            tables = fetch_tables(cursor)
            columns = fetch_columns(cursor)
            constraint_counts = fetch_constraint_counts(cursor)
            foreign_keys = fetch_foreign_key_relations(cursor)
            index_count = fetch_index_count(cursor)

    public_tables = {
        table["table_name"]
        for table in tables
        if table["table_schema"] == "public"
    }

    missing_public_tables = sorted(REQUIRED_PUBLIC_TABLES - public_tables)
    missing_relations = find_missing_relations(foreign_keys)
    personal_data_candidates = find_personal_data_candidates(tables, columns)
    env_is_gitignored = check_env_is_gitignored()

    errors: list[str] = []
    warnings: list[str] = []

    if "public" not in schemas:
        errors.append("Le schéma PostgreSQL public est introuvable.")

    if missing_public_tables:
        errors.append(
            "Tables métier manquantes : " + ", ".join(missing_public_tables)
        )

    if missing_relations:
        errors.append(
            f"{len(missing_relations)} relation(s) métier attendue(s) sont absentes."
        )

    if personal_data_candidates["tables"] or personal_data_candidates["columns"]:
        errors.append(
            "Des tables ou colonnes candidates à des données personnelles "
            "ont été détectées dans le MVP."
        )

    if not env_is_gitignored:
        warnings.append(
            "Le motif .env n'a pas été détecté dans .gitignore."
        )

    status = "PASSED" if not errors else "FAILED"

    return {
        "status": status,
        "generated_at_utc": utc_now_iso(),
        "database": {
            "name": database_identity.get("database_name"),
            "server_version": database_identity.get("server_version"),
            "connection_configured": True,
            "connection_secret_exposed_in_report": False,
        },
        "schemas": {
            "detected": schemas,
            "core_schema_present": "public" in schemas,
            "analytical_schemas_detected": [
                schema for schema in schemas if schema in {"ml", "ml_national"}
            ],
        },
        "tables": {
            "total_detected": len(tables),
            "required_public_tables": sorted(REQUIRED_PUBLIC_TABLES),
            "missing_public_tables": missing_public_tables,
            "detected": tables,
        },
        "constraints": {
            **constraint_counts,
            "required_relations": len(REQUIRED_RELATIONS),
            "detected_foreign_key_relations": len(foreign_keys),
            "missing_relations": missing_relations,
            "relations": foreign_keys,
            "indexes": index_count,
        },
        "rgpd_scope": {
            "mvp_user_accounts": False,
            "mvp_payment_data": False,
            "mvp_personal_data_collection": False,
            "personal_data_candidates": personal_data_candidates,
            "database_url_stored_outside_git": env_is_gitignored,
            "data_categories": [
                "données football issues de sources documentées",
                "données préparées et features analytiques",
                "prédictions et recommandations calculées",
                "logs techniques sans secret",
            ],
        },
        "errors": errors,
        "warnings": warnings,
    }


# Écrit le rapport JSON de preuve sans exposer la chaîne de connexion.
def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# Affiche une synthèse lisible et retourne un code d'échec si la preuve est invalide.
def main() -> int:
    try:
        report = build_validation_report()
    except Exception as error:
        report = {
            "status": "FAILED",
            "generated_at_utc": utc_now_iso(),
            "errors": [str(error)],
            "warnings": [],
        }

    write_report(report)

    if report["status"] == "PASSED":
        table_total = report["tables"]["total_detected"]
        foreign_key_total = report["constraints"]["detected_foreign_key_relations"]
        print(
            "Validation PostgreSQL RubyBets : PASSED — "
            f"{table_total} table(s), "
            f"{foreign_key_total} relation(s) détectée(s), "
            "0 donnée personnelle MVP détectée."
        )
        print(f"Rapport : {REPORT_PATH.relative_to(REPO_ROOT)}")
        return 0

    print("Validation PostgreSQL RubyBets : FAILED")
    for error in report.get("errors", []):
        print(f"- {error}")
    print(f"Rapport : {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


# Schéma de communication :
# backend/.env (DATABASE_URL)
#        ↓
# PostgreSQL rubybets_db
#        ↓
# backend/scripts/ci/validate_database_schema.py
#        ↓
# reports/evidence/database/database_schema_validation.json
#        ↓
# docs/database_rgpd.md + matrice RNCP C4
