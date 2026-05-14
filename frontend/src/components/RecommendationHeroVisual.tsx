// Ce composant affiche un visuel décoratif inspiré d’un terrain de football

function RecommendationHeroVisual() {
  return (
    <div className="rb-reco-visual rb-reco-pitch-visual" aria-hidden="true">
      <div className="rb-reco-pitch-visual__glow" />

      <div className="rb-reco-pitch-visual__field">
        <span className="rb-reco-pitch-line rb-reco-pitch-line--outer" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--mid" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--center-circle" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--box-left" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--box-right" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--goal-left" />
        <span className="rb-reco-pitch-line rb-reco-pitch-line--goal-right" />

        <span className="rb-reco-pitch-node rb-reco-pitch-node--one" />
        <span className="rb-reco-pitch-node rb-reco-pitch-node--two" />
        <span className="rb-reco-pitch-node rb-reco-pitch-node--three" />
        <span className="rb-reco-pitch-node rb-reco-pitch-node--four" />
        <span className="rb-reco-pitch-node rb-reco-pitch-node--five" />
      </div>
    </div>
  );
}

export default RecommendationHeroVisual;

// Schéma de communication du fichier :
// RecommendationHeroVisual.tsx
// ├── utilisé par RecommendationScreen.tsx
// ├── fournit uniquement un décor visuel frontend
// └── ne communique ni avec l’API ni avec le backend