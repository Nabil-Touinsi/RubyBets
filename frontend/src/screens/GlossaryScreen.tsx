// Ce fichier affiche l’écran Glossaire de RubyBets avec une structure dédiée à la maquette MVP.

import type { GlossaryResponse } from "../models/rubybets";
import GlossarySection from "../components/GlossarySection";

type GlossaryScreenProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
};

// Ce composant transmet les données du glossaire au composant visuel sans modifier la logique API.
function GlossaryScreen({ glossary, glossaryStatus }: GlossaryScreenProps) {
  return (
    <div className="rb-glossary-screen">
      <GlossarySection glossary={glossary} glossaryStatus={glossaryStatus} />
    </div>
  );
}

export default GlossaryScreen;

// Schéma de communication du fichier :
// GlossaryScreen.tsx
// ├── reçoit glossary et glossaryStatus depuis App.tsx
// ├── transmet ces données à GlossarySection.tsx
// ├── conserve la navigation gérée par AppShell.tsx
// └── ne modifie ni services/api.ts, ni models/rubybets.ts, ni le backend
