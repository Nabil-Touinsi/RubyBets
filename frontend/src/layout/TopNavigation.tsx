// Ce composant affiche la navigation principale horizontale de RubyBets, alignée avec les maquettes MVP.

import type { AppScreen, NavigationItem } from "../types/navigation";

type TopNavigationProps = {
  currentScreen: AppScreen;
  items: NavigationItem[];
  hasSelectedMatch: boolean;
  onNavigate: (screen: AppScreen) => void;
};

const navigationIcons: Record<AppScreen, string> = {
  dashboard: "⌂",
  matches: "▦",
  "match-details": "◇",
  analysis: "✦",
  predictions: "◎",
  recommendation: "✓",
  "lab-ml-v1833": "⚙",
  glossary: "□",
  responsible: "ⓘ",
};

// Ce composant affiche les boutons de navigation et désactive les écrans qui nécessitent un match sélectionné.
function TopNavigation({
  currentScreen,
  items,
  hasSelectedMatch,
  onNavigate,
}: TopNavigationProps) {
  return (
    <nav className="rb-top-navigation" aria-label="Navigation principale RubyBets">
      {items.map((item) => {
        const isDisabled = Boolean(item.requiresMatch && !hasSelectedMatch);
        const itemClassName =
          currentScreen === item.id
            ? "rb-top-navigation__item rb-top-navigation__item--active"
            : "rb-top-navigation__item";

        return (
          <button
            key={item.id}
            type="button"
            className={itemClassName}
            disabled={isDisabled}
            onClick={() => onNavigate(item.id)}
            title={isDisabled ? "Sélectionnez d’abord un match" : item.label}
          >
            <span className="rb-top-navigation__icon" aria-hidden="true">
              {navigationIcons[item.id]}
            </span>
            <span className="rb-top-navigation__label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export default TopNavigation;

// Schéma de communication du fichier :
// TopNavigation.tsx
// ├── reçoit les écrans depuis navigation.ts
// ├── reçoit currentScreen et onNavigate depuis AppShell.tsx
// ├── déclenche le changement d’écran affiché dans App.tsx
// └── affiche aussi l’entrée Lab ML national sans modifier les écrans officiels