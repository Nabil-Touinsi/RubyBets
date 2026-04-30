// Ce fichier affiche la page principale temporaire de RubyBets avec compétitions, matchs, détails et contexte réel.

import { useEffect, useState } from "react";
import "./App.css";
import {
  getCompetitions,
  getHealth,
  getMatchContext,
  getMatchDetails,
  getMatches,
} from "./services/api";

type Competition = {
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

type Team = {
  id: number;
  name: string;
  short_name: string;
  tla?: string;
  crest: string;
};

type Match = {
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

type TeamStanding = {
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

type MatchDetailsResponse = {
  source: string;
  match: Match;
  data_freshness: {
    last_updated: string;
    provider: string;
  };
};

type MatchContextResponse = {
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

function App() {
  const [apiStatus, setApiStatus] = useState<string>("Vérification en cours...");
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [selectedCompetition, setSelectedCompetition] = useState<string>("PL");

  const [selectedMatchDetails, setSelectedMatchDetails] =
    useState<MatchDetailsResponse | null>(null);

  const [selectedMatchContext, setSelectedMatchContext] =
    useState<MatchContextResponse | null>(null);

  const [competitionsStatus, setCompetitionsStatus] = useState<string>(
    "Chargement des compétitions..."
  );
  const [matchesStatus, setMatchesStatus] = useState<string>(
    "Chargement des matchs..."
  );
  const [matchDetailsStatus, setMatchDetailsStatus] = useState<string>(
    "Aucun match sélectionné"
  );
  const [matchContextStatus, setMatchContextStatus] = useState<string>(
    "Aucun contexte chargé"
  );

  useEffect(() => {
    getHealth()
      .then((data) => {
        setApiStatus(data.status === "ok" ? "Backend connecté" : "Réponse inattendue");
      })
      .catch(() => {
        setApiStatus("Backend inaccessible");
      });

    getCompetitions()
      .then((data) => {
        setCompetitions(data.competitions || []);
        setCompetitionsStatus("Compétitions chargées");
      })
      .catch(() => {
        setCompetitionsStatus("Impossible de charger les compétitions");
      });
  }, []);

  useEffect(() => {
    setMatchesStatus("Chargement des matchs...");
    setSelectedMatchDetails(null);
    setSelectedMatchContext(null);
    setMatchDetailsStatus("Aucun match sélectionné");
    setMatchContextStatus("Aucun contexte chargé");

    getMatches(selectedCompetition)
      .then((data) => {
        setMatches(data.matches || []);
        setMatchesStatus("Matchs chargés");
      })
      .catch(() => {
        setMatches([]);
        setMatchesStatus("Impossible de charger les matchs");
      });
  }, [selectedCompetition]);

  function handleSelectMatch(matchId: number) {
    setMatchDetailsStatus("Chargement du détail du match...");
    setMatchContextStatus("Chargement du contexte avant-match...");

    Promise.all([getMatchDetails(matchId), getMatchContext(matchId)])
      .then(([detailsData, contextData]) => {
        setSelectedMatchDetails(detailsData);
        setSelectedMatchContext(contextData);
        setMatchDetailsStatus("Détail du match chargé");
        setMatchContextStatus("Contexte avant-match chargé");
      })
      .catch(() => {
        setSelectedMatchDetails(null);
        setSelectedMatchContext(null);
        setMatchDetailsStatus("Impossible de charger le détail du match");
        setMatchContextStatus("Impossible de charger le contexte avant-match");
      });
  }

  return (
    <main>
      <h1>RubyBets</h1>

      <p>Application d’aide à la décision football avant-match.</p>
      <p>Frontend React connecté aux routes backend métier.</p>

      <p className="api-status">{apiStatus}</p>
      <p className="api-status">{competitionsStatus}</p>
      <p className="api-status">{matchesStatus}</p>
      <p className="api-status">{matchDetailsStatus}</p>
      <p className="api-status">{matchContextStatus}</p>

      <section>
        <h2>Compétitions MVP</h2>

        {competitions.length === 0 ? (
          <p>Aucune compétition disponible pour le moment.</p>
        ) : (
          <div>
            {competitions.map((competition) => (
              <button
                key={competition.id}
                type="button"
                onClick={() => setSelectedCompetition(competition.code)}
              >
                {competition.name} ({competition.code})
              </button>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Matchs à venir — {selectedCompetition}</h2>

        {matches.length === 0 ? (
          <p>Aucun match disponible pour cette compétition.</p>
        ) : (
          <ul>
            {matches.map((match) => (
              <li key={match.id}>
                <button type="button" onClick={() => handleSelectMatch(match.id)}>
                  <strong>{match.home_team.name}</strong> vs{" "}
                  <strong>{match.away_team.name}</strong>
                </button>
                <br />
                <span>
                  {match.competition.name} — Journée {match.matchday} —{" "}
                  {new Date(match.utc_date).toLocaleString("fr-FR")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedMatchDetails && (
        <section>
          <h2>Fiche détail match</h2>

          <h3>
            {selectedMatchDetails.match.home_team.name} vs{" "}
            {selectedMatchDetails.match.away_team.name}
          </h3>

          <p>
            Compétition : {selectedMatchDetails.match.competition.name} (
            {selectedMatchDetails.match.competition.code})
          </p>

          <p>
            Date :{" "}
            {new Date(selectedMatchDetails.match.utc_date).toLocaleString("fr-FR")}
          </p>

          <p>Statut : {selectedMatchDetails.match.status}</p>
          <p>Journée : {selectedMatchDetails.match.matchday}</p>
          <p>Source : {selectedMatchDetails.source}</p>
          <p>
            Dernière mise à jour :{" "}
            {selectedMatchDetails.data_freshness.last_updated}
          </p>
        </section>
      )}

      {selectedMatchContext && (
        <section>
          <h2>Contexte avant-match</h2>

          <h3>{selectedMatchContext.context.summary.title}</h3>

          <ul>
            {selectedMatchContext.context.summary.main_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>

          <h4>Classement des équipes</h4>

          <div>
            {selectedMatchContext.context.home_team_standing && (
              <article>
                <h5>{selectedMatchContext.context.home_team_standing.team.name}</h5>
                <p>
                  Position :{" "}
                  {selectedMatchContext.context.home_team_standing.position}
                </p>
                <p>
                  Points : {selectedMatchContext.context.home_team_standing.points}
                </p>
                <p>
                  Matchs joués :{" "}
                  {selectedMatchContext.context.home_team_standing.played_games}
                </p>
                <p>
                  Buts pour / contre :{" "}
                  {selectedMatchContext.context.home_team_standing.goals_for} /{" "}
                  {selectedMatchContext.context.home_team_standing.goals_against}
                </p>
                <p>
                  Différence de buts :{" "}
                  {selectedMatchContext.context.home_team_standing.goal_difference}
                </p>
              </article>
            )}

            {selectedMatchContext.context.away_team_standing && (
              <article>
                <h5>{selectedMatchContext.context.away_team_standing.team.name}</h5>
                <p>
                  Position :{" "}
                  {selectedMatchContext.context.away_team_standing.position}
                </p>
                <p>
                  Points : {selectedMatchContext.context.away_team_standing.points}
                </p>
                <p>
                  Matchs joués :{" "}
                  {selectedMatchContext.context.away_team_standing.played_games}
                </p>
                <p>
                  Buts pour / contre :{" "}
                  {selectedMatchContext.context.away_team_standing.goals_for} /{" "}
                  {selectedMatchContext.context.away_team_standing.goals_against}
                </p>
                <p>
                  Différence de buts :{" "}
                  {selectedMatchContext.context.away_team_standing.goal_difference}
                </p>
              </article>
            )}
          </div>
        </section>
      )}
    </main>
  );
}

export default App;