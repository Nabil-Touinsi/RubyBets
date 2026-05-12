// Ce fichier affiche l’écran Accueil / Dashboard de RubyBets en s’appuyant sur les composants existants.

import type { Competition, Match } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import CompetitionsSection from "../components/CompetitionsSection";
import MatchesSection from "../components/MatchesSection";

type DashboardScreenProps = {
  apiStatus: string;
  competitions: Competition[];
  matches: Match[];
  selectedCompetition: string;
  onSelectCompetition: (competitionCode: string) => void;
  onSelectMatch: (matchId: number) => void;
  onNavigate: (screen: AppScreen) => void;
};

// Ce composant structure l’écran d’accueil selon la logique de la maquette : hero, indicateurs, ligues et matchs à venir.
function DashboardScreen({
  apiStatus,
  competitions,
  matches,
  selectedCompetition,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: DashboardScreenProps) {
  const featuredMatches = matches.slice(0, 4);

  return (
    <div className="rb-dashboard-screen">
      <section className="rb-dashboard-hero">
        <div className="rb-dashboard-hero__content">
          <p className="rb-eyebrow">Dashboard</p>
          <h2>Analyse football avant-match, sans pari réel.</h2>
          <p>
            RubyBets centralise les compétitions, les matchs disponibles et les
            premiers signaux d’analyse pour aider à structurer une décision
            avant-match.
          </p>

          <div className="rb-dashboard-hero__actions">
            <button type="button" onClick={() => onNavigate("matches")}>
              Voir les matchs
            </button>
            <button type="button" onClick={() => onNavigate("responsible")}>
              Lire les limites
            </button>
          </div>
        </div>

        <aside className="rb-dashboard-hero__card">
          <p className="rb-eyebrow">Statut MVP</p>
          <h3>{apiStatus}</h3>
          <p>
            Données football réelles, scoring explicable et affichage responsable
            des recommandations.
          </p>
        </aside>
      </section>

      <section className="rb-dashboard-grid">
        <article className="rb-dashboard-card">
          <p className="rb-eyebrow">Vue rapide</p>
          <h3>État des données</h3>

          <div className="rb-dashboard-stats">
            <div>
              <span>Compétitions</span>
              <strong>{competitions.length}</strong>
            </div>
            <div>
              <span>Matchs chargés</span>
              <strong>{matches.length}</strong>
            </div>
            <div>
              <span>Compétition active</span>
              <strong>{selectedCompetition}</strong>
            </div>
          </div>
        </article>

        <article className="rb-dashboard-card rb-dashboard-card--wide">
          <CompetitionsSection
            competitions={competitions}
            onSelectCompetition={onSelectCompetition}
          />
        </article>

        <article className="rb-dashboard-card rb-dashboard-card--wide">
          <div className="rb-dashboard-section-header">
            <div>
              <p className="rb-eyebrow">À venir</p>
              <h3>Matchs à analyser</h3>
            </div>

            <button type="button" onClick={() => onNavigate("matches")}>
              Voir tous
            </button>
          </div>

          <MatchesSection
            selectedCompetition={selectedCompetition}
            matches={featuredMatches}
            onSelectMatch={onSelectMatch}
          />
        </article>

        <article className="rb-dashboard-card">
          <p className="rb-eyebrow">Glossaire</p>
          <h3>Comprendre les termes</h3>
          <p>
            Définitions des marchés, niveaux de confiance, risques et notions
            utilisées dans les analyses.
          </p>
          <button type="button" onClick={() => onNavigate("glossary")}>
            Ouvrir le glossaire
          </button>
        </article>

        <article className="rb-dashboard-card">
          <p className="rb-eyebrow">Cadre responsable</p>
          <h3>Limites de l’outil</h3>
          <p>
            RubyBets ne permet pas de parier, n’est pas un bookmaker et ne
            garantit aucun résultat sportif.
          </p>
          <button type="button" onClick={() => onNavigate("responsible")}>
            Voir les informations
          </button>
        </article>
      </section>
    </div>
  );
}

export default DashboardScreen;

// Schéma de communication du fichier :
// DashboardScreen.tsx
// ├── reçoit les données et actions depuis App.tsx
// ├── utilise CompetitionsSection.tsx pour les ligues
// ├── utilise MatchesSection.tsx pour les matchs mis en avant
// └── déclenche la navigation via onNavigate vers les autres écrans MVP
