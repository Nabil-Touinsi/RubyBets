# Rôle du fichier : valider les artefacts ML RubyBets, leurs métadonnées et leur lisibilité avant livraison continue.

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


DEFAULT_REPORT_PATH = Path(
    "reports/evidence/model_delivery/model_artifacts_validation.json"
)
MODEL_EXTENSION = ".joblib"
METADATA_FILENAMES = {"model_metadata.json"}
METADATA_SUFFIX = "_metadata.json"


@dataclass
class ValidationContext:
    """Centralise les résultats de validation avant génération du rapport JSON."""

    project_root: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata_files: list[dict[str, Any]] = field(default_factory=list)


# Convertit un chemin du dépôt en notation POSIX stable pour les rapports et GitHub Actions.
def to_repo_path(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


# Normalise un chemin déclaré dans un JSON afin de supporter Windows et Linux.
def normalize_declared_path(raw_path: str) -> Path:
    return Path(raw_path.replace("\\", "/"))


# Calcule l'empreinte SHA-256 d'un artefact pour assurer son intégrité et sa traçabilité.
def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as binary_file:
        for chunk in iter(lambda: binary_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


# Retourne la version installée d'une dépendance sans faire échouer le contrôle si elle est absente.
def get_package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


# Charge un JSON de métadonnées et vérifie qu'il contient bien un objet.
def load_metadata_file(path: Path, context: ValidationContext) -> dict[str, Any] | None:
    relative_path = to_repo_path(path, context.project_root)

    try:
        with path.open("r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        context.errors.append(
            f"Métadonnées illisibles ({relative_path}) : {type(error).__name__}: {error}"
        )
        return None

    if not isinstance(metadata, dict):
        context.errors.append(
            f"Métadonnées invalides ({relative_path}) : un objet JSON est attendu."
        )
        return None

    return metadata


# Repère les fichiers de métadonnées reconnus dans le dossier models du dépôt.
def discover_metadata_files(models_root: Path) -> list[Path]:
    return sorted(
        path
        for path in models_root.rglob("*.json")
        if path.name in METADATA_FILENAMES or path.name.endswith(METADATA_SUFFIX)
    )


# Extrait la liste de features quel que soit le format de métadonnées RubyBets utilisé.
def extract_feature_list(metadata: dict[str, Any]) -> list[str] | None:
    for key in ("features_used", "features_expected", "feature_columns"):
        value = metadata.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value

    return None


# Vérifie les champs essentiels d'un fichier de métadonnées et son lien vers l'artefact déclaré.
def validate_metadata(
    metadata_path: Path,
    metadata: dict[str, Any],
    context: ValidationContext,
) -> Path | None:
    relative_metadata_path = to_repo_path(metadata_path, context.project_root)
    declared_artifact = metadata.get("model_artifact")
    features = extract_feature_list(metadata)
    target = metadata.get("target") or metadata.get("target_column")
    model_identity = metadata.get("model_name") or metadata.get("model_version")
    metadata_errors: list[str] = []
    metadata_warnings: list[str] = []
    resolved_artifact: Path | None = None

    if not isinstance(declared_artifact, str) or not declared_artifact.strip():
        metadata_errors.append("champ model_artifact absent ou vide")
    else:
        normalized_path = normalize_declared_path(declared_artifact)
        candidate_path = (context.project_root / normalized_path).resolve()

        try:
            candidate_path.relative_to(context.project_root.resolve())
        except ValueError:
            metadata_errors.append("model_artifact pointe en dehors du dépôt")
        else:
            resolved_artifact = candidate_path
            if not candidate_path.is_file():
                metadata_errors.append(
                    f"artefact déclaré introuvable : {normalized_path.as_posix()}"
                )
            elif candidate_path.suffix.lower() != MODEL_EXTENSION:
                metadata_errors.append("model_artifact ne pointe pas vers un fichier .joblib")

    if not isinstance(model_identity, str) or not model_identity.strip():
        metadata_errors.append("identité du modèle absente (model_name ou model_version)")

    if not isinstance(target, str) or not target.strip():
        metadata_errors.append("cible absente (target ou target_column)")

    if features is None or not features:
        metadata_errors.append("liste de features absente ou vide")

    declared_feature_count = metadata.get("feature_count")
    if declared_feature_count is not None:
        if not isinstance(declared_feature_count, int):
            metadata_errors.append("feature_count doit être un entier")
        elif features is not None and declared_feature_count != len(features):
            metadata_errors.append(
                "feature_count ne correspond pas au nombre de features déclarées"
            )

    evaluation_results = metadata.get("evaluation_results")
    if evaluation_results is None:
        metadata_warnings.append("evaluation_results absent")
    elif not isinstance(evaluation_results, dict):
        metadata_errors.append("evaluation_results doit être un objet JSON")

    for error in metadata_errors:
        context.errors.append(f"{relative_metadata_path} : {error}.")

    for warning in metadata_warnings:
        context.warnings.append(f"{relative_metadata_path} : {warning}.")

    context.metadata_files.append(
        {
            "path": relative_metadata_path,
            "status": "invalid" if metadata_errors else "valid",
            "model_identity": model_identity,
            "target": target,
            "feature_count": len(features) if features is not None else None,
            "declared_artifact": (
                normalize_declared_path(declared_artifact).as_posix()
                if isinstance(declared_artifact, str)
                else None
            ),
            "errors": metadata_errors,
            "warnings": metadata_warnings,
        }
    )

    return resolved_artifact


# Retrouve l'estimateur exploitable dans un artefact simple ou dans un bundle multimarché.
def extract_estimator(loaded_artifact: Any) -> tuple[Any | None, str]:
    if hasattr(loaded_artifact, "predict"):
        return loaded_artifact, "direct_estimator"

    if isinstance(loaded_artifact, dict):
        bundled_model = loaded_artifact.get("model")
        if hasattr(bundled_model, "predict"):
            return bundled_model, "model_bundle"

    return None, "unsupported"


# Vérifie la structure métier des bundles multimarchés V18.3 embarquant leurs métadonnées.
def validate_embedded_bundle(
    artifact_path: Path,
    loaded_artifact: Any,
    estimator: Any,
    context: ValidationContext,
) -> list[str]:
    relative_path = to_repo_path(artifact_path, context.project_root)
    bundle_errors: list[str] = []

    if not isinstance(loaded_artifact, dict):
        return bundle_errors

    required_keys = {
        "market",
        "target_column",
        "labels",
        "feature_columns",
        "model_name",
        "model",
        "metrics",
    }
    missing_keys = sorted(required_keys.difference(loaded_artifact))
    if missing_keys:
        bundle_errors.append(f"clés embarquées manquantes : {missing_keys}")

    labels = loaded_artifact.get("labels")
    if not isinstance(labels, list) or not labels or not all(
        isinstance(label, str) for label in labels
    ):
        bundle_errors.append("labels doit être une liste non vide de chaînes")

    feature_columns = loaded_artifact.get("feature_columns")
    if not isinstance(feature_columns, list) or not feature_columns or not all(
        isinstance(feature, str) for feature in feature_columns
    ):
        bundle_errors.append("feature_columns doit être une liste non vide de chaînes")

    metrics = loaded_artifact.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        bundle_errors.append("metrics doit être un objet non vide")

    estimator_classes = getattr(estimator, "classes_", None)
    if isinstance(labels, list) and estimator_classes is not None:
        if set(map(str, estimator_classes)) != set(labels):
            bundle_errors.append(
                "les labels embarqués ne correspondent pas aux classes de l'estimateur"
            )

    return bundle_errors


# Charge un artefact Joblib et vérifie qu'il expose un estimateur utilisable par RubyBets.
def validate_model_artifact(
    artifact_path: Path,
    context: ValidationContext,
    metadata_by_artifact: dict[Path, dict[str, Any]],
) -> None:
    relative_path = to_repo_path(artifact_path, context.project_root)
    artifact_errors: list[str] = []
    artifact_warnings: list[str] = []
    loaded_artifact: Any | None = None
    estimator: Any | None = None
    artifact_kind = "unknown"

    if artifact_path.stat().st_size == 0:
        artifact_errors.append("artefact vide")
    else:
        try:
            loaded_artifact = joblib.load(artifact_path)
        except Exception as error:  # noqa: BLE001 - le rapport doit capturer toute incompatibilité de chargement.
            artifact_errors.append(
                f"désérialisation impossible : {type(error).__name__}: {error}"
            )

    if loaded_artifact is not None:
        estimator, artifact_kind = extract_estimator(loaded_artifact)
        if estimator is None:
            artifact_errors.append(
                "aucun estimateur compatible trouvé directement ou dans la clé model"
            )
        elif not callable(getattr(estimator, "predict", None)):
            artifact_errors.append("méthode predict absente ou non appelable")

    if estimator is not None and artifact_kind == "model_bundle":
        artifact_errors.extend(
            validate_embedded_bundle(
                artifact_path,
                loaded_artifact,
                estimator,
                context,
            )
        )

    linked_metadata = metadata_by_artifact.get(artifact_path.resolve())
    if linked_metadata is None and artifact_kind != "model_bundle":
        artifact_warnings.append("aucun fichier de métadonnées lié à cet artefact")

    if linked_metadata is not None and estimator is not None:
        declared_classes = linked_metadata.get("target_classes")
        estimator_classes = getattr(estimator, "classes_", None)
        if isinstance(declared_classes, list) and estimator_classes is not None:
            if set(map(str, estimator_classes)) != set(map(str, declared_classes)):
                artifact_errors.append(
                    "target_classes ne correspond pas aux classes de l'estimateur"
                )

    for error in artifact_errors:
        context.errors.append(f"{relative_path} : {error}.")

    for warning in artifact_warnings:
        context.warnings.append(f"{relative_path} : {warning}.")

    context.artifacts.append(
        {
            "path": relative_path,
            "status": "invalid" if artifact_errors else "valid",
            "size_bytes": artifact_path.stat().st_size,
            "sha256": calculate_sha256(artifact_path),
            "artifact_kind": artifact_kind,
            "loaded_type": (
                f"{type(loaded_artifact).__module__}.{type(loaded_artifact).__name__}"
                if loaded_artifact is not None
                else None
            ),
            "estimator_type": (
                f"{type(estimator).__module__}.{type(estimator).__name__}"
                if estimator is not None
                else None
            ),
            "classes": (
                [str(item) for item in getattr(estimator, "classes_", [])]
                if estimator is not None
                else []
            ),
            "metadata_linked": linked_metadata is not None,
            "errors": artifact_errors,
            "warnings": artifact_warnings,
        }
    )


# Lance la validation de tous les artefacts et métadonnées présents dans models/.
def run_validation(project_root: Path) -> ValidationContext:
    resolved_root = project_root.resolve()
    models_root = resolved_root / "models"
    context = ValidationContext(project_root=resolved_root)

    if not models_root.is_dir():
        context.errors.append("Dossier models/ introuvable à la racine du dépôt.")
        return context

    metadata_by_artifact: dict[Path, dict[str, Any]] = {}
    metadata_paths = discover_metadata_files(models_root)

    for metadata_path in metadata_paths:
        metadata = load_metadata_file(metadata_path, context)
        if metadata is None:
            continue

        resolved_artifact = validate_metadata(metadata_path, metadata, context)
        if resolved_artifact is not None:
            if resolved_artifact in metadata_by_artifact:
                context.errors.append(
                    "Plusieurs fichiers de métadonnées déclarent le même artefact : "
                    f"{to_repo_path(resolved_artifact, resolved_root)}."
                )
            else:
                metadata_by_artifact[resolved_artifact] = metadata

    artifact_paths = sorted(models_root.rglob(f"*{MODEL_EXTENSION}"))
    if not artifact_paths:
        context.errors.append("Aucun artefact .joblib trouvé dans models/.")

    for artifact_path in artifact_paths:
        validate_model_artifact(artifact_path, context, metadata_by_artifact)

    referenced_paths = set(metadata_by_artifact)
    existing_paths = {artifact.resolve() for artifact in artifact_paths}
    for missing_reference in sorted(referenced_paths.difference(existing_paths)):
        context.errors.append(
            "Artefact référencé mais absent de l'inventaire : "
            f"{to_repo_path(missing_reference, resolved_root)}."
        )

    return context


# Construit le rapport JSON final avec versions, inventaire, erreurs et avertissements.
def build_report(context: ValidationContext) -> dict[str, Any]:
    valid_artifacts = sum(
        artifact["status"] == "valid" for artifact in context.artifacts
    )
    valid_metadata = sum(
        metadata["status"] == "valid" for metadata in context.metadata_files
    )

    return {
        "project": "RubyBets",
        "validation": "ml_model_artifacts",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not context.errors else "failed",
        "environment": {
            "python": platform.python_version(),
            "joblib": get_package_version("joblib"),
            "scikit_learn": get_package_version("scikit-learn"),
            "pandas": get_package_version("pandas"),
            "xgboost": get_package_version("xgboost"),
        },
        "summary": {
            "artifact_count": len(context.artifacts),
            "valid_artifact_count": valid_artifacts,
            "metadata_count": len(context.metadata_files),
            "valid_metadata_count": valid_metadata,
            "error_count": len(context.errors),
            "warning_count": len(context.warnings),
        },
        "artifacts": context.artifacts,
        "metadata_files": context.metadata_files,
        "errors": context.errors,
        "warnings": context.warnings,
    }


# Écrit le rapport dans le dépôt en créant le dossier de preuve si nécessaire.
def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# Analyse les arguments de ligne de commande utilisés localement et dans GitHub Actions.
def parse_arguments() -> argparse.Namespace:
    default_project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Valide les artefacts ML RubyBets avant leur livraison."
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
        help="Chemin du rapport JSON, relatif à la racine du dépôt par défaut.",
    )
    return parser.parse_args()


# Orchestre le contrôle, affiche la synthèse et retourne un code d'échec si une preuve est invalide.
def main() -> int:
    arguments = parse_arguments()
    project_root = arguments.project_root.resolve()
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = project_root / output_path

    context = run_validation(project_root)
    report = build_report(context)
    write_report(report, output_path)

    print(
        "Validation des artefacts ML RubyBets : "
        f"{report['status'].upper()} — "
        f"{report['summary']['valid_artifact_count']}/"
        f"{report['summary']['artifact_count']} artefacts valides, "
        f"{report['summary']['error_count']} erreur(s), "
        f"{report['summary']['warning_count']} avertissement(s)."
    )
    print(f"Rapport : {to_repo_path(output_path, project_root)}")

    if context.errors:
        for error in context.errors:
            print(f"ERREUR — {error}", file=sys.stderr)
        return 1

    for warning in context.warnings:
        print(f"AVERTISSEMENT — {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Schéma de communication :
# models/**/*.joblib + models/**/*metadata.json
#              -> backend/scripts/ci/validate_model_artifacts.py
#              -> reports/evidence/model_delivery/model_artifacts_validation.json
#              -> futur workflow .github/workflows/ml-model-delivery.yml
