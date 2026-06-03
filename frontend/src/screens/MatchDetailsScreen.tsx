// Ce fichier affiche l’écran Détail match de RubyBets sous forme de fiche premium avant-match.

import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type {
  Match,
  MatchContextResponse,
  MatchDetailsResponse,
  Team,
  TeamStanding,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import {
  formatDateTime,
  formatMatchStatus,
  getTeamDisplayName,
  getTeamInitials,
  getTeamShortName,
  hasKnownTeams,
} from "../helpers/displayText";

type MatchDetailsScreenProps = {
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchDetailsStatus: string;
  matchContextStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

type DetailTabKey =
  | "overview"
  | "analysis"
  | "form"
  | "lineup"
  | "headToHead"
  | "context";

type DetailTab = {
  key: DetailTabKey;
  icon: string;
  label: string;
};

type InfoLine = {
  icon: string;
  label: string;
  value: string;
};

type InsightCard = {
  icon: string;
  tone: "teal" | "red" | "amber" | "blue";
  title: string;
  description: string;
  badge: string;
};

type MetricCard = {
  label: string;
  note: string;
  homeValue: string;
  awayValue: string;
  homeBar: number;
  awayBar: number;
  accent: "teal" | "red" | "neutral";
};

const DETAIL_TABS: DetailTab[] = [
  { key: "overview", icon: "▦", label: "Vue d’ensemble" },
  { key: "analysis", icon: "↗", label: "Analyse détaillée" },
  { key: "form", icon: "⌁", label: "Forme & tendances" },
  { key: "lineup", icon: "◌", label: "Compo probable" },
  { key: "headToHead", icon: "◇", label: "Face à face" },
  { key: "context", icon: "◈", label: "Contexte" },
];

// Cette fonction récupère le match disponible depuis le détail ou le contexte.
function getSelectedMatch(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
): Match | null {
  return matchDetails?.match ?? matchContext?.match ?? null;
}

// Cette fonction formate une date courte pour le hero match.
function formatShortDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

// Cette fonction formate l’heure du coup d’envoi.
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

// Cette fonction affiche la fraîcheur la plus pertinente disponible.
function getFreshnessLabel(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
) {
  const value =
    matchDetails?.data_freshness.last_updated ??
    matchContext?.data_freshness.match_last_updated ??
    matchDetails?.match.last_updated ??
    matchContext?.match.last_updated ??
    null;

  return value ? formatDateTime(value) : "Non datée";
}

// Cette fonction récupère le classement disponible d’une équipe.
function getStanding(
  matchContext: MatchContextResponse | null,
  teamType: "home" | "away",
): TeamStanding | null {
  return teamType === "home"
    ? matchContext?.context.home_team_standing ?? null
    : matchContext?.context.away_team_standing ?? null;
}

// Cette fonction affiche le classement d’une équipe si disponible.
function getStandingLabel(
  matchContext: MatchContextResponse | null,
  teamType: "home" | "away",
) {
  const standing = getStanding(matchContext, teamType);

  if (!standing) {
    return "Classement non fourni";
  }

  return `${standing.position}e · ${standing.points} pts`;
}

// Cette fonction prépare le libellé de journée.
function getMatchdayLabel(match: Match) {
  return match.matchday ? `Journée ${match.matchday}` : "Journée non précisée";
}

// Cette fonction calcule une moyenne par match à partir d’un classement.
function getAveragePerGame(value: number, playedGames: number) {
  if (!playedGames) {
    return null;
  }

  return value / playedGames;
}

// Cette fonction formate une moyenne numérique lisible.
function formatAverage(value: number | null) {
  return value === null ? "—" : value.toFixed(1);
}

// Cette fonction transforme une valeur en largeur de barre visuelle.
function getBarWidth(value: number | null, maxValue: number) {
  if (value === null || maxValue <= 0) {
    return 14;
  }

  return Math.min(100, Math.max(18, Math.round((value / maxValue) * 100)));
}

// Cette fonction copie le lien de la page quand le navigateur le permet.
function copyCurrentPageLink() {
  if (typeof window === "undefined" || !window.navigator?.clipboard) {
    return;
  }

  void window.navigator.clipboard.writeText(window.location.href);
}

// Ce composant affiche un logo d’équipe avec un fallback texte.
function TeamLogo({ team }: { team: Team }) {
  const teamLabel = getTeamDisplayName(team);

  return (
    <span className="rb-detail-v2-team-logo" aria-label={`Logo ${teamLabel}`}>
      <span className="rb-detail-v2-team-logo__fallback">
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

// Ce composant affiche la ligne supérieure de contexte de la fiche match.
function DetailTopbar({
  match,
  onNavigate,
}: {
  match: Match;
  onNavigate: (screen: AppScreen) => void;
}) {
  return (
    <header className="rb-detail-v2-topbar">
      <button type="button" onClick={() => onNavigate("matches")}>
        ← Retour aux matchs
      </button>

      <div>
        <span>{match.competition.name}</span>
        <strong>{getMatchdayLabel(match)}</strong>
      </div>

      <button type="button" onClick={copyCurrentPageLink}>
        Partager le match
      </button>
    </header>
  );
}

// Ce composant affiche le hero principal du match sélectionné.
function MatchHero({
  match,
  matchContext,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
}) {
  return (
    <section className="rb-detail-v2-hero" aria-label="Résumé de la rencontre">
      <span className="rb-detail-v2-hero__glow" aria-hidden="true" />
      <span className="rb-detail-v2-hero__pitch" aria-hidden="true" />

      <div className="rb-detail-v2-team rb-detail-v2-team--home">
        <TeamLogo team={match.home_team} />
        <div>
          <p>Domicile</p>
          <h2>{getTeamDisplayName(match.home_team)}</h2>
          <span>{getStandingLabel(matchContext, "home")}</span>
        </div>
      </div>

      <div className="rb-detail-v2-hero-center">
        <p>{formatShortDate(match.utc_date)}</p>
        <strong>{formatKickoffTime(match.utc_date)}</strong>
        <span>{formatMatchStatus(match.status)}</span>
        <small>{match.competition.name} · {getMatchdayLabel(match)}</small>
      </div>

      <div className="rb-detail-v2-team rb-detail-v2-team--away">
        <TeamLogo team={match.away_team} />
        <div>
          <p>Extérieur</p>
          <h2>{getTeamDisplayName(match.away_team)}</h2>
          <span>{getStandingLabel(matchContext, "away")}</span>
        </div>
      </div>
    </section>
  );
}

// Ce composant affiche les onglets internes de la fiche match.
function DetailTabs({
  activeTab,
  onSelectTab,
}: {
  activeTab: DetailTabKey;
  onSelectTab: (tab: DetailTabKey) => void;
}) {
  return (
    <nav className="rb-detail-v2-tabs" aria-label="Navigation interne détail match">
      {DETAIL_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={
            activeTab === tab.key
              ? "rb-detail-v2-tab rb-detail-v2-tab--active"
              : "rb-detail-v2-tab"
          }
          onClick={() => onSelectTab(tab.key)}
        >
          <span>{tab.icon}</span>
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

// Cette fonction prépare les cartes d’analyse synthétique selon les données disponibles.
function buildInsightCards(
  match: Match,
  matchContext: MatchContextResponse | null,
): InsightCard[] {
  const homeStanding = getStanding(matchContext, "home");
  const awayStanding = getStanding(matchContext, "away");
  const homeGoalsForAvg = homeStanding
    ? getAveragePerGame(homeStanding.goals_for, homeStanding.played_games)
    : null;
  const awayGoalsForAvg = awayStanding
    ? getAveragePerGame(awayStanding.goals_for, awayStanding.played_games)
    : null;
  const homeGoalsAgainstAvg = homeStanding
    ? getAveragePerGame(homeStanding.goals_against, homeStanding.played_games)
    : null;
  const awayGoalsAgainstAvg = awayStanding
    ? getAveragePerGame(awayStanding.goals_against, awayStanding.played_games)
    : null;

  return [
    {
      icon: "⌁",
      tone: "teal",
      title: "État de forme",
      description: homeStanding && awayStanding
        ? `${getTeamShortName(match.home_team)} ${homeStanding.position}e, ${getTeamShortName(match.away_team)} ${awayStanding.position}e : première lecture du rapport de forces.`
        : "La source confirme l’affiche, mais ne fournit pas encore de classement exploitable.",
      badge: homeStanding && awayStanding ? "Lecture classements" : "Lecture limitée",
    },
    {
      icon: "◎",
      tone: "red",
      title: "Attaque",
      description: homeGoalsForAvg !== null && awayGoalsForAvg !== null
        ? `Volume offensif moyen : ${formatAverage(homeGoalsForAvg)} vs ${formatAverage(awayGoalsForAvg)} buts par match.`
        : "Le volume offensif détaillé sera affiché uniquement lorsqu’il est confirmé par la source.",
      badge: homeGoalsForAvg !== null && awayGoalsForAvg !== null ? "Signal offensif" : "Signal prudent",
    },
    {
      icon: "◌",
      tone: "amber",
      title: "Défense",
      description: homeGoalsAgainstAvg !== null && awayGoalsAgainstAvg !== null
        ? `Buts encaissés moyens : ${formatAverage(homeGoalsAgainstAvg)} vs ${formatAverage(awayGoalsAgainstAvg)}.`
        : "La lecture défensive reste volontairement prudente sans statistique confirmée.",
      badge: homeGoalsAgainstAvg !== null && awayGoalsAgainstAvg !== null ? "Point défensif" : "À surveiller",
    },
    {
      icon: "▣",
      tone: "blue",
      title: "Contexte",
      description: `${match.competition.name}, ${getMatchdayLabel(match).toLowerCase()}, statut ${formatMatchStatus(match.status).toLowerCase()}.`,
      badge: "Avant-match",
    },
  ];
}

// Ce composant affiche une carte courte d’analyse pré-match.
function AnalysisInsightCard({ card }: { card: InsightCard }) {
  return (
    <article className={`rb-detail-v2-insight-card rb-detail-v2-insight-card--${card.tone}`}>
      <span>{card.icon}</span>
      <div>
        <h4>{card.title}</h4>
        <p>{card.description}</p>
      </div>
      <strong>{card.badge}</strong>
    </article>
  );
}

// Cette fonction prépare les indicateurs comparatifs affichables sans inventer de données.
function buildMetricCards(matchContext: MatchContextResponse | null): MetricCard[] {
  const homeStanding = getStanding(matchContext, "home");
  const awayStanding = getStanding(matchContext, "away");
  const homeGoalsForAvg = homeStanding
    ? getAveragePerGame(homeStanding.goals_for, homeStanding.played_games)
    : null;
  const awayGoalsForAvg = awayStanding
    ? getAveragePerGame(awayStanding.goals_for, awayStanding.played_games)
    : null;
  const homeGoalsAgainstAvg = homeStanding
    ? getAveragePerGame(homeStanding.goals_against, homeStanding.played_games)
    : null;
  const awayGoalsAgainstAvg = awayStanding
    ? getAveragePerGame(awayStanding.goals_against, awayStanding.played_games)
    : null;
  const maxPoints = Math.max(homeStanding?.points ?? 0, awayStanding?.points ?? 0, 1);
  const maxGoalsFor = Math.max(homeGoalsForAvg ?? 0, awayGoalsForAvg ?? 0, 1);
  const maxGoalsAgainst = Math.max(homeGoalsAgainstAvg ?? 0, awayGoalsAgainstAvg ?? 0, 1);
  const homeGoalDifference = homeStanding?.goal_difference ?? null;
  const awayGoalDifference = awayStanding?.goal_difference ?? null;
  const maxGoalDifference = Math.max(
    Math.abs(homeGoalDifference ?? 0),
    Math.abs(awayGoalDifference ?? 0),
    1,
  );

  return [
    {
      label: "Classement",
      note: "position officielle",
      homeValue: homeStanding ? `${homeStanding.position}e` : "—",
      awayValue: awayStanding ? `${awayStanding.position}e` : "—",
      homeBar: homeStanding ? getBarWidth(22 - homeStanding.position, 22) : 14,
      awayBar: awayStanding ? getBarWidth(22 - awayStanding.position, 22) : 14,
      accent: "teal",
    },
    {
      label: "Points",
      note: "cumul compétition",
      homeValue: homeStanding ? String(homeStanding.points) : "—",
      awayValue: awayStanding ? String(awayStanding.points) : "—",
      homeBar: getBarWidth(homeStanding?.points ?? null, maxPoints),
      awayBar: getBarWidth(awayStanding?.points ?? null, maxPoints),
      accent: "teal",
    },
    {
      label: "Buts marqués",
      note: "moyenne / match",
      homeValue: formatAverage(homeGoalsForAvg),
      awayValue: formatAverage(awayGoalsForAvg),
      homeBar: getBarWidth(homeGoalsForAvg, maxGoalsFor),
      awayBar: getBarWidth(awayGoalsForAvg, maxGoalsFor),
      accent: "teal",
    },
    {
      label: "Buts encaissés",
      note: "moyenne / match",
      homeValue: formatAverage(homeGoalsAgainstAvg),
      awayValue: formatAverage(awayGoalsAgainstAvg),
      homeBar: getBarWidth(homeGoalsAgainstAvg, maxGoalsAgainst),
      awayBar: getBarWidth(awayGoalsAgainstAvg, maxGoalsAgainst),
      accent: "red",
    },
    {
      label: "Différence buts",
      note: "signal d’équilibre",
      homeValue: homeGoalDifference === null ? "—" : String(homeGoalDifference),
      awayValue: awayGoalDifference === null ? "—" : String(awayGoalDifference),
      homeBar: getBarWidth(homeGoalDifference === null ? null : Math.abs(homeGoalDifference), maxGoalDifference),
      awayBar: getBarWidth(awayGoalDifference === null ? null : Math.abs(awayGoalDifference), maxGoalDifference),
      accent: "neutral",
    },
  ];
}

// Ce composant affiche un indicateur comparatif entre les deux équipes.
function MetricComparisonCard({
  metric,
  homeTeam,
  awayTeam,
}: {
  metric: MetricCard;
  homeTeam: Team;
  awayTeam: Team;
}) {
  const style = {
    "--home-width": `${metric.homeBar}%`,
    "--away-width": `${metric.awayBar}%`,
  } as CSSProperties;

  return (
    <article className={`rb-detail-v2-metric-card rb-detail-v2-metric-card--${metric.accent}`} style={style}>
      <div className="rb-detail-v2-metric-card__header">
        <h4>{metric.label}</h4>
        <span>{metric.note}</span>
      </div>

      <div className="rb-detail-v2-metric-card__values">
        <p>
          <small>{getTeamShortName(homeTeam)}</small>
          <strong>{metric.homeValue}</strong>
          <span aria-hidden="true" />
        </p>
        <p>
          <small>{getTeamShortName(awayTeam)}</small>
          <strong>{metric.awayValue}</strong>
          <span aria-hidden="true" />
        </p>
      </div>
    </article>
  );
}

// Ce composant affiche les cartes d’analyse pré-match.
function PreMatchAnalysisSection({
  match,
  matchContext,
  onNavigate,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
  onNavigate: (screen: AppScreen) => void;
}) {
  const insightCards = useMemo(
    () => buildInsightCards(match, matchContext),
    [match, matchContext],
  );

  return (
    <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
      <div className="rb-detail-v2-section-header">
        <div>
          <p>Analyse pré-match</p>
          <h3>Lecture synthétique de la rencontre</h3>
        </div>
        <button type="button" onClick={() => onNavigate("analysis")}>
          Voir l’analyse complète →
        </button>
      </div>

      <div className="rb-detail-v2-insight-grid">
        {insightCards.map((card) => (
          <AnalysisInsightCard key={card.title} card={card} />
        ))}
      </div>
    </section>
  );
}

// Ce composant affiche les indicateurs clés comparatifs.
function KeyIndicatorsSection({
  match,
  matchContext,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
}) {
  const metrics = useMemo(() => buildMetricCards(matchContext), [matchContext]);

  return (
    <section className="rb-detail-v2-card rb-detail-v2-stats-card">
      <div className="rb-detail-v2-section-header">
        <div>
          <p>Indicateurs clés</p>
          <h3>Comparaison avant-match</h3>
        </div>
        <span>Données source</span>
      </div>

      <div className="rb-detail-v2-metric-grid">
        {metrics.map((metric) => (
          <MetricComparisonCard
            key={metric.label}
            metric={metric}
            homeTeam={match.home_team}
            awayTeam={match.away_team}
          />
        ))}
      </div>
    </section>
  );
}

// Ce composant affiche une section compacte pour la forme récente.
function RecentMatchesSection({ match }: { match: Match }) {
  return (
    <section className="rb-detail-v2-card rb-detail-v2-recent-card">
      <div className="rb-detail-v2-section-header">
        <div>
          <p>Derniers matchs</p>
          <h3>Forme récente</h3>
        </div>
        <span>Historique source</span>
      </div>

      <div className="rb-detail-v2-recent-grid">
        {[match.home_team, match.away_team].map((team) => (
          <article key={`${team.id ?? team.name}-recent`} className="rb-detail-v2-recent-team">
            <div className="rb-detail-v2-recent-team__heading">
              <TeamLogo team={team} />
              <strong>{getTeamDisplayName(team)}</strong>
            </div>
            <div>
              <span>Calendrier suivi</span>
              <span>Historique détaillé non fourni</span>
              <span>Forme à compléter par source enrichie</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

// Ce composant affiche une carte simple de la sidebar.
function SidebarCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="rb-detail-v2-side-card">
      <h3>{title}</h3>
      {children}
    </article>
  );
}

// Ce composant affiche une ligne d’information match.
function MatchInfoLine({ line }: { line: InfoLine }) {
  return (
    <p className="rb-detail-v2-info-line">
      <span>{line.icon}</span>
      <small>{line.label}</small>
      <strong>{line.value}</strong>
    </p>
  );
}

// Ce composant affiche les informations principales du match dans la sidebar.
function MatchInfoCard({
  match,
  freshnessLabel,
}: {
  match: Match;
  freshnessLabel: string;
}) {
  const infoLines: InfoLine[] = [
    { icon: "▦", label: "Compétition", value: match.competition.name },
    { icon: "◌", label: "Journée", value: getMatchdayLabel(match) },
    { icon: "◷", label: "Date", value: formatShortDate(match.utc_date) },
    { icon: "⌚", label: "Heure", value: formatKickoffTime(match.utc_date) },
    { icon: "●", label: "Statut", value: formatMatchStatus(match.status) },
    { icon: "↻", label: "Fraîcheur", value: freshnessLabel },
  ];

  return (
    <SidebarCard title="Informations match">
      <div className="rb-detail-v2-info-list">
        {infoLines.map((line) => (
          <MatchInfoLine key={line.label} line={line} />
        ))}
      </div>
    </SidebarCard>
  );
}

// Ce composant affiche l’état du face à face lorsque l’historique n’est pas fourni.
function HeadToHeadCard() {
  return (
    <SidebarCard title="Face à face">
      <div className="rb-detail-v2-empty-mini">
        <span>◇</span>
        <p>Les confrontations directes ne sont pas exposées par la source actuelle.</p>
      </div>
      <button type="button">Historique non fourni</button>
    </SidebarCard>
  );
}

// Ce composant affiche les enjeux et limites utiles dans la sidebar.
function ContextIssuesCard({
  match,
  matchContext,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
}) {
  const facts = matchContext?.context.summary.main_facts ?? [];
  const items = facts.length
    ? facts.slice(0, 3)
    : [
        "Rencontre suivie dans le périmètre avant-match RubyBets.",
        `${match.competition.name} · ${getMatchdayLabel(match)}.`,
        "Les données partielles sont affichées avec prudence.",
      ];

  return (
    <SidebarCard title="Contexte & enjeux">
      <ul className="rb-detail-v2-context-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </SidebarCard>
  );
}

// Ce composant affiche la notice responsable de la fiche match.
function ResponsibleNoticeCard() {
  return (
    <article className="rb-detail-v2-responsible-card">
      <span>◇</span>
      <div>
        <strong>RubyBets est un outil d’aide à la décision.</strong>
        <p>
          Les analyses reposent sur des données réelles, mais ne garantissent aucun résultat sportif.
        </p>
      </div>
    </article>
  );
}

// Ce composant affiche un état propre pour les onglets non encore détaillés.
function PendingTabContent({ activeTab }: { activeTab: DetailTabKey }) {
  const currentTab = DETAIL_TABS.find((tab) => tab.key === activeTab);

  return (
    <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
      <p>Vue dédiée</p>
      <h3>{currentTab?.label ?? "Section"}</h3>
      <p>
        Cette lecture sera affichée avec le même niveau de détail dès que les données correspondantes seront disponibles dans la source.
      </p>
    </section>
  );
}

// Ce composant affiche le contenu de la vue d’ensemble.
function OverviewTabContent({
  match,
  matchContext,
  onNavigate,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
  onNavigate: (screen: AppScreen) => void;
}) {
  return (
    <>
      <PreMatchAnalysisSection
        match={match}
        matchContext={matchContext}
        onNavigate={onNavigate}
      />
      <KeyIndicatorsSection match={match} matchContext={matchContext} />
      <RecentMatchesSection match={match} />
    </>
  );
}

// Ce composant structure l’écran Détail match sans modifier la logique métier existante.
function MatchDetailsScreen({
  matchDetails,
  matchContext,
  matchDetailsStatus,
  matchContextStatus,
  onNavigate,
}: MatchDetailsScreenProps) {
  const [activeTab, setActiveTab] = useState<DetailTabKey>("overview");
  const selectedMatch = getSelectedMatch(matchDetails, matchContext);
  const freshnessLabel = getFreshnessLabel(matchDetails, matchContext);
  const statusMessage = matchDetailsStatus || matchContextStatus;

  if (!selectedMatch) {
    return (
      <div className="rb-detail-v2 rb-detail-v2--premium">
        <article className="rb-detail-v2-empty-state">
          <p>Détail match</p>
          <h2>Aucun match sélectionné</h2>
          <p>{statusMessage || "Sélectionnez une rencontre depuis l’écran Matchs."}</p>
          <button type="button" onClick={() => onNavigate("matches")}>
            Retour aux matchs
          </button>
        </article>
      </div>
    );
  }

  if (!hasKnownTeams(selectedMatch)) {
    return (
      <div className="rb-detail-v2 rb-detail-v2--premium">
        <DetailTopbar match={selectedMatch} onNavigate={onNavigate} />
        <article className="rb-detail-v2-empty-state">
          <p>Analyse limitée</p>
          <h2>Équipes à confirmer</h2>
          <p>
            Cette rencontre est suivie par RubyBets, mais les équipes ne sont pas encore confirmées. L’analyse détaillée reste donc désactivée jusqu’à publication de l’affiche complète.
          </p>
          <button type="button" onClick={() => onNavigate("matches")}>
            Retour aux matchs
          </button>
        </article>
      </div>
    );
  }

  return (
    <div className="rb-detail-v2 rb-detail-v2--premium">
      <DetailTopbar match={selectedMatch} onNavigate={onNavigate} />
      <MatchHero match={selectedMatch} matchContext={matchContext} />
      <DetailTabs activeTab={activeTab} onSelectTab={setActiveTab} />

      <main className="rb-detail-v2-layout">
        <section className="rb-detail-v2-main-column">
          {activeTab === "overview" ? (
            <OverviewTabContent
              match={selectedMatch}
              matchContext={matchContext}
              onNavigate={onNavigate}
            />
          ) : (
            <PendingTabContent activeTab={activeTab} />
          )}
        </section>

        <aside className="rb-detail-v2-side-column">
          <MatchInfoCard match={selectedMatch} freshnessLabel={freshnessLabel} />
          <HeadToHeadCard />
          <ContextIssuesCard match={selectedMatch} matchContext={matchContext} />
          <ResponsibleNoticeCard />
        </aside>
      </main>

      <p className="rb-detail-v2-footer-note">
        Outil d’aide à la décision avant-match. RubyBets ne permet aucun pari réel et ne promet aucun résultat sportif.
      </p>
    </div>
  );
}

export default MatchDetailsScreen;

// Schéma de communication du fichier :
// MatchDetailsScreen.tsx
// ├── reçoit le détail et le contexte depuis App.tsx
// ├── utilise les types MatchDetailsResponse et MatchContextResponse de models/rubybets.ts
// ├── utilise les helpers d’affichage de helpers/displayText.ts
// ├── déclenche la navigation vers Matchs, Analyse et Prédictions via onNavigate
// └── reste isolé visuellement avec les classes rb-detail-v2-* définies dans App.css
