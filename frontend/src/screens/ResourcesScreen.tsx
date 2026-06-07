// Ce fichier affiche l’écran Ressources unifié de RubyBets avec un hero premium, le glossaire et le cadre responsable.

import type {
  GlossaryResponse,
  ResponsibleInfoResponse,
} from "../models/rubybets";
import GlossarySection from "../components/GlossarySection";

type ResourcesScreenProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
  responsibleInfo: ResponsibleInfoResponse | null;
  responsibleInfoStatus: string;
};

// Ce composant affiche les ressources pédagogiques et responsables sans modifier les appels API existants.
function ResourcesScreen({
  glossary,
  glossaryStatus,
}: ResourcesScreenProps) {
  return (
    <div className="rb-resources-v2-screen">
      <header className="rb-resources-v2-hero">
        <div className="rb-resources-v2-hero__copy">
          <p className="rb-resources-v2-kicker">Ressources</p>
          <h2>Centre de ressources RubyBets</h2>
          <p>
            Comprenez les notions clés utilisées dans l’application ainsi que le cadre responsable
            qui accompagne chaque lecture avant-match.
          </p>
        </div>

        <div className="rb-resources-v2-hero__visual" aria-hidden="true">
          <span className="rb-resources-v2-visual__tag rb-resources-v2-visual__tag--analysis">
            Analyse
          </span>
          <span className="rb-resources-v2-visual__tag rb-resources-v2-visual__tag--data">
            Données
          </span>
          <span className="rb-resources-v2-visual__tag rb-resources-v2-visual__tag--safe">
            Responsable
          </span>

          <span className="rb-resources-v2-visual__document">
            <span />
            <span />
            <span />
            <span />
            <span />
          </span>
        </div>
      </header>

      <GlossarySection glossary={glossary} glossaryStatus={glossaryStatus} />
    </div>
  );
}

export default ResourcesScreen;

// Schéma de communication du fichier :
// ResourcesScreen.tsx
// ├── reçoit glossary et responsibleInfo depuis App.tsx
// ├── transmet glossary à GlossarySection.tsx
// ├── affiche le hero premium de l’écran Ressources
// └── utilise App.css pour le rendu visuel sans modifier backend, API ou modèles ML