// Ce fichier affiche l’écran d’accueil RubyBets avec une mise en page premium fidèle à la maquette produit validée.

import {
  Activity,
  BarChart3,
  BookOpen,
  CalendarDays,
  ChevronRight,
  Database,
  FileText,
  Gauge,
  ShieldCheck,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import type { Competition, Match, Team } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import {
  getTeamInitials,
  getTeamShortName,
  hasKnownTeams,
} from "../helpers/displayText";

type DashboardScreenProps = {
  apiStatus: string;
  competitions: Competition[];
  matches: Match[];
  selectedCompetition: string;
  onSelectCompetition: (competitionCode: string) => void;
  onSelectMatch: (matchId: number) => void;
  onNavigate: (screen: AppScreen) => void;
};

const MATCH_ANALYSIS_LABEL = "Voir l’analyse complète";

// Formate une date de match en version courte pour les listes compactes de l’accueil.
function formatDashboardDate(value: string) {
  if (!value) {
    return "Date à confirmer";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Formate une date plus lisible pour le match principal mis en avant.
function formatFeaturedMatchDate(value: string) {
  if (!value) {
    return "Date à confirmer";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Réduit un nom d’équipe long tout en conservant un fallback pour les équipes inconnues.
function getTeamLabel(team: Team | null | undefined) {
  return getTeamShortName(team);
}

// Construit un libellé accessible stable pour l’action d’analyse d’un match.
function getMatchActionAriaLabel(match: Match) {
  if (!hasKnownTeams(match)) {
    return "Voir le match : équipes à confirmer";
  }

  return `${MATCH_ANALYSIS_LABEL} : ${getTeamLabel(match.home_team)} contre ${getTeamLabel(
    match.away_team,
  )}`;
}

// Affiche le logo d’une équipe ou un fallback propre basé sur les initiales.
function renderTeamLogo(team: Team | null | undefined, variant: "default" | "featured" = "default") {
  const teamLabel = getTeamLabel(team);
  const className = [
    "rb-home-premium-team-logo",
    variant === "featured" ? "rb-home-premium-team-logo--featured" : "",
    team?.crest ? "rb-home-premium-team-logo--image" : "rb-home-premium-team-logo--fallback",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={className} aria-label={`Logo ${teamLabel}`} title={teamLabel}>
      {team?.crest ? (
        <img src={team.crest} alt="" loading="lazy" decoding="async" />
      ) : (
        <span>{getTeamInitials(team)}</span>
      )}
    </span>
  );
}

// Affiche le logo réel d’une compétition avec un fallback court si aucun emblème n’est disponible.
function renderCompetitionLogo(
  competition: Competition | null | undefined,
  variant: "chip" | "kpi" = "chip",
) {
  const className = [
    "rb-home-premium-competition-logo",
    variant === "kpi" ? "rb-home-premium-competition-logo--kpi" : "",
    competition?.emblem
      ? "rb-home-premium-competition-logo--image"
      : "rb-home-premium-competition-logo--fallback",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={className} aria-hidden="true">
      {competition?.emblem ? (
        <img src={competition.emblem} alt="" loading="lazy" decoding="async" />
      ) : (
        <span>{competition?.code || "RB"}</span>
      )}
    </span>
  );
}

// Retourne un libellé court et stable pour les compétitions du MVP.
function getCompetitionLabel(competition: Competition) {
  const labels: Record<string, string> = {
    PL: "Premier League",
    FL1: "Ligue 1",
    SA: "Serie A",
    PD: "La Liga",
    BL1: "Bundesliga",
    CL: "Champions League",
    WC: "World Cup",
  };

  return labels[competition.code] || competition.name;
}

// Normalise le statut API en libellé court pour l’accueil.
function getApiStatusLabel(apiStatus: string) {
  const normalizedStatus = apiStatus.toLowerCase();

  if (normalizedStatus.includes("connect")) {
    return "Connectée";
  }

  if (normalizedStatus.includes("cours")) {
    return "Vérification";
  }

  return apiStatus;
}

// Sélectionne le match principal à mettre en avant sur l’accueil.
function getFeaturedMatch(matches: Match[]) {
  return matches.find((match) => hasKnownTeams(match)) || matches[0] || null;
}

// Affiche une icône Lucide décorative avec une taille stable pour le dashboard premium.
function renderIcon(Icon: LucideIcon, size = 18) {
  return <Icon aria-hidden="true" size={size} strokeWidth={2.15} />;
}

// Ce composant restitue l’accueil en bloc produit compact : hero, données, KPI, compétition, matchs, valeur et accès responsables.
function DashboardScreen({
  apiStatus,
  competitions,
  matches,
  selectedCompetition,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: DashboardScreenProps) {
  const selectedCompetitionData = competitions.find(
    (competition) => competition.code === selectedCompetition,
  );

  const selectedCompetitionName = selectedCompetitionData?.name || selectedCompetition;
  const featuredMatch = getFeaturedMatch(matches);
  const secondaryMatches = featuredMatch
    ? matches.filter((match) => match.id !== featuredMatch.id).slice(0, 3)
    : matches.slice(0, 3);
  const completeMatchesCount = matches.filter((match) => hasKnownTeams(match)).length;
  const apiStatusLabel = getApiStatusLabel(apiStatus);

  const updatedLabel = featuredMatch?.last_updated
    ? formatDashboardDate(featuredMatch.last_updated)
    : "Temps réel";

  return (
    <div className="rb-home-premium" aria-labelledby="home-premium-title">
      <section className="rb-home-premium-hero" aria-label="Présentation RubyBets">
        <div className="rb-home-premium-hero__copy">
          <p className="rb-home-premium-eyebrow">Bienvenue sur RubyBets</p>

          <h2 id="home-premium-title">Analysez les matchs avant coup d’envoi.</h2>

          <p className="rb-home-premium-hero__lead">
            Données réelles, signaux avancés et scoring explicable pour une lecture claire,
            rationnelle et responsable.
          </p>

          <div className="rb-home-premium-hero__actions" aria-label="Actions principales">
            <button
              type="button"
              className="rb-home-premium-button rb-home-premium-button--primary"
              onClick={() => onNavigate("matches")}
            >
              Explorer les matchs
              {renderIcon(ChevronRight, 16)}
            </button>

            <button
              type="button"
              className="rb-home-premium-button rb-home-premium-button--secondary"
              onClick={() => onNavigate("recommendation")}
            >
              {renderIcon(BarChart3, 16)}
              Voir les recommandations
            </button>
          </div>

          <p className="rb-home-premium-hero__note">
            Outil d’aide à la décision — aucune garantie sportive.
          </p>
        </div>

        <aside className="rb-home-premium-data" aria-label="État des données RubyBets">
          <div className="rb-home-premium-section-title">
            <p className="rb-home-premium-eyebrow">État des données</p>
            <span className="rb-home-premium-status-pill">
              <span aria-hidden="true" />
              {apiStatusLabel}
            </span>
          </div>

          <dl className="rb-home-premium-data-list">
            <div>
              <dt>Compétition active</dt>
              <dd>{selectedCompetitionName}</dd>
            </div>

            <div>
              <dt>Matchs disponibles</dt>
              <dd>{matches.length}</dd>
            </div>

            <div>
              <dt>Analyses possibles</dt>
              <dd>{completeMatchesCount}</dd>
            </div>

            <div>
              <dt>Données mises à jour</dt>
              <dd>{updatedLabel}</dd>
            </div>

            <div>
              <dt>API</dt>
              <dd>
                <span className="rb-home-premium-data-badge">{apiStatusLabel}</span>
              </dd>
            </div>
          </dl>

          <p className="rb-home-premium-source">
            Source : <strong>Football-Data.org</strong>
          </p>
        </aside>
      </section>

      <section className="rb-home-premium-kpis" aria-label="Indicateurs essentiels">
        <article className="rb-home-premium-kpi">
          <span aria-hidden="true">{renderIcon(CalendarDays)}</span>
          <div>
            <strong>{matches.length}</strong>
            <p>Matchs disponibles</p>
          </div>
        </article>

        <article className="rb-home-premium-kpi">
          <span aria-hidden="true">{renderIcon(Trophy)}</span>
          <div>
            <strong>{competitions.length}</strong>
            <p>Compétitions suivies</p>
          </div>
        </article>

        <article className="rb-home-premium-kpi">
          {renderCompetitionLogo(selectedCompetitionData, "kpi")}
          <div>
            <strong>{selectedCompetitionName}</strong>
            <p>Compétition active</p>
          </div>
        </article>

        <article className="rb-home-premium-kpi rb-home-premium-kpi--success">
          <span aria-hidden="true">{renderIcon(Activity)}</span>
          <div>
            <strong>API {apiStatusLabel}</strong>
            <p>Données avant-match</p>
          </div>
        </article>
      </section>

      <section className="rb-home-premium-competitions" aria-labelledby="home-competitions-title">
        <p className="rb-home-premium-eyebrow">Choisir une compétition</p>
        <h3 id="home-competitions-title">Compétitions du MVP</h3>

        <div className="rb-home-premium-competition-row" aria-label="Sélection des compétitions">
          {competitions.map((competition) => (
            <button
              key={competition.id}
              type="button"
              className={
                competition.code === selectedCompetition
                  ? "rb-home-premium-chip rb-home-premium-chip--active"
                  : "rb-home-premium-chip"
              }
              onClick={() => onSelectCompetition(competition.code)}
            >
              {renderCompetitionLogo(competition, "chip")}
              {getCompetitionLabel(competition)}
            </button>
          ))}
        </div>
      </section>

      <section className="rb-home-premium-match-grid" aria-label="Rencontres à analyser">
        <article className="rb-home-premium-featured-match">
          <p className="rb-home-premium-eyebrow">Rencontre à analyser</p>
          <h3>Match prioritaire</h3>

          {featuredMatch ? (
            <>
              <button
                type="button"
                className="rb-home-premium-featured-fixture"
                onClick={() => onSelectMatch(featuredMatch.id)}
                aria-label={getMatchActionAriaLabel(featuredMatch)}
              >
                <span className="rb-home-premium-featured-team rb-home-premium-featured-team--home">
                  {renderTeamLogo(featuredMatch.home_team, "featured")}
                  <strong>{getTeamLabel(featuredMatch.home_team)}</strong>
                </span>

                <span className="rb-home-premium-vs" aria-hidden="true">
                  VS
                </span>

                <span className="rb-home-premium-featured-team rb-home-premium-featured-team--away">
                  <strong>{getTeamLabel(featuredMatch.away_team)}</strong>
                  {renderTeamLogo(featuredMatch.away_team, "featured")}
                </span>
              </button>

              <div className="rb-home-premium-featured-meta">
                <span>{featuredMatch.competition.name}</span>
                <span>{formatFeaturedMatchDate(featuredMatch.utc_date)}</span>
                <span>
                  {hasKnownTeams(featuredMatch) ? "Données complètes" : "Équipes à confirmer"}
                </span>
              </div>

              <button
                type="button"
                className="rb-home-premium-button rb-home-premium-button--wide"
                onClick={() => onSelectMatch(featuredMatch.id)}
                aria-label={getMatchActionAriaLabel(featuredMatch)}
              >
                {hasKnownTeams(featuredMatch) ? MATCH_ANALYSIS_LABEL : "Voir le match"}
                {renderIcon(ChevronRight, 16)}
              </button>
            </>
          ) : (
            <div className="rb-home-premium-empty-state">
              <h4>Aucun match disponible</h4>
              <p>La compétition sélectionnée ne retourne pas encore de rencontre exploitable.</p>
            </div>
          )}
        </article>

        <aside className="rb-home-premium-upcoming" aria-label="Prochains matchs">
          <div className="rb-home-premium-upcoming__header">
            <div>
              <p className="rb-home-premium-eyebrow">Prochains matchs</p>
              <h3>Aperçu rapide</h3>
            </div>

            <button type="button" onClick={() => onNavigate("matches")}>
              Voir tous
            </button>
          </div>

          <div className="rb-home-premium-upcoming-list">
            {secondaryMatches.length > 0 ? (
              secondaryMatches.map((match) => (
                <button
                  key={match.id}
                  type="button"
                  className="rb-home-premium-upcoming-item"
                  onClick={() => onSelectMatch(match.id)}
                  aria-label={getMatchActionAriaLabel(match)}
                >
                  <span className="rb-home-premium-upcoming-date">
  {formatDashboardDate(match.utc_date)}
</span>

    <span className="rb-home-premium-upcoming-team rb-home-premium-upcoming-team--home">
      <strong>{getTeamLabel(match.home_team)}</strong>
      {renderTeamLogo(match.home_team)}
    </span>

    <em>vs</em>

    <span className="rb-home-premium-upcoming-team rb-home-premium-upcoming-team--away">
      {renderTeamLogo(match.away_team)}
      <strong>{getTeamLabel(match.away_team)}</strong>
    </span>

    {renderIcon(ChevronRight, 16)}
                </button>
              ))
            ) : (
              <div className="rb-home-premium-empty-state rb-home-premium-empty-state--compact">
                <h4>Aucun autre match</h4>
                <p>Les prochaines rencontres apparaîtront ici dès disponibilité.</p>
              </div>
            )}
          </div>
        </aside>
      </section>

      <section className="rb-home-premium-value-grid" aria-label="Valeur produit RubyBets">
        <article>
          <span aria-hidden="true">{renderIcon(Database, 24)}</span>
          <div>
            <h3>Données réelles</h3>
            <p>Sources fiables et données disponibles en temps réel.</p>
          </div>
        </article>

        <article>
          <span aria-hidden="true">{renderIcon(Gauge, 24)}</span>
          <div>
            <h3>Scoring explicable</h3>
            <p>Un score basé sur des signaux clairs et transparents.</p>
          </div>
        </article>

        <article>
          <span aria-hidden="true">{renderIcon(ShieldCheck, 24)}</span>
          <div>
            <h3>Usage responsable</h3>
            <p>Un outil d’aide à la décision, pas une garantie de gain.</p>
          </div>
        </article>
      </section>

      <section className="rb-home-premium-resources" aria-label="Accès secondaires">
        <article>
          <span aria-hidden="true">{renderIcon(BookOpen, 24)}</span>
          <div>
            <h3>Glossaire</h3>
            <p>Comprendre les métriques, signaux et concepts utilisés.</p>
          </div>
          <button type="button" onClick={() => onNavigate("glossary")} aria-label="Ouvrir le glossaire">
            {renderIcon(ChevronRight, 18)}
          </button>
        </article>

        <article>
          <span aria-hidden="true">{renderIcon(FileText, 24)}</span>
          <div>
            <h3>Informations responsables</h3>
            <p>Nos engagements pour un usage sain et éclairé.</p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("responsible")}
            aria-label="Voir les informations responsables"
          >
            {renderIcon(ChevronRight, 18)}
          </button>
        </article>
      </section>

      <p className="rb-home-premium-footer-note" role="note">
        RubyBets est un outil d’aide à la décision avant-match. Les analyses proposées ne
        constituent pas un conseil d’investissement, un pari ou une garantie de résultat sportif.
      </p>
    </div>
  );
}

export default DashboardScreen;

// Schéma de communication du fichier :
// DashboardScreen.tsx
// ├── reçoit compétitions, matchs, statut API et actions depuis App.tsx
// ├── utilise les modèles Competition, Match et Team de models/rubybets.ts
// ├── utilise Competition.emblem pour afficher les logos réels déjà fournis par l’API/backend
// ├── utilise lucide-react pour homogénéiser les icônes des fonctions produit
// ├── sécurise les équipes inconnues via helpers/displayText.ts
// ├── déclenche la sélection compétition/match via les callbacks existants
// ├── déclenche la navigation vers Matchs, Recommandation, Glossaire et Informations responsables
// └── ne modifie ni l’API, ni le backend, ni les calculs, ni les modèles ML