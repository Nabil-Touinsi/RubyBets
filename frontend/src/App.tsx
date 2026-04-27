// Ce fichier affiche la page principale temporaire de RubyBets et teste les données backend.

import { useEffect, useState } from "react";
import "./App.css";
import { getCompetitions, getHealth } from "./services/api";

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

function App() {
  const [apiStatus, setApiStatus] = useState<string>("Vérification en cours...");
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [competitionsStatus, setCompetitionsStatus] = useState<string>(
    "Chargement des compétitions..."
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

  return (
    <main>
      <h1>RubyBets</h1>

      <p>Application d’aide à la décision football avant-match.</p>
      <p>Frontend React connecté aux premières routes backend métier.</p>

      <p className="api-status">{apiStatus}</p>
      <p className="api-status">{competitionsStatus}</p>

      <section>
        <h2>Compétitions MVP</h2>

        {competitions.length === 0 ? (
          <p>Aucune compétition disponible pour le moment.</p>
        ) : (
          <ul>
            {competitions.map((competition) => (
              <li key={competition.id}>
                <strong>{competition.name}</strong> — {competition.country} ({competition.code})
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default App;