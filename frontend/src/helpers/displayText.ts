// Ce fichier regroupe les fonctions qui transforment les valeurs techniques en textes lisibles pour l'interface RubyBets.

import type { Match, Team } from "../models/rubybets";

const UNKNOWN_TEAM_LABEL = "Équipe à confirmer";
const UNKNOWN_FIXTURE_LABEL = "Affiche à confirmer";

// Cette fonction évite d'afficher des puces vides lorsque le backend renvoie une chaîne vide.
export function cleanTextItems(items: string[]) {
  return items.filter((item) => item.trim().length > 0);
}

// Cette fonction traduit les niveaux de risque techniques en libellés utilisateur.
export function formatRiskLevel(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyen",
    high: "élevé",
  };

  return labels[value] || value;
}

// Cette fonction traduit les niveaux de confiance techniques en libellés utilisateur.
export function formatConfidenceLevel(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyenne",
    high: "élevée",
  };

  return labels[value] || value;
}

// Cette fonction traduit les niveaux de priorité techniques en libellés utilisateur.
export function formatPriority(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyenne",
    high: "haute",
  };

  return labels[value] || value;
}

// Cette fonction traduit le statut technique d'une prédiction en texte lisible.
export function formatPredictionStatus(value: string) {
  const labels: Record<string, string> = {
    available: "disponible",
    partial: "partiel",
    unavailable: "indisponible",
    insufficient_data: "données insuffisantes",
  };

  return labels[value] || value;
}

// Cette fonction traduit une tendance de contexte en texte lisible.
export function formatContextTrend(value: string) {
  const labels: Record<string, string> = {
    home_advantage: "avantage domicile",
    home_context_advantage: "avantage contextuel domicile",
    away_advantage: "avantage extérieur",
    away_context_advantage: "avantage contextuel extérieur",
    balanced: "équilibré",
    cautious: "lecture prudente",
    insufficient_data: "données insuffisantes",
  };

  return labels[value] || value;
}

// Cette fonction traduit le statut technique d'un match en texte lisible.
export function formatMatchStatus(value: string) {
  const labels: Record<string, string> = {
    TIMED: "programmé",
    SCHEDULED: "planifié",
    FINISHED: "terminé",
    IN_PLAY: "en cours",
    PAUSED: "pause",
    POSTPONED: "reporté",
    CANCELLED: "annulé",
  };

  return labels[value] || value;
}

// Cette fonction indique si une donnée vient du cache ou d'un appel source récent.
export function formatCacheStatus(fromCache: boolean) {
  return fromCache ? "donnée servie depuis le cache" : "donnée récupérée depuis la source";
}

// Cette fonction transforme une date ISO en date lisible pour l'utilisateur.
export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "non disponible";
  }

  return new Date(value).toLocaleString("fr-FR");
}

// Cette fonction affiche la durée de validité du cache en minutes.
export function formatTtlMinutes(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "non disponible";
  }

  return `${value} minutes`;
}

// Cette fonction vérifie si un texte est réellement exploitable pour l'interface.
function hasReadableValue(value: string | null | undefined) {
  return Boolean(value && value.trim().length > 0);
}

// Cette fonction indique si une équipe possède un nom exploitable.
export function hasKnownTeam(team: Team | null | undefined) {
  return hasReadableValue(team?.name) || hasReadableValue(team?.short_name) || hasReadableValue(team?.tla);
}

// Cette fonction indique si les deux équipes d'un match sont connues.
export function hasKnownTeams(match: Match | null | undefined) {
  return hasKnownTeam(match?.home_team) && hasKnownTeam(match?.away_team);
}

// Cette fonction retourne le nom lisible d'une équipe avec un fallback pour les matchs incomplets.
export function getTeamDisplayName(team: Team | null | undefined, fallback = UNKNOWN_TEAM_LABEL) {
  if (hasReadableValue(team?.name)) {
    return team!.name!.trim();
  }

  if (hasReadableValue(team?.short_name)) {
    return team!.short_name!.trim();
  }

  if (hasReadableValue(team?.tla)) {
    return team!.tla!.trim();
  }

  return fallback;
}

// Cette fonction retourne un nom court d'équipe en privilégiant short_name et tla.
export function getTeamShortName(team: Team | null | undefined, fallback = UNKNOWN_TEAM_LABEL) {
  if (hasReadableValue(team?.short_name)) {
    return team!.short_name!.trim();
  }

  if (hasReadableValue(team?.tla)) {
    return team!.tla!.trim();
  }

  if (hasReadableValue(team?.name)) {
    return team!.name!.trim();
  }

  return fallback;
}

// Cette fonction génère des initiales lisibles même lorsque l'équipe n'est pas encore connue.
export function getTeamInitials(team: Team | null | undefined, fallback = "?") {
  if (hasReadableValue(team?.tla)) {
    return team!.tla!.trim().slice(0, 3).toUpperCase();
  }

  const label = getTeamShortName(team, fallback);

  if (label === fallback) {
    return fallback;
  }

  return label
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("") || fallback;
}

// Cette fonction retourne un libellé complet de rencontre avec fallback pour les affiches inconnues.
export function getFixtureDisplayName(match: Match | null | undefined) {
  if (!match) {
    return UNKNOWN_FIXTURE_LABEL;
  }

  if (!hasKnownTeams(match)) {
    return UNKNOWN_FIXTURE_LABEL;
  }

  return `${getTeamShortName(match.home_team)} vs ${getTeamShortName(match.away_team)}`;
}

// Cette fonction construit un texte de recherche sécurisé pour les filtres côté frontend.
export function getTeamSearchText(team: Team | null | undefined) {
  return [team?.name, team?.short_name, team?.tla]
    .filter((value): value is string => hasReadableValue(value))
    .join(" ")
    .toLowerCase();
}

// Schéma de communication du fichier :
// displayText.ts
// ├── utilisé par les composants React pour afficher des libellés compréhensibles
// ├── sécurise les noms d'équipes lorsque l'API renvoie des valeurs nulles
// ├── utilisé par les blocs matchs, détails, analyse, prédictions et recommandations
// └── préparé pour afficher les informations de fraîcheur des données backend
