// Ce composant affiche le décor lumineux du hero de l’écran Sélection.

// Ce composant fournit uniquement une animation visuelle sans donnée métier.
function RecommendationHeroVisual() {
  return (
    <div className="rb-selection-hero-visual" aria-hidden="true">
      <span className="rb-selection-hero-visual__halo" />
      <span className="rb-selection-hero-visual__scan" />
      <span className="rb-selection-hero-visual__spark rb-selection-hero-visual__spark--one" />
      <span className="rb-selection-hero-visual__spark rb-selection-hero-visual__spark--two" />
      <span className="rb-selection-hero-visual__spark rb-selection-hero-visual__spark--three" />
    </div>
  );
}

export default RecommendationHeroVisual;

// Schéma de communication du fichier :
// RecommendationScreen.tsx -> RecommendationHeroVisual.tsx
// RecommendationHeroVisual.tsx -> selection-hero-field.png via RecommendationScreen.css
