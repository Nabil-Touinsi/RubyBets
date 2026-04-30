// Ce fichier centralise les appels API entre le frontend React et le backend RubyBets.

const API_BASE_URL = "http://127.0.0.1:8000";

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);

  if (!response.ok) {
    throw new Error("Erreur lors de la vérification du backend.");
  }

  return response.json();
}

export async function getCompetitions() {
  const response = await fetch(`${API_BASE_URL}/api/competitions`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement des compétitions.");
  }

  return response.json();
}

export async function getMatches(competitionCode = "PL") {
  const response = await fetch(
    `${API_BASE_URL}/api/matches?competition_code=${competitionCode}`
  );

  if (!response.ok) {
    throw new Error("Erreur lors du chargement des matchs.");
  }

  return response.json();
}

export async function getMatchDetails(matchId: number) {
  const response = await fetch(`${API_BASE_URL}/api/matches/${matchId}`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement du détail du match.");
  }

  return response.json();
}

export async function getMatchContext(matchId: number) {
  const response = await fetch(`${API_BASE_URL}/api/matches/${matchId}/context`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement du contexte du match.");
  }

  return response.json();
}

export async function getMatchAnalysis(matchId: number) {
  const response = await fetch(`${API_BASE_URL}/api/matches/${matchId}/analysis`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement de l’analyse du match.");
  }

  return response.json();
}

// Cette fonction récupère les prédictions avant-match d’un match précis.
export async function getMatchPredictions(matchId: number) {
  const response = await fetch(`${API_BASE_URL}/api/matches/${matchId}/predictions`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement des prédictions du match.");
  }

  return response.json();
}

// Cette fonction demande au backend de générer une recommandation multi-matchs selon une compétition, un nombre de matchs et un niveau de risque.
export async function getMultiMatchRecommendation(
  competitionCode: string,
  matchCount: number,
  riskLevel: "low" | "medium" | "high"
) {
  const response = await fetch(`${API_BASE_URL}/api/recommendations/multimatch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      competition_code: competitionCode,
      match_count: matchCount,
      risk_level: riskLevel,
    }),
  });

  if (!response.ok) {
    throw new Error("Erreur lors de la génération de la recommandation multi-matchs.");
  }

  return response.json();
}

// Cette fonction récupère le glossaire pédagogique de RubyBets.
export async function getGlossary() {
  const response = await fetch(`${API_BASE_URL}/api/glossary`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement du glossaire.");
  }

  return response.json();
}

// Cette fonction récupère les messages responsables et les limites d’utilisation de RubyBets.
export async function getResponsibleInfo() {
  const response = await fetch(`${API_BASE_URL}/api/responsible-info`);

  if (!response.ok) {
    throw new Error("Erreur lors du chargement des informations responsables.");
  }

  return response.json();
}