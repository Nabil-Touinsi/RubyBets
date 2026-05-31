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

// Ce type décrit la fraîcheur d’une recommandation multi-matchs.
export type RecommendationDataFreshness = {
  provider: string;
  generated_at: string;
  matches_cache: CacheFreshness;
  standings_cache: CacheFreshness;
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

// Ce type décrit une recommandation sélectionnée dans la réponse multi-matchs.
export type MultiMatchRecommendationItem = {
  match: Match;
  selected_prediction: PredictionItem;
  selection_score: number;
  prediction_key: string;
  method: string;
  data_used: {
    match_details: boolean;
    competition_standings: boolean;
    home_team_standing_available: boolean;
    away_team_standing_available: boolean;
  };
};

// Ce type décrit la réponse backend du générateur de recommandation multi-matchs.
export type MultiMatchRecommendationResponse = {
  source: string;
  method: string;
  request: {
    competition_code: string;
    match_count: number;
    risk_level: "low" | "medium" | "high";
    date_from: string | null;
    date_to: string | null;
  };
  available_matches_count: number;
  selected_count: number;
  recommendations: MultiMatchRecommendationItem[];
  selection_logic: {
    description: string;
    risk_levels: {
      low: string;
      medium: string;
      high: string;
    };
  };
  limits: string[];
  data_freshness: RecommendationDataFreshness;
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

// Ce type décrit les métadonnées d’un match réel issu du CSV V18.3 global.
export type V1833MatchMetadata = {
  clean_match_id: string;
  feature_id: string;
  feature_version: string;
  match_date_utc: string;
  season: string;
  competition_code: string;
  competition_name: string;
  stage: string | null;
  group_name: string | null;
  team_a_name: string;
  team_b_name: string;
};

// Ce type décrit le résultat du sélecteur expérimental V18.3.3.
export type V1833SelectorResult = {
  source: string;
  scope: string;
  status: "RECOMMEND" | "ABSTAIN";
  selector_version: string;
  selector_profile: string;
  selector_variant: string;
  selected_market: string;
  selected_prediction: string | null;
  selected_confidence: number | null;
  risk_level: string;
  selector_rule: string;
  reference_reliability: number;
  reference_coverage: number;
  reference_selected_rows: number;
  reference_double_chance_share: number;
  responsible_note: string;
  excluded_outcome?: string;
};

// Ce type décrit la réponse API expérimentale V18.3.3 pour un match réel.
export type V1833MatchPredictionResponse = {
  source: string;
  scope: string;
  status: "computed";
  data_source_file: string;
  match: V1833MatchMetadata;
  selector_result: V1833SelectorResult;
  responsible_note: string;
};

// Schéma de communication du fichier :
// rubybets.ts
// ├── utilisé par api.ts pour typer les réponses backend
// ├── utilisé par App.tsx pour stocker les données dans les states React
// ├── utilisé par les composants frontend pour afficher matchs, analyses, prédictions et recommandations
// └── prépare le typage du Lab ML V18.3.3 expérimental sans toucher aux prédictions officielles