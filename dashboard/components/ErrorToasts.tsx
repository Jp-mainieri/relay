"use client";

import { useEffect } from "react";

interface Props {
  errors: { id: number; message: string }[];
  onDismiss: (id: number) => void;
}

/**
 * O evento `error` do contrato nunca derruba a conexão nem a UI — é só aviso
 * (RNF04). Fica em cinza, canto inferior direito. Nunca coral: coral pertence
 * ao alerta da Ambiguous e confundir os dois no vídeo seria ruim.
 */
export function ErrorToasts({ errors, onDismiss }: Props) {
  useEffect(() => {
    if (errors.length === 0) return;
    const timers = errors.map((e) => setTimeout(() => onDismiss(e.id), 6000));
    return () => timers.forEach(clearTimeout);
  }, [errors, onDismiss]);

  if (errors.length === 0) return null;

  return (
    <div className="toasts">
      {errors.map((e) => (
        <p key={e.id} className="toast">
          {e.message}
        </p>
      ))}
    </div>
  );
}
