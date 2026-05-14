// Ce composant prépare la zone Actualités & contexte récent de l’écran Analyse sans appel backend.

import type { Match } from "../models/rubybets";

type AnalysisNewsSectionProps = {
  match: Match | null;
};

// Cette fonction retourne un libellé court et lisible pour une équipe.
function getTeamLabel(match: Match | null) {
  if (!match) {
    return "la rencontre sélectionnée";
  }

  return `${match.home_team.short_name || match.home_team.name} vs ${
    match.away_team.short_name || match.away_team.name
  }`;
}

// Ce composant affiche un placeholder propre pour les futures actualités de l’analyse.
function AnalysisNewsSection({ match }: AnalysisNewsSectionProps) {
  return (
    <section className="rb-analysis-card rb-analysis-news-card">
      <div className="rb-analysis-card__header">
        <div>
          <p className="rb-analysis-kicker">Actualités & contexte récent</p>
          <h3>Signaux externes à connecter</h3>
        </div>
        <span className="rb-analysis-soft-badge">Prévu</span>
      </div>

      <div className="rb-analysis-news-list">
        <article className="rb-analysis-news-item">
          <span className="rb-analysis-news-item__icon">●</span>
          <div>
            <strong>Contexte récent du match</strong>
            <p>
              Emplacement prévu pour les informations récentes liées à {getTeamLabel(match)}.
            </p>
          </div>
        </article>

        <article className="rb-analysis-news-item">
          <span className="rb-analysis-news-item__icon">↗</span>
          <div>
            <strong>Signaux de préparation</strong>
            <p>
              Cette zone pourra accueillir plus tard des informations sur dynamique, annonces ou contexte d’équipe.
            </p>
          </div>
        </article>

        <article className="rb-analysis-news-item">
          <span className="rb-analysis-news-item__icon">!</span>
          <div>
            <strong>Branchement backend reporté</strong>
            <p>
              Aucun flux d’actualité n’est appelé pour l’instant afin de préserver la stabilité du MVP.
            </p>
          </div>
        </article>
      </div>
    </section>
  );
}

export default AnalysisNewsSection;

// Schéma de communication du fichier :
// AnalysisNewsSection.tsx
// ├── reçoit le match sélectionné depuis AnalysisScreen.tsx
// ├── affiche une zone actualités dédiée à l’écran Analyse
// ├── ne fait aucun fetch et ne modifie pas services/api.ts
// └── pourra être branché plus tard à une route backend dédiée