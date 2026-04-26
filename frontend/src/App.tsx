import { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [apiStatus, setApiStatus] = useState<string>("Vérification en cours...");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/health")
      .then((response) => response.json())
      .then((data) => {
        setApiStatus(data.status === "ok" ? "Backend connecté" : "Réponse inattendue");
      })
      .catch(() => {
        setApiStatus("Backend inaccessible");
      });
  }, []);

  return (
    <main>
      <h1>RubyBets</h1>
      <p>Application d’aide à la décision football avant-match.</p>
      <p>Frontend React opérationnel.</p>
      <p className="api-status">{apiStatus}</p>
    </main>
  );
}

export default App;