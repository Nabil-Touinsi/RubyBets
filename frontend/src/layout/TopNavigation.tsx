// Ce composant affiche la navigation principale horizontale de RubyBets sans pictogrammes instables.
// Il clarifie les états actif, disponible et désactivé pour une lecture plus professionnelle en soutenance.

import type { AppScreen, NavigationItem } from "../types/navigation";

type TopNavigationProps = {
  currentScreen: AppScreen;
  items: NavigationItem[];
  hasSelectedMatch: boolean;
  onNavigate: (screen: AppScreen) => void;
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
        const isActive = currentScreen === item.id;
        const isDisabled = Boolean(item.requiresMatch && !hasSelectedMatch);
        const itemClassName = isActive
          ? "rb-top-navigation__item rb-top-navigation__item--active"
          : "rb-top-navigation__item";

        return (
          <button
            key={item.id}
            type="button"
            className={itemClassName}
            disabled={isDisabled}
            data-disabled={isDisabled ? "true" : "false"}
            aria-current={isActive ? "page" : undefined}
            onClick={() => onNavigate(item.id)}
            title={isDisabled ? "Sélectionnez d’abord un match" : item.label}
          >
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
// └── garde une navigation sans icônes fragiles, alignée avec App.css
