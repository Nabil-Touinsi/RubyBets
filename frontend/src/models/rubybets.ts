// Ce fichier centralise les modèles de données TypeScript utilisés par RubyBets côté frontend.

// Types utilisés pour structurer les données reçues depuis le backend.
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

export type Team = {
  id: number;
  name: string;
  short_name: string;
  tla?: string;
  crest: string;
};

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

export type MatchDetailsResponse = {
  source: string;
  match: Match;
  data_freshness: {
    last_updated: string;
    provider: string;
  };
};

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
  data_freshness: {
    match_last_updated: string;
    provider: string;
  };
};

export type AnalysisKeyFactor = {
  label: string;
  value: number;
  reading: string;
};

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
  data_freshness: {
    match_last_updated: string;
    provider: string;
  };
};

export type PredictionItem = {
  market: string;
  prediction: string;
  label: string;
  confidence: string;
  risk: string;
  justification: string;
};

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
  data_freshness: {
    match_last_updated: string;
    provider: string;
  };
};

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
  data_freshness: {
    provider: string;
    generated_at: string;
  };
};

export type GlossaryItem = {
  term: string;
  slug: string;
  category: string;
  definition: string;
};

export type GlossaryResponse = {
  count: number;
  filters: {
    category: string | null;
    search: string | null;
  };
  items: GlossaryItem[];
};

export type ResponsibleInfoItem = {
  type: string;
  priority: string;
  title: string;
  content: string;
  display_zone: string;
  is_active: boolean;
};

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
