"use client";

export type DemoId = "completo" | "incompleto" | "empilhadeira2";

const DEMOS: { id: DemoId; title: string; detail: string }[] = [
  { id: "completo", title: "Turno completo", detail: "4/4" },
  { id: "incompleto", title: "Carga pendente", detail: "3/4 + alerta" },
  { id: "empilhadeira2", title: "Empilhadeira 2", detail: "incidentes" },
];

interface DemoControlsProps {
  running: boolean;
  status: string | null;
  onRun: (id: DemoId) => void;
}

export function DemoControls({ running, status, onRun }: DemoControlsProps) {
  return (
    <section className="demo-controls" aria-label="Demonstrações guiadas">
      <div className="demo-copy">
        <span className="demo-label">Demonstração guiada</span>
        <span className="demo-status" aria-live="polite">
          {status ?? "Escolha um cenário para reproduzir."}
        </span>
      </div>
      <div className="demo-actions">
        {DEMOS.map((demo) => (
          <button
            className="demo-button"
            disabled={running}
            key={demo.id}
            onClick={() => onRun(demo.id)}
            type="button"
          >
            <span>{demo.title}</span>
            <small>{demo.detail}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
