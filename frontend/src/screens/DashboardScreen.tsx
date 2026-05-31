// Ce fichier affiche le Dashboard RubyBets avec une mise en page compacte proche de la maquette Obsidian Teal.

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

const MATCH_ACTION_LABEL = "Voir l’analyse";

// Formate une date de match en version courte pour les cartes du dashboard.
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
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Réduit un nom d’équipe long pour préserver la lisibilité des petites cartes.
function getTeamLabel(team: Team | null | undefined) {
  return getTeamShortName(team);
}

// Construit un libellé accessible stable pour l’action d’analyse d’un match.
function getMatchActionAriaLabel(match: Match) {
  if (!hasKnownTeams(match)) {
    return "Voir le match : affiche à confirmer";
  }

  return `${MATCH_ACTION_LABEL} : ${getTeamLabel(match.home_team)} contre ${getTeamLabel(
    match.away_team,
  )}`;
}

// Affiche le logo d’une équipe ou un fallback propre basé sur les initiales.
function renderTeamLogo(team: Team | null | undefined) {
  const teamLabel = getTeamLabel(team);
  const logoClassName = team?.crest
    ? "rb-home-team-logo rb-home-team-logo--with-image"
    : "rb-home-team-logo rb-home-team-logo--fallback";

  return (
    <span className={logoClassName} aria-label={`Logo ${teamLabel}`} title={teamLabel}>
      {team?.crest ? (
        <img src={team.crest} alt="" loading="lazy" decoding="async" />
      ) : (
        <span className="rb-home-team-logo__fallback">{getTeamInitials(team)}</span>
      )}
    </span>
  );
}

// Retourne une icône textuelle simple pour identifier rapidement les compétitions.
function getCompetitionIcon(code: string) {
  const icons: Record<string, string> = {
    PL: "🏴",
    FL1: "🇫🇷",
    SA: "🇮🇹",
    PD: "🇪🇸",
    BL1: "🇩🇪",
    CL: "★",
    WC: "🏆",
  };

  return icons[code] || "◆";
}

// Limite le nom d’une compétition pour garder des boutons compacts.
function getCompetitionLabel(competition: Competition) {
  const labels: Record<string, string> = {
    PL: "Premier League",
    FL1: "Ligue 1",
    SA: "Serie A",
    PD: "Liga",
    BL1: "Bundesliga",
    CL: "Champions League",
    WC: "FIFA World Cup",
  };

  return labels[competition.code] || competition.name;
}

// Cette fonction retourne le libellé d’action adapté au niveau de complétude du match.
function getMatchActionLabel(match: Match) {
  return hasKnownTeams(match) ? MATCH_ACTION_LABEL : "Voir le match";
}

// Ce composant structure l’écran d’accueil selon la maquette : hero, terrain, indicateurs, ligues, matchs et accès secondaires.
function DashboardScreen({
  apiStatus,
  competitions,
  matches,
  selectedCompetition,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: DashboardScreenProps) {
  const featuredMatches = matches.slice(0, 5);
  const selectedCompetitionName =
    competitions.find((competition) => competition.code === selectedCompetition)?.name ||
    selectedCompetition;

  return (
    <div className="rb-home-dashboard">
      <section className="rb-home-hero" aria-labelledby="dashboard-title">
        <div className="rb-home-hero__copy">
          <p className="rb-home-kicker">RubyBets MVP</p>
          <h2 id="dashboard-title">
            RubyBets, votre copilote data & IA pour des décisions éclairées avant match.
          </h2>
          <p>
            Analyses statistiques, scoring explicable et signaux clés pour comprendre les
            dynamiques d’un match avant toute décision.
          </p>
          <button type="button" className="rb-home-primary-action" onClick={() => onNavigate("matches")}>
            Voir les matchs
          </button>
        </div>

        <div className="rb-home-pitch-card" aria-hidden="true">
          <div className="rb-home-pitch">
            <span className="rb-home-pitch__line rb-home-pitch__line--middle" />
            <span className="rb-home-pitch__circle" />
            <span className="rb-home-pitch__box rb-home-pitch__box--left" />
            <span className="rb-home-pitch__box rb-home-pitch__box--right" />
            <span className="rb-home-pitch__dot rb-home-pitch__dot--one" />
            <span className="rb-home-pitch__dot rb-home-pitch__dot--two" />
            <span className="rb-home-pitch__dot rb-home-pitch__dot--three" />
            <span className="rb-home-pitch__score">72%</span>
          </div>
        </div>

        <aside className="rb-home-confidence" aria-label="Statut global du MVP">
          <div>
            <p className="rb-home-panel-label">Statut global</p>
            <strong>{apiStatus}</strong>
            <span>Données réelles et moteur V1 explicable</span>
          </div>

          <ul>
            <li>
              <span>Compétitions</span>
              <strong>{competitions.length}</strong>
            </li>
            <li>
              <span>Matchs chargés</span>
              <strong>{matches.length}</strong>
            </li>
            <li>
              <span>Compétition active</span>
              <strong>{selectedCompetition}</strong>
            </li>
          </ul>
        </aside>
      </section>

      <div className="rb-home-main-grid">
        <section className="rb-home-content" aria-labelledby="dashboard-leagues-title">
          <div className="rb-home-section-heading">
            <div>
              <p className="rb-home-panel-label">Ligues principales</p>
              <h3 id="dashboard-leagues-title">Compétitions MVP</h3>
            </div>
          </div>

          <div className="rb-home-league-row" aria-label="Sélection des compétitions">
            {competitions.map((competition) => (
              <button
                key={competition.id}
                type="button"
                className={
                  competition.code === selectedCompetition
                    ? "rb-home-league-pill rb-home-league-pill--active"
                    : "rb-home-league-pill"
                }
                onClick={() => onSelectCompetition(competition.code)}
              >
                <span>{getCompetitionIcon(competition.code)}</span>
                {getCompetitionLabel(competition)}
              </button>
            ))}
          </div>

          <div className="rb-home-section-heading rb-home-section-heading--matches">
            <div>
              <p className="rb-home-panel-label">Matchs à venir</p>
              <h3>Rencontres à analyser — {selectedCompetition}</h3>
            </div>
            <button type="button" className="rb-home-secondary-action" onClick={() => onNavigate("matches")}>
              Voir tous
            </button>
          </div>

          <div className="rb-home-match-row">
            {featuredMatches.length > 0 ? (
              featuredMatches.map((match) => {
                const actionLabel = getMatchActionLabel(match);

                return (
                  <article key={match.id} className="rb-home-match-card">
                    <div className="rb-home-match-card__top">
                      <p className="rb-home-match-card__league">{match.competition.name}</p>
                      <span>{formatDashboardDate(match.utc_date)}</span>
                    </div>

                    <button
                      type="button"
                      className="rb-home-match-card__button"
                      onClick={() => onSelectMatch(match.id)}
                      aria-label={getMatchActionAriaLabel(match)}
                    >
                      <span className="rb-home-match-card__fixture">
                        <span className="rb-home-match-team rb-home-match-team--home">
                          {renderTeamLogo(match.home_team)}
                        </span>
                        <span className="rb-home-vs">VS</span>
                        <span className="rb-home-match-team rb-home-match-team--away">
                          {renderTeamLogo(match.away_team)}
                        </span>
                      </span>

                      <span className="rb-home-match-card__names">
                        <strong title={getTeamLabel(match.home_team)}>{getTeamLabel(match.home_team)}</strong>
                        <strong title={getTeamLabel(match.away_team)}>{getTeamLabel(match.away_team)}</strong>
                      </span>
                    </button>

                    <button
                      type="button"
                      className="rb-home-match-action"
                      onClick={() => onSelectMatch(match.id)}
                      aria-label={getMatchActionAriaLabel(match)}
                    >
                      <span className="rb-home-match-action__icon" aria-hidden="true">▥</span>
                      <span className="rb-home-match-action__label">{actionLabel}</span>
                    </button>
                  </article>
                );
              })
            ) : (
              <article className="rb-home-empty-card">
                <h4>Aucun match disponible</h4>
                <p>La compétition sélectionnée ne retourne pas encore de rencontre exploitable.</p>
              </article>
            )}
          </div>
          <div className="rb-home-link-grid rb-home-link-grid--dashboard" aria-label="Accès pédagogiques et responsables">
            <article className="rb-home-link-card rb-home-link-card--glossary">
              <span className="rb-home-link-card__icon" aria-hidden="true">□</span>
              <div className="rb-home-link-card__content">
                <p className="rb-home-panel-label">Glossaire</p>
                <h3>Comprendre les termes</h3>
                <p>Comprendre les indicateurs, niveaux de confiance et notions utilisées.</p>
              </div>
              <button type="button" className="rb-home-link-card__action" onClick={() => onNavigate("glossary")}>
                Ouvrir
              </button>
            </article>

            <article className="rb-home-link-card rb-home-link-card--responsible">
              <span className="rb-home-link-card__icon" aria-hidden="true">ⓘ</span>
              <div className="rb-home-link-card__content">
                <p className="rb-home-panel-label">Cadre responsable</p>
                <h3>Limites de l’outil</h3>
                <p>RubyBets structure l’analyse et ne garantit aucun résultat sportif.</p>
              </div>
              <button type="button" className="rb-home-link-card__action" onClick={() => onNavigate("responsible")}>
                Voir
              </button>
            </article>
          </div>
        </section>

        <aside className="rb-home-side-panel rb-home-side-panel--quick" aria-label="Vue rapide">
          <div className="rb-home-side-panel__title">
            <div>
              <p className="rb-home-panel-label">Vue rapide</p>
              <h3>Indicateurs MVP</h3>
            </div>
            <span className="rb-home-side-panel__icon" aria-hidden="true">◎</span>
          </div>

          <article className="rb-home-stat-card rb-home-stat-card--primary">
            <span className="rb-home-stat-card__icon" aria-hidden="true">▦</span>
            <div>
              <strong>{matches.length}</strong>
              <p>Matchs affichables</p>
              <small>Données chargées, même partielles</small>
            </div>
          </article>

          <article className="rb-home-stat-card">
            <span className="rb-home-stat-card__icon" aria-hidden="true">▥</span>
            <div>
              <strong>{competitions.length}</strong>
              <p>Compétitions suivies</p>
              <small>Ligues disponibles</small>
            </div>
          </article>

          <article className="rb-home-stat-card">
            <span className="rb-home-stat-card__icon" aria-hidden="true">✓</span>
            <div>
              <strong>{selectedCompetition}</strong>
              <p>Compétition active</p>
              <small>{selectedCompetitionName}</small>
            </div>
          </article>
        </aside>
      </div>

      <p className="rb-home-responsible-note" role="note">
        <span className="rb-home-responsible-note__icon" aria-hidden="true">◇</span>
        <span>
          Outil d’aide à la décision. Les analyses proposées ne constituent ni un conseil
          d’investissement, ni une garantie de résultat sportif.
        </span>
      </p>
    </div>
  );
}

export default DashboardScreen;

// Schéma de communication du fichier :
// DashboardScreen.tsx
// ├── reçoit compétitions, matchs, statut API et actions depuis App.tsx
// ├── utilise les modèles Competition, Match et Team de models/rubybets.ts
// ├── sécurise les équipes inconnues via helpers/displayText.ts
// ├── déclenche la sélection compétition/match via les callbacks existants
// └── déclenche la navigation vers Matchs, Glossaire et Informations responsables
