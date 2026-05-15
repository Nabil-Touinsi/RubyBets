// Ce fichier affiche l’écran Informations responsables de RubyBets avec une structure proche de la maquette validée.

import type { ResponsibleInfoResponse } from "../models/rubybets";
import ResponsibleInfoSection from "../components/ResponsibleInfoSection";

type ResponsibleInfoScreenProps = {
  responsibleInfo: ResponsibleInfoResponse | null;
  responsibleInfoStatus: string;
};

// Ce composant organise l’écran responsable : retour, introduction, visuel bouclier et cartes pédagogiques.
function ResponsibleInfoScreen({
  responsibleInfo,
  responsibleInfoStatus,
}: ResponsibleInfoScreenProps) {
  return (
    <div className="rb-responsible-screen--mockup">
      <button
        type="button"
        className="rb-responsible-back-button"
        onClick={() => window.history.back()}
      >
        ← Retour
      </button>

      <header className="rb-responsible-hero--mockup">
        <div className="rb-responsible-hero__content">
          <h2>Informations responsables / limites de l’outil</h2>
          <p>
            RubyBets est conçu pour vous aider à prendre des décisions éclairées avant match.
            Cette page vous informe sur le positionnement de l’outil, ses limites et les bonnes
            pratiques à adopter.
          </p>
        </div>

        <div className="rb-responsible-shield" aria-hidden="true">
          <span className="rb-responsible-shield__halo" />
          <span className="rb-responsible-shield__shape">
            <span>✓</span>
          </span>
        </div>
      </header>

      <ResponsibleInfoSection
        responsibleInfo={responsibleInfo}
        responsibleInfoStatus={responsibleInfoStatus}
      />

      <p className="rb-responsible-footer-note">
        Outil d’aide à la décision. Les analyses proposées ne constituent pas un conseil en
        investissement ou un pari.
      </p>
    </div>
  );
}

export default ResponsibleInfoScreen;

// Schéma de communication du fichier :
// ResponsibleInfoScreen.tsx
// ├── reçoit responsibleInfo et responsibleInfoStatus depuis App.tsx
// ├── transmet ces données à ResponsibleInfoSection.tsx
// ├── affiche un visuel décoratif sans ajouter de logique métier
// └── est stylisé par App.css avec la classe rb-responsible-screen--mockup