// Ce composant définit la structure générale de l’application RubyBets : header premium, logo officiel, navigation et contenu.
// Il garde le statut backend hors de la navbar afin de conserver une interface plus sobre et moins technique.

import { Moon } from "lucide-react";
import type { ReactNode } from "react";
import rubyBetsNavbarLogo from "../assets/rubybets_logo_pack_premium/rubybets_logo_navbar.svg";
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
          <div className="rb-brand" aria-label="RubyBets">
            <img
              className="rb-brand__logo"
              src={rubyBetsNavbarLogo}
              alt="RubyBets"
              decoding="async"
            />
          </div>

          <div className="rb-app-header__right">
            <TopNavigation
              currentScreen={currentScreen}
              items={navigationItems}
              hasSelectedMatch={hasSelectedMatch}
              onNavigate={onNavigate}
            />

            <div className="rb-navbar-actions" aria-label="Actions d’interface">
              <span className="rb-theme-indicator" aria-label="Mode sombre actif" title="Mode sombre actif">
                <Moon aria-hidden="true" size={16} strokeWidth={1.9} />
              </span>
            </div>
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
// ├── utilise rubybets_logo_navbar.svg pour afficher le logo premium dans la navbar
// ├── utilise TopNavigation.tsx pour afficher le menu principal
// ├── reçoit l’écran actif et les contenus depuis App.tsx
// └── encadre les écrans du dossier screens/ sans modifier les appels API
