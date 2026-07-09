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
  source_name: string | null;
  source_url: string | null;
  published_at: string | null;
  category: NewsCategory | string;
  category_label: string;
  relevance: "low" | "medium" | "high" | string;
  team_detected: string | null;
};

// Ce type décrit le bloc d'actualités associé à une équipe.
export type TeamNewsBlock = {
  name: string | null;
  query: string | null;
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
  home_team: TeamNewsBlock;
  away_team: TeamNewsBlock;
  empty_state: string | null;
  limits: string[];
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

// Ce type décrit les sources possibles utilisées par la route d'historique des équipes.
export type TeamHistorySourceUsed =
  | "cache"
  | "football_data"
  | "api_football"
  | "flashscore"
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
  match_id: number | null;
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
  club_name: string | null;
  club_logo: string | null;
  reason: string | null;
};

// Ce type décrit la composition disponible pour une équipe sur un match.
export type MatchLineupSide = {
  side: "home" | "away" | string;
  status: "official_available" | "predicted_available" | "unavailable" | string;
  average_rating: number | null;
  formation: string | null;
  official_formation: string | null;
  predicted_formation: string | null;
  official_available: boolean;
  predicted_available: boolean;
  starting_lineups: MatchLineupPlayer[];
  substitutes: MatchLineupPlayer[];
  predicted_lineups: MatchLineupPlayer[];
  missing_players: MatchLineupPlayer[];
  unsure_missing_players: MatchLineupPlayer[];
};

// Ce type décrit la réponse backend des compositions probables, absences et statuts de disponibilité.
export type MatchLineupsResponse = {
  source: string;
  source_used: string | null;
  status: "available" | "unavailable" | string;
  match_id: number;
  source_match_id: string | null;
  lineups: {
    composition_status: "official_available" | "predicted_available" | "unavailable" | string;
    official_available: boolean;
    predicted_available: boolean;
    squad_available: boolean;
    home: MatchLineupSide;
    away: MatchLineupSide;
    empty_state: string | null;
    limits: string[];
  };
  data_used: {
    flashscore_lineups: boolean;
    official_lineups: boolean;
    predicted_lineups: boolean;
    missing_players: boolean;
    squad: boolean;
    odds_used: boolean;
  };
  data_freshness: CacheFreshness;
  fallback_available: boolean;
};

// Ce type décrit une prédiction individuelle affichée dans RubyBets.
export type PredictionItem = {
  market: string;
  prediction: string;
  label: string;
  confidence: string;
  risk: string;
  justification: string;
};

// Ce type décrit la réponse backend des prédictions avant-match.
export type MatchPredictionsResponse = {
  source: string;
  match_id: number;
  predictions: {
    status: string;
    message?: string;
    method?: string;
    inputs?: {
      home_team_position: number | null;
      away_team_position: number | null;
      position_gap: number | null;
      points_gap: number | null;
      goal_difference_gap: number | null;
      average_goal_context: number | null;
      home_goals_for_avg: number | null;
      away_goals_for_avg: number | null;
    };
    predictions: {
      one_x_two: PredictionItem;
      goals: PredictionItem;
      btts: PredictionItem;
    } | null;
    limits?: string[];
  };
  data_used: {
    match_details: boolean;
    competition_standings: boolean;
    home_team_standing_available: boolean;
    away_team_standing_available: boolean;
  };
  data_freshness: MatchCompositeDataFreshness;
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

// Ce type décrit une sélection issue du selector_result du modèle national expérimental.
export type MultiMatchRecommendationItem = {
  match: Match;
  selected_market: string | null;
  selected_prediction: string | null;
  selected_confidence: number | null;
  risk_level: "low" | "medium" | "high" | string;
  selector_rule: string | null;
  reference_reliability: number | null;
  reference_coverage: number | null;
  reference_selected_rows: number | null;
  selector_version: string | null;
  selector_profile: string | null;
  selector_variant: string | null;
  model_family: string;
  model_variant: string;
  odds_used: boolean;
  source_match_prediction: string | null;
  consistency_checks?: MarketConsistencyChecks | null;
  responsible_note?: string | null;
};

// Ce type décrit la réponse backend de la sélection multi-matchs basée sur le modèle national.
export type MultiMatchRecommendationResponse = {
  source: string;
  scope?: string;
  status: "computed" | "empty" | string;
  method: string;
  request: {
    competition_code: string;
    match_count: number;
    risk_level: "low" | "medium" | "high";
    date_from: string | null;
    date_to: string | null;
  };
  available_matches_count: number;
  computed_matches_count?: number;
  skipped_matches_count?: number;
  selected_count: number;
  recommendations: MultiMatchRecommendationItem[];
  selection_logic: {
    description: string;
    risk_filter?: string;
    sorting?: string;
    risk_levels?: {
      low: string;
      medium: string;
      high: string;
    };
  };
  limits: string[];
  data_freshness?: RecommendationDataFreshness;
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

// Ce type décrit les métadonnées d’un match analysé par le modèle national expérimental.
export type NationalMlMatchMetadata = {
  clean_match_id: string;
  rubybets_match_id?: number | null;
  feature_id: string;
  feature_version: string;
  match_date_utc: string | null;
  season: string | null;
  competition_code: string | null;
  competition_name: string | null;
  stage: string | null;
  group_name: string | null;
  team_a_name: string | null;
  team_b_name: string | null;
  inference_mode?: string;
};

// Ce type limite les clés de marchés principales utilisées par l’écran Prédictions.
export type NationalMlMarketKey = "1x2" | "over_1_5" | "over_2_5" | "btts";

// Ce type décrit le résultat du sélecteur expérimental du modèle national.
export type NationalMlSelectorResult = {
  source: string;
  scope: string;
  status: "RECOMMEND" | "ABSTAIN" | string;
  selector_version: string;
  selector_profile: string;
  selector_variant: string;
  selected_market: string;
  selected_prediction: string | null;
  selected_confidence: number | null;
  risk_level: string;
  selector_rule: string;
  reference_reliability: number | null;
  reference_coverage: number | null;
  reference_selected_rows: number | null;
  reference_double_chance_share: number | null;
  responsible_note: string;
  excluded_outcome?: string;
};

// Ce type décrit une prédiction brute ou corrigée par marché produite par le modèle national.
export type NationalMlMarketPrediction = {
  model_name: string;
  prediction: string;
  probabilities: Record<string, number>;
  max_probability: number;
  consistency_status?: "adjusted" | "ok" | string;
  raw_prediction?: string;
  raw_max_probability?: number;
  adjusted_by_rule?: string;
  adjustment_reason?: string;
};

// Ce type décrit les features construites dynamiquement pour le match sélectionné.
export type NationalMlDynamicFeatures = Record<string, number | null>;

// Ce type décrit la réponse API du modèle national expérimental pour un match sélectionné.
export type NationalMlPredictionResponse = {
  source: string;
  scope: string;
  status: "computed" | "unavailable" | string;
  data_source_file: string;
  match: NationalMlMatchMetadata;
  dynamic_features?: NationalMlDynamicFeatures;
  market_predictions?: Partial<Record<NationalMlMarketKey, NationalMlMarketPrediction>> &
    Record<string, NationalMlMarketPrediction | undefined>;
  raw_market_predictions?: Partial<Record<NationalMlMarketKey, NationalMlMarketPrediction>> &
    Record<string, NationalMlMarketPrediction | undefined>;
  consistency_checks?: MarketConsistencyChecks | null;
  selector_result: NationalMlSelectorResult | null;
  unavailable_reason?: string;
  responsible_note: string;
  rubybets_match_id?: number | null;
  source_used_for_match?: string;
  model_family?: "national" | string;
  model_variant?: string;
  odds_used?: boolean;
  data_freshness?: {
    match_cache?: CacheFreshness | null;
    match_last_updated?: string | null;
  };
};

// Ces alias conservent la compatibilité avec l’ancien nommage V18.3.3 déjà utilisé dans certains composants.
export type V1833MatchMetadata = NationalMlMatchMetadata;
export type V1833SelectorResult = NationalMlSelectorResult;
export type V1833MarketPrediction = NationalMlMarketPrediction;
export type V1833DynamicFeatures = NationalMlDynamicFeatures;
export type V1833MatchPredictionResponse = NationalMlPredictionResponse;


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
  engine_version: string | null;
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

// Ce type décrit la réponse backend de la liste paginée des prédictions archivées.
export type ArchivedPredictionsResponse = {
  status: "available" | "unavailable" | string;
  count: number;
  limit: number;
  offset: number;
  items: ArchivedPrediction[];
  available_competitions?: string[];
  message?: string;
};

// Schéma de communication du fichier :
// rubybets.ts
// ├── utilisé par api.ts pour typer les réponses backend
// ├── utilisé par App.tsx pour stocker les données dans les states React
// ├── utilisé par les composants frontend pour afficher matchs, historiques d'équipes, compositions probables, actualités contextuelles, analyses, prédictions, recommandations et archives
// └── prépare le typage du modèle national expérimental V18.3.4 dc018 et des archives pour les écrans Prédictions, Sélection et Archives
