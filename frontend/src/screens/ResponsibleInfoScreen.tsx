// Ce fichier affiche l’écran Informations responsables de RubyBets.

import type { ResponsibleInfoResponse } from "../models/rubybets";
import ResponsibleInfoSection from "../components/ResponsibleInfoSection";

type ResponsibleInfoScreenProps = {
  responsibleInfo: ResponsibleInfoResponse | null;
  responsibleInfoStatus: string;
};

// Ce composant structure l’écran responsable avec le contenu principal et une colonne de rappel produit.
function ResponsibleInfoScreen({
  responsibleInfo,
  responsibleInfoStatus,
}: ResponsibleInfoScreenProps) {
  return (
    <div className="rb-responsible-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Cadre responsable</p>
          <h2>Informations responsables et limites de l’outil</h2>
          <p>
            Cette page précise le positionnement de RubyBets, ses limites
            d’usage et les principes à respecter pour interpréter correctement
            les recommandations avant-match.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Statut</p>
          <h3>{responsibleInfoStatus}</h3>
          <p>
            Le cadre responsable fait partie du MVP afin d’éviter toute
            confusion avec une plateforme de pari ou une promesse de résultat.
          </p>
        </aside>
      </section>

      <section className="rb-responsible-layout">
        <div className="rb-responsible-main">
          <ResponsibleInfoSection responsibleInfo={responsibleInfo} />
        </div>

        <aside className="rb-responsible-aside">
          <article>
            <p className="rb-eyebrow">Positionnement</p>
            <h3>Aide à la décision</h3>
            <p>
              RubyBets accompagne l’analyse football avant-match. L’application
              ne permet pas de parier et ne remplace pas le jugement de
              l’utilisateur.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Limite principale</p>
            <h3>Aucune garantie</h3>
            <p>
              Une recommandation analytique reste soumise à l’incertitude des
              données, du contexte sportif et des événements imprévisibles.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">V1 RubyBets</p>
            <h3>Scoring explicable</h3>
            <p>
              La V1 repose sur des règles métier et des données réelles. Elle
              ne doit pas être présentée comme un modèle Machine Learning
              entraîné.
            </p>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default ResponsibleInfoScreen;

// Schéma de communication du fichier :
// ResponsibleInfoScreen.tsx
// ├── reçoit responsibleInfo et responsibleInfoStatus depuis App.tsx
// ├── utilise ResponsibleInfoSection.tsx pour afficher les messages responsables
// ├── s’appuie sur les types de models/rubybets.ts