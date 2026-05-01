// Ce composant affiche les statuts de chargement visibles pendant les tests du MVP RubyBets.

type StatusPanelProps = {
  apiStatus: string;
  competitionsStatus: string;
  matchesStatus: string;
  matchDetailsStatus: string;
  matchContextStatus: string;
  matchAnalysisStatus: string;
  matchPredictionsStatus: string;
  multiMatchStatus: string;
  glossaryStatus: string;
  responsibleInfoStatus: string;
};

function StatusPanel({
  apiStatus,
  competitionsStatus,
  matchesStatus,
  matchDetailsStatus,
  matchContextStatus,
  matchAnalysisStatus,
  matchPredictionsStatus,
  multiMatchStatus,
  glossaryStatus,
  responsibleInfoStatus,
}: StatusPanelProps) {
  return (
    <>
      <p className="api-status">{apiStatus}</p>
      <p className="api-status">{competitionsStatus}</p>
      <p className="api-status">{matchesStatus}</p>
      <p className="api-status">{matchDetailsStatus}</p>
      <p className="api-status">{matchContextStatus}</p>
      <p className="api-status">{matchAnalysisStatus}</p>
      <p className="api-status">{matchPredictionsStatus}</p>
      <p className="api-status">{multiMatchStatus}</p>
      <p className="api-status">{glossaryStatus}</p>
      <p className="api-status">{responsibleInfoStatus}</p>
    </>
  );
}

export default StatusPanel;