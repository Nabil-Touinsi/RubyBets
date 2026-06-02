// Ce fichier initialise l’application React RubyBets et charge les polices premium utilisées par l’interface.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-sans/800.css";
import "@fontsource/geist-mono/500.css";
import "@fontsource/geist-mono/700.css";

import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Schéma de communication du fichier :
// main.tsx
// ├── charge les polices Geist depuis @fontsource
// ├── charge les styles globaux index.css
// ├── initialise App.tsx
// └── ne modifie ni l’API, ni le backend, ni les modèles ML