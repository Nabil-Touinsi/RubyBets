// Ce fichier définit les écrans de navigation du MVP RubyBets et les libellés utilisés dans le menu principal.

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
  shortLabel?: string;
  requiresMatch?: boolean;
};

export const NAVIGATION_ITEMS: NavigationItem[] = [
  { id: "dashboard", label: "Accueil" },
  { id: "matches", label: "Matchs" },
  { id: "match-details", label: "Détail match", shortLabel: "Détail", requiresMatch: true },
  { id: "analysis", label: "Analyse", requiresMatch: true },
  { id: "predictions", label: "Prédictions", requiresMatch: true },
  { id: "recommendation", label: "Recommandation", shortLabel: "Sélection" },
  { id: "glossary", label: "Glossaire" },
  { id: "responsible", label: "Infos responsables", shortLabel: "Responsable" },
];

// Schéma de communication du fichier :
// navigation.ts
// ├── fournit la liste des écrans MVP officiels
// ├── alimente TopNavigation.tsx pour afficher le menu principal
// ├── alimente App.tsx pour contrôler l’écran actif
// └── garde le Lab ML national hors navigation principale
