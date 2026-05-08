// Ce fichier regroupe les fonctions qui transforment les valeurs techniques en textes lisibles pour l'interface RubyBets.

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

// Schéma de communication du fichier :
// displayText.ts
// ├── utilisé par les composants React pour afficher des libellés compréhensibles
// ├── utilisé par les blocs prédictions, recommandations, contexte et statuts
// └── préparé pour afficher les informations de fraîcheur des données backend