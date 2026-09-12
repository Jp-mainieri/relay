import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

const DEMOS = {
  completo: {
    file: "completa_padrao.txt",
    title: "Turno completo",
    description: "Checklist 4/4, sem intervenção.",
  },
  incompleto: {
    file: "incompleta_sem_refrigerada.txt",
    title: "Carga pendente",
    description: "Checklist 3/4 e intervenção ao encerrar.",
  },
  empilhadeira2: {
    file: "empilhadeira2_problema.txt",
    title: "Empilhadeira 2",
    description: "Incidentes para testar memória longitudinal.",
  },
} as const;

type Scenario = keyof typeof DEMOS;

function isScenario(value: string): value is Scenario {
  return value in DEMOS;
}

function parseTranscript(content: string) {
  return content
    .split(/\r?\n/)
    .map((raw) => raw.trim())
    .filter(Boolean)
    .map((line) => {
      const match = /^([^:]{1,31}):\s*(.+)$/.exec(line);
      return match
        ? { speaker: match[1].trim(), text: match[2].trim() }
        : { speaker: null, text: line };
    });
}

export async function GET(_request: Request, { params }: { params: { scenario: string } }) {
  if (!isScenario(params.scenario)) {
    return NextResponse.json({ error: "Demo não encontrada." }, { status: 404 });
  }

  const demo = DEMOS[params.scenario];
  const file = path.join(process.cwd(), "..", "mocks", "transcricoes", demo.file);

  try {
    const content = await readFile(file, "utf8");
    return NextResponse.json({
      id: params.scenario,
      title: demo.title,
      description: demo.description,
      lines: parseTranscript(content),
    });
  } catch {
    return NextResponse.json(
      { error: "Arquivo da demo indisponível neste ambiente." },
      { status: 503 },
    );
  }
}
