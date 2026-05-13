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

// Ce composant encadre tous les écrans MVP avec un header compact, une navigation stable et le contenu courant.
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
        <div className="rb-app-header__inner">
          <div className="rb-brand" aria-label="RubyBets MVP">
            <span className="rb-brand__mark">◆</span>
            <div className="rb-brand__text">
              <p className="rb-eyebrow">RubyBets MVP</p>
              <h1>RubyBets</h1>
              <p>Application d’aide à la décision football avant-match.</p>
            </div>
          </div>

          <div className="rb-app-header__right">
            <TopNavigation
              currentScreen={currentScreen}
              items={navigationItems}
              hasSelectedMatch={hasSelectedMatch}
              onNavigate={onNavigate}
            />

            <span className="rb-header-badge">Aide à la décision avant-match</span>
          </div>
        </div>
      </header>

      <section className="rb-screen-container">{children}</section>

      <footer className="rb-status-footer">{statusNode}</footer>
    </main>
  );
}

export default AppShell;

// Schéma de communication du fichier :
// AppShell.tsx
// ├── utilise TopNavigation.tsx pour afficher le menu principal
// ├── reçoit l’écran actif, le statut et les contenus depuis App.tsx
// └── encadre les écrans du dossier screens/ sans modifier les appels API
