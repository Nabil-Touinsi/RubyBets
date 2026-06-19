// Ce fichier affiche l’écran Détail match de RubyBets sous forme de fiche premium avant-match.

import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type {
  HeadToHeadMatch,
  Match,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchLineupPlayer,
  MatchLineupSide,
  MatchLineupsResponse,
  MatchNewsContextResponse,
  MatchDetailsResponse,
  Team,
  TeamFormSummary,
  TeamHistoryBlock,
  TeamHistoryResponse,
  TeamRecentMatch,
  TeamStanding,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import MatchNewsContextSection from "../components/MatchNewsContextSection";
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
  matchAnalysis: MatchAnalysisResponse | null;
  matchLineups: MatchLineupsResponse | null;
  matchNewsContext: MatchNewsContextResponse | null;
  teamHistory: TeamHistoryResponse | null;
  matchDetailsStatus: string;
  matchContextStatus: string;
  matchAnalysisStatus: string;
  matchLineupsStatus: string;
  matchNewsContextStatus: string;
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

type FormTrendSignal = {
  label: string;
  homeValue: string;
  awayValue: string;
  reading: string;
  tone: "teal" | "red" | "amber" | "blue";
};

type HeadToHeadHistoricalSummary = {
  total: number;
  calculable: number;
  homeWins: number;
  awayWins: number;
  draws: number;
  homeGoals: number;
  awayGoals: number;
};

type HeadToHeadSummaryCard = {
  icon: string;
  tone: "teal" | "red" | "amber" | "blue";
  title: string;
  description: string;
  badge: string;
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

// Cette fonction formate une date courte pour un match récent quand la date peut être absente.
function formatRecentMatchDate(value: string | null) {
  if (!value) {
    return "Date non fournie";
  }

  return formatShortDate(value);
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

// Cette fonction affiche un statut lisible pour l’analyse détaillée chargée depuis le backend.
function getAnalysisStatusLabel(matchAnalysis: MatchAnalysisResponse | null) {
  const responseStatus = (matchAnalysis as { status?: string } | null)?.status;

  if (responseStatus === "partial") {
    return "Analyse partielle";
  }

  if (responseStatus === "available") {
    return "Analyse disponible";
  }

  if (responseStatus === "unavailable") {
    return "Analyse indisponible";
  }

  return matchAnalysis ? "Analyse chargée" : "Analyse en attente";
}

// Cette fonction transforme le statut backend des compositions en libellé lisible.
function getLineupsStatusLabel(matchLineups: MatchLineupsResponse | null) {
  const compositionStatus = matchLineups?.lineups.composition_status;

  if (compositionStatus === "official_available") {
    return "Composition officielle disponible";
  }

  if (compositionStatus === "predicted_available") {
    return "Composition probable disponible";
  }

  if (matchLineups?.status === "unavailable") {
    return "Composition indisponible";
  }

  return matchLineups ? "Données composition chargées" : "Composition en attente";
}

// Cette fonction sélectionne les joueurs à afficher selon la donnée la plus fiable disponible.
function getDisplayLineupPlayers(lineupSide: MatchLineupSide): MatchLineupPlayer[] {
  if (lineupSide.starting_lineups.length) {
    return lineupSide.starting_lineups;
  }

  if (lineupSide.predicted_lineups.length) {
    return lineupSide.predicted_lineups;
  }

  return [];
}

// Cette fonction indique si la liste affichée correspond à une composition officielle ou probable.
function getLineupModeLabel(lineupSide: MatchLineupSide) {
  if (lineupSide.starting_lineups.length || lineupSide.official_available) {
    return "Composition officielle";
  }

  if (lineupSide.predicted_lineups.length || lineupSide.predicted_available) {
    return "Composition probable";
  }

  return "Composition non disponible";
}

// Cette fonction sécurise l'affichage du numéro d'un joueur sans inventer de valeur.
function getPlayerNumberLabel(player: MatchLineupPlayer) {
  return player.number ? `#${player.number}` : "—";
}

// Cette fonction sécurise l'affichage du club d'un joueur sans inventer de donnée.
function getPlayerClubLabel(player: MatchLineupPlayer) {
  return player.club_name || "Club non fourni";
}

// Cette fonction prépare les libellés de disponibilité visibles en haut de l'onglet compositions.
function buildLineupsAvailabilityItems(matchLineups: MatchLineupsResponse | null) {
  return [
    {
      label: "Composition officielle",
      value: matchLineups?.lineups.official_available ? "disponible" : "non disponible",
    },
    {
      label: "Composition probable",
      value: matchLineups?.lineups.predicted_available ? "disponible" : "non disponible",
    },
    {
      label: "Absents / incertains",
      value: matchLineups?.data_used.missing_players ? "disponibles" : "non disponibles",
    },
    {
      label: "Effectif complet",
      value: matchLineups?.lineups.squad_available ? "disponible" : "non disponible",
    },
    {
      label: "Cotes",
      value: matchLineups?.data_used.odds_used ? "utilisées" : "non utilisées",
    },
  ];
}

// Cette fonction transforme une valeur d’indicateur en texte lisible, même si la source retourne un objet partiel.
function formatAnalysisFactorValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Non fourni";
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  if (typeof value === "string" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.length
      ? value.map((item: unknown) => formatAnalysisFactorValue(item)).join(" · ")
      : "Non fourni";
  }

  if (typeof value === "object") {
    const entries: string[] = Object.entries(value as Record<string, unknown>)
      .filter(([, entryValue]) => entryValue !== null && entryValue !== undefined)
      .map(
        ([key, entryValue]) =>
          `${key} : ${formatAnalysisFactorValue(entryValue)}`
      );

    return entries.length ? entries.join(" · ") : "Non fourni";
  }

  return "Non fourni";
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

// Cette fonction transforme le résultat W/D/L en libellé lisible.
function getRecentResultLabel(result: TeamRecentMatch["team_result"]) {
  if (result === "W") {
    return "Victoire";
  }

  if (result === "D") {
    return "Nul";
  }

  return "Défaite";
}

// Cette fonction affiche le score d’un match récent.
function formatRecentScore(recentMatch: TeamRecentMatch) {
  if (
    recentMatch.home_score === null ||
    recentMatch.away_score === null
  ) {
    return "Score non fourni";
  }

  return `${recentMatch.home_score} - ${recentMatch.away_score}`;
}


// Cette fonction affiche le score d’une confrontation directe.
function formatHeadToHeadScore(headToHeadMatch: HeadToHeadMatch) {
  if (
    headToHeadMatch.home_score === null ||
    headToHeadMatch.away_score === null
  ) {
    return "Score non fourni";
  }

  return `${headToHeadMatch.home_score} - ${headToHeadMatch.away_score}`;
}

// Cette fonction prépare le libellé d’une confrontation directe.
function formatHeadToHeadTeams(headToHeadMatch: HeadToHeadMatch) {
  const homeTeam = headToHeadMatch.home_team ?? "Équipe domicile";
  const awayTeam = headToHeadMatch.away_team ?? "Équipe extérieure";

  return `${homeTeam} vs ${awayTeam}`;
}

// Cette fonction normalise un nom d’équipe pour comparer les confrontations sans dépendre des accents ou de la casse.
function normalizeTeamNameForComparison(value: string | null | undefined) {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "")
    .trim();
}

// Cette fonction vérifie si un nom d’équipe d’une confrontation correspond à l’équipe courante.
function isSameHistoricalTeam(candidate: string | null, team: Team) {
  const candidateName = normalizeTeamNameForComparison(candidate);
  const teamNames = [team.name, team.short_name, team.tla]
    .map((name) => normalizeTeamNameForComparison(name))
    .filter(Boolean);

  return teamNames.some((teamName) => candidateName === teamName || candidateName.includes(teamName) || teamName.includes(candidateName));
}

// Cette fonction récupère les buts d’une équipe courante dans une confrontation directe, si la correspondance est possible.
function getHistoricalGoalsForTeam(
  headToHeadMatch: HeadToHeadMatch,
  team: Team,
): number | null {
  if (
    headToHeadMatch.home_score === null ||
    headToHeadMatch.away_score === null
  ) {
    return null;
  }

  if (isSameHistoricalTeam(headToHeadMatch.home_team, team)) {
    return headToHeadMatch.home_score;
  }

  if (isSameHistoricalTeam(headToHeadMatch.away_team, team)) {
    return headToHeadMatch.away_score;
  }

  return null;
}


// Cette fonction produit une synthèse chiffrée des confrontations directes sans inventer les scores manquants.
function buildHeadToHeadHistoricalSummary(
  headToHeadMatches: HeadToHeadMatch[],
  match: Match,
): HeadToHeadHistoricalSummary {
  return headToHeadMatches.reduce<HeadToHeadHistoricalSummary>(
    (summary, headToHeadMatch) => {
      const homeGoals = getHistoricalGoalsForTeam(headToHeadMatch, match.home_team);
      const awayGoals = getHistoricalGoalsForTeam(headToHeadMatch, match.away_team);

      if (homeGoals === null || awayGoals === null) {
        return summary;
      }

      const nextSummary = {
        ...summary,
        calculable: summary.calculable + 1,
        homeGoals: summary.homeGoals + homeGoals,
        awayGoals: summary.awayGoals + awayGoals,
      };

      if (homeGoals > awayGoals) {
        return { ...nextSummary, homeWins: nextSummary.homeWins + 1 };
      }

      if (awayGoals > homeGoals) {
        return { ...nextSummary, awayWins: nextSummary.awayWins + 1 };
      }

      return { ...nextSummary, draws: nextSummary.draws + 1 };
    },
    {
      total: headToHeadMatches.length,
      calculable: 0,
      homeWins: 0,
      awayWins: 0,
      draws: 0,
      homeGoals: 0,
      awayGoals: 0,
    },
  );
}

// Cette fonction transforme une confrontation directe en lecture courte et responsable.
function buildHeadToHeadMatchReading(headToHeadMatch: HeadToHeadMatch, match: Match) {
  const homeGoals = getHistoricalGoalsForTeam(headToHeadMatch, match.home_team);
  const awayGoals = getHistoricalGoalsForTeam(headToHeadMatch, match.away_team);

  if (homeGoals === null || awayGoals === null) {
    return "Score ou correspondance d’équipe non exploitable.";
  }

  if (homeGoals > awayGoals) {
    return `Victoire historique ${getTeamShortName(match.home_team)}.`;
  }

  if (awayGoals > homeGoals) {
    return `Victoire historique ${getTeamShortName(match.away_team)}.`;
  }

  return "Match nul historique.";
}

// Cette fonction prépare les cartes d’interprétation de l’onglet Face à face.
function buildHeadToHeadSummaryCards(
  summary: HeadToHeadHistoricalSummary,
  match: Match,
  responsibleNote: string | null,
): HeadToHeadSummaryCard[] {
  const hasCalculableMatches = summary.calculable > 0;
  const balanceDescription = hasCalculableMatches
    ? `${getTeamShortName(match.home_team)} : ${summary.homeWins} victoire(s), ${getTeamShortName(match.away_team)} : ${summary.awayWins} victoire(s), ${summary.draws} nul(s).`
    : "Les confrontations disponibles ne fournissent pas assez de scores comparables pour établir un bilan chiffré.";
  const goalsDescription = hasCalculableMatches
    ? `${summary.homeGoals} but(s) pour ${getTeamShortName(match.home_team)} et ${summary.awayGoals} pour ${getTeamShortName(match.away_team)} sur les matchs exploitables.`
    : "Les buts cumulés ne sont pas calculés lorsque les scores ou les équipes ne sont pas clairement exploitables.";

  return [
    {
      icon: "◇",
      tone: "teal",
      title: "Volume historique",
      description: `${summary.total} confrontation(s) directe(s) trouvée(s), dont ${summary.calculable} avec score exploitable pour le bilan.`,
      badge: "Disponibilité",
    },
    {
      icon: "▦",
      tone: "blue",
      title: "Bilan comparé",
      description: balanceDescription,
      badge: "Historique",
    },
    {
      icon: "◎",
      tone: "amber",
      title: "Buts cumulés",
      description: goalsDescription,
      badge: "Scores",
    },
    {
      icon: "◷",
      tone: "red",
      title: "Lecture responsable",
      description: responsibleNote ?? "Le face-à-face donne un contexte historique, mais ne suffit pas à anticiper le résultat d’un match.",
      badge: "Prudence",
    },
  ];
}

// Cette fonction récupère le bloc historique correspondant à une équipe.
function getTeamHistoryBlock(
  teamHistory: TeamHistoryResponse | null,
  teamType: "home" | "away",
): TeamHistoryBlock | null {
  return teamType === "home"
    ? teamHistory?.home_team_history ?? null
    : teamHistory?.away_team_history ?? null;
}

// Cette fonction récupère la synthèse de forme d’une équipe quand l’historique est disponible.
function getTeamFormSummary(
  teamHistory: TeamHistoryResponse | null,
  teamType: "home" | "away",
): TeamFormSummary | null {
  return getTeamHistoryBlock(teamHistory, teamType)?.form_summary ?? null;
}

// Cette fonction calcule les points de forme récents selon la règle football classique.
function getRecentFormPoints(formSummary: TeamFormSummary | null) {
  if (!formSummary) {
    return null;
  }

  return formSummary.wins * 3 + formSummary.draws;
}

// Cette fonction calcule le maximum de points possibles sur les matchs récents analysés.
function getRecentFormMaxPoints(formSummary: TeamFormSummary | null) {
  if (!formSummary) {
    return null;
  }

  return formSummary.matches_count * 3;
}

// Cette fonction affiche les points de forme sous forme de fraction lisible.
function formatRecentFormPointsFraction(formSummary: TeamFormSummary | null) {
  const points = getRecentFormPoints(formSummary);
  const maxPoints = getRecentFormMaxPoints(formSummary);

  if (points === null || maxPoints === null || maxPoints <= 0) {
    return "—";
  }

  return `${points} / ${maxPoints} pts`;
}

// Cette fonction transforme le ratio de points de forme en largeur de barre visuelle.
function getRecentFormBarWidth(formSummary: TeamFormSummary | null) {
  const points = getRecentFormPoints(formSummary);
  const maxPoints = getRecentFormMaxPoints(formSummary);

  if (points === null || maxPoints === null || maxPoints <= 0) {
    return 14;
  }

  return getBarWidth(points, maxPoints);
}

// Cette fonction affiche un bilan de forme sous une forme courte et lisible.
function formatRecentFormRecord(formSummary: TeamFormSummary | null) {
  if (!formSummary) {
    return "Bilan non disponible";
  }

  return `${formSummary.wins}V - ${formSummary.draws}N - ${formSummary.losses}D`;
}

// Cette fonction formate une moyenne issue de l’historique récent avec deux décimales.
function formatHistoryAverage(value: number | null | undefined) {
  return typeof value === "number" ? value.toFixed(2) : "—";
}

// Cette fonction calcule la différence de buts sur l’historique récent.
function getHistoryGoalDifference(formSummary: TeamFormSummary | null) {
  if (!formSummary) {
    return null;
  }

  return formSummary.goals_for - formSummary.goals_against;
}

// Cette fonction affiche une valeur signée pour les écarts de buts positifs ou négatifs.
function formatSignedMetric(value: number | null) {
  if (value === null) {
    return "—";
  }

  return value > 0 ? `+${value}` : String(value);
}

// Cette fonction affiche le statut de disponibilité de l’historique sous forme lisible.
function getTeamHistoryStatusLabel(teamHistory: TeamHistoryResponse | null) {
  if (!teamHistory) {
    return "Historique en attente";
  }

  if (teamHistory.data_status === "available") {
    return "Historique disponible";
  }

  if (teamHistory.data_status === "partial") {
    return "Historique partiel";
  }

  return "Historique indisponible";
}

// Cette fonction transforme une série W/D/L en libellés courts compréhensibles.
function formatRecentSeries(series: TeamFormSummary["recent_series"] | undefined) {
  if (!series?.length) {
    return "Série non disponible";
  }

  return series
    .map((result) => (result === "W" ? "V" : result === "D" ? "N" : "D"))
    .join(" · ");
}

// Cette fonction calcule le pourcentage de points pris sur la période récente analysée.
function getRecentFormRate(formSummary: TeamFormSummary | null) {
  const points = getRecentFormPoints(formSummary);
  const maxPoints = getRecentFormMaxPoints(formSummary);

  if (points === null || maxPoints === null || maxPoints <= 0) {
    return null;
  }

  return Math.round((points / maxPoints) * 100);
}

// Cette fonction vérifie si un bloc historique contient une forme exploitable.
function hasUsableHistoryBlock(historyBlock: TeamHistoryBlock | null) {
  return Boolean(historyBlock?.form_summary && historyBlock.form_summary.matches_count > 0);
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
  teamHistory: TeamHistoryResponse | null,
): InsightCard[] {
  const homeStanding = getStanding(matchContext, "home");
  const awayStanding = getStanding(matchContext, "away");
  const homeFormSummary = getTeamFormSummary(teamHistory, "home");
  const awayFormSummary = getTeamFormSummary(teamHistory, "away");

  const hasHistoryForm = Boolean(homeFormSummary && awayFormSummary);

  const homeGoalsForAvg = hasHistoryForm
    ? homeFormSummary?.avg_goals_for ?? null
    : homeStanding
      ? getAveragePerGame(homeStanding.goals_for, homeStanding.played_games)
      : null;
  const awayGoalsForAvg = hasHistoryForm
    ? awayFormSummary?.avg_goals_for ?? null
    : awayStanding
      ? getAveragePerGame(awayStanding.goals_for, awayStanding.played_games)
      : null;
  const homeGoalsAgainstAvg = hasHistoryForm
    ? homeFormSummary?.avg_goals_against ?? null
    : homeStanding
      ? getAveragePerGame(homeStanding.goals_against, homeStanding.played_games)
      : null;
  const awayGoalsAgainstAvg = hasHistoryForm
    ? awayFormSummary?.avg_goals_against ?? null
    : awayStanding
      ? getAveragePerGame(awayStanding.goals_against, awayStanding.played_games)
      : null;

  return [
    {
      icon: "⌁",
      tone: "teal",
      title: "État de forme",
      description: hasHistoryForm
        ? `${getTeamShortName(match.home_team)} : ${formatRecentFormRecord(homeFormSummary)} ; ${getTeamShortName(match.away_team)} : ${formatRecentFormRecord(awayFormSummary)}.`
        : homeStanding && awayStanding
          ? `${getTeamShortName(match.home_team)} ${homeStanding.position}e, ${getTeamShortName(match.away_team)} ${awayStanding.position}e : première lecture du rapport de forces.`
          : "La source confirme l’affiche, mais ne fournit pas encore de forme exploitable.",
      badge: hasHistoryForm ? "Forme récente" : "Lecture limitée",
    },
    {
      icon: "◎",
      tone: "red",
      title: "Attaque",
      description: homeGoalsForAvg !== null && awayGoalsForAvg !== null
        ? `${getTeamShortName(match.home_team)} marque ${formatHistoryAverage(homeGoalsForAvg)} but/match, contre ${formatHistoryAverage(awayGoalsForAvg)} pour ${getTeamShortName(match.away_team)}.`
        : "Les moyennes offensives ne sont pas encore entièrement disponibles.",
      badge: "Buts marqués",
    },
    {
      icon: "◷",
      tone: "amber",
      title: "Défense",
      description: homeGoalsAgainstAvg !== null && awayGoalsAgainstAvg !== null
        ? `${getTeamShortName(match.home_team)} encaisse ${formatHistoryAverage(homeGoalsAgainstAvg)} but/match, contre ${formatHistoryAverage(awayGoalsAgainstAvg)} pour ${getTeamShortName(match.away_team)}.`
        : "La lecture défensive reste dépendante des données disponibles.",
      badge: "Buts encaissés",
    },
    {
      icon: "◇",
      tone: "blue",
      title: "Contexte",
      description: hasHistoryForm
        ? `${match.competition.name} · ${getMatchdayLabel(match)}. Historique récent toutes compétitions confondues lorsque la source le permet.`
        : `${match.competition.name} · ${getMatchdayLabel(match)}. Analyse limitée aux données gratuites disponibles.`,
      badge: formatMatchStatus(match.status),
    },
  ];
}

// Cette fonction prépare les cartes d’indicateurs comparatifs.
function buildMetricCards(
  matchContext: MatchContextResponse | null,
  teamHistory: TeamHistoryResponse | null,
): MetricCard[] {
  const homeStanding = getStanding(matchContext, "home");
  const awayStanding = getStanding(matchContext, "away");
  const homeFormSummary = getTeamFormSummary(teamHistory, "home");
  const awayFormSummary = getTeamFormSummary(teamHistory, "away");
  const hasHistoryForm = Boolean(homeFormSummary && awayFormSummary);

  const homeGoalsForAvg = hasHistoryForm
    ? homeFormSummary?.avg_goals_for ?? null
    : homeStanding
      ? getAveragePerGame(homeStanding.goals_for, homeStanding.played_games)
      : null;
  const awayGoalsForAvg = hasHistoryForm
    ? awayFormSummary?.avg_goals_for ?? null
    : awayStanding
      ? getAveragePerGame(awayStanding.goals_for, awayStanding.played_games)
      : null;
  const homeGoalsAgainstAvg = hasHistoryForm
    ? homeFormSummary?.avg_goals_against ?? null
    : homeStanding
      ? getAveragePerGame(homeStanding.goals_against, homeStanding.played_games)
      : null;
  const awayGoalsAgainstAvg = hasHistoryForm
    ? awayFormSummary?.avg_goals_against ?? null
    : awayStanding
      ? getAveragePerGame(awayStanding.goals_against, awayStanding.played_games)
      : null;
  const homeGoalDifference = hasHistoryForm
    ? getHistoryGoalDifference(homeFormSummary)
    : homeStanding?.goal_difference ?? null;
  const awayGoalDifference = hasHistoryForm
    ? getHistoryGoalDifference(awayFormSummary)
    : awayStanding?.goal_difference ?? null;

  const maxPoints = Math.max(homeStanding?.points ?? 0, awayStanding?.points ?? 0, 1);
  const maxGoalsFor = Math.max(homeGoalsForAvg ?? 0, awayGoalsForAvg ?? 0, 1);
  const maxGoalsAgainst = Math.max(homeGoalsAgainstAvg ?? 0, awayGoalsAgainstAvg ?? 0, 1);
  const maxGoalDifference = Math.max(
    Math.abs(homeGoalDifference ?? 0),
    Math.abs(awayGoalDifference ?? 0),
    1,
  );

  return [
    {
      label: hasHistoryForm ? "Score de forme" : "Points",
      note: hasHistoryForm ? "points obtenus / max" : "classement actuel",
      homeValue: hasHistoryForm
        ? formatRecentFormPointsFraction(homeFormSummary)
        : homeStanding
          ? String(homeStanding.points)
          : "—",
      awayValue: hasHistoryForm
        ? formatRecentFormPointsFraction(awayFormSummary)
        : awayStanding
          ? String(awayStanding.points)
          : "—",
      homeBar: hasHistoryForm
        ? getRecentFormBarWidth(homeFormSummary)
        : getBarWidth(homeStanding?.points ?? null, maxPoints),
      awayBar: hasHistoryForm
        ? getRecentFormBarWidth(awayFormSummary)
        : getBarWidth(awayStanding?.points ?? null, maxPoints),
      accent: "neutral",
    },
    {
      label: "Buts marqués",
      note: "moyenne / match",
      homeValue: formatHistoryAverage(homeGoalsForAvg),
      awayValue: formatHistoryAverage(awayGoalsForAvg),
      homeBar: getBarWidth(homeGoalsForAvg, maxGoalsFor),
      awayBar: getBarWidth(awayGoalsForAvg, maxGoalsFor),
      accent: "teal",
    },
    {
      label: "Buts encaissés",
      note: "moyenne / match",
      homeValue: formatHistoryAverage(homeGoalsAgainstAvg),
      awayValue: formatHistoryAverage(awayGoalsAgainstAvg),
      homeBar: getBarWidth(homeGoalsAgainstAvg, maxGoalsAgainst),
      awayBar: getBarWidth(awayGoalsAgainstAvg, maxGoalsAgainst),
      accent: "red",
    },
    {
      label: "Différence buts",
      note: hasHistoryForm ? "total récent" : "signal d’équilibre",
      homeValue: formatSignedMetric(homeGoalDifference),
      awayValue: formatSignedMetric(awayGoalDifference),
      homeBar: getBarWidth(homeGoalDifference === null ? null : Math.abs(homeGoalDifference), maxGoalDifference),
      awayBar: getBarWidth(awayGoalDifference === null ? null : Math.abs(awayGoalDifference), maxGoalDifference),
      accent: "neutral",
    },
  ];
}

// Ce composant affiche une carte d’analyse synthétique.
function AnalysisInsightCard({ card }: { card: InsightCard }) {
  return (
    <article className={`rb-detail-v2-insight-card rb-detail-v2-insight-card--${card.tone}`}>
      <span>{card.icon}</span>
      <div>
        <p>{card.badge}</p>
        <h4>{card.title}</h4>
        <small>{card.description}</small>
      </div>
    </article>
  );
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
  teamHistory,
  onNavigate,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
  teamHistory: TeamHistoryResponse | null;
  onNavigate: (screen: AppScreen) => void;
}) {
  const insightCards = useMemo(
    () => buildInsightCards(match, matchContext, teamHistory),
    [match, matchContext, teamHistory],
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
  teamHistory,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
  teamHistory: TeamHistoryResponse | null;
}) {
  const metrics = useMemo(
    () => buildMetricCards(matchContext, teamHistory),
    [matchContext, teamHistory],
  );

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

// Ce composant affiche une ligne de match récent dans la fiche détail.
function RecentMatchRow({ recentMatch }: { recentMatch: TeamRecentMatch }) {
  return (
    <span>
      {formatRecentMatchDate(recentMatch.utc_date)} ·{" "}
      {recentMatch.home_team ?? "Équipe domicile"} vs{" "}
      {recentMatch.away_team ?? "Équipe extérieure"} ·{" "}
      {formatRecentScore(recentMatch)} ·{" "}
      {getRecentResultLabel(recentMatch.team_result)}
    </span>
  );
}

// Ce composant affiche l’historique récent d’une équipe dans la vue d’ensemble.
function RecentTeamHistoryCard({
  team,
  historyBlock,
}: {
  team: Team;
  historyBlock: TeamHistoryBlock | null;
}) {
  const recentMatches = historyBlock?.recent_matches_overview ?? [];
  const formSummary = historyBlock?.form_summary ?? null;

  return (
    <article className="rb-detail-v2-recent-team">
      <div className="rb-detail-v2-recent-team__heading">
        <TeamLogo team={team} />
        <strong>{getTeamDisplayName(team)}</strong>
      </div>

      {recentMatches.length ? (
        <div>
          <span>
            {formSummary
              ? `${formSummary.wins}V · ${formSummary.draws}N · ${formSummary.losses}D`
              : "Bilan non calculé"}
          </span>
          {recentMatches.map((recentMatch) => (
            <RecentMatchRow
              key={`${recentMatch.match_id ?? recentMatch.utc_date}-${recentMatch.team_result}`}
              recentMatch={recentMatch}
            />
          ))}
        </div>
      ) : (
        <div>
          <span>Historique indisponible</span>
          <span>Aucun match récent exploitable dans les sources gratuites actuelles.</span>
          <span>Donnée non inventée par RubyBets</span>
        </div>
      )}
    </article>
  );
}

// Cette fonction compare deux valeurs numériques et produit une lecture prudente.
function buildComparativeReading({
  homeValue,
  awayValue,
  homeTeam,
  awayTeam,
  higherIsBetter,
  threshold,
}: {
  homeValue: number | null;
  awayValue: number | null;
  homeTeam: Team;
  awayTeam: Team;
  higherIsBetter: boolean;
  threshold: number;
}) {
  if (homeValue === null || awayValue === null) {
    return "Lecture limitée : la source ne fournit pas les deux valeurs nécessaires.";
  }

  const difference = homeValue - awayValue;

  if (Math.abs(difference) <= threshold) {
    return "Signal proche entre les deux équipes : la donnée ne suffit pas à créer un écart net.";
  }

  const homeHasAdvantage = higherIsBetter ? difference > 0 : difference < 0;
  const leadingTeam = homeHasAdvantage ? getTeamShortName(homeTeam) : getTeamShortName(awayTeam);
  const gapLabel = Math.abs(difference) >= threshold * 2 ? "avantage visible" : "avantage léger";

  return `${leadingTeam} présente un ${gapLabel} sur ce signal, à interpréter avec prudence.`;
}

// Cette fonction interprète la régularité récente à partir des points pris.
function buildRegularityReading({
  homeSummary,
  awaySummary,
  homeTeam,
  awayTeam,
}: {
  homeSummary: TeamFormSummary | null;
  awaySummary: TeamFormSummary | null;
  homeTeam: Team;
  awayTeam: Team;
}) {
  return buildComparativeReading({
    homeValue: getRecentFormRate(homeSummary),
    awayValue: getRecentFormRate(awaySummary),
    homeTeam,
    awayTeam,
    higherIsBetter: true,
    threshold: 8,
  });
}

// Cette fonction interprète la série W/D/L sans prédire le résultat du match.
function buildSeriesReading(series: TeamFormSummary["recent_series"] | undefined) {
  if (!series?.length) {
    return "Série non disponible : RubyBets ne complète pas l’historique avec des données inventées.";
  }

  const wins = series.filter((result) => result === "W").length;
  const draws = series.filter((result) => result === "D").length;
  const losses = series.filter((result) => result === "L").length;

  if (wins >= losses + 2) {
    return "Dynamique plutôt favorable : les victoires récentes sont plus nombreuses que les défaites.";
  }

  if (losses >= wins + 2) {
    return "Dynamique fragile : les défaites récentes pèsent davantage que les résultats positifs.";
  }

  if (draws >= Math.max(wins, losses) && draws >= 2) {
    return "Lecture équilibrée : plusieurs matchs se terminent sur un résultat serré ou neutre.";
  }

  return "Dynamique irrégulière : la série alterne entre résultats positifs et négatifs.";
}

// Cette fonction prépare des cartes d’interprétation non redondantes pour l’onglet Forme & tendances.
function buildFormDiagnosticCards({
  match,
  homeSummary,
  awaySummary,
  responsibleNote,
}: {
  match: Match;
  homeSummary: TeamFormSummary | null;
  awaySummary: TeamFormSummary | null;
  responsibleNote: string | null;
}): InsightCard[] {
  const homeGoalsForAvg = homeSummary?.avg_goals_for ?? null;
  const awayGoalsForAvg = awaySummary?.avg_goals_for ?? null;
  const homeGoalsAgainstAvg = homeSummary?.avg_goals_against ?? null;
  const awayGoalsAgainstAvg = awaySummary?.avg_goals_against ?? null;

  return [
    {
      icon: "⌁",
      tone: "teal",
      title: "Régularité récente",
      description: buildRegularityReading({
        homeSummary,
        awaySummary,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
      }),
      badge: "Dynamique",
    },
    {
      icon: "◎",
      tone: "blue",
      title: "Signal offensif",
      description: buildComparativeReading({
        homeValue: homeGoalsForAvg,
        awayValue: awayGoalsForAvg,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: true,
        threshold: 0.25,
      }),
      badge: "Buts marqués",
    },
    {
      icon: "◷",
      tone: "amber",
      title: "Vulnérabilité défensive",
      description: buildComparativeReading({
        homeValue: homeGoalsAgainstAvg,
        awayValue: awayGoalsAgainstAvg,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: false,
        threshold: 0.25,
      }),
      badge: "Buts encaissés",
    },
    {
      icon: "◇",
      tone: "red",
      title: "Lecture responsable",
      description: responsibleNote ?? "La forme récente aide à lire une dynamique, mais ne garantit aucun résultat sportif.",
      badge: "Prudence",
    },
  ];
}

// Cette fonction prépare les signaux comparatifs de forme sous forme de lignes de tableau, sans reprendre la liste des derniers matchs.
function buildFormTrendSignals({
  match,
  homeSummary,
  awaySummary,
}: {
  match: Match;
  homeSummary: TeamFormSummary | null;
  awaySummary: TeamFormSummary | null;
}): FormTrendSignal[] {
  const homeGoalDifference = getHistoryGoalDifference(homeSummary);
  const awayGoalDifference = getHistoryGoalDifference(awaySummary);

  return [
    {
      label: "Victoires récentes",
      homeValue: homeSummary ? `${homeSummary.wins}/${homeSummary.matches_count}` : "Non fourni",
      awayValue: awaySummary ? `${awaySummary.wins}/${awaySummary.matches_count}` : "Non fourni",
      reading: buildComparativeReading({
        homeValue: homeSummary?.wins ?? null,
        awayValue: awaySummary?.wins ?? null,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: true,
        threshold: 1,
      }),
      tone: "teal",
    },
    {
      label: "Buts marqués / match",
      homeValue: formatHistoryAverage(homeSummary?.avg_goals_for),
      awayValue: formatHistoryAverage(awaySummary?.avg_goals_for),
      reading: buildComparativeReading({
        homeValue: homeSummary?.avg_goals_for ?? null,
        awayValue: awaySummary?.avg_goals_for ?? null,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: true,
        threshold: 0.25,
      }),
      tone: "blue",
    },
    {
      label: "Buts encaissés / match",
      homeValue: formatHistoryAverage(homeSummary?.avg_goals_against),
      awayValue: formatHistoryAverage(awaySummary?.avg_goals_against),
      reading: buildComparativeReading({
        homeValue: homeSummary?.avg_goals_against ?? null,
        awayValue: awaySummary?.avg_goals_against ?? null,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: false,
        threshold: 0.25,
      }),
      tone: "amber",
    },
    {
      label: "Écart de buts récent",
      homeValue: formatSignedMetric(homeGoalDifference),
      awayValue: formatSignedMetric(awayGoalDifference),
      reading: buildComparativeReading({
        homeValue: homeGoalDifference,
        awayValue: awayGoalDifference,
        homeTeam: match.home_team,
        awayTeam: match.away_team,
        higherIsBetter: true,
        threshold: 2,
      }),
      tone: "red",
    },
  ];
}

// Ce composant affiche les signaux comparés dans un vrai tableau pour éviter la répétition des cartes de la vue d’ensemble.
function FormTrendSignalsTable({
  match,
  signals,
}: {
  match: Match;
  signals: FormTrendSignal[];
}) {
  const tableStyle: CSSProperties = {
    width: "100%",
    borderCollapse: "separate",
    borderSpacing: "0 10px",
  };
  const headStyle: CSSProperties = {
    color: "rgba(226, 232, 240, 0.58)",
    fontSize: "0.72rem",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    textAlign: "left",
  };
  const cellStyle: CSSProperties = {
    background: "rgba(15, 23, 42, 0.62)",
    borderTop: "1px solid rgba(148, 163, 184, 0.12)",
    borderBottom: "1px solid rgba(148, 163, 184, 0.12)",
    padding: "13px 14px",
    color: "rgba(226, 232, 240, 0.82)",
    verticalAlign: "top",
  };
  const firstCellStyle: CSSProperties = {
    ...cellStyle,
    borderLeft: "1px solid rgba(148, 163, 184, 0.12)",
    borderTopLeftRadius: "14px",
    borderBottomLeftRadius: "14px",
    fontWeight: 800,
    color: "#f8fafc",
  };
  const lastCellStyle: CSSProperties = {
    ...cellStyle,
    borderRight: "1px solid rgba(148, 163, 184, 0.12)",
    borderTopRightRadius: "14px",
    borderBottomRightRadius: "14px",
    color: "rgba(203, 213, 225, 0.76)",
    lineHeight: 1.55,
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={{ ...headStyle, padding: "0 14px" }}>Signal</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>{getTeamShortName(match.home_team)}</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>{getTeamShortName(match.away_team)}</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>Lecture RubyBets</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal) => (
            <tr key={signal.label}>
              <td style={firstCellStyle}>{signal.label}</td>
              <td style={cellStyle}>{signal.homeValue}</td>
              <td style={cellStyle}>{signal.awayValue}</td>
              <td style={lastCellStyle}>{signal.reading}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Ce composant décode une série récente sans répéter la liste complète des matchs.
function SeriesReadingCard({
  team,
  historyBlock,
}: {
  team: Team;
  historyBlock: TeamHistoryBlock | null;
}) {
  const formSummary = historyBlock?.form_summary ?? null;

  return (
    <article className="rb-detail-v2-recent-team">
      <div className="rb-detail-v2-recent-team__heading">
        <TeamLogo team={team} />
        <strong>{getTeamDisplayName(team)}</strong>
      </div>

      <div>
        <span>Série : {formatRecentSeries(formSummary?.recent_series)}</span>
        <span>{buildSeriesReading(formSummary?.recent_series)}</span>
        <span>
          Bilan utilisé : {formatRecentFormRecord(formSummary)} · {formSummary?.matches_count ?? 0} match(s)
        </span>
      </div>
    </article>
  );
}

// Ce composant affiche l’onglet Forme & tendances comme une lecture comparative, sans répéter la vue d’ensemble.
function FormTrendsTabContent({
  match,
  teamHistory,
}: {
  match: Match;
  teamHistory: TeamHistoryResponse | null;
}) {
  const homeHistory = getTeamHistoryBlock(teamHistory, "home");
  const awayHistory = getTeamHistoryBlock(teamHistory, "away");
  const homeSummary = homeHistory?.form_summary ?? null;
  const awaySummary = awayHistory?.form_summary ?? null;
  const hasHomeHistory = hasUsableHistoryBlock(homeHistory);
  const hasAwayHistory = hasUsableHistoryBlock(awayHistory);
  const sourceLabel = teamHistory?.data_freshness.source_label ?? "Source en attente";
  const limitations = teamHistory?.data_freshness.limitations ?? [];
  const summary = teamHistory?.summary ?? null;
  const diagnosticCards = buildFormDiagnosticCards({
    match,
    homeSummary,
    awaySummary,
    responsibleNote: summary?.responsible_note ?? null,
  });
  const trendSignals = buildFormTrendSignals({ match, homeSummary, awaySummary });

  if (!hasHomeHistory && !hasAwayHistory) {
    return (
      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Forme & tendances</p>
        <h3>Lecture comparative indisponible</h3>
        <p>
          La source actuelle ne fournit pas encore assez de données récentes pour comparer les dynamiques des deux équipes. RubyBets affiche uniquement les informations réellement disponibles.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Forme & tendances</p>
            <h3>Ce que les dynamiques récentes suggèrent</h3>
          </div>
          <span>{getTeamHistoryStatusLabel(teamHistory)} · {sourceLabel}</span>
        </div>

        <div className="rb-detail-v2-insight-grid">
          {diagnosticCards.map((card) => (
            <AnalysisInsightCard key={card.title} card={card} />
          ))}
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-stats-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Comparaison des signaux récents</p>
            <h3>Table de lecture comparative</h3>
          </div>
          <span>Interprétation prudente, pas prédiction</span>
        </div>

        <FormTrendSignalsTable match={match} signals={trendSignals} />
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-recent-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Séries décodées</p>
            <h3>Comprendre les enchaînements de résultats</h3>
          </div>
          <span>{summary?.comparison_note ?? "Lecture prudente"}</span>
        </div>

        <div className="rb-detail-v2-recent-grid">
          <SeriesReadingCard team={match.home_team} historyBlock={homeHistory} />
          <SeriesReadingCard team={match.away_team} historyBlock={awayHistory} />
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Limites de lecture</p>
        <h3>Cadre responsable</h3>
        <ul className="rb-detail-v2-context-list">
          {(limitations.length
            ? limitations
            : [
                "La forme récente reste un indicateur d’aide à l’analyse, pas une certitude.",
                "Les données affichées dépendent des informations réellement fournies par la source.",
                "RubyBets ne permet aucun pari réel et ne promet aucun résultat sportif.",
              ]
          ).map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

// Ce composant affiche une section compacte pour la forme récente.
function RecentMatchesSection({
  match,
  teamHistory,
}: {
  match: Match;
  teamHistory: TeamHistoryResponse | null;
}) {
  const homeHistory = getTeamHistoryBlock(teamHistory, "home");
  const awayHistory = getTeamHistoryBlock(teamHistory, "away");
  const sourceLabel = teamHistory?.data_freshness.source_label ?? "Source en attente";

  return (
    <section className="rb-detail-v2-card rb-detail-v2-recent-card">
      <div className="rb-detail-v2-section-header">
        <div>
          <p>Derniers matchs</p>
          <h3>Forme récente</h3>
        </div>
        <span>{sourceLabel}</span>
      </div>

      <div className="rb-detail-v2-recent-grid">
        <RecentTeamHistoryCard
          team={match.home_team}
          historyBlock={homeHistory}
        />
        <RecentTeamHistoryCard
          team={match.away_team}
          historyBlock={awayHistory}
        />
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

// Ce composant affiche les confrontations directes disponibles entre les deux équipes.
function HeadToHeadCard({
  teamHistory,
}: {
  teamHistory: TeamHistoryResponse | null;
}) {
  const headToHeadMatches = teamHistory?.head_to_head ?? [];

  return (
    <SidebarCard title="Face à face">
      {headToHeadMatches.length ? (
        <>
          <ul className="rb-detail-v2-context-list">
            {headToHeadMatches.map((headToHeadMatch) => (
              <li key={`${headToHeadMatch.match_id ?? headToHeadMatch.utc_date}`}>
                {formatRecentMatchDate(headToHeadMatch.utc_date)} · {" "}
                {formatHeadToHeadTeams(headToHeadMatch)} · {" "}
                {formatHeadToHeadScore(headToHeadMatch)}
                {headToHeadMatch.competition_name ? (
                  <> · {headToHeadMatch.competition_name}</>
                ) : null}
              </li>
            ))}
          </ul>
          <button type="button">
            {headToHeadMatches.length} confrontation{headToHeadMatches.length > 1 ? "s" : ""} directe{headToHeadMatches.length > 1 ? "s" : ""}
          </button>
        </>
      ) : (
        <>
          <div className="rb-detail-v2-empty-mini">
            <span>◇</span>
            <p>Aucune confrontation directe récente n’est disponible dans la source actuelle.</p>
          </div>
          <button type="button">Historique non fourni</button>
        </>
      )}
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

// Ce composant affiche l’onglet Analyse détaillée à partir de la route /analysis.
function AnalysisDetailTabContent({
  matchAnalysis,
  matchAnalysisStatus,
}: {
  matchAnalysis: MatchAnalysisResponse | null;
  matchAnalysisStatus: string;
}) {
  if (!matchAnalysis?.analysis) {
    return (
      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Analyse détaillée</p>
        <h3>Analyse non disponible</h3>
        <p>{matchAnalysisStatus || "L’analyse pré-match n’a pas encore été chargée pour cette rencontre."}</p>
      </section>
    );
  }

  const { analysis } = matchAnalysis;

  return (
    <>
      <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Analyse détaillée</p>
            <h3>{analysis.title}</h3>
          </div>
          <span>{getAnalysisStatusLabel(matchAnalysis)}</span>
        </div>

        <ul className="rb-detail-v2-context-list">
          {analysis.observed_facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-stats-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Facteurs clés</p>
            <h3>Signaux utilisés dans la lecture du match</h3>
          </div>
          <span>Données disponibles</span>
        </div>

        <div className="rb-detail-v2-insight-grid">
          {analysis.key_factors.map((factor) => (
            <article
              className="rb-detail-v2-insight-card rb-detail-v2-insight-card--blue"
              key={`${factor.label}-${formatAnalysisFactorValue(factor.value)}`}
            >
              <span>◇</span>
              <div>
                <p>{factor.label}</p>
                <h4>{formatAnalysisFactorValue(factor.value)}</h4>
                <small>{factor.reading}</small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-recent-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Interprétation</p>
            <h3>Lecture responsable</h3>
          </div>
          <span>{analysis.context_trend}</span>
        </div>

        <ul className="rb-detail-v2-context-list">
          {analysis.interpretation.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Limites</p>
        <h3>Cadre d’utilisation</h3>
        <ul className="rb-detail-v2-context-list">
          {analysis.limits.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

// Ce composant affiche un badge de disponibilité dans l'onglet compositions.
function LineupsAvailabilityBadge({
  item,
}: {
  item: { label: string; value: string };
}) {
  return (
    <article className="rb-detail-v2-insight-card rb-detail-v2-insight-card--blue">
      <span>◌</span>
      <div>
        <p>{item.label}</p>
        <h4>{item.value}</h4>
        <small>Donnée affichée uniquement si elle est fournie par la source.</small>
      </div>
    </article>
  );
}

// Ce composant affiche une ligne joueur pour une composition ou une absence.
function LineupPlayerRow({
  player,
  showReason = false,
}: {
  player: MatchLineupPlayer;
  showReason?: boolean;
}) {
  return (
    <li>
      {player.image_path ? (
        <img
          src={player.image_path}
          alt=""
          loading="lazy"
          style={{
            width: 26,
            height: 26,
            borderRadius: "999px",
            objectFit: "cover",
            marginRight: 8,
            verticalAlign: "middle",
          }}
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
      <strong>{getPlayerNumberLabel(player)} · {player.name || "Joueur non nommé"}</strong>
      <span> · {getPlayerClubLabel(player)}</span>
      {showReason && player.reason ? <span> · {player.reason}</span> : null}
    </li>
  );
}

// Ce composant affiche la composition disponible pour une équipe.
function LineupTeamCard({
  team,
  lineupSide,
}: {
  team: Team;
  lineupSide: MatchLineupSide;
}) {
  const players = getDisplayLineupPlayers(lineupSide);

  return (
    <article className="rb-detail-v2-side-card">
      <h3>{getTeamDisplayName(team)}</h3>
      <p className="rb-detail-v2-info-line">
        <span>◌</span>
        <small>{getLineupModeLabel(lineupSide)}</small>
        <strong>{lineupSide.formation || "Formation non fournie"}</strong>
      </p>

      {players.length ? (
        <ul className="rb-detail-v2-context-list">
          {players.map((player) => (
            <LineupPlayerRow
              key={`${lineupSide.side}-${player.player_id ?? player.name}`}
              player={player}
            />
          ))}
        </ul>
      ) : (
        <p>La source ne fournit pas de composition exploitable pour cette équipe.</p>
      )}
    </article>
  );
}

// Ce composant affiche les absents et les joueurs incertains pour une équipe.
function MissingPlayersCard({
  team,
  lineupSide,
}: {
  team: Team;
  lineupSide: MatchLineupSide;
}) {
  const missingPlayers = lineupSide.missing_players;
  const unsurePlayers = lineupSide.unsure_missing_players;
  const hasUnavailablePlayers = missingPlayers.length || unsurePlayers.length;

  return (
    <article className="rb-detail-v2-side-card">
      <h3>{getTeamShortName(team)}</h3>
      {hasUnavailablePlayers ? (
        <>
          {missingPlayers.length ? (
            <>
              <p>Absents confirmés</p>
              <ul className="rb-detail-v2-context-list">
                {missingPlayers.map((player) => (
                  <LineupPlayerRow
                    key={`missing-${lineupSide.side}-${player.player_id ?? player.name}`}
                    player={player}
                    showReason
                  />
                ))}
              </ul>
            </>
          ) : null}

          {unsurePlayers.length ? (
            <>
              <p>Incertains</p>
              <ul className="rb-detail-v2-context-list">
                {unsurePlayers.map((player) => (
                  <LineupPlayerRow
                    key={`unsure-${lineupSide.side}-${player.player_id ?? player.name}`}
                    player={player}
                    showReason
                  />
                ))}
              </ul>
            </>
          ) : null}
        </>
      ) : (
        <p>Aucun absent ou joueur incertain fourni par la source actuelle.</p>
      )}
    </article>
  );
}

// Ce composant affiche l'onglet Compo probable à partir de la route /lineups.
function LineupsTabContent({
  match,
  matchLineups,
  matchLineupsStatus,
}: {
  match: Match;
  matchLineups: MatchLineupsResponse | null;
  matchLineupsStatus: string;
}) {
  const availabilityItems = buildLineupsAvailabilityItems(matchLineups);
  const lineups = matchLineups?.lineups;

  if (!lineups || matchLineups?.status === "unavailable") {
    return (
      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Compositions & effectifs</p>
        <h3>Composition probable non disponible</h3>
        <p>
          {lineups?.empty_state ||
            matchLineupsStatus ||
            "La source actuelle ne fournit pas encore de composition probable exploitable pour cette rencontre."}
        </p>
        <p>RubyBets n’invente pas de titulaires, de remplaçants ou d’effectif complet.</p>
      </section>
    );
  }

  return (
    <>
      <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Compositions & effectifs</p>
            <h3>{getLineupsStatusLabel(matchLineups)}</h3>
          </div>
          <span>{matchLineups?.source_used || "Source non fournie"}</span>
        </div>

        <div className="rb-detail-v2-insight-grid">
          {availabilityItems.map((item) => (
            <LineupsAvailabilityBadge key={item.label} item={item} />
          ))}
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-recent-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Compositions probables</p>
            <h3>Lecture équipe par équipe</h3>
          </div>
          <span>{lineups.composition_status}</span>
        </div>

        <div className="rb-detail-v2-recent-grid">
          <LineupTeamCard team={match.home_team} lineupSide={lineups.home} />
          <LineupTeamCard team={match.away_team} lineupSide={lineups.away} />
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-recent-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Disponibilités joueurs</p>
            <h3>Absents et incertains fournis par la source</h3>
          </div>
          <span>Sans donnée inventée</span>
        </div>

        <div className="rb-detail-v2-recent-grid">
          <MissingPlayersCard team={match.home_team} lineupSide={lineups.home} />
          <MissingPlayersCard team={match.away_team} lineupSide={lineups.away} />
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Limites de lecture</p>
        <h3>Cadre responsable</h3>
        <ul className="rb-detail-v2-context-list">
          {(lineups.limits.length
            ? lineups.limits
            : [
                "Les compositions affichées restent probables tant que la composition officielle n’est pas fournie.",
                "RubyBets n’invente pas les joueurs absents de la source actuelle.",
                "Aucune cote FlashScore n’est utilisée par RubyBets.",
              ]
          ).map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

// Ce composant affiche un tableau détaillé des confrontations directes avec une lecture courte par match.
function HeadToHeadMatchesTable({
  match,
  headToHeadMatches,
}: {
  match: Match;
  headToHeadMatches: HeadToHeadMatch[];
}) {
  const tableStyle: CSSProperties = {
    width: "100%",
    borderCollapse: "separate",
    borderSpacing: "0 10px",
  };
  const headStyle: CSSProperties = {
    color: "rgba(226, 232, 240, 0.58)",
    fontSize: "0.72rem",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    textAlign: "left",
  };
  const cellStyle: CSSProperties = {
    background: "rgba(15, 23, 42, 0.62)",
    borderTop: "1px solid rgba(148, 163, 184, 0.12)",
    borderBottom: "1px solid rgba(148, 163, 184, 0.12)",
    padding: "13px 14px",
    color: "rgba(226, 232, 240, 0.82)",
    verticalAlign: "top",
  };
  const firstCellStyle: CSSProperties = {
    ...cellStyle,
    borderLeft: "1px solid rgba(148, 163, 184, 0.12)",
    borderTopLeftRadius: "14px",
    borderBottomLeftRadius: "14px",
    fontWeight: 800,
    color: "#f8fafc",
  };
  const lastCellStyle: CSSProperties = {
    ...cellStyle,
    borderRight: "1px solid rgba(148, 163, 184, 0.12)",
    borderTopRightRadius: "14px",
    borderBottomRightRadius: "14px",
    color: "rgba(203, 213, 225, 0.76)",
    lineHeight: 1.55,
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={{ ...headStyle, padding: "0 14px" }}>Date</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>Compétition</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>Match</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>Score</th>
            <th style={{ ...headStyle, padding: "0 14px" }}>Lecture</th>
          </tr>
        </thead>
        <tbody>
          {headToHeadMatches.map((headToHeadMatch, index) => (
            <tr key={`${headToHeadMatch.match_id ?? headToHeadMatch.utc_date ?? index}`}>
              <td style={firstCellStyle}>{formatRecentMatchDate(headToHeadMatch.utc_date)}</td>
              <td style={cellStyle}>{headToHeadMatch.competition_name || "Compétition non fournie"}</td>
              <td style={cellStyle}>{formatHeadToHeadTeams(headToHeadMatch)}</td>
              <td style={cellStyle}>{formatHeadToHeadScore(headToHeadMatch)}</td>
              <td style={lastCellStyle}>{buildHeadToHeadMatchReading(headToHeadMatch, match)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Ce composant affiche l’onglet Face à face comme un historique détaillé et non comme un résumé de sidebar.
function HeadToHeadTabContent({
  match,
  teamHistory,
}: {
  match: Match;
  teamHistory: TeamHistoryResponse | null;
}) {
  const headToHeadMatches = teamHistory?.head_to_head ?? [];
  const summary = buildHeadToHeadHistoricalSummary(headToHeadMatches, match);
  const sourceLabel = teamHistory?.data_freshness.source_label ?? "Source en attente";
  const summaryCards = buildHeadToHeadSummaryCards(
    summary,
    match,
    teamHistory?.summary?.head_to_head_note ?? null,
  );

  if (!headToHeadMatches.length) {
    return (
      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Face à face</p>
        <h3>Aucune confrontation directe disponible</h3>
        <p>
          La source actuelle ne fournit pas de confrontation directe exploitable pour cette rencontre. RubyBets n’invente pas d’historique absent.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Disponibilité des confrontations</p>
            <h3>Historique direct disponible</h3>
          </div>
          <span>{getTeamHistoryStatusLabel(teamHistory)} · {sourceLabel}</span>
        </div>

        <div className="rb-detail-v2-insight-grid">
          {summaryCards.map((card) => (
            <AnalysisInsightCard key={card.title} card={card} />
          ))}
        </div>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-stats-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Résumé historique</p>
            <h3>{getTeamShortName(match.home_team)} vs {getTeamShortName(match.away_team)}</h3>
          </div>
          <span>Contexte historique uniquement</span>
        </div>

        <p className="rb-detail-v2-analysis-lead">
          RubyBets a trouvé {summary.total} confrontation{summary.total > 1 ? "s" : ""} directe{summary.total > 1 ? "s" : ""} dans les données disponibles. Cet historique sert à contextualiser la rencontre, sans être transformé en certitude sportive.
        </p>
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-stats-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Confrontations disponibles</p>
            <h3>Liste détaillée</h3>
          </div>
          <span>{summary.calculable} score(s) exploitable(s)</span>
        </div>

        <HeadToHeadMatchesTable match={match} headToHeadMatches={headToHeadMatches} />
      </section>

      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Ce que l’historique peut dire</p>
        <h3>Limites de lecture</h3>
        <ul className="rb-detail-v2-context-list">
          <li>Les confrontations directes donnent un contexte historique, mais ne suffisent pas à anticiper le résultat du match.</li>
          <li>Les effectifs, la forme récente, les absences et le contexte de compétition peuvent avoir changé.</li>
          <li>RubyBets affiche uniquement les confrontations réellement disponibles et n’utilise aucune cote FlashScore.</li>
        </ul>
      </section>
    </>
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
  teamHistory,
  onNavigate,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
  teamHistory: TeamHistoryResponse | null;
  onNavigate: (screen: AppScreen) => void;
}) {
  return (
    <>
      <PreMatchAnalysisSection
        match={match}
        matchContext={matchContext}
        teamHistory={teamHistory}
        onNavigate={onNavigate}
      />
      <KeyIndicatorsSection
        match={match}
        matchContext={matchContext}
        teamHistory={teamHistory}
      />
      <RecentMatchesSection match={match} teamHistory={teamHistory} />
    </>
  );
}

// Ce composant structure l’écran Détail match sans modifier la logique métier existante.
function MatchDetailsScreen({
  matchDetails,
  matchContext,
  matchAnalysis,
  matchLineups,
  matchNewsContext,
  teamHistory,
  matchDetailsStatus,
  matchContextStatus,
  matchAnalysisStatus,
  matchLineupsStatus,
  matchNewsContextStatus,
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
              teamHistory={teamHistory}
              onNavigate={onNavigate}
            />
          ) : null}

          {activeTab === "analysis" ? (
            <AnalysisDetailTabContent
              matchAnalysis={matchAnalysis}
              matchAnalysisStatus={matchAnalysisStatus}
            />
          ) : null}

          {activeTab === "form" ? (
            <FormTrendsTabContent
              match={selectedMatch}
              teamHistory={teamHistory}
            />
          ) : null}

          {activeTab === "lineup" ? (
            <LineupsTabContent
              match={selectedMatch}
              matchLineups={matchLineups}
              matchLineupsStatus={matchLineupsStatus}
            />
          ) : null}

          {activeTab === "headToHead" ? (
            <HeadToHeadTabContent
              match={selectedMatch}
              teamHistory={teamHistory}
            />
          ) : null}

          {activeTab === "context" ? (
            <MatchNewsContextSection
              matchNewsContext={matchNewsContext}
              matchNewsContextStatus={matchNewsContextStatus}
            />
          ) : null}

          {activeTab !== "overview" && activeTab !== "analysis" && activeTab !== "form" && activeTab !== "lineup" && activeTab !== "headToHead" && activeTab !== "context" ? (
            <PendingTabContent activeTab={activeTab} />
          ) : null}
        </section>

        <aside className="rb-detail-v2-side-column">
          <MatchInfoCard match={selectedMatch} freshnessLabel={freshnessLabel} />
          <HeadToHeadCard teamHistory={teamHistory} />
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
// ├── reçoit le détail, le contexte, l’analyse, les compositions et l’historique des équipes depuis App.tsx
// ├── utilise les types MatchDetailsResponse, MatchContextResponse, MatchAnalysisResponse, MatchLineupsResponse et TeamHistoryResponse de models/rubybets.ts
// ├── utilise les helpers d’affichage de helpers/displayText.ts
// ├── alimente l’onglet Analyse détaillée avec matchAnalysis.analysis
// ├── alimente l’onglet Compo probable avec matchLineups.lineups sans inventer de joueurs
// ├── alimente l’onglet Forme & tendances avec une table comparative issue de teamHistory.form_summary
// ├── alimente l’analyse synthétique avec teamHistory.form_summary quand il est disponible
// ├── alimente la comparaison avant-match avec les points, buts et écarts issus de teamHistory.form_summary
// ├── affiche les derniers matchs disponibles uniquement dans la Vue d’ensemble via teamHistory.recent_matches_overview
// ├── affiche les confrontations directes disponibles via teamHistory.head_to_head
// ├── déclenche la navigation vers Matchs, Analyse et Prédictions via onNavigate
// └── reste isolé visuellement avec les classes rb-detail-v2-* définies dans App.css