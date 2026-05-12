// Ce fichier définit les écrans de navigation du MVP RubyBets et les entrées du menu principal.

export type AppScreen =
  | "dashboard"
  | "matches"
  | "match-details"
  | "analysis"
  | "predictions"
  | "recommendation"
  | "glossary"
  | "responsible";

export type NavigationItem = {
  id: AppScreen;
  label: string;
  requiresMatch?: boolean;
};

export const NAVIGATION_ITEMS: NavigationItem[] = [
  { id: "dashboard", label: "Accueil" },
  { id: "matches", label: "Matchs" },
  { id: "match-details", label: "Détail match", requiresMatch: true },
  { id: "analysis", label: "Analyse", requiresMatch: true },
  { id: "predictions", label: "Prédictions", requiresMatch: true },
  { id: "recommendation", label: "Recommandation" },
  { id: "glossary", label: "Glossaire" },
  { id: "responsible", label: "Infos responsables" },
];

// Schéma de communication du fichier :
// navigation.ts
// ├── fournit la liste des écrans MVP
// ├── alimente TopNavigation.tsx pour afficher le menu
// └── alimente App.tsx pour contrôler l’écran actif
