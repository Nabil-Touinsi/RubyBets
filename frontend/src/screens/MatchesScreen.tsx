// Ce fichier affiche l’écran Matchs de RubyBets avec filtres, liste des rencontres et colonne d’aide.

import { useMemo, useState } from "react";
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

type DateFilter = "all" | "7d" | "30d";
type SortMode = "date_asc" | "date_desc" | "competition";

// Cette fonction vérifie si un match peut être affiché comme exploitable pour l’analyse.
function isAnalysisAvailable(match: Match) {
  const status = match.status?.toUpperCase();

  return hasKnownTeams(match) && (status === "SCHEDULED" || status === "TIMED");
}

// Cette fonction filtre les matchs selon la période choisie.
function filterMatchesByDate(matches: Match[], dateFilter: DateFilter) {
  if (dateFilter === "all") {
    return matches;
  }

  const now = Date.now();
  const days = dateFilter === "7d" ? 7 : 30;
  const limit = now + days * 24 * 60 * 60 * 1000;

  return matches.filter((match) => {
    const matchTime = new Date(match.utc_date).getTime();

    return Number.isFinite(matchTime) && matchTime >= now && matchTime <= limit;
  });
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

  return (
    homeTeamSearchText.includes(searchValue) ||
    awayTeamSearchText.includes(searchValue)
  );
}

// Ce composant structure l’écran Matchs sans modifier les appels API existants.
function MatchesScreen({
  competitions,
  matches,
  selectedCompetition,
  matchesStatus,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: MatchesScreenProps) {
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [teamSearch, setTeamSearch] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("date_asc");

  const activeCompetition = competitions.find(
    (competition) => competition.code === selectedCompetition,
  );

  const filteredMatches = useMemo(() => {
    const matchesFilteredByDate = filterMatchesByDate(matches, dateFilter);
    const searchValue = teamSearch.trim().toLowerCase();

    const matchesFilteredByTeam = matchesFilteredByDate.filter((match) => {
      return matchContainsTeamSearch(match, searchValue);
    });

    return sortMatches(matchesFilteredByTeam, sortMode);
  }, [matches, dateFilter, teamSearch, sortMode]);

  const availableMatchesCount = filteredMatches.filter(isAnalysisAvailable).length;
  const pendingMatchesCount = Math.max(
    filteredMatches.length - availableMatchesCount,
    0,
  );

  const dateFilterLabel =
    dateFilter === "7d"
      ? "Prochains 7 jours"
      : dateFilter === "30d"
        ? "Prochains 30 jours"
        : "Tous les matchs";

  return (
    <div className="rb-matches-screen rb-matches-screen--refined">
      <header className="rb-matches-page-header">
        <div>
          <h2>Matchs à venir</h2>
          <p>
            Explorez les prochaines rencontres et accédez à nos analyses avant
            chaque rencontre.
          </p>
        </div>

        <div className="rb-matches-page-header__badge">
          <span>Compétition active</span>
          <strong>{activeCompetition?.name ?? selectedCompetition}</strong>
          <small>{matchesStatus}</small>
        </div>
      </header>

      <div className="rb-matches-board">
        <main className="rb-matches-board__main">
          <section className="rb-matches-filter-panel">
            <div className="rb-matches-filter-grid">
              <label className="rb-matches-filter-field">
                <span>Ligue</span>
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

              <label className="rb-matches-filter-field">
                <span>Date</span>
                <select
                  value={dateFilter}
                  onChange={(event) =>
                    setDateFilter(event.target.value as DateFilter)
                  }
                >
                  <option value="all">Tous les matchs</option>
                  <option value="7d">Prochains 7 jours</option>
                  <option value="30d">Prochains 30 jours</option>
                </select>
              </label>

              <label className="rb-matches-filter-field">
                <span>Équipe</span>
                <input
                  type="search"
                  value={teamSearch}
                  placeholder="Rechercher une équipe ou un match..."
                  onChange={(event) => setTeamSearch(event.target.value)}
                />
              </label>
            </div>

            <CompetitionsSection
              competitions={competitions}
              selectedCompetition={selectedCompetition}
              onSelectCompetition={onSelectCompetition}
            />
          </section>

          <section className="rb-matches-table-panel">
            <div className="rb-matches-table-panel__header">
              <div>
                <span className="rb-matches-panel-label">Rencontres</span>
                <h3>{filteredMatches.length} matchs affichés</h3>
              </div>

              <label className="rb-matches-sort-field">
                <span>Trier par</span>
                <select
                  value={sortMode}
                  onChange={(event) =>
                    setSortMode(event.target.value as SortMode)
                  }
                >
                  <option value="date_asc">Date croissante</option>
                  <option value="date_desc">Date décroissante</option>
                  <option value="competition">Compétition</option>
                </select>
              </label>
            </div>

            <MatchesSection
              selectedCompetition={selectedCompetition}
              matches={filteredMatches}
              onSelectMatch={onSelectMatch}
            />
          </section>
        </main>

        <aside className="rb-matches-board__aside">
          <article className="rb-matches-side-card rb-matches-side-card--overview">
            <div className="rb-matches-side-title">
              <h3>Aperçu</h3>
              <span>ⓘ</span>
            </div>

            <strong>{filteredMatches.length}</strong>
            <p>Matchs à venir</p>

            <div className="rb-matches-side-stat">
              <span className="rb-dot rb-dot--success" />
              <span>Analyses disponibles</span>
              <strong>{availableMatchesCount}</strong>
            </div>

            <div className="rb-matches-side-stat">
              <span className="rb-dot rb-dot--warning" />
              <span>Équipes à confirmer</span>
              <strong>{pendingMatchesCount}</strong>
            </div>

            <div className="rb-matches-side-stat">
              <span className="rb-dot rb-dot--muted" />
              <span>{dateFilterLabel}</span>
              <strong>{filteredMatches.length}</strong>
            </div>
          </article>

          <article className="rb-matches-side-card">
            <h3>Filtres rapides</h3>

            <div className="rb-matches-quick-row">
              <span>Analyses disponibles</span>
              <strong>{availableMatchesCount}</strong>
            </div>

            <div className="rb-matches-quick-row">
              <span>Équipes à confirmer</span>
              <strong>{pendingMatchesCount}</strong>
            </div>

            <div className="rb-matches-quick-row">
              <span>Recherche active</span>
              <strong>{teamSearch.trim() ? "Oui" : "Non"}</strong>
            </div>

            <div className="rb-matches-quick-row">
              <span>Compétition suivie</span>
              <strong>{selectedCompetition}</strong>
            </div>
          </article>

          <article className="rb-matches-side-card">
            <h3>Astuces</h3>
            <p>
              Sélectionnez une rencontre pour consulter son détail. Les matchs
              dont les équipes ne sont pas encore connues restent affichés comme
              données partielles.
            </p>

            <button
              type="button"
              onClick={() => onNavigate("recommendation")}
            >
              Recommandation multi-matchs
            </button>
          </article>

          <p className="rb-matches-responsible-note">
            Outil d’aide à la décision. Les analyses proposées ne constituent
            pas un conseil d’investissement ou un pari.
          </p>
        </aside>
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
