// Ce composant prépare la zone Actualités & contexte d’un match sans appel backend pour le moment.

import type { Match } from "../models/rubybets";
import { getFixtureDisplayName } from "../helpers/displayText";

type MatchNewsSectionProps = {
  match: Match;
};

// Ce composant affiche un emplacement propre pour les futures actualités du match.
function MatchNewsSection({ match }: MatchNewsSectionProps) {
  return (
    <section className="rb-detail-card rb-detail-news">
      <div className="rb-detail-card__header">
        <div>
          <p className="rb-detail-kicker">Actualités & contexte</p>
          <h3>Zone préparée pour le suivi du match</h3>
        </div>
        <span className="rb-detail-soft-badge">À connecter</span>
      </div>

      <div className="rb-detail-news-list">
        <article className="rb-detail-news-item">
          <span className="rb-detail-news-item__icon">📰</span>
          <div>
            <strong>Actualités du match</strong>
            <p>
              Emplacement prévu pour les informations liées à{" "}
              {getFixtureDisplayName(match)}.
            </p>
          </div>
        </article>

        <article className="rb-detail-news-item">
          <span className="rb-detail-news-item__icon">⚕</span>
          <div>
            <strong>Disponibilités et absences</strong>
            <p>
              Cette zone pourra afficher plus tard les absences, retours de
              joueurs ou signaux de composition.
            </p>
          </div>
        </article>

        <article className="rb-detail-news-item">
          <span className="rb-detail-news-item__icon">↗</span>
          <div>
            <strong>Contexte récent</strong>
            <p>
              Aucun flux d’actualité n’est encore branché côté backend. Le bloc
              reste volontairement informatif.
            </p>
          </div>
        </article>
      </div>
    </section>
  );
}

export default MatchNewsSection;

// Schéma de communication du fichier :
// MatchNewsSection.tsx
// ├── reçoit le match depuis MatchDetailsScreen.tsx
// ├── prépare l’emplacement frontend des actualités du match
// ├── sécurise l’affichage quand les équipes sont inconnues
// ├── ne lance aucun appel API
// └── pourra être relié plus tard à une route backend dédiée
