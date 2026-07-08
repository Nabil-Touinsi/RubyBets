// Ce fichier définit les écrans de navigation du MVP RubyBets et les libellés utilisés dans le menu principal.

export type AppScreen =
  | "dashboard"
  | "matches"
  | "match-details"
  | "analysis"
  | "predictions"
  | "recommendation"
  | "archives"
  | "resources";

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
  { id: "predictions", label: "Prédictions", requiresMatch: true },
  { id: "recommendation", label: "Recommandation", shortLabel: "Sélection" },
  { id: "archives", label: "Archives" },
  { id: "resources", label: "Ressources" },
];

// Schéma de communication du fichier :
// navigation.ts
// ├── fournit la liste des écrans disponibles dans RubyBets
// ├── alimente TopNavigation.tsx pour afficher le menu principal simplifié
// ├── conserve analysis pour l’accès interne depuis le détail match
// ├── ajoute archives comme nouvel écran de suivi des prédictions
// └── regroupe glossaire et informations responsables dans resources