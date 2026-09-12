"use client";

/**
 * Contexto que vale o turno inteiro, por isso fica no topo — o rodapé é
 * reservado para o overlay de intervenção. Só renderiza quando
 * ambiguous_alert !== null; o grid da shell absorve a ausência sem buraco.
 */
export function AlertBand({ text }: { text: string }) {
  return (
    <div className="alert-band" role="status">
      <span className="alert-tag">Reincidência</span>
      <span>{text}</span>
    </div>
  );
}
