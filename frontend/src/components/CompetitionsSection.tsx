// Ce composant affiche la liste des compétitions MVP disponibles dans RubyBets.

import type { Competition } from "../models/rubybets";

type CompetitionsSectionProps = {
  competitions: Competition[];
  onSelectCompetition: (competitionCode: string) => void;
};

function CompetitionsSection({
  competitions,
  onSelectCompetition,
}: CompetitionsSectionProps) {
  return (
    <section>
      <h2>Compétitions MVP</h2>

      {competitions.length === 0 ? (
        <p>Aucune compétition disponible pour le moment.</p>
      ) : (
        <div>
          {competitions.map((competition) => (
            <button
              key={competition.id}
              type="button"
              onClick={() => onSelectCompetition(competition.code)}
            >
              {competition.name} ({competition.code})
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default CompetitionsSection;