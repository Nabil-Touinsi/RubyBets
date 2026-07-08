// Ce composant affiche la navigation principale compacte de RubyBets avec icônes, libellés courts et états accessibles.
// Il garde une barre horizontale premium sans modifier la logique métier ni les contrats API.

import {
  Activity,
  Archive,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  FileText,
  Home,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { AppScreen, NavigationItem } from "../types/navigation";

type TopNavigationProps = {
  currentScreen: AppScreen;
  items: NavigationItem[];
  hasSelectedMatch: boolean;
  onNavigate: (screen: AppScreen) => void;
};

const NAVIGATION_ICONS: Record<AppScreen, LucideIcon> = {
  dashboard: Home,
  matches: CalendarDays,
  "match-details": FileText,
  analysis: Activity,
  predictions: TrendingUp,
  recommendation: CheckCircle2,
  archives: Archive,
  resources: BookOpen,
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
        const Icon = NAVIGATION_ICONS[item.id];
        const isActive = currentScreen === item.id;
        const isDisabled = Boolean(item.requiresMatch && !hasSelectedMatch);
        const itemClassName = isActive
          ? "rb-top-navigation__item rb-top-navigation__item--active"
          : "rb-top-navigation__item";
        const visibleLabel = item.shortLabel || item.label;

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
            <Icon className="rb-top-navigation__icon" aria-hidden="true" size={16} strokeWidth={1.9} />
            <span className="rb-top-navigation__label">{visibleLabel}</span>
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
// ├── affiche aussi l’entrée Archives ajoutée au MVP
// └── utilise App.css pour rendre la navigation compacte et alignée