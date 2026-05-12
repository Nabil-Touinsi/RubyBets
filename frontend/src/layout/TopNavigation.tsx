// Ce composant affiche la navigation principale horizontale de RubyBets, alignée avec les maquettes MVP.

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
        const isDisabled = Boolean(item.requiresMatch && !hasSelectedMatch);

        return (
          <button
            key={item.id}
            type="button"
            className={
              currentScreen === item.id
                ? "rb-top-navigation__item rb-top-navigation__item--active"
                : "rb-top-navigation__item"
            }
            disabled={isDisabled}
            onClick={() => onNavigate(item.id)}
            title={isDisabled ? "Sélectionnez d’abord un match" : item.label}
          >
            {item.label}
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
// ├── reçoit l’état currentScreen depuis App.tsx
// └── déclenche onNavigate pour changer l’écran affiché dans App.tsx
