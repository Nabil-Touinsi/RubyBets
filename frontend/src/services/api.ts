// Ce fichier centralise les appels API entre le frontend React et le backend RubyBets.
// Il sécurise les échanges front/back avec des réponses TypeScript typées.

import type {
  CompetitionsResponse,
  GlossaryResponse,
  HealthResponse,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchPredictionsResponse,
  MatchesResponse,
  MultiMatchRecommendationResponse,
  ResponsibleInfoResponse,
} from "../models/rubybets";

const API_BASE_URL = "http://127.0.0.1:8000";

// Cette fonction générique appelle le backend et retourne une réponse JSON typée.
async function fetchJson<T>(
  endpoint: string,
  errorMessage: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

  if (!response.ok) {
    throw new Error(`${errorMessage} Code HTTP : ${response.status}.`);
  }

  return response.json() as Promise<T>;
}

// Cette fonction vérifie que le backend RubyBets est disponible.
export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>(
    "/health",
    "Erreur lors de la vérification du backend."
  );
}

// Cette fonction récupère les compétitions football suivies par RubyBets.
export async function getCompetitions(): Promise<CompetitionsResponse> {
  return fetchJson<CompetitionsResponse>(
    "/api/competitions",
    "Erreur lors du chargement des compétitions."
  );
}

// Cette fonction récupère les matchs à venir pour une compétition donnée.
export async function getMatches(competitionCode = "PL"): Promise<MatchesResponse> {
  return fetchJson<MatchesResponse>(
    `/api/matches?competition_code=${competitionCode}`,
    "Erreur lors du chargement des matchs."
  );
}

// Cette fonction récupère le détail complet d’un match précis.
export async function getMatchDetails(
  matchId: number
): Promise<MatchDetailsResponse> {
  return fetchJson<MatchDetailsResponse>(
    `/api/matches/${matchId}`,
    "Erreur lors du chargement du détail du match."
  );
}

// Cette fonction récupère le contexte avant-match d’un match précis.
export async function getMatchContext(
  matchId: number
): Promise<MatchContextResponse> {
  return fetchJson<MatchContextResponse>(
    `/api/matches/${matchId}/context`,
    "Erreur lors du chargement du contexte du match."
  );
}

// Cette fonction récupère l’analyse explicable avant-match d’un match précis.
export async function getMatchAnalysis(
  matchId: number
): Promise<MatchAnalysisResponse> {
  return fetchJson<MatchAnalysisResponse>(
    `/api/matches/${matchId}/analysis`,
    "Erreur lors du chargement de l’analyse du match."
  );
}

// Cette fonction récupère les prédictions avant-match d’un match précis.
export async function getMatchPredictions(
  matchId: number
): Promise<MatchPredictionsResponse> {
  return fetchJson<MatchPredictionsResponse>(
    `/api/matches/${matchId}/predictions`,
    "Erreur lors du chargement des prédictions du match."
  );
}

// Cette fonction demande au backend de générer une recommandation multi-matchs selon une compétition, un nombre de matchs et un niveau de risque.
export async function getMultiMatchRecommendation(
  competitionCode: string,
  matchCount: number,
  riskLevel: "low" | "medium" | "high"
): Promise<MultiMatchRecommendationResponse> {
  return fetchJson<MultiMatchRecommendationResponse>(
    "/api/recommendations/multimatch",
    "Erreur lors de la génération de la recommandation multi-matchs.",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        competition_code: competitionCode,
        match_count: matchCount,
        risk_level: riskLevel,
      }),
    }
  );
}

// Cette fonction récupère le glossaire pédagogique de RubyBets.
export async function getGlossary(): Promise<GlossaryResponse> {
  return fetchJson<GlossaryResponse>(
    "/api/glossary",
    "Erreur lors du chargement du glossaire."
  );
}

// Cette fonction récupère les messages responsables et les limites d’utilisation de RubyBets.
export async function getResponsibleInfo(): Promise<ResponsibleInfoResponse> {
  return fetchJson<ResponsibleInfoResponse>(
    "/api/responsible-info",
    "Erreur lors du chargement des informations responsables."
  );
}

// Schéma de communication du fichier :
// api.ts
// ├── appelle le backend FastAPI RubyBets
// ├── utilise rubybets.ts pour typer les réponses reçues
// ├── alimente App.tsx avec des données sécurisées
// └── transmet les données aux composants React d’affichage