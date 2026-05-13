// Ce composant affiche les compétitions MVP sous forme de filtres horizontaux.

import type { Competition } from "../models/rubybets";

type CompetitionsSectionProps = {
  competitions: Competition[];
  selectedCompetition: string;
  onSelectCompetition: (competitionCode: string) => void;
};

// Cette fonction prépare un libellé court pour garder les boutons de ligue lisibles.
function getCompetitionShortLabel(competition: Competition) {
  return competition.name
    .replace("Premier League", "Premier League")
    .replace("UEFA Champions League", "Champions League")
    .replace("Campeonato Brasileiro Série A", "Brasileirão");
}

// Ce composant affiche les ligues disponibles avec un état actif clair.
function CompetitionsSection({
  competitions,
  selectedCompetition,
  onSelectCompetition,
}: CompetitionsSectionProps) {
  return (
    <section className="rb-competitions-strip">
      <div className="rb-competitions-strip__header">
        <span className="rb-matches-panel-label">Ligues principales</span>
      </div>

      {competitions.length === 0 ? (
        <p className="rb-competitions-empty">
          Aucune compétition disponible pour le moment.
        </p>
      ) : (
        <div className="rb-competition-chip-row">
          {competitions.map((competition) => (
            <button
              key={competition.id}
              className={
                competition.code === selectedCompetition
                  ? "rb-competition-chip rb-competition-chip--active"
                  : "rb-competition-chip"
              }
              type="button"
              onClick={() => onSelectCompetition(competition.code)}
            >
              {competition.emblem ? (
                <span className="rb-competition-chip__logo">
                  <img src={competition.emblem} alt="" loading="lazy" />
                </span>
              ) : (
                <span className="rb-competition-chip__fallback">
                  {competition.code}
                </span>
              )}

              <span>{getCompetitionShortLabel(competition)}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default CompetitionsSection;

// Schéma de communication du fichier :
// CompetitionsSection.tsx
// ├── reçoit competitions depuis MatchesScreen.tsx
// ├── affiche les ligues sous forme de chips horizontaux
// ├── renvoie le code de compétition sélectionné à App.tsx
// └── utilise App.css pour le style Obsidian Teal