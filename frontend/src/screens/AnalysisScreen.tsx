// Ce fichier affiche l’écran Analyse pré-match sous forme de dashboard compact proche de la maquette.

import type {
  Match,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  Team,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import {
  cleanTextItems,
  formatMatchStatus,
  getTeamInitials,
  getTeamShortName,
} from "../helpers/displayText";
import MatchAnalysisSection from "../components/MatchAnalysisSection";
import AnalysisNewsSection from "../components/AnalysisNewsSection";

type AnalysisScreenProps = {
  matchAnalysis: MatchAnalysisResponse | null;
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchAnalysisStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Cette fonction récupère le match disponible depuis les données déjà chargées côté frontend.
function getSelectedMatch(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
): Match | null {
  return matchDetails?.match ?? matchContext?.match ?? null;
}

// Cette fonction formate une date courte pour le hero de l’analyse.
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

// Cette fonction formate l’heure locale du coup d’envoi.
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

// Cette fonction calcule un score de couverture des données pour l’affichage de confiance.
function getDataCoverage(matchAnalysis: MatchAnalysisResponse | null) {
  if (!matchAnalysis) {
    return 0;
  }

  const values = Object.values(matchAnalysis.data_used);
  const activeValues = values.filter(Boolean).length;

  return Math.round((activeValues / values.length) * 100);
}

// Cette fonction retourne les premiers éléments nettoyés d’une liste d’analyse.
function getLimitedItems(items: string[] | undefined, limit: number) {
  return cleanTextItems(items ?? []).slice(0, limit);
}

// Ce composant affiche le logo d’une équipe avec fallback texte.
function AnalysisTeamLogo({ team }: { team: Team }) {
  const teamLabel = getTeamShortName(team);

  return (
    <span className="rb-analysis-team-logo" aria-label={`Logo ${teamLabel}`}>
      <span className="rb-analysis-team-logo__fallback">{getTeamInitials(team)}</span>
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

// Ce composant affiche le hero compact du match analysé.
function AnalysisMatchHero({ match }: { match: Match | null }) {
  if (!match) {
    return (
      <section className="rb-analysis-hero rb-analysis-hero--empty">
        <p className="rb-analysis-kicker">Match sélectionné</p>
        <h2>Données du match en cours de chargement</h2>
        <p>Le hero sera complété dès que le détail ou le contexte du match sera disponible.</p>
      </section>
    );
  }

  return (
    <section className="rb-analysis-hero">
      <div className="rb-analysis-hero-team rb-analysis-hero-team--home">
        <AnalysisTeamLogo team={match.home_team} />
        <strong>{getTeamShortName(match.home_team)}</strong>
      </div>

      <div className="rb-analysis-hero-center">
        <span>{formatShortDate(match.utc_date)} · {formatKickoffTime(match.utc_date)}</span>
        <strong>VS</strong>
        <p>
          {match.competition.name} · Journée {match.matchday} · {formatMatchStatus(match.status)}
        </p>
      </div>

      <div className="rb-analysis-hero-team rb-analysis-hero-team--away">
        <strong>{getTeamShortName(match.away_team)}</strong>
        <AnalysisTeamLogo team={match.away_team} />
      </div>
    </section>
  );
}

// Ce composant affiche une ligne de lecture synthétique dans la colonne droite.
function ReadingItem({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <article className="rb-analysis-reading-item">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </article>
  );
}

// Ce composant affiche la colonne de lecture synthétique de l’analyse.
function AnalysisReadingPanel({ matchAnalysis }: { matchAnalysis: MatchAnalysisResponse | null }) {
  const coverage = getDataCoverage(matchAnalysis);
  const interpretations = getLimitedItems(matchAnalysis?.analysis.interpretation, 2);
  const limits = getLimitedItems(matchAnalysis?.analysis.limits, 1);

  return (
    <section className="rb-analysis-card rb-analysis-reading-card">
      <div className="rb-analysis-card__header">
        <div>
          <p className="rb-analysis-kicker">Lecture du match</p>
          <h3>Ce que les éléments suggèrent</h3>
        </div>
        <span className="rb-analysis-soft-badge">{coverage}% données</span>
      </div>

      <div className="rb-analysis-reading-list">
        <ReadingItem
          icon="◎"
          title="Lecture principale"
          text={interpretations[0] ?? "Analyse en attente de données interprétables pour ce match."}
        />
        <ReadingItem
          icon="↗"
          title="Scénario analytique"
          text={interpretations[1] ?? "Le scénario doit rester prudent tant que toutes les données ne sont pas disponibles."}
        />
        <ReadingItem
          icon="!"
          title="Limite importante"
          text={limits[0] ?? "L’analyse reste une aide à la décision avant-match, sans garantie de résultat."}
        />
      </div>

      <div className="rb-analysis-confidence-box">
        <span>Niveau de couverture</span>
        <strong>{coverage}%</strong>
        <p>Calculé selon les données disponibles pour cette analyse.</p>
      </div>
    </section>
  );
}

// Ce composant affiche les points clés à retenir en bas d’écran.
function AnalysisKeyTakeaways({ matchAnalysis }: { matchAnalysis: MatchAnalysisResponse | null }) {
  const facts = getLimitedItems(matchAnalysis?.analysis.observed_facts, 2);
  const limits = getLimitedItems(matchAnalysis?.analysis.limits, 1);

  const items = [
    facts[0] ?? "Analyse fondée sur les données disponibles avant le match.",
    facts[1] ?? "Les facteurs clés servent à structurer la lecture du match.",
    limits[0] ?? "Les limites de données doivent être prises en compte.",
    "Aucune lecture ne garantit l’issue sportive de la rencontre.",
  ];

  return (
    <section className="rb-analysis-takeaways">
      <div className="rb-analysis-takeaways__title">
        <span>★</span>
        <h3>Points clés à retenir</h3>
      </div>

      <div className="rb-analysis-takeaways__grid">
        {items.map((item) => (
          <p key={item}>
            <span>✓</span>
            {item}
          </p>
        ))}
      </div>
    </section>
  );
}

// Ce composant structure l’écran Analyse avec hero, analyse principale, sidebar et points clés.
function AnalysisScreen({
  matchAnalysis,
  matchDetails,
  matchContext,
  matchAnalysisStatus,
  onNavigate,
}: AnalysisScreenProps) {
  const selectedMatch = getSelectedMatch(matchDetails, matchContext);

  return (
    <div className="rb-analysis-screen rb-analysis-screen--mockup">
      <header className="rb-analysis-topbar">
        <div>
          <button type="button" onClick={() => onNavigate("matches")}>
            ← Retour aux matchs
          </button>
          <h2>Analyse pré-match</h2>
        </div>

        <button type="button" onClick={() => onNavigate("matches")}>
          Changer de match
        </button>
      </header>

      <AnalysisMatchHero match={selectedMatch} />

      <main className="rb-analysis-dashboard-grid">
        <div className="rb-analysis-dashboard-grid__main">
          {matchAnalysis ? (
            <MatchAnalysisSection matchAnalysis={matchAnalysis} />
          ) : (
            <article className="rb-analysis-card rb-analysis-empty-state">
              <p className="rb-analysis-kicker">Analyse</p>
              <h3>Analyse pré-match indisponible</h3>
              <p>{matchAnalysisStatus}</p>
            </article>
          )}
        </div>

        <aside className="rb-analysis-dashboard-grid__side">
          <AnalysisReadingPanel matchAnalysis={matchAnalysis} />
          <AnalysisNewsSection match={selectedMatch} />
        </aside>
      </main>

      <AnalysisKeyTakeaways matchAnalysis={matchAnalysis} />

      <p className="rb-analysis-footer-note">
        Outil d’aide à la décision. Les analyses proposées ne constituent pas un conseil d’investissement ou un pari.
      </p>
    </div>
  );
}

export default AnalysisScreen;

// Schéma de communication du fichier :
// AnalysisScreen.tsx
// ├── reçoit matchAnalysis, matchDetails et matchContext depuis App.tsx
// ├── utilise MatchAnalysisSection.tsx pour l’analyse principale
// ├── utilise AnalysisNewsSection.tsx pour la future zone actualités
// ├── sécurise les équipes inconnues via helpers/displayText.ts
// └── conserve la navigation vers Matchs et Prédictions via onNavigate
