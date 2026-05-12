// Ce fichier affiche l’écran Fiche détail match de RubyBets avec une structure dédiée proche de la maquette MVP.

import type { Match, MatchContextResponse, MatchDetailsResponse } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import { formatDateTime, formatMatchStatus } from "../helpers/displayText";
import MatchDetailsSection from "../components/MatchDetailsSection";
import MatchContextSection from "../components/MatchContextSection";

type MatchDetailsScreenProps = {
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchDetailsStatus: string;
  matchContextStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Cette fonction récupère le match disponible depuis le détail ou le contexte.
function getSelectedMatch(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null
): Match | null {
  return matchDetails?.match ?? matchContext?.match ?? null;
}

// Ce composant affiche l’en-tête synthétique du match sélectionné.
function MatchSummaryHero({ match }: { match: Match }) {
  return (
    <section className="rb-match-details-hero">
      <div>
        <p className="rb-eyebrow">Fiche détail match</p>
        <h2>
          {match.home_team.name} <span>vs</span> {match.away_team.name}
        </h2>
        <p>
          {match.competition.name} ({match.competition.code}) — Journée{" "}
          {match.matchday}
        </p>
      </div>

      <aside>
        <p className="rb-eyebrow">Coup d’envoi</p>
        <h3>{formatDateTime(match.utc_date)}</h3>
        <p>Statut : {formatMatchStatus(match.status)}</p>
      </aside>
    </section>
  );
}

// Ce composant structure la fiche match avec détail, contexte et passerelles vers analyse/prédictions.
function MatchDetailsScreen({
  matchDetails,
  matchContext,
  matchDetailsStatus,
  matchContextStatus,
  onNavigate,
}: MatchDetailsScreenProps) {
  const selectedMatch = getSelectedMatch(matchDetails, matchContext);

  return (
    <div className="rb-match-details-screen">
      {selectedMatch && <MatchSummaryHero match={selectedMatch} />}

      <section className="rb-match-details-layout">
        <div className="rb-match-details-main">
          {matchDetails ? (
            <MatchDetailsSection matchDetails={matchDetails} />
          ) : (
            <article className="rb-empty-state">
              <p className="rb-eyebrow">Détail</p>
              <h3>Données du match</h3>
              <p>{matchDetailsStatus}</p>
            </article>
          )}
        </div>

        <aside className="rb-match-details-aside">
          <article>
            <p className="rb-eyebrow">Parcours</p>
            <h3>Continuer l’analyse</h3>
            <p>
              La fiche match centralise les informations utiles avant de passer à
              l’analyse et aux prédictions.
            </p>
            <div className="rb-match-details-actions">
              <button type="button" onClick={() => onNavigate("analysis")}>
                Voir l’analyse
              </button>
              <button type="button" onClick={() => onNavigate("predictions")}>
                Voir les prédictions
              </button>
            </div>
          </article>

          <article>
            <p className="rb-eyebrow">Cadre</p>
            <h3>Avant-match uniquement</h3>
            <p>
              Les données sont utilisées pour structurer une lecture avant match,
              sans pari réel et sans garantie de résultat.
            </p>
          </article>
        </aside>
      </section>

      <section className="rb-match-context-panel">
        {matchContext ? (
          <MatchContextSection matchContext={matchContext} />
        ) : (
          <article className="rb-empty-state">
            <p className="rb-eyebrow">Contexte</p>
            <h3>Contexte avant-match</h3>
            <p>{matchContextStatus}</p>
          </article>
        )}
      </section>
    </div>
  );
}

export default MatchDetailsScreen;

// Schéma de communication du fichier :
// MatchDetailsScreen.tsx
// ├── reçoit le détail et le contexte depuis App.tsx
// ├── utilise MatchDetailsSection.tsx pour les informations principales
// ├── utilise MatchContextSection.tsx pour le contexte avant-match
// └── déclenche la navigation vers AnalysisScreen et PredictionsScreen via onNavigate
