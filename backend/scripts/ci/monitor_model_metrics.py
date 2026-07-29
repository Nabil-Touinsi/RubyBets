# Rôle du fichier : produire une preuve CI synthétique des métriques, couvertures et garde-fous des modèles ML RubyBets.

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


DEFAULT_REPORT_PATH = Path(
    "reports/evidence/model_monitoring/model_metrics_monitoring.json"
)
METRIC_KEYS = (
    "accuracy",
    "balanced_accuracy",
    "f1_macro",
    "f1_weighted",
    "precision_macro",
    "recall_macro",
)


@dataclass
class MonitoringContext:
    """Centralise les modèles suivis, les contrôles et les messages du rapport."""

    project_root: Path
    models: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Convertit un chemin absolu en chemin stable relatif à la racine du dépôt.
def to_repo_path(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


# Normalise un chemin déclaré dans les métadonnées Windows ou Linux.
def normalize_declared_path(raw_path: str) -> Path:
    return Path(raw_path.replace("\\", "/"))


# Charge un fichier JSON de métadonnées en contrôlant son format.
def load_json(path: Path, context: MonitoringContext) -> dict[str, Any] | None:
    relative_path = to_repo_path(path, context.project_root)

    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        context.errors.append(
            f"Métadonnées illisibles ({relative_path}) : {type(error).__name__}: {error}"
        )
        return None

    if not isinstance(payload, dict):
        context.errors.append(
            f"Métadonnées invalides ({relative_path}) : un objet JSON est attendu."
        )
        return None

    return payload


# Conserve uniquement les métriques numériques reconnues et les arrondit pour le rapport.
def extract_metrics(raw_metrics: Any) -> dict[str, float]:
    if not isinstance(raw_metrics, dict):
        return {}

    metrics: dict[str, float] = {}
    for key in METRIC_KEYS:
        value = raw_metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = round(float(value), 6)

    return metrics


# Vérifie qu'une métrique reste dans l'intervalle probabiliste attendu [0, 1].
def validate_metric_range(
    model_id: str,
    metrics: dict[str, float],
    context: MonitoringContext,
) -> None:
    for metric_name, metric_value in metrics.items():
        if not 0.0 <= metric_value <= 1.0:
            context.errors.append(
                f"{model_id} : {metric_name}={metric_value} est hors de l'intervalle [0, 1]."
            )


# Vérifie qu'un candidat annoncé comme amélioré ne régresse pas sous sa référence déclarée.
def validate_declared_reference(
    model_id: str,
    metadata: dict[str, Any],
    metrics: dict[str, float],
    context: MonitoringContext,
) -> dict[str, Any] | None:
    reference = metadata.get("official_baseline_reference")
    if not isinstance(reference, dict):
        return None

    comparison: dict[str, Any] = {"status": "not_comparable", "metrics": {}}
    comparable_count = 0
    regression_count = 0

    for metric_name in ("accuracy", "f1_macro"):
        current_value = metrics.get(metric_name)
        reference_value = reference.get(metric_name)
        if not isinstance(reference_value, (int, float)) or current_value is None:
            continue

        comparable_count += 1
        delta = round(current_value - float(reference_value), 6)
        comparison["metrics"][metric_name] = {
            "current": current_value,
            "reference": round(float(reference_value), 6),
            "delta": delta,
        }
        if delta < 0:
            regression_count += 1
            context.errors.append(
                f"{model_id} : régression déclarée sur {metric_name} ({current_value} < {reference_value})."
            )

    if comparable_count:
        comparison["status"] = "regression" if regression_count else "no_regression"

    return comparison


# Extrait les informations de couverture sélective lorsqu'elles sont documentées.
def extract_selective_coverage(metadata: dict[str, Any]) -> dict[str, Any] | None:
    threshold_data = metadata.get("high_confidence_reference_threshold")
    if not isinstance(threshold_data, dict):
        return None

    monitored: dict[str, Any] = {}
    for key in ("threshold", "selected_rows", "coverage", "accuracy"):
        value = threshold_data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            monitored[key] = value

    return monitored or None


# Analyse un modèle accompagné d'un fichier JSON de métadonnées externe.
def monitor_metadata_model(
    metadata_path: Path,
    metadata: dict[str, Any],
    context: MonitoringContext,
) -> None:
    relative_metadata_path = to_repo_path(metadata_path, context.project_root)
    model_id = str(
        metadata.get("model_version")
        or metadata.get("model_name")
        or metadata_path.parent.name
    )
    declared_artifact = metadata.get("model_artifact")
    artifact_path: Path | None = None

    if isinstance(declared_artifact, str) and declared_artifact.strip():
        artifact_path = (
            context.project_root / normalize_declared_path(declared_artifact)
        ).resolve()
        if not artifact_path.is_file():
            context.errors.append(
                f"{model_id} : artefact déclaré introuvable ({declared_artifact})."
            )
    else:
        context.errors.append(f"{model_id} : model_artifact absent des métadonnées.")

    metrics = extract_metrics(metadata.get("evaluation_results"))
    if "accuracy" not in metrics or "f1_macro" not in metrics:
        context.errors.append(
            f"{model_id} : les métriques accuracy et f1_macro sont obligatoires."
        )
    validate_metric_range(model_id, metrics, context)

    reference_comparison = validate_declared_reference(
        model_id, metadata, metrics, context
    )
    selective_coverage = extract_selective_coverage(metadata)

    if selective_coverage:
        coverage = selective_coverage.get("coverage")
        selective_accuracy = selective_coverage.get("accuracy")
        for metric_name, metric_value in (
            ("coverage", coverage),
            ("selective_accuracy", selective_accuracy),
        ):
            if isinstance(metric_value, (int, float)) and not 0.0 <= float(metric_value) <= 1.0:
                context.errors.append(
                    f"{model_id} : {metric_name}={metric_value} est hors de [0, 1]."
                )

    context.models.append(
        {
            "model_id": model_id,
            "source": "metadata_json",
            "scope": metadata.get("scope") or metadata.get("model_scope"),
            "status": metadata.get("status")
            or metadata.get("responsible_positioning", {}).get("status"),
            "target": metadata.get("target") or metadata.get("target_column"),
            "artifact": (
                to_repo_path(artifact_path, context.project_root)
                if artifact_path and artifact_path.is_file()
                else declared_artifact
            ),
            "metadata": relative_metadata_path,
            "feature_count": metadata.get("feature_count")
            or len(metadata.get("features_used", []))
            or len(metadata.get("features_expected", [])),
            "metrics": metrics,
            "reference_comparison": reference_comparison,
            "selective_coverage": selective_coverage,
        }
    )


# Analyse un bundle multimarché dont les métriques sont embarquées dans le fichier Joblib.
def monitor_embedded_bundle(
    artifact_path: Path,
    context: MonitoringContext,
) -> None:
    relative_path = to_repo_path(artifact_path, context.project_root)

    try:
        bundle = joblib.load(artifact_path)
    except Exception as error:  # noqa: BLE001 - la preuve doit capturer toute erreur de désérialisation.
        context.errors.append(
            f"Bundle illisible ({relative_path}) : {type(error).__name__}: {error}"
        )
        return

    if not isinstance(bundle, dict):
        context.errors.append(f"{relative_path} : bundle dictionnaire attendu.")
        return

    market = str(bundle.get("market") or artifact_path.stem)
    model_id = f"v18_3_{market.lower()}_{bundle.get('model_name', 'model')}"
    raw_metrics = bundle.get("metrics")
    metrics = extract_metrics(raw_metrics)

    if "accuracy" not in metrics or "f1_macro" not in metrics:
        context.errors.append(
            f"{model_id} : les métriques accuracy et f1_macro sont obligatoires."
        )
    validate_metric_range(model_id, metrics, context)

    embedded_status = raw_metrics.get("status") if isinstance(raw_metrics, dict) else None
    if embedded_status not in (None, "OK"):
        context.errors.append(
            f"{model_id} : statut embarqué inattendu ({embedded_status})."
        )

    context.models.append(
        {
            "model_id": model_id,
            "source": "embedded_joblib_bundle",
            "scope": "v18_3_global_multimarket",
            "status": embedded_status or "OK",
            "target": bundle.get("target_column"),
            "market": market,
            "artifact": relative_path,
            "feature_count": len(bundle.get("feature_columns", [])),
            "train_rows": raw_metrics.get("train_rows") if isinstance(raw_metrics, dict) else None,
            "test_rows": raw_metrics.get("test_rows") if isinstance(raw_metrics, dict) else None,
            "metrics": metrics,
            "reference_comparison": None,
            "selective_coverage": None,
        }
    )


# Découvre et contrôle les métadonnées externes ainsi que les bundles multimarchés actifs.
def run_monitoring(project_root: Path) -> MonitoringContext:
    resolved_root = project_root.resolve()
    context = MonitoringContext(project_root=resolved_root)
    models_root = resolved_root / "models"

    if not models_root.is_dir():
        context.errors.append("Le dossier models est introuvable.")
        return context

    metadata_paths = sorted(
        path
        for path in models_root.rglob("*.json")
        if path.name == "model_metadata.json" or path.name.endswith("_metadata.json")
    )
    for metadata_path in metadata_paths:
        metadata = load_json(metadata_path, context)
        if metadata is not None:
            monitor_metadata_model(metadata_path, metadata, context)

    bundle_root = models_root / "ml_national" / "v18_3_global_multimarket"
    for artifact_path in sorted(bundle_root.glob("*.joblib")):
        monitor_embedded_bundle(artifact_path, context)

    if len(context.models) != 7:
        context.errors.append(
            f"Inventaire incomplet : 7 modèles attendus, {len(context.models)} suivis."
        )

    return context


# Construit le rapport JSON lisible par GitHub Actions et exploitable en soutenance.
def build_report(context: MonitoringContext) -> dict[str, Any]:
    metric_values = [
        value
        for model in context.models
        for value in model.get("metrics", {}).values()
    ]
    selective_models = sum(
        1 for model in context.models if model.get("selective_coverage")
    )

    return {
        "report_name": "RubyBets ML model metrics monitoring",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FAILED" if context.errors else "PASSED",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "summary": {
            "models_monitored": len(context.models),
            "metrics_monitored": len(metric_values),
            "selective_models_monitored": selective_models,
            "errors": len(context.errors),
            "warnings": len(context.warnings),
        },
        "models": context.models,
        "errors": context.errors,
        "warnings": context.warnings,
        "responsible_note": (
            "Ce rapport surveille les artefacts et métriques techniques disponibles. "
            "Il ne constitue pas une garantie de résultat sportif."
        ),
    }


# Écrit le rapport dans un JSON UTF-8 stable et crée le dossier cible si nécessaire.
def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(report, destination, ensure_ascii=False, indent=2)
        destination.write("\n")


# Définit les paramètres de ligne de commande pour les usages local et CI.
def parse_arguments() -> argparse.Namespace:
    default_project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Surveille les métriques déclarées des modèles ML RubyBets."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_project_root,
        help="Racine du dépôt RubyBets.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Chemin du rapport JSON, relatif à la racine si nécessaire.",
    )
    return parser.parse_args()


# Exécute le monitoring, affiche la synthèse et retourne un code compatible avec la CI.
def main() -> int:
    arguments = parse_arguments()
    project_root = arguments.project_root.resolve()
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = project_root / output_path

    context = run_monitoring(project_root)
    report = build_report(context)
    write_report(report, output_path)

    summary = report["summary"]
    print(
        "Monitoring des métriques ML RubyBets : "
        f"{report['status']} — {summary['models_monitored']}/7 modèles suivis, "
        f"{summary['metrics_monitored']} métriques, "
        f"{summary['errors']} erreur(s), {summary['warnings']} avertissement(s)."
    )
    print(f"Rapport : {to_repo_path(output_path, project_root)}")

    for error in context.errors:
        print(f"ERREUR : {error}", file=sys.stderr)
    for warning in context.warnings:
        print(f"AVERTISSEMENT : {warning}", file=sys.stderr)

    return 1 if context.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())


# Schéma de communication :
# models/**/*.json + models/**/*.joblib -> monitor_model_metrics.py
# monitor_model_metrics.py -> reports/evidence/model_monitoring/model_metrics_monitoring.json
# backend-tests.yml -> monitor_model_metrics.py -> artefact GitHub Actions temporaire
