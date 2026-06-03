// Ce fichier regroupe le glossaire et les informations responsables dans un seul écran Ressources.

import type {
  GlossaryResponse,
  ResponsibleInfoResponse,
} from "../models/rubybets";
import GlossarySection from "../components/GlossarySection";
import ResponsibleInfoSection from "../components/ResponsibleInfoSection";

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
  responsibleInfo,
  responsibleInfoStatus,
}: ResourcesScreenProps) {
  return (
    <div className="rb-resources-screen">
      <header className="rb-resources-hero">
        <p className="rb-resources-hero__eyebrow">RESSOURCES</p>
        <h2>Comprendre RubyBets et ses limites</h2>
        <p>
          Retrouvez les notions clés utilisées dans l’application ainsi que le cadre responsable
          qui accompagne chaque lecture avant-match.
        </p>
      </header>

      <section className="rb-resources-grid" aria-label="Ressources RubyBets">
        <article className="rb-resources-panel">
          <GlossarySection glossary={glossary} glossaryStatus={glossaryStatus} />
        </article>

        <article className="rb-resources-panel">
          <ResponsibleInfoSection
            responsibleInfo={responsibleInfo}
            responsibleInfoStatus={responsibleInfoStatus}
          />
        </article>
      </section>
    </div>
  );
}

export default ResourcesScreen;

// Schéma de communication du fichier :
// ResourcesScreen.tsx
// ├── reçoit glossary et responsibleInfo depuis App.tsx
// ├── transmet glossary à GlossarySection.tsx
// ├── transmet responsibleInfo à ResponsibleInfoSection.tsx
// └── utilise App.css pour afficher un écran Ressources unifié