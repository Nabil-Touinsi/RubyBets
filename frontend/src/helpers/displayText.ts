// Ce fichier regroupe les fonctions qui transforment les valeurs techniques en textes lisibles pour l’interface RubyBets.

// Évite d'afficher des puces vides lorsque le backend renvoie une chaîne vide.
export function cleanTextItems(items: string[]) {
  return items.filter((item) => item.trim().length > 0);
}

// Traduit les valeurs techniques du backend en libellés lisibles côté utilisateur.
export function formatRiskLevel(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyen",
    high: "élevé",
  };

  return labels[value] || value;
}

export function formatConfidenceLevel(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyenne",
    high: "élevée",
  };

  return labels[value] || value;
}

export function formatPriority(value: string) {
  const labels: Record<string, string> = {
    low: "faible",
    medium: "moyenne",
    high: "haute",
  };

  return labels[value] || value;
}

export function formatPredictionStatus(value: string) {
  const labels: Record<string, string> = {
    available: "disponible",
    partial: "partiel",
    unavailable: "indisponible",
    insufficient_data: "données insuffisantes",
  };

  return labels[value] || value;
}

export function formatContextTrend(value: string) {
  const labels: Record<string, string> = {
    home_advantage: "avantage domicile",
    away_advantage: "avantage extérieur",
    balanced: "équilibré",
    cautious: "lecture prudente",
    insufficient_data: "données insuffisantes",
  };

  return labels[value] || value;
}

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
