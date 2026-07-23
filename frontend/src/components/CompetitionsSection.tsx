// Ce composant affiche les compétitions MVP sur une seule ligne avec une pagination fluide par groupes de ligues.

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { Competition } from "../models/rubybets";

type CompetitionsSectionProps = {
  competitions: Competition[];
  selectedCompetition: string;
  onSelectCompetition: (competitionCode: string) => void;
};

type CompetitionPageDirection = "next" | "previous";

// Cette constante fixe le nombre de ligues visibles simultanément sur la ligne desktop.
const COMPETITIONS_PER_PAGE = 6;

// Cette fonction prépare un libellé court pour garder les boutons de ligue lisibles.
function getCompetitionShortLabel(competition: Competition) {
  return competition.name
    .replace("UEFA Champions League", "Champions League")
    .replace("Campeonato Brasileiro Série A", "Brasileirão")
    .replace("Primera Division", "Primera División");
}

// Cette fonction repère les emblèmes sombres nécessitant un traitement visuel renforcé.
function requiresHighContrastLogo(competition: Competition) {
  const searchableValue = `${competition.code} ${competition.name}`.toLowerCase();

  return searchableValue.includes("champions") || competition.code === "CL";
}

// Ce composant affiche une page de ligues à la fois et permet de basculer vers les suivantes.
function CompetitionsSection({
  competitions,
  selectedCompetition,
  onSelectCompetition,
}: CompetitionsSectionProps) {
  const [competitionPage, setCompetitionPage] = useState(0);
  const [pageDirection, setPageDirection] =
    useState<CompetitionPageDirection>("next");
  const totalPages = Math.max(
    1,
    Math.ceil(competitions.length / COMPETITIONS_PER_PAGE),
  );

  const visibleCompetitions = useMemo(() => {
    const firstCompetitionIndex = competitionPage * COMPETITIONS_PER_PAGE;

    return competitions.slice(
      firstCompetitionIndex,
      firstCompetitionIndex + COMPETITIONS_PER_PAGE,
    );
  }, [competitions, competitionPage]);

  const isLastCompetitionPage = competitionPage === totalPages - 1;

  // Cette synchronisation affiche automatiquement la page contenant la compétition sélectionnée.
  useEffect(() => {
    const selectedCompetitionIndex = competitions.findIndex(
      (competition) => competition.code === selectedCompetition,
    );

    if (selectedCompetitionIndex < 0) {
      return;
    }

    const targetPage = Math.floor(
      selectedCompetitionIndex / COMPETITIONS_PER_PAGE,
    );

    setCompetitionPage((currentPage) => {
      if (targetPage === currentPage) {
        return currentPage;
      }

      setPageDirection(targetPage > currentPage ? "next" : "previous");
      return targetPage;
    });
  }, [competitions, selectedCompetition]);

  // Cette synchronisation garde la page valide lorsque la liste des compétitions change.
  useEffect(() => {
    setCompetitionPage((currentPage) =>
      Math.min(currentPage, Math.max(totalPages - 1, 0)),
    );
  }, [totalPages]);

  // Cette fonction bascule vers la page suivante ou revient à la première page.
  function switchCompetitionPage() {
    if (totalPages <= 1) {
      return;
    }

    setCompetitionPage((currentPage) => {
      const nextPage =
        currentPage >= totalPages - 1 ? 0 : currentPage + 1;

      setPageDirection(nextPage > currentPage ? "next" : "previous");
      return nextPage;
    });
  }

  return (
    <section className="rb-competitions-strip">
      {competitions.length === 0 ? (
        <p className="rb-competitions-empty">
          Aucune compétition disponible pour le moment.
        </p>
      ) : (
        <div className="rb-competition-chip-shell">
          <div
            key={`competition-page-${competitionPage}`}
            className={`rb-competition-chip-row rb-competition-chip-row--${pageDirection}`}
            aria-live="polite"
            aria-label={`Groupe de compétitions ${competitionPage + 1} sur ${totalPages}`}
          >
            {visibleCompetitions.map((competition, competitionIndex) => {
              const isSelected =
                competition.code === selectedCompetition;
              const highContrastLogo =
                requiresHighContrastLogo(competition);

              return (
                <button
                  key={competition.id}
                  className={
                    isSelected
                      ? "rb-competition-chip rb-competition-chip--active"
                      : "rb-competition-chip"
                  }
                  type="button"
                  onClick={() => onSelectCompetition(competition.code)}
                  aria-pressed={isSelected}
                  style={
                    {
                      "--competition-index": competitionIndex,
                    } as CSSProperties
                  }
                >
                  {competition.emblem ? (
                    <span
                      className={
                        highContrastLogo
                          ? "rb-competition-chip__logo rb-competition-chip__logo--high-contrast"
                          : "rb-competition-chip__logo"
                      }
                    >
                      <img
                        src={competition.emblem}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                    </span>
                  ) : (
                    <span className="rb-competition-chip__fallback">
                      {competition.code}
                    </span>
                  )}

                  <span className="rb-competition-chip__label">
                    {getCompetitionShortLabel(competition)}
                  </span>
                </button>
              );
            })}
          </div>

          {totalPages > 1 ? (
            <button
              className="rb-competition-chip-next"
              type="button"
              onClick={switchCompetitionPage}
              aria-label={
                isLastCompetitionPage
                  ? "Revenir aux premières compétitions"
                  : "Afficher les compétitions suivantes"
              }
            >
              {isLastCompetitionPage ? (
                <ChevronLeft size={18} aria-hidden="true" />
              ) : (
                <ChevronRight size={18} aria-hidden="true" />
              )}
            </button>
          ) : null}
        </div>
      )}
    </section>
  );
}

export default CompetitionsSection;

// Schéma de communication du fichier :
// CompetitionsSection.tsx
// ├── reçoit competitions depuis MatchesScreen.tsx
// ├── affiche six ligues maximum sur une seule ligne
// ├── anime le changement de groupe de ligues via le bouton fléché
// ├── renforce le contraste des emblèmes sombres comme la Champions League
// ├── renvoie le code de compétition sélectionné à App.tsx
// └── utilise styles/MatchesScreen.css pour le rendu Obsidian Teal premium
