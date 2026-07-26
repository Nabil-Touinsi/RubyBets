// Ce fichier compose l’écran Ressources modernisé avec son hero lumineux et le centre d’apprentissage RubyBets.

import {
  BarChart3,
  BookOpen,
  ShieldCheck,
  Target,
  TrendingUp,
} from "lucide-react";
import type {
  GlossaryResponse,
  ResponsibleInfoResponse,
} from "../models/rubybets";
import GlossarySection from "../components/GlossarySection";
import "../styles/ResourcesScreen.css";

type ResourcesScreenProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
  responsibleInfo: ResponsibleInfoResponse | null;
  responsibleInfoStatus: string;
};

// Ce composant dessine le livre lumineux et les quatre repères pédagogiques du hero.
function ResourcesHeroVisual() {
  return (
    <div className="rb-learning-hero-visual" aria-hidden="true">
      <span className="rb-learning-orbit rb-learning-orbit--one" />
      <span className="rb-learning-orbit rb-learning-orbit--two" />
      <span className="rb-learning-orbit rb-learning-orbit--three" />
      <span className="rb-learning-hero-glow" />

      <span className="rb-learning-book-stage">
        <span className="rb-learning-book-halo" />
        <span className="rb-learning-book">
          <BookOpen size={86} strokeWidth={1.2} />
        </span>
        <span className="rb-learning-stage-ring rb-learning-stage-ring--one" />
        <span className="rb-learning-stage-ring rb-learning-stage-ring--two" />
      </span>

      <span className="rb-learning-hero-node rb-learning-hero-node--understand">
        <span className="rb-learning-hero-node__icon">
          <BarChart3 size={23} strokeWidth={1.7} />
        </span>
        <span>
          <strong>Comprendre</strong>
          <small>les statistiques</small>
        </span>
      </span>

      <span className="rb-learning-hero-node rb-learning-hero-node--analyse">
        <span className="rb-learning-hero-node__icon">
          <Target size={23} strokeWidth={1.7} />
        </span>
        <span>
          <strong>Analyser</strong>
          <small>les tendances</small>
        </span>
      </span>

      <span className="rb-learning-hero-node rb-learning-hero-node--decide">
        <span className="rb-learning-hero-node__icon">
          <ShieldCheck size={23} strokeWidth={1.7} />
        </span>
        <span>
          <strong>Décider</strong>
          <small>en toute confiance</small>
        </span>
      </span>

      <span className="rb-learning-hero-node rb-learning-hero-node--progress">
        <span className="rb-learning-hero-node__icon">
          <TrendingUp size={23} strokeWidth={1.7} />
        </span>
        <span>
          <strong>Progresser</strong>
          <small>à chaque match</small>
        </span>
      </span>
    </div>
  );
}

// Ce composant affiche les ressources pédagogiques et responsables sans modifier les appels API existants.
function ResourcesScreen({
  glossary,
  glossaryStatus,
  responsibleInfo,
  responsibleInfoStatus,
}: ResourcesScreenProps) {
  return (
    <div className="rb-learning-screen">
      <header className="rb-learning-hero">
        <div className="rb-learning-hero__copy">
          <p className="rb-learning-pill">Ressources</p>
          <h1 className="rb-learning-hero-title">
            <span className="rb-learning-hero-title__line">Centre de ressources</span>
            <span className="rb-learning-hero-title__brand" aria-label="RubyBets">
              <span>Ruby</span><strong>Bets</strong>
            </span>
          </h1>
          <p>
            Des explications simples pour comprendre les notions clés et mieux interpréter
            chaque analyse avant-match.
          </p>
        </div>

        <ResourcesHeroVisual />
      </header>

      <GlossarySection
        glossary={glossary}
        glossaryStatus={glossaryStatus}
        responsibleInfo={responsibleInfo}
        responsibleInfoStatus={responsibleInfoStatus}
      />
    </div>
  );
}

export default ResourcesScreen;

// Schéma de communication du fichier :
// App.tsx
//   └── ResourcesScreen.tsx
//         ├── ResourcesHeroVisual (visuel local React/CSS)
//         ├── GlossarySection.tsx (recherche, catégories et définitions)
//         └── ResourcesScreen.css (design, animations et responsive)
