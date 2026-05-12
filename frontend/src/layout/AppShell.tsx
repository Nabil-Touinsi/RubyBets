// Ce composant définit la structure générale de l’application RubyBets : header, navigation, contenu et zone de statut.

import type { ReactNode } from "react";
import type { AppScreen, NavigationItem } from "../types/navigation";
import TopNavigation from "./TopNavigation";

type AppShellProps = {
  currentScreen: AppScreen;
  navigationItems: NavigationItem[];
  hasSelectedMatch: boolean;
  statusNode: ReactNode;
  children: ReactNode;
  onNavigate: (screen: AppScreen) => void;
};

// Ce composant encadre tous les écrans MVP avec un header commun et une navigation stable.
function AppShell({
  currentScreen,
  navigationItems,
  hasSelectedMatch,
  statusNode,
  children,
  onNavigate,
}: AppShellProps) {
  return (
    <main className="rb-app-shell">
      <header className="rb-app-header">
        <div className="rb-brand">
          <span className="rb-brand__mark">◆</span>
          <div>
            <p className="rb-eyebrow">RubyBets MVP</p>
            <h1>RubyBets</h1>
            <p>Application d’aide à la décision football avant-match.</p>
          </div>
        </div>

        <TopNavigation
          currentScreen={currentScreen}
          items={navigationItems}
          hasSelectedMatch={hasSelectedMatch}
          onNavigate={onNavigate}
        />
      </header>

      <section className="rb-screen-container">{children}</section>

      <footer className="rb-status-footer">{statusNode}</footer>
    </main>
  );
}

export default AppShell;

// Schéma de communication du fichier :
// AppShell.tsx
// ├── utilise TopNavigation.tsx pour afficher le menu
// ├── reçoit l’écran actif et les contenus depuis App.tsx
// └── encadre les futurs écrans du dossier screens/
