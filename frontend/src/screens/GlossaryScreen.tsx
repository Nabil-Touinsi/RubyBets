// Ce fichier affiche l’écran Glossaire de RubyBets.

import type { GlossaryResponse } from "../models/rubybets";
import GlossarySection from "../components/GlossarySection";

type GlossaryScreenProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
};

// Ce composant structure l’écran Glossaire avec un bloc principal et une colonne d’explication.
function GlossaryScreen({ glossary, glossaryStatus }: GlossaryScreenProps) {
  return (
    <div className="rb-glossary-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Glossaire</p>
          <h2>Comprendre les termes utilisés</h2>
          <p>
            Le glossaire aide à comprendre les marchés MVP, les niveaux de
            confiance, les niveaux de risque et les notions utilisées dans les
            analyses RubyBets.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Statut</p>
          <h3>{glossaryStatus}</h3>
          <p>
            Ces définitions rendent l’application plus accessible et facilitent
            la lecture des recommandations analytiques.
          </p>
        </aside>
      </section>

      <section className="rb-glossary-layout">
        <div className="rb-glossary-main">
          <GlossarySection glossary={glossary} />
        </div>

        <aside className="rb-glossary-aside">
          <article>
            <p className="rb-eyebrow">Objectif</p>
            <h3>Lecture pédagogique</h3>
            <p>
              Chaque terme sert à mieux comprendre les blocs d’analyse, de
              prédiction et de recommandation multi-matchs.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Notions clés</p>
            <h3>Confiance et risque</h3>
            <p>
              RubyBets distingue le niveau de confiance d’une recommandation et
              le niveau de risque associé à son interprétation.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Cadre responsable</p>
            <h3>Aucune garantie</h3>
            <p>
              RubyBets est une aide à la décision avant-match. L’application ne
              permet pas de parier, n’est pas un bookmaker et ne promet aucun
              résultat sportif.
            </p>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default GlossaryScreen;

// Schéma de communication du fichier :
// GlossaryScreen.tsx
// ├── reçoit glossary et glossaryStatus depuis App.tsx
// ├── utilise GlossarySection.tsx pour afficher les définitions
// ├── s’appuie sur les types de models/rubybets.ts
