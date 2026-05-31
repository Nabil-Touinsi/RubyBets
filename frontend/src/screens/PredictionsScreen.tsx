// Ce fichier affiche l’écran Prédictions avec les prédictions officielles et le bloc ML national expérimental.

import type {
  Match,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchPredictionsResponse,
  Team,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import {
  formatMatchStatus,
  getTeamInitials,
  getTeamShortName,
  hasKnownTeams,
} from "../helpers/displayText";
import MatchPredictionsSection from "../components/MatchPredictionsSection";
import PredictionSummaryPanel from "../components/PredictionSummaryPanel";
import MlLabNational from "../components/MlLabNational";

type PredictionsScreenProps = {
  matchPredictions: MatchPredictionsResponse | null;
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchPredictionsStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Cette fonction récupère le match disponible depuis les données déjà chargées côté frontend.
function getSelectedMatch(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
): Match | null {
  return matchDetails?.match ?? matchContext?.match ?? null;
}

// Cette fonction formate une date courte pour le hero.
function formatShortDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(date);
}

// Cette fonction formate l’heure locale du match.
function formatKickoffTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Heure à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Ce composant affiche un logo d’équipe avec fallback texte.
function PredictionTeamLogo({ team }: { team: Team }) {
  const teamLabel = getTeamShortName(team);

  return (
    <span className="rb-prediction-team-logo" aria-label={`Logo ${teamLabel}`}>
      <span className="rb-prediction-team-logo__fallback">
        {getTeamInitials(team)}
      </span>

      {team.crest ? (
        <img
          src={team.crest}
          alt=""
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
    </span>
  );
}

// Ce composant affiche le hero compact du match sélectionné.
function PredictionMatchHero({ match }: { match: Match | null }) {
  if (!match) {
    return (
      <section className="rb-prediction-hero rb-prediction-hero--empty">
        <p className="rb-prediction-kicker">Match sélectionné</p>
        <h2>Données du match en cours de chargement</h2>
        <p>
          Les équipes, logos et informations de match seront affichés dès que les
          données seront disponibles.
        </p>
      </section>
    );
  }

  return (
    <section className="rb-prediction-hero">
      <div className="rb-prediction-hero__team rb-prediction-hero__team--home">
        <PredictionTeamLogo team={match.home_team} />
        <div>
          <span>{match.competition.name}</span>
          <strong>{getTeamShortName(match.home_team)}</strong>
        </div>
      </div>

      <div className="rb-prediction-hero__center">
        <span>
          {formatShortDate(match.utc_date)} · {formatKickoffTime(match.utc_date)}
        </span>
        <strong>VS</strong>
        <p>
          Journée {match.matchday} · {formatMatchStatus(match.status)}
        </p>
      </div>

      <div className="rb-prediction-hero__team rb-prediction-hero__team--away">
        <div>
          <span>Adversaire</span>
          <strong>{getTeamShortName(match.away_team)}</strong>
        </div>
        <PredictionTeamLogo team={match.away_team} />
      </div>

      <div className="rb-prediction-hero__meta">
        <span>Compétition</span>
        <strong>{match.competition.name}</strong>
      </div>

      <div className="rb-prediction-hero__meta">
        <span>Journée</span>
        <strong>{match.matchday}</strong>
      </div>

      <div className="rb-prediction-hero__meta">
        <span>Statut</span>
        <strong>{formatMatchStatus(match.status)}</strong>
      </div>
    </section>
  );
}

// Cette fonction prépare les éléments courts de résumé responsable.
function getSummaryItems(matchPredictions: MatchPredictionsResponse | null) {
  const predictions = matchPredictions?.predictions.predictions;

  if (!predictions) {
    return [
      "Les données prédictives ne sont pas encore disponibles.",
      "La lecture doit rester prudente.",
      "Aucun résultat sportif n’est garanti.",
    ];
  }

  return [
    `Tendance 1X2 : ${predictions.one_x_two.label}.`,
    `Volume de buts : ${predictions.goals.label}.`,
    `BTTS : ${predictions.btts.label}.`,
    "Ces prédictions ne constituent pas un conseil d’investissement.",
  ];
}

// Ce composant affiche la carte de résumé située sous le baromètre.
function PredictionResponsibleSummary({
  matchPredictions,
}: {
  matchPredictions: MatchPredictionsResponse | null;
}) {
  const items = getSummaryItems(matchPredictions);

  return (
    <section className="rb-prediction-side-card">
      <p className="rb-prediction-kicker">En résumé</p>
      <h3>Lecture responsable</h3>

      <div className="rb-prediction-summary-list">
        {items.map((item) => (
          <p key={item}>
            <span>◎</span>
            {item}
          </p>
        ))}
      </div>
    </section>
  );
}

// Ce composant structure l’écran Prédictions avec le bloc officiel puis le bloc ML national expérimental.
function PredictionsScreen({
  matchPredictions,
  matchDetails,
  matchContext,
  matchPredictionsStatus,
  onNavigate,
}: PredictionsScreenProps) {
  const selectedMatch = getSelectedMatch(matchDetails, matchContext);
  const hasCompleteTeams = !selectedMatch || hasKnownTeams(selectedMatch);

  return (
    <div className="rb-predictions-screen rb-predictions-screen--mockup">
      <header className="rb-prediction-topbar">
        <button type="button" onClick={() => onNavigate("matches")}>
          ← Retour aux matchs
        </button>

        <h2>Prédictions</h2>

        <button type="button" onClick={() => onNavigate("analysis")}>
          Voir l’analyse du match
        </button>
      </header>

      <PredictionMatchHero match={selectedMatch} />

      {selectedMatch && !hasCompleteTeams ? (
        <article className="rb-prediction-card rb-prediction-empty-state">
          <p className="rb-prediction-kicker">Données partielles</p>
          <h3>Prédictions officielles désactivées</h3>
          <p>
            Les équipes ne sont pas encore connues pour cette affiche. RubyBets
            conserve le match visible, mais ne génère pas de prédiction officielle
            tant que les données sportives de base restent incomplètes.
          </p>
        </article>
      ) : null}

      <main className="rb-prediction-dashboard-grid">
        <div className="rb-prediction-dashboard-grid__main">
          {matchPredictions && hasCompleteTeams ? (
            <MatchPredictionsSection matchPredictions={matchPredictions} />
          ) : (
            <article className="rb-prediction-card rb-prediction-empty-state">
              <p className="rb-prediction-kicker">Prédictions officielles</p>
              <h3>Prédictions indisponibles</h3>
              <p>
                {selectedMatch && !hasCompleteTeams
                  ? "Équipes à confirmer"
                  : matchPredictionsStatus}
              </p>
            </article>
          )}

          <MlLabNational selectedMatch={selectedMatch} />
        </div>

        <aside className="rb-prediction-dashboard-grid__side">
          <PredictionSummaryPanel matchPredictions={matchPredictions} />
          <PredictionResponsibleSummary matchPredictions={matchPredictions} />
        </aside>
      </main>

      <p className="rb-prediction-footer-note">
        Outil d’aide à la décision. Les prédictions proposées ne constituent pas
        un conseil d’investissement ou un pari.
      </p>
    </div>
  );
}

export default PredictionsScreen;

// Schéma de communication du fichier :
// PredictionsScreen.tsx
// ├── reçoit les données chargées par App.tsx
// ├── affiche MatchPredictionsSection.tsx pour les prédictions officielles
// ├── intègre MlLabNational.tsx comme bloc expérimental dynamique séparé
// └── utilise displayText.ts pour sécuriser les noms d’équipes et les états partiels
