// Ce fichier centralise les appels API entre le frontend React et le backend RubyBets.
// Il sécurise les échanges front/back avec des réponses TypeScript typées.

import type {
  ArchivedPredictionsQuery,
  ArchivedPredictionsResponse,
  CompetitionsResponse,
  GlossaryResponse,
  HealthResponse,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchLineupsResponse,
  MatchNewsContextResponse,
  NewsChatbotRequest,
  NewsChatbotResponse,
  MatchPredictionsResponse,
  MatchesResponse,
  NationalMlPredictionResponse,
  MultiMatchRecommendationResponse,
  ResponsibleInfoResponse,
  TeamHistoryResponse,
  V1833MatchPredictionResponse,
  V19H2HEntityType,
  V19H2HResponse,
  V19ProductPredictionResponse,
  V19SelectionProfile,
  V19SelectionRequest,
  V19SelectionResponse,
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

// Cette fonction récupère les actualités publiques récentes liées aux deux équipes d'un match.
export async function getMatchNewsContext(
  matchId: number
): Promise<MatchNewsContextResponse> {
  return fetchJson<MatchNewsContextResponse>(
    `/api/matches/${matchId}/news-context`,
    "Erreur lors du chargement des actualités contextuelles du match."
  );
}

// Cette classe conserve le statut HTTP d'une erreur Ruby afin d'afficher un message adapté dans l'interface.
export class RubyNewsChatApiError extends Error {
  status: number;
  code: string | null;

  // Ce constructeur prépare une erreur lisible sans exposer les détails techniques du fournisseur.
  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "RubyNewsChatApiError";
    this.status = status;
    this.code = code;
  }
}

// Cette fonction extrait le message public renvoyé par FastAPI dans les réponses d'erreur de Ruby.
function getRubyApiErrorDetails(payload: unknown): {
  message: string | null;
  code: string | null;
} {
  if (!payload || typeof payload !== "object") {
    return { message: null, code: null };
  }

  const detail = "detail" in payload ? payload.detail : null;

  if (typeof detail === "string") {
    return { message: detail, code: null };
  }

  if (!detail || typeof detail !== "object") {
    return { message: null, code: null };
  }

  const message =
    "message" in detail && typeof detail.message === "string"
      ? detail.message
      : null;
  const code =
    "code" in detail && typeof detail.code === "string" ? detail.code : null;

  return { message, code };
}

// Cette fonction demande à Ruby de résumer les actualités d'un match ou de répondre à une question.
export async function askRubyAboutMatchNews(
  matchId: number,
  request: NewsChatbotRequest,
  signal?: AbortSignal
): Promise<NewsChatbotResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/matches/${matchId}/news-chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal,
    }
  );

  const payload = (await response.json().catch(() => null)) as unknown;

  if (!response.ok) {
    const details = getRubyApiErrorDetails(payload);
    throw new RubyNewsChatApiError(
      details.message || "Ruby n'a pas pu terminer la demande.",
      response.status,
      details.code
    );
  }

  return payload as NewsChatbotResponse;
}

// Cette fonction récupère l'historique récent des deux équipes pour alimenter la fiche détail match.
export async function getMatchTeamHistory(
  matchId: number
): Promise<TeamHistoryResponse> {
  return fetchJson<TeamHistoryResponse>(
    `/api/matches/${matchId}/team-history`,
    "Erreur lors du chargement de l'historique des équipes."
  );
}


// Cette fonction détermine le profil H2H V19 selon la compétition actuellement sélectionnée.
function getV19H2HEntityType(competitionCode: string): V19H2HEntityType {
  return competitionCode === "WC" ? "NATIONAL_TEAM" : "CLUB";
}

// Cette fonction récupère l'analyse expérimentale H2H V19 d'un match RubyBets réel.
export async function getV19H2HAnalysis(
  matchId: number,
  competitionCode: string
): Promise<V19H2HResponse> {
  const entityType = getV19H2HEntityType(competitionCode);

  return fetchJson<V19H2HResponse>(
    `/api/experimental/ml-v19/h2h/rubybets-matches/${matchId}?entity_type=${entityType}`,
    "Erreur lors du chargement de l'analyse H2H V19."
  );
}

// Cette fonction récupère la décision produit V19 d'un match RubyBets réel.
export async function getV19ProductPrediction(
  matchId: number
): Promise<V19ProductPredictionResponse> {
  return fetchJson<V19ProductPredictionResponse>(
    `/api/experimental/ml-v19/rubybets-matches/${matchId}`,
    "Erreur lors du chargement de la décision produit V19."
  );
}

// Cette fonction demande au backend de composer une sélection multi-matchs V19 à partir des matchs déjà chargés.
export async function getV19MultiMatchSelection(
  matchIds: number[],
  matchCount: number,
  selectionProfile: V19SelectionProfile
): Promise<V19SelectionResponse> {
  const payload: V19SelectionRequest = {
    match_ids: matchIds,
    match_count: matchCount,
    selection_profile: selectionProfile,
  };

  return fetchJson<V19SelectionResponse>(
    "/api/experimental/ml-v19/selection",
    "Erreur lors de la génération de la sélection multi-matchs V19.",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
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


// Cette fonction récupère les compositions probables, officielles et absences disponibles pour un match précis.
export async function getMatchLineups(
  matchId: number
): Promise<MatchLineupsResponse> {
  return fetchJson<MatchLineupsResponse>(
    `/api/matches/${matchId}/lineups`,
    "Erreur lors du chargement des compositions du match."
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

// Cette fonction récupère une prédiction expérimentale V18.3.3 à partir d’un clean_match_id réel du CSV 348.
export async function getV1833PredictionByMatchId(
  cleanMatchId: string
): Promise<V1833MatchPredictionResponse> {
  return fetchJson<V1833MatchPredictionResponse>(
    `/api/experimental/ml-national/v18-3-3/matches/${cleanMatchId}`,
    "Erreur lors du chargement du résultat expérimental V18.3.3."
  );
}

// Cette fonction demande au backend de calculer le modèle national expérimental pour le match RubyBets sélectionné.
export async function getNationalDynamicPredictionByRubyBetsMatchId(
  matchId: number
): Promise<NationalMlPredictionResponse> {
  return fetchJson<NationalMlPredictionResponse>(
    `/api/experimental/ml-national/v18-3-3/rubybets-matches/${matchId}`,
    "Erreur lors du calcul dynamique du modèle national expérimental."
  );
}

// Cette fonction conserve l’ancien nom d’appel V18.3.3 pour éviter de casser les imports existants pendant la migration.
export async function getV1833DynamicPredictionByRubyBetsMatchId(
  matchId: number
): Promise<V1833MatchPredictionResponse> {
  return getNationalDynamicPredictionByRubyBetsMatchId(matchId);
}

// Cette fonction demande au backend de générer une sélection ML nationale à partir des mêmes prédictions que l’écran Prédictions.
export async function getNationalMlMultiMatchSelection(
  competitionCode: string,
  matchCount: number,
  riskLevel: "low" | "medium" | "high"
): Promise<MultiMatchRecommendationResponse> {
  return fetchJson<MultiMatchRecommendationResponse>(
    "/api/experimental/ml-national/v18-3-3/selection",
    "Erreur lors de la génération de la sélection ML nationale.",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        competition_code: competitionCode,
        match_count: matchCount,
        risk_level: riskLevel,
        date_from: null,
        date_to: null,
      }),
    }
  );
}

// Cette fonction conserve l’ancien nom utilisé par App.tsx pendant la migration de l’écran Sélection.
export async function getMultiMatchRecommendation(
  competitionCode: string,
  matchCount: number,
  riskLevel: "low" | "medium" | "high"
): Promise<MultiMatchRecommendationResponse> {
  return getNationalMlMultiMatchSelection(
    competitionCode,
    matchCount,
    riskLevel
  );
}


// Cette fonction récupère les prédictions archivées avec filtres et pagination.
export async function getArchivedPredictions(
  filters: ArchivedPredictionsQuery = {}
): Promise<ArchivedPredictionsResponse> {
  const params = new URLSearchParams();

  if (filters.market_type) {
    params.set("market_type", filters.market_type);
  }

  if (filters.verdict) {
    params.set("verdict", filters.verdict);
  }

  if (filters.match_status) {
    params.set("match_status", filters.match_status);
  }

  if (filters.competition_name) {
    params.set("competition_name", filters.competition_name);
  }

  if (filters.search) {
    params.set("search", filters.search);
  }

  if (filters.limit !== undefined) {
    params.set("limit", String(filters.limit));
  }

  if (filters.offset !== undefined) {
    params.set("offset", String(filters.offset));
  }

  const queryString = params.toString();
  const endpoint = `/api/archives/predictions${queryString ? `?${queryString}` : ""}`;

  return fetchJson<ArchivedPredictionsResponse>(
    endpoint,
    "Erreur lors du chargement des archives de prédictions."
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
// ├── transmet les données aux composants React d’affichage, dont l’historique des équipes, les compositions, les actualités contextuelles et les archives
// └── expose les décisions produit V19 individuelles et multi-matchs sans transmettre de score brut, odds ou payload fournisseur