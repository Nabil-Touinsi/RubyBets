// Ce fichier affiche la page principale temporaire de RubyBets avec les compétitions et matchs réels.

import { useEffect, useState } from "react";
import "./App.css";
import { getCompetitions, getHealth, getMatches } from "./services/api";

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

type Match = {
  id: number;
  utc_date: string;
  status: string;
  matchday: number;
  competition: {
    code: string;
    name: string;
  };
  home_team: {
    name: string;
    short_name: string;
    crest: string;
  };
  away_team: {
    name: string;
    short_name: string;
    crest: string;
  };
};

function App() {
  const [apiStatus, setApiStatus] = useState<string>("Vérification en cours...");
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [selectedCompetition, setSelectedCompetition] = useState<string>("PL");

  const [competitionsStatus, setCompetitionsStatus] = useState<string>(
    "Chargement des compétitions..."
  );
  const [matchesStatus, setMatchesStatus] = useState<string>(
    "Chargement des matchs..."
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

  return (
    <main>
      <h1>RubyBets</h1>

      <p>Application d’aide à la décision football avant-match.</p>
      <p>Frontend React connecté aux routes backend métier.</p>

      <p className="api-status">{apiStatus}</p>
      <p className="api-status">{competitionsStatus}</p>
      <p className="api-status">{matchesStatus}</p>

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
                <strong>{match.home_team.name}</strong> vs{" "}
                <strong>{match.away_team.name}</strong>
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
    </main>
  );
}

export default App;