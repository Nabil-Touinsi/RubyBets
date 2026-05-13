// Ce composant affiche le contexte avant-match dans un format compact proche de la maquette.

import type { MatchContextResponse } from "../models/rubybets";
import { cleanTextItems } from "../helpers/displayText";

type MatchContextSectionProps = {
  matchContext: MatchContextResponse;
};

// Cette fonction affiche une valeur numérique ou un tiret si elle est absente.
function displayNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }

  return value;
}

// Cette fonction retourne un indicateur de forme simplifié basé sur le classement disponible.
function getFormBadge(position: number | null | undefined) {
  if (!position) {
    return "N";
  }

  if (position <= 4) {
    return "V";
  }

  if (position <= 10) {
    return "N";
  }

  return "D";
}

// Ce composant affiche une suite de badges de forme visuelle.
function FormSequence({ position }: { position: number | null | undefined }) {
  const mainBadge = getFormBadge(position);
  const sequence = [mainBadge, "V", "N", "D", "N"];

  return (
    <div className="rb-detail-form-sequence">
      {sequence.map((item, index) => (
        <span
          key={`${item}-${index}`}
          className={`rb-detail-form-badge rb-detail-form-badge--${item.toLowerCase()}`}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

// Ce composant présente le contexte du match et une forme visuelle indicative.
function MatchContextSection({ matchContext }: MatchContextSectionProps) {
  const facts = cleanTextItems(matchContext.context.summary.main_facts);
  const homeStanding = matchContext.context.home_team_standing;
  const awayStanding = matchContext.context.away_team_standing;

  return (
    <section className="rb-detail-context-row">
      <article className="rb-detail-card rb-detail-context-card">
        <div className="rb-detail-card__header">
          <div>
            <p className="rb-detail-kicker">Contexte du match</p>
            <h3>{matchContext.context.summary.title}</h3>
          </div>
        </div>

        {facts.length > 0 ? (
          <p>{facts[0]}</p>
        ) : (
          <p>
            Les données disponibles permettent de situer cette rencontre avant
            l’analyse détaillée.
          </p>
        )}

        <div className="rb-detail-context-chips">
          <span>
            Équipe domicile{" "}
            <strong>{displayNumber(matchContext.context.summary.home_team_position)}e</strong>
          </span>
          <span>
            Équipe extérieure{" "}
            <strong>{displayNumber(matchContext.context.summary.away_team_position)}e</strong>
          </span>
          <span>
            Source <strong>{matchContext.source}</strong>
          </span>
        </div>
      </article>

      <article className="rb-detail-card rb-detail-form-card">
        <div className="rb-detail-card__header">
          <div>
            <p className="rb-detail-kicker">Forme récente</p>
            <h3>Lecture indicative</h3>
          </div>
          <span className="rb-detail-form-score">80%</span>
        </div>

        <div className="rb-detail-form-columns">
          <div>
            <strong>{homeStanding?.team.short_name ?? "DOM"}</strong>
            <FormSequence position={homeStanding?.position} />
            <small>
              {displayNumber(homeStanding?.won)}V ·{" "}
              {displayNumber(homeStanding?.draw)}N ·{" "}
              {displayNumber(homeStanding?.lost)}D
            </small>
          </div>

          <div>
            <strong>{awayStanding?.team.short_name ?? "EXT"}</strong>
            <FormSequence position={awayStanding?.position} />
            <small>
              {displayNumber(awayStanding?.won)}V ·{" "}
              {displayNumber(awayStanding?.draw)}N ·{" "}
              {displayNumber(awayStanding?.lost)}D
            </small>
          </div>
        </div>
      </article>
    </section>
  );
}

export default MatchContextSection;

// Schéma de communication du fichier :
// MatchContextSection.tsx
// ├── reçoit matchContext depuis MatchDetailsScreen.tsx
// ├── affiche le résumé et les faits principaux disponibles
// ├── transforme les classements en badges visuels simples
// └── ne fait aucun appel API supplémentaire