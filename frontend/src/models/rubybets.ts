// Ce fichier centralise les modèles de données TypeScript utilisés par RubyBets côté frontend.
// Il décrit les structures reçues depuis le backend afin de sécuriser l'affichage des données réelles.

// Ce type décrit les informations de fraîcheur d’un cache backend simple.
export type CacheFreshness = {
  source: string;
  from_cache: boolean;
  updated_at: string | null;
  ttl_minutes: number;
};

// Ce type décrit la fraîcheur d’une réponse simple venant d’une seule source.
export type SimpleDataFreshness = CacheFreshness & {
  provider?: string;
  last_updated?: string | null;
};

// Ce type décrit la fraîcheur d’une réponse composée utilisant les données du match et du classement.
export type MatchCompositeDataFreshness = {
  provider: string;
  match_last_updated: string | null;
  match_cache: CacheFreshness | null;
  standings_cache: CacheFreshness | null;
};

// Ce type décrit la fraîcheur d’une recommandation multi-matchs ou d’une sélection nationale.
export type RecommendationDataFreshness = {
  provider: string;
  generated_at: string;
  matches_cache: CacheFreshness;
  standings_cache?: CacheFreshness;
};

// Ce type décrit une compétition football suivie par RubyBets.
export type Competition = {
  id: number;
  code: string;
  name: string;
  country: string;
  type: string;
  emblem: string;
  current_season: {
    id: number;
    start_date: string;
    end_date: string;
    current_matchday: number;
  };
};

// Ce type décrit une équipe affichée dans les matchs, classements et recommandations.
// Certains champs peuvent être null lorsque l’API expose des matchs dont les affiches ne sont pas encore connues.
export type Team = {
  id: number | null;
  name: string | null;
  short_name: string | null;
  tla?: string | null;
  crest: string | null;
};

// Ce type décrit un match football formaté par le backend.
export type Match = {
  id: number;
  utc_date: string;
  status: string;
  matchday: number;
  stage?: string;
  last_updated?: string;
  competition: {
    code: string;
    name: string;
  };
  home_team: Team;
  away_team: Team;
};

// Ce type décrit la réponse backend de vérification de santé de l’API.
export type HealthResponse = {
  status: string;
};

// Ce type décrit la réponse backend de la liste des compétitions.
export type CompetitionsResponse = {
  count: number;
  competitions: Competition[];
};

// Ce type décrit la réponse backend de la liste des matchs à venir.
export type MatchesResponse = {
  count: number;
  matches: Match[];
};

// Ce type décrit le classement d’une équipe dans une compétition.
export type TeamStanding = {
  position: number;
  team: Team;
  played_games: number;
  won: number;
  draw: number;
  lost: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
};

// Ce type décrit la réponse backend du détail d’un match.
export type MatchDetailsResponse = {
  source: string;
  match: Match;
  data_freshness: SimpleDataFreshness;
};

// Ce type décrit la réponse backend du contexte avant-match.
export type MatchContextResponse = {
  source: string;
  match: Match;
  context: {
    competition: {
      code: string;
      name: string;
    };
    home_team_standing: TeamStanding | null;
    away_team_standing: TeamStanding | null;
    summary: {
      title: string;
      main_facts: string[];
      home_team_position: number | null;
      away_team_position: number | null;
    };
  };
  data_freshness: MatchCompositeDataFreshness;
};

// Ce type décrit les catégories d'actualités contextuelles affichées dans l'onglet Contexte.
export type NewsCategory =
  | "injury_absence"
  | "lineup_squad"
  | "recent_form"
  | "coach_tactics"
  | "competition_context"
  | "other";

// Ce type décrit un article d'actualité normalisé par le backend RubyBets.
export type TeamNewsArticle = {
  title: string | null;
  description: string | null;
  url: string | null;
  resolved_url?: string | null;
  image_url?: string | null;
  preview_status?: "available" | "partial" | "unavailable" | string;
  source_name: string | null;
  source_url: string | null;
  published_at: string | null;
  category: NewsCategory | string;
  category_label: string;
  relevance: "low" | "medium" | "high" | string;
  team_detected: string | null;
  teams_detected?: string[];
};

// Ce type décrit le bloc d'actualités associé à une équipe.
export type TeamNewsBlock = {
  name: string | null;
  query: string | null;
  queries?: string[];
  status: "available" | "partial" | "empty" | "unavailable" | string;
  articles_count: number;
  articles: TeamNewsArticle[];
  message: string | null;
};

// Ce type décrit la réponse backend dédiée aux actualités contextuelles d'un match.
export type MatchNewsContextResponse = {
  status: "available" | "partial" | "empty" | "unavailable" | string;
  source: string;
  source_used?: string;
  match_source?: string;
  match_id: number;
  competition: string | null;
  generated_at: string;
  articles_count?: number;
  articles?: TeamNewsArticle[];
  home_team: TeamNewsBlock;
  away_team: TeamNewsBlock;
  empty_state: string | null;
  limits: string[];
  ai_context?: unknown;
  match?: Match;
  data_used?: {
    match_details: boolean;
    rss_news: boolean;
    odds_used: boolean;
  };
  data_freshness?: {
    provider: string;
    generated_at: string;
    match_cache?: CacheFreshness | null;
  };
  fallback_available?: boolean;
};

// Ce type distingue les états visibles du chargement différé des actualités du match.
export type MatchNewsContextLoadState =
  | "idle"
  | "loading"
  | "success"
  | "error";

// Ce type décrit les deux actions que Ruby peut envoyer au chatbot d'actualités du backend.
export type NewsChatbotMode = "summary" | "question";

// Ce type décrit la demande envoyée par Ruby pour résumer les actualités ou répondre à une question.
export type NewsChatbotRequest = {
  mode: NewsChatbotMode;
  question?: string;
};

// Ce type décrit une source réellement citée dans une réponse de Ruby.
export type NewsChatbotSource = {
  article_id: string;
  title: string;
  url: string;
  source_name: string | null;
  published_at: string | null;
  content_status: string;
};

// Ce type décrit la réponse complète du chatbot d'actualités Ruby.
export type NewsChatbotResponse = {
  status: string;
  match_id: number;
  mode: NewsChatbotMode;
  answer: string;
  sources: NewsChatbotSource[];
  source_articles_count: number;
  full_content_articles_count: number;
  partial_content_articles_count: number;
  unavailable_articles_count: number;
  analyzed_articles_count: number;
  analyzed_chunks_count: number;
  insufficient_data: boolean;
  cached: boolean;
  generated_at: string;
  model: string;
  match_source: string | null;
  responsible_note: string;
  limitations: string[];
};

// Ce type décrit les sources possibles utilisées par la route d'historique des équipes.
export type TeamHistorySourceUsed =
  | "cache"
  | "football_data"
  | "api_football"
  | "flashscore"
  | "flashscore_rapidapi"
  | "mixed"
  | "unavailable";

// Ce type décrit le statut de disponibilité des données d'historique.
export type TeamHistoryDataStatus = "available" | "partial" | "unavailable";

// Ce type décrit le résultat d'une équipe sur un match récent.
export type TeamRecentMatchResult = "W" | "D" | "L";

// Ce type décrit un match récent normalisé pour l'historique d'une équipe.
export type TeamRecentMatch = {
  match_id: number | null;
  utc_date: string | null;
  competition_name: string | null;
  home_team: string | null;
  away_team: string | null;
  home_score: number | null;
  away_score: number | null;
  team_result: TeamRecentMatchResult;
  is_home: boolean;
  goals_for: number;
  goals_against: number;
  data_source: string;
};

// Ce type décrit la synthèse statistique de forme d'une équipe.
export type TeamFormSummary = {
  matches_count: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  avg_goals_for: number;
  avg_goals_against: number;
  recent_series: TeamRecentMatchResult[];
};

// Ce type décrit le bloc d'historique complet d'une équipe.
export type TeamHistoryBlock = {
  team_id: number | null;
  team_name: string | null;
  team?: Team;
  recent_matches: TeamRecentMatch[];
  recent_matches_overview: TeamRecentMatch[];
  form_summary: TeamFormSummary;
};

// Ce type décrit une confrontation directe disponible entre les deux équipes.
export type HeadToHeadMatch = {
  match_id: number | string | null;
  utc_date: string | null;
  competition_name: string | null;
  home_team: string | null;
  away_team: string | null;
  home_score: number | null;
  away_score: number | null;
  result_label: string;
  data_source: string;
};

// Ce type décrit la synthèse responsable produite par la route d'historique.
export type TeamHistorySummary = {
  home_recent_form_label?: string;
  away_recent_form_label?: string;
  comparison_note?: string;
  head_to_head_note?: string;
  responsible_note: string;
};

// Ce type décrit la fraîcheur des données utilisées pour l'historique des équipes.
export type TeamHistoryFreshness = {
  last_updated_at: string | null;
  source_label: string;
  is_cache: boolean;
  match_cache?: CacheFreshness | null;
  home_team_history_cache?: CacheFreshness | null;
  away_team_history_cache?: CacheFreshness | null;
  limitations: string[];
};

// Ce type décrit la réponse backend complète de la route /team-history.
export type TeamHistoryResponse = {
  match_id: number;
  source_used: TeamHistorySourceUsed;
  data_status: TeamHistoryDataStatus;
  home_team_history: TeamHistoryBlock;
  away_team_history: TeamHistoryBlock;
  head_to_head: HeadToHeadMatch[];
  summary: TeamHistorySummary;
  data_freshness: TeamHistoryFreshness;
};

// Ce type décrit le résumé public de la recommandation produit V19.
export type V19ProductRecommendation = {
  market_type: string;
  value: string;
  confidence_level: string | null;
  risk_level: string | null;
};

// Ce type décrit l’explication publique déterministe produite par le backend V19.
export type V19PublicExplanation = {
  contract_version: string;
  headline: string;
  summary: string;
  supporting_factors: string[];
  caution_factors: string[];
  rejected_alternatives: string[];
  data_quality_summary: string;
  confidence_explanation: string;
  abstention_explanation: string | null;
  source_freshness_summary: string;
  responsible_note: string;
};

// Ce type décrit la réponse publique stable du pipeline produit V19.
export type V19ProductPredictionResponse = {
  source: string;
  scope: string;
  match_id: number;
  request_id: string;
  status: "RECOMMEND" | "ABSTAIN";
  recommendation: V19ProductRecommendation | null;
  explanation: V19PublicExplanation;
  data_quality: {
    target_match_provider_status: string | null;
    market_provider_status: string | null;
    market_module_status: string | null;
    market_quality_flags: string[] | null;
    history_provider_status: string | null;
    history_data_status: string | null;
    history_source_used: string | null;
  };
  versions: {
    engine: string;
    experts: Record<string, string>;
    features: string[];
    product_service: string | null;
    explanation: string;
  };
  responsible_note: string;
};

// Ce type décrit les profils publics de sélectivité acceptés par la sélection V19.
export type V19SelectionProfile = "LOW" | "MEDIUM" | "HIGH";

// Ce type décrit les états publics possibles d’une sélection multi-matchs V19.
export type V19SelectionStatus = "READY" | "PARTIAL" | "EMPTY" | string;

// Ce type décrit le payload public envoyé à la route de sélection V19.
export type V19SelectionRequest = {
  match_ids: number[];
  match_count: number;
  selection_profile: V19SelectionProfile;
};

// Ce type décrit la qualité des données publiques associée à une sélection V19.
export type V19SelectionDataQuality = {
  target_match_provider_status: string | null;
  market_provider_status: string | null;
  market_module_status: string | null;
  market_quality_flags: string[] | string | null;
  history_provider_status: string | null;
  history_data_status: string | null;
  history_source_used: string | null;
};

// Ce type décrit une décision V19 retenue dans la sélection multi-matchs publique.
export type V19SelectionItem = {
  match_id: number;
  status: "RECOMMEND" | string;
  recommendation: {
    market_type: string;
    value: string;
  };
  explanation: V19PublicExplanation;
  data_quality: V19SelectionDataQuality;
  versions: {
    engine: string;
    experts: Record<string, string>;
    features: string[];
    product_service: string | null;
    explanation: string;
  };
};

// Ce type décrit un match évalué mais exclu de la sélection publique V19.
export type V19ExcludedSelectionMatch = {
  match_id: number;
  status: "ABSTAIN" | "PROFILE_FILTERED" | "PIPELINE_ERROR" | string;
  summary: string;
};

// Ce type décrit la réponse publique stable de la sélection multi-matchs V19.
export type V19SelectionResponse = {
  source: string;
  scope: string;
  contract_version: string;
  request_id: string;
  status: V19SelectionStatus;
  profile: {
    value: V19SelectionProfile;
    label: string;
    description: string;
  };
  requested_count: number;
  candidate_count: number;
  evaluated_count: number;
  selected_count: number;
  abstain_count: number;
  profile_filtered_count: number;
  error_count: number;
  selections: V19SelectionItem[];
  excluded_matches: V19ExcludedSelectionMatch[];
  selection_explanation: {
    headline: string;
    summary: string;
  };
  versions: {
    selection_service: string;
    selection_contract: string;
    explanation: string;
  };
  responsible_note: string;
};

// Ce type décrit un facteur clé affiché dans l’analyse pré-match.
export type AnalysisKeyFactor = {
  label: string;
  value: number;
  reading: string;
};

// Ce type décrit la réponse backend de l’analyse pré-match.
export type MatchAnalysisResponse = {
  source: string;
  match_id: number;
  analysis: {
    title: string;
    context_trend: string;
    observed_facts: string[];
    key_factors: AnalysisKeyFactor[];
    interpretation: string[];
    limits: string[];
  };
  data_used: {
    match_details: boolean;
    competition_standings: boolean;
    home_team_standing_available: boolean;
    away_team_standing_available: boolean;
  };
  data_freshness: MatchCompositeDataFreshness;
};

// Ce type décrit un joueur de composition ou d'absence fourni par la route /lineups.
export type MatchLineupPlayer = {
  name: string | null;
  field_name: string | null;
  number: string | null;
  player_id: string | null;
  player_url: string | null;
  image_path: string | null;
  country_name: string | null;
  country_logo: string | null;
  club_name: string | null;
  club_logo: string | null;
  reason: string | null;
};

// Ce type décrit le match terminé utilisé comme repère pour une composition historique.
export type MatchLineupReferenceMatch = {
  match_id: number | string;
  source_match_id: string | null;
  utc_date: string | null;
  competition_name: string | null;
  home_team: string | null;
  away_team: string | null;
  home_score: number | null;
  away_score: number | null;
  data_source: string | null;
};

// Ce type décrit la composition disponible pour une équipe sur un match.
export type MatchLineupSide = {
  side: "home" | "away" | string;
  status:
    | "official_available"
    | "predicted_available"
    | "historical_official_available"
    | "unavailable"
    | string;
  composition_origin: "current_official" | "current_predicted" | "historical_official" | string | null;
  average_rating: number | null;
  formation: string | null;
  official_formation: string | null;
  predicted_formation: string | null;
  official_available: boolean;
  predicted_available: boolean;
  historical_official_available: boolean;
  starting_lineups: MatchLineupPlayer[];
  substitutes: MatchLineupPlayer[];
  predicted_lineups: MatchLineupPlayer[];
  missing_players: MatchLineupPlayer[];
  unsure_missing_players: MatchLineupPlayer[];
  reference_match?: MatchLineupReferenceMatch | null;
};

// Ce type décrit les informations de secours utilisées lorsque la composition actuelle n'est pas publiée.
export type MatchLineupFallback = {
  strategy: string;
  status: "complete" | "partial" | "unavailable" | string;
  matches_checked_per_team: number;
  home_reference_match: MatchLineupReferenceMatch | null;
  away_reference_match: MatchLineupReferenceMatch | null;
};

// Ce type décrit la réponse backend des compositions, repères historiques et statuts de disponibilité.
export type MatchLineupsResponse = {
  source: string;
  source_used: string | null;
  status: "available" | "partial" | "unavailable" | string;
  match_id: number;
  source_match_id: string | null;
  lineups: {
    composition_status:
      | "official_available"
      | "predicted_available"
      | "historical_official_fallback_available"
      | "historical_official_fallback_partial"
      | "unavailable"
      | string;
    composition_origin: "current_official" | "current_predicted" | "historical_official" | string | null;
    official_available: boolean;
    predicted_available: boolean;
    historical_fallback_available: boolean;
    historical_fallback_complete: boolean;
    squad_available: boolean;
    home: MatchLineupSide;
    away: MatchLineupSide;
    empty_state: string | null;
    fallback_label?: string | null;
    limits: string[];
  };
  data_used: {
    flashscore_lineups: boolean;
    official_lineups: boolean;
    predicted_lineups: boolean;
    historical_official_lineups: boolean;
    missing_players: boolean;
    squad: boolean;
    odds_used: boolean;
  };
  data_freshness: CacheFreshness | Record<string, unknown>;
  fallback_available: boolean;
  fallback_checked?: boolean;
  fallback?: MatchLineupFallback | null;
};

// Ce type décrit une correction de cohérence appliquée entre deux marchés prédictifs.
export type MarketConsistencyAdjustment = {
  code: string;
  severity: string;
  reference_market: string;
  adjusted_market: string;
  raw_prediction: string;
  adjusted_prediction: string;
  reference_prediction: string;
  raw_max_probability: number | null;
  adjusted_probability: number | null;
  message: string;
};

// Ce type décrit le diagnostic de cohérence inter-marchés renvoyé par le backend expérimental.
export type MarketConsistencyChecks = {
  source: string;
  scope: string;
  status: "ok" | "adjusted" | string;
  rules_version: string;
  adjustments_count: number;
  adjustments: MarketConsistencyAdjustment[];
};

// Ce type décrit un élément du glossaire pédagogique.
export type GlossaryItem = {
  term: string;
  slug: string;
  category: string;
  definition: string;
};

// Ce type décrit la réponse backend du glossaire.
export type GlossaryResponse = {
  count: number;
  filters: {
    category: string | null;
    search: string | null;
  };
  items: GlossaryItem[];
};

// Ce type décrit un message responsable affiché dans RubyBets.
export type ResponsibleInfoItem = {
  type: string;
  priority: string;
  title: string;
  content: string;
  display_zone: string;
  is_active: boolean;
};

// Ce type décrit la réponse backend des informations responsables.
export type ResponsibleInfoResponse = {
  count: number;
  items: ResponsibleInfoItem[];
  summary: {
    product_positioning: string;
    real_betting_enabled: boolean;
    live_analysis_enabled: boolean;
    uses_real_data: boolean;
    guarantees_result: boolean;
  };
};

// Ce type décrit les verdicts possibles d’une prédiction archivée.
export type ArchivedPredictionVerdict =
  | "correct"
  | "incorrect"
  | "pending"
  | "not_verifiable"
  | string;

// Ce type décrit une prédiction historisée dans la table archived_predictions.
export type ArchivedPrediction = {
  id: number;
  rubybets_match_id: string | number | null;
  source_match_id: string | null;
  competition_name: string | null;
  home_team_name: string | null;
  away_team_name: string | null;
  home_team_logo_url: string | null;
  away_team_logo_url: string | null;
  home_team_country_code: string | null;
  away_team_country_code: string | null;
  match_date: string | null;
  prediction_date: string | null;
  market_type: string | null;
  predicted_value: string | null;
  confidence_level: string | null;
  risk_level: string | null;
  justification: string | null;
  final_home_score: number | null;
  final_away_score: number | null;
  match_status: string | null;
  verdict: ArchivedPredictionVerdict;
  checked_at: string | null;
};

// Ce type décrit les filtres envoyés à l’API Archives.
export type ArchivedPredictionsQuery = {
  market_type?: string;
  verdict?: string;
  match_status?: string;
  competition_name?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

// Ce type décrit les indicateurs globaux calculés sur toutes les archives filtrées.
export type ArchivedPredictionsSummary = {
  total: number;
  evaluated: number;
  successful: number;
  unsuccessful: number;
  pending: number;
  not_verifiable: number;
  success_rate: number | null;
};

// Ce type décrit la réponse backend de la liste paginée des prédictions archivées.
export type ArchivedPredictionsResponse = {
  status: "available" | "unavailable" | string;
  count: number;
  limit: number;
  offset: number;
  items: ArchivedPrediction[];
  summary?: ArchivedPredictionsSummary;
  available_competitions?: string[];
  message?: string;
};

// Ce type décrit le résultat public d’une actualisation des archives en attente.
export type ArchivesReconciliationResponse = {
  status: "updated" | "unavailable" | string;
  checked_count: number;
  updated_count: number;
  resolved_count: number;
  pending_count: number;
  error_count: number;
  message?: string;
};

// Ce type décrit une métrique avancée agrégée uniquement sur les matchs où la donnée existe réellement.
export type MatchAdvancedStatsMetric = {
  value: number;
  unit: string;
  matches_used: number;
  matches_requested: number;
  coverage: number;
  aggregation?: string;
  successful?: number;
  attempted?: number;
  numerator_total?: number;
  denominator_total?: number;
  formula?: string;
};

// Ce type décrit les statistiques avancées agrégées pour une équipe du match futur.
export type MatchAdvancedStatsTeam = {
  team_id: string | number | null;
  team_name: string;
  matches_requested: number;
  matches_found: number;
  matches_with_stats: number;
  metrics: Record<string, MatchAdvancedStatsMetric>;
};

// Ce type décrit une limite de qualité remontée sans masquer les données encore exploitables.
export type MatchAdvancedStatsLimitation = {
  code: string;
  message: string;
  team?: "home" | "away" | string;
  match_id?: string;
  status?: string;
  metrics?: string[];
  [key: string]: unknown;
};

// Ce type décrit la réponse publique de la route /advanced-stats utilisée par l'onglet Analyse détaillée.
export type MatchAdvancedStatsResponse = {
  match_id: number;
  status: "available" | "partial" | "unavailable" | string;
  sample_size_requested: number;
  home_team: MatchAdvancedStatsTeam;
  away_team: MatchAdvancedStatsTeam;
  data_quality: {
    status: "available" | "partial" | "unavailable" | string;
    limitations: MatchAdvancedStatsLimitation[];
    metric_coverage: {
      home_team: Record<string, {
        matches_used: number;
        matches_requested: number;
        coverage: number;
      }>;
      away_team: Record<string, {
        matches_used: number;
        matches_requested: number;
        coverage: number;
      }>;
    };
  };
  data_freshness: {
    source: string;
    generated_at: string;
    match_stats_cache_ttl_minutes: number;
    match_stats_requests: number;
    match_stats_from_cache: number;
    updated_at_values: string[];
  };
};

// Schéma de communication du fichier :
// rubybets.ts
// ├── utilisé par api.ts pour typer les réponses backend
// ├── utilisé par App.tsx pour stocker les données dans les states React
// ├── utilisé par les composants frontend pour afficher matchs, historiques d'équipes, compositions probables, statistiques avancées, actualités contextuelles, Ruby, analyses, prédictions, recommandations et archives
// └── prépare aussi les contrats publics V19 de prédiction individuelle et de sélection multi-matchs, sans exposer les données internes
