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