"use client";

import { useEffect, useRef, useState } from "react";
import type { ChecklistItemStatus } from "@shared/types";

export function ChecklistPanel({ items }: { items: ChecklistItemStatus[] }) {
  const covered = items.filter((i) => i.covered).length;
  const pct = items.length === 0 ? 0 : Math.round((100 * covered) / items.length);
  const shown = useRamp(pct);
  const flashing = useNewlyCovered(items);

  return (
    <section className="panel">
      <div className="coverage">
        <div className="coverage-row">
          <span className="coverage-num">{shown}%</span>
          <span className="coverage-of">
            {covered} de {items.length} confirmados
          </span>
        </div>
        <div className="coverage-track">
          <div className="coverage-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="panel-body">
        <div className="cards">
          {items.length === 0 && (
            <p className="empty">Nenhum checklist configurado para esta estação.</p>
          )}

          {items.map((item) => (
            <article
              key={item.item}
              className="card"
              data-covered={item.covered}
              data-flash={flashing.has(item.item)}
            >
              <span className="card-item">{item.item}</span>
              {/* Evidência sempre visível: num vídeo ninguém vê o mouse parado. */}
              {item.covered && item.evidence && (
                <span className="card-evidence">{item.evidence}</span>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

/** Contador que sobe em vez de saltar — 300ms, imperceptível como efeito. */
function useRamp(target: number): number {
  const [value, setValue] = useState(target);
  const from = useRef(target);

  useEffect(() => {
    const start = performance.now();
    const origin = from.current;
    let raf = 0;

    const tick = (now: number) => {
      const t = Math.min((now - start) / 300, 1);
      setValue(Math.round(origin + (target - origin) * t));
      if (t < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  return value;
}

/**
 * Com snapshot completo, o React re-renderiza tudo e não há como saber o que
 * mudou. Diferença contra o snapshot anterior identifica quais itens acabaram
 * de virar — só esses recebem o pulso de glow.
 */
function useNewlyCovered(items: ChecklistItemStatus[]): Set<string> {
  const previous = useRef<Set<string>>(new Set());
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  useEffect(() => {
    const now = new Set(items.filter((i) => i.covered).map((i) => i.item));
    const fresh = [...now].filter((item) => !previous.current.has(item));
    previous.current = now;

    if (fresh.length === 0) return;
    setFlashing(new Set(fresh));
    const timer = setTimeout(() => setFlashing(new Set()), 700);
    return () => clearTimeout(timer);
  }, [items]);

  return flashing;
}
