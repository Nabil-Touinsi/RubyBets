// Ce fichier affiche l’écran Matchs de RubyBets avec un rendu premium inspiré de la maquette Match Center.

import { useMemo, useState } from "react";
import {
  CalendarDays,
  Database,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { Competition, Match } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import {
  getTeamSearchText,
  hasKnownTeams,
} from "../helpers/displayText";
import CompetitionsSection from "../components/CompetitionsSection";
import MatchesSection from "../components/MatchesSection";

type MatchesScreenProps = {
  competitions: Competition[];
  matches: Match[];
  selectedCompetition: string;
  matchesStatus: string;
  onSelectCompetition: (competitionCode: string) => void;
  onSelectMatch: (matchId: number) => void;
  onNavigate: (screen: AppScreen) => void;
};

type DateFilter = "all" | "today" | "tomorrow" | "7d" | "30d";
type StatusFilter = "all" | "upcoming" | "live" | "finished";
type SortMode = "date_asc" | "date_desc" | "competition";

// Cette fonction vérifie si un statut correspond à un match à venir.
function isUpcomingStatus(statusValue: string | null | undefined) {
  const status = statusValue?.toUpperCase();

  return status === "SCHEDULED" || status === "TIMED";
}

// Cette fonction vérifie si un statut correspond à un match en cours.
function isLiveStatus(statusValue: string | null | undefined) {
  const status = statusValue?.toUpperCase();

  return status === "IN_PLAY" || status === "LIVE" || status === "PAUSED";
}

// Cette fonction vérifie si un statut correspond à un match terminé.
function isFinishedStatus(statusValue: string | null | undefined) {
  return statusValue?.toUpperCase() === "FINISHED";
}

// Cette fonction vérifie si un match peut être affiché comme exploitable pour l’analyse.
function isAnalysisAvailable(match: Match) {
  return hasKnownTeams(match) && isUpcomingStatus(match.status);
}

// Cette fonction construit une date locale sans heure pour comparer aujourd’hui et demain.
function startOfLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

// Cette fonction vérifie si la date du match correspond exactement à un jour local donné.
function isSameLocalDay(dateValue: string, targetDate: Date) {
  const matchDate = new Date(dateValue);

  if (Number.isNaN(matchDate.getTime())) {
    return false;
  }

  return startOfLocalDay(matchDate) === startOfLocalDay(targetDate);
}

// Cette fonction filtre les matchs selon la période choisie dans la colonne de filtres.
function filterMatchesByDate(matches: Match[], dateFilter: DateFilter) {
  if (dateFilter === "all") {
    return matches;
  }

  const now = new Date();

  if (dateFilter === "today") {
    return matches.filter((match) => isSameLocalDay(match.utc_date, now));
  }

  if (dateFilter === "tomorrow") {
    const tomorrow = new Date(now);
    tomorrow.setDate(now.getDate() + 1);

    return matches.filter((match) => isSameLocalDay(match.utc_date, tomorrow));
  }

  const nowTime = now.getTime();
  const days = dateFilter === "7d" ? 7 : 30;
  const limit = nowTime + days * 24 * 60 * 60 * 1000;

  return matches.filter((match) => {
    const matchTime = new Date(match.utc_date).getTime();

    return Number.isFinite(matchTime) && matchTime >= nowTime && matchTime <= limit;
  });
}

// Cette fonction filtre les matchs selon leur statut sans modifier les données reçues de l’API.
function filterMatchesByStatus(matches: Match[], statusFilter: StatusFilter) {
  if (statusFilter === "all") {
    return matches;
  }

  if (statusFilter === "upcoming") {
    return matches.filter((match) => isUpcomingStatus(match.status));
  }

  if (statusFilter === "live") {
    return matches.filter((match) => isLiveStatus(match.status));
  }

  return matches.filter((match) => isFinishedStatus(match.status));
}

// Cette fonction trie les matchs pour rendre la liste plus lisible.
function sortMatches(matches: Match[], sortMode: SortMode) {
  return [...matches].sort((firstMatch, secondMatch) => {
    if (sortMode === "competition") {
      return firstMatch.competition.name.localeCompare(
        secondMatch.competition.name,
        "fr-FR",
      );
    }

    const firstDate = new Date(firstMatch.utc_date).getTime();
    const secondDate = new Date(secondMatch.utc_date).getTime();

    if (sortMode === "date_desc") {
      return secondDate - firstDate;
    }

    return firstDate - secondDate;
  });
}

// Cette fonction vérifie si un match correspond à la recherche équipe sans casser sur les valeurs nulles.
function matchContainsTeamSearch(match: Match, searchValue: string) {
  if (!searchValue) {
    return true;
  }

  const homeTeamSearchText = getTeamSearchText(match.home_team);
  const awayTeamSearchText = getTeamSearchText(match.away_team);
  const competitionSearchText = match.competition.name.toLowerCase();

  return (
    homeTeamSearchText.includes(searchValue) ||
    awayTeamSearchText.includes(searchValue) ||
    competitionSearchText.includes(searchValue)
  );
}

// Cette fonction récupère la date de mise à jour la plus récente disponible dans les matchs.
function getLatestUpdateLabel(matches: Match[]) {
  const timestamps = matches
    .map((match) => match.last_updated)
    .filter((value): value is string => Boolean(value))
    .map((value) => new Date(value).getTime())
    .filter(Number.isFinite);

  if (timestamps.length === 0) {
    return "mise à jour API";
  }

  const latestTimestamp = Math.max(...timestamps);

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(latestTimestamp));
}

// Cette fonction retourne un libellé court pour le filtre date actif.
function getDateFilterLabel(dateFilter: DateFilter) {
  const labels: Record<DateFilter, string> = {
    all: "Tous",
    today: "Aujourd’hui",
    tomorrow: "Demain",
    "7d": "7 jours",
    "30d": "30 jours",
  };

  return labels[dateFilter];
}

// Ce composant structure l’écran Matchs comme un Match Center visuel sans modifier les appels API existants.
function MatchesScreen({
  competitions,
  matches,
  selectedCompetition,
  matchesStatus,
  onSelectCompetition,
  onSelectMatch,
}: MatchesScreenProps) {
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [teamSearch, setTeamSearch] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("date_asc");

  const activeCompetition = competitions.find(
    (competition) => competition.code === selectedCompetition,
  );

  const filteredMatches = useMemo(() => {
    const matchesFilteredByDate = filterMatchesByDate(matches, dateFilter);
    const matchesFilteredByStatus = filterMatchesByStatus(
      matchesFilteredByDate,
      statusFilter,
    );
    const searchValue = teamSearch.trim().toLowerCase();

    const matchesFilteredByTeam = matchesFilteredByStatus.filter((match) => {
      return matchContainsTeamSearch(match, searchValue);
    });

    return sortMatches(matchesFilteredByTeam, sortMode);
  }, [matches, dateFilter, statusFilter, teamSearch, sortMode]);

  const availableMatchesCount = filteredMatches.filter(isAnalysisAvailable).length;
  const partialMatchesCount = Math.max(
    filteredMatches.length - availableMatchesCount,
    0,
  );
  const upcomingMatchesCount = matches.filter((match) =>
    isUpcomingStatus(match.status),
  ).length;
  const latestUpdateLabel = getLatestUpdateLabel(matches);

  return (
    <div className="rb-matches-screen rb-matches-screen--clone">
      <aside className="rb-matches-clone-filters" aria-label="Filtres des matchs">
        <div className="rb-matches-clone-filters__header">
          <div>
            <span className="rb-matches-clone-label">Filtres</span>
            <h3>Affiner la liste</h3>
          </div>

          <button
            className="rb-matches-reset-button"
            type="button"
            onClick={() => {
              setDateFilter("all");
              setStatusFilter("all");
              setTeamSearch("");
              setSortMode("date_asc");
            }}
          >
            <RotateCcw size={14} aria-hidden="true" />
            Réinitialiser
          </button>
        </div>

        <label className="rb-matches-clone-field">
          <span>Compétition</span>
          <select
            value={selectedCompetition}
            onChange={(event) => onSelectCompetition(event.target.value)}
          >
            {competitions.map((competition) => (
              <option key={competition.id} value={competition.code}>
                {competition.name}
              </option>
            ))}
          </select>
        </label>

        <div className="rb-matches-filter-group">
          <span className="rb-matches-filter-group__title">Date</span>
          <div className="rb-matches-filter-options">
            {[
              ["all", "Tous"],
              ["today", "Aujourd’hui"],
              ["tomorrow", "Demain"],
              ["7d", "Cette semaine"],
              ["30d", "30 jours"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={
                  dateFilter === value
                    ? "rb-matches-filter-option rb-matches-filter-option--active"
                    : "rb-matches-filter-option"
                }
                type="button"
                onClick={() => setDateFilter(value as DateFilter)}
              >
                <span className="rb-matches-filter-dot" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="rb-matches-filter-group">
          <span className="rb-matches-filter-group__title">Statut du match</span>
          <div className="rb-matches-filter-options">
            {[
              ["all", "Tous"],
              ["upcoming", "À venir"],
              ["live", "En cours"],
              ["finished", "Terminé"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={
                  statusFilter === value
                    ? "rb-matches-filter-option rb-matches-filter-option--active"
                    : "rb-matches-filter-option"
                }
                type="button"
                onClick={() => setStatusFilter(value as StatusFilter)}
              >
                <span className="rb-matches-filter-square" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <article className="rb-matches-data-card">
          <span className="rb-matches-clone-label">État des données</span>

          <div className="rb-matches-data-row">
            <Database size={18} aria-hidden="true" />
            <div>
              <strong>Données réelles</strong>
              <span>Source Football-Data.org</span>
            </div>
          </div>

          <div className="rb-matches-data-row">
            <CalendarDays size={18} aria-hidden="true" />
            <div>
              <strong>{upcomingMatchesCount} matchs à venir</strong>
              <span>{matchesStatus}</span>
            </div>
          </div>

          <div className="rb-matches-data-row">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>Cadre responsable</strong>
              <span>Analyse sans garantie sportive</span>
            </div>
          </div>
        </article>
      </aside>

      <div className="rb-matches-clone-main">
        <header className="rb-matches-clone-header">
          <div className="rb-matches-clone-title">
            <span className="rb-matches-clone-icon" aria-hidden="true">
              <CalendarDays size={22} />
            </span>

            <div>
              <h2>Matchs à venir</h2>
              <p>
                Consultez tous les matchs programmés et filtrez selon vos
                critères d’analyse avant-match.
              </p>
            </div>
          </div>

          <div className="rb-matches-clone-header__meta">
            <span>Dernière mise à jour</span>
            <strong>{latestUpdateLabel}</strong>
            <button
              type="button"
              onClick={() => window.location.reload()}
              aria-label="Actualiser l’application"
            >
              Actualiser
            </button>
          </div>
        </header>

        <section className="rb-matches-clone-competitions">
          <div className="rb-matches-clone-section-title">
            <span className="rb-matches-clone-label">Choisir une compétition</span>
            <strong>{activeCompetition?.name ?? selectedCompetition}</strong>
          </div>

          <CompetitionsSection
            competitions={competitions}
            selectedCompetition={selectedCompetition}
            onSelectCompetition={onSelectCompetition}
          />
        </section>

        <section className="rb-matches-clone-toolbar">
          <label className="rb-matches-search-field">
            <Search size={18} aria-hidden="true" />
            <input
              type="search"
              value={teamSearch}
              placeholder="Rechercher un match, une équipe ou une compétition..."
              onChange={(event) => setTeamSearch(event.target.value)}
            />
          </label>

          <label className="rb-matches-sort-select">
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span>Trier par</span>
            <select
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value as SortMode)}
            >
              <option value="date_asc">Date croissante</option>
              <option value="date_desc">Date décroissante</option>
              <option value="competition">Compétition</option>
            </select>
          </label>
        </section>

        <section className="rb-matches-clone-table-panel">
          <div className="rb-matches-clone-table-header">
            <div>
              <span className="rb-matches-clone-label">Rencontres à analyser</span>
              <h3>{filteredMatches.length} matchs affichés</h3>
            </div>

            <div className="rb-matches-clone-summary">
              <span>{getDateFilterLabel(dateFilter)}</span>
              <span>{availableMatchesCount} analyses disponibles</span>
              <span>{partialMatchesCount} données partielles</span>
            </div>
          </div>

          <MatchesSection
            selectedCompetition={selectedCompetition}
            matches={filteredMatches}
            onSelectMatch={onSelectMatch}
          />
        </section>

        <p className="rb-matches-clone-responsible-note">
          RubyBets structure une analyse avant-match à partir de données réelles.
          L’application ne propose aucun pari réel et ne garantit aucun résultat.
        </p>
      </div>
    </div>
  );
}

export default MatchesScreen;

// Schéma de communication du fichier :
// MatchesScreen.tsx
// ├── reçoit compétitions et matchs depuis App.tsx
// ├── filtre les matchs côté frontend sans modifier l’API
// ├── sécurise la recherche lorsque les équipes sont inconnues
// ├── utilise CompetitionsSection.tsx pour les ligues
// ├── utilise MatchesSection.tsx pour la liste des rencontres
// └── renvoie la sélection d’un match vers App.tsx via onSelectMatch
