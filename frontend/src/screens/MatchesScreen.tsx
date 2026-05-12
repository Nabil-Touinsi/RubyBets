// Ce fichier affiche l’écran Matchs de RubyBets avec une structure dédiée proche de la maquette MVP.

import type { Competition, Match } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import CompetitionsSection from "../components/CompetitionsSection";
import MatchesSection from "../components/MatchesSection";

type MatchesScreenProps = {
  competitions: Competition[];
  matches: Match[];
  selectedCompetition: string;
  matchesStatus: string;
  onSelectCompetition: (competitionCode: string) => void;
  onSelectMatch: (matchId: number) => void;
  onNavigate: (screen: AppScreen) => void;
};

// Ce composant structure l’écran Matchs avec une zone de filtres, une liste principale et une colonne d’aide.
function MatchesScreen({
  competitions,
  matches,
  selectedCompetition,
  matchesStatus,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: MatchesScreenProps) {
  return (
    <div className="rb-matches-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Matchs à venir</p>
          <h2>Explorer les rencontres disponibles</h2>
          <p>
            Sélectionnez une compétition, parcourez les matchs disponibles et
            ouvrez une rencontre pour accéder au détail, à l’analyse et aux
            prédictions avant-match.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Compétition active</p>
          <h3>{selectedCompetition}</h3>
          <p>{matchesStatus}</p>
        </aside>
      </section>

      <section className="rb-matches-filters">
        <div className="rb-matches-filters__header">
          <div>
            <p className="rb-eyebrow">Filtres</p>
            <h3>Ligues principales</h3>
          </div>

          <button type="button" onClick={() => onNavigate("recommendation")}>
            Recommandation multi-matchs
          </button>
        </div>

        <CompetitionsSection
          competitions={competitions}
          onSelectCompetition={onSelectCompetition}
        />
      </section>

      <section className="rb-matches-layout">
        <div className="rb-matches-main">
          <MatchesSection
            selectedCompetition={selectedCompetition}
            matches={matches}
            onSelectMatch={onSelectMatch}
          />
        </div>

        <aside className="rb-matches-aside">
          <article>
            <p className="rb-eyebrow">Aperçu</p>
            <h3>{matches.length} matchs chargés</h3>
            <p>
              La sélection d’un match ouvre automatiquement la fiche détail,
              puis permet d’accéder à l’analyse et aux prédictions.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Parcours</p>
            <h3>Lecture avant-match</h3>
            <ol>
              <li>Sélection du match</li>
              <li>Consultation du détail</li>
              <li>Analyse pré-match</li>
              <li>Prédictions explicables</li>
            </ol>
          </article>

          <article>
            <p className="rb-eyebrow">Cadre responsable</p>
            <h3>Aucune promesse</h3>
            <p>
              RubyBets affiche des recommandations analytiques, sans pari réel
              et sans garantie de résultat sportif.
            </p>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default MatchesScreen;

// Schéma de communication du fichier :
// MatchesScreen.tsx
// ├── reçoit les compétitions et matchs depuis App.tsx
// ├── utilise CompetitionsSection.tsx pour les filtres de ligues
// ├── utilise MatchesSection.tsx pour la liste des rencontres
// └── renvoie la sélection d’un match vers App.tsx via onSelectMatch
