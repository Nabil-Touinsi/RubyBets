// Ce composant affiche les messages responsables et les limites d’usage de RubyBets.

import type { ResponsibleInfoResponse } from "../models/rubybets";
import { formatPriority } from "../helpers/displayText";

type ResponsibleInfoSectionProps = {
  responsibleInfo: ResponsibleInfoResponse | null;
};

function ResponsibleInfoSection({ responsibleInfo }: ResponsibleInfoSectionProps) {
  return (
    <section>
      <h2>Informations responsables</h2>

      <p>
        Cette section rappelle les limites de RubyBets et son positionnement
        comme outil d’aide à la décision.
      </p>

      {responsibleInfo ? (
        <div>
          <p>Nombre de messages : {responsibleInfo.count}</p>

          <p>
            Positionnement :{" "}
            <strong>{responsibleInfo.summary.product_positioning}</strong>
          </p>

          <p>
            Pari réel activé :{" "}
            {responsibleInfo.summary.real_betting_enabled ? "Oui" : "Non"}
          </p>

          <p>
            Analyse live activée :{" "}
            {responsibleInfo.summary.live_analysis_enabled ? "Oui" : "Non"}
          </p>

          <p>
            Données réelles utilisées :{" "}
            {responsibleInfo.summary.uses_real_data ? "Oui" : "Non"}
          </p>

          <p>
            Garantie de résultat :{" "}
            {responsibleInfo.summary.guarantees_result ? "Oui" : "Non"}
          </p>

          {responsibleInfo.items.map((item) => (
            <article key={`${item.type}-${item.title}`}>
              <h3>{item.title}</h3>
              <p>Priorité : {formatPriority(item.priority)}</p>
              <p>{item.content}</p>
            </article>
          ))}
        </div>
      ) : (
        <p>Aucune information responsable disponible pour le moment.</p>
      )}
    </section>
  );
}

export default ResponsibleInfoSection;