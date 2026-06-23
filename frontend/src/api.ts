// API client + shared types. All calls go through /api which Vite (dev) or
// nginx (prod) proxies to the FastAPI backend.

const BASE = import.meta.env.VITE_API_BASE || "/api";

export type Statut = "extrait" | "en_revue" | "valide";

export interface FicheListItem {
  fiche_id: number;
  ref_produit: string;
  designation: string | null;
  n_of: string;
  quantite: number | null;
  date_creation: string;
  statut: Statut;
  overall_confidence: number | null;
  n_items: number;
  n_operations: number;
  has_scan: boolean;
}

export interface FicheListResponse {
  total: number;
  page: number;
  page_size: number;
  items: FicheListItem[];
}

export interface Analytics {
  kpis: { fiches: number; operations: number; coverage_pct: number; conformity_pct: number; operators: number; serials: number; validated: number };
  operation_coverage: { name: string; value: number }[];
  operator_workload: { matricule: string; operations: number }[];
  conformity: { name: string; value: number }[];
  timeline: { date: string; operations: number }[];
  product_volumes: { ref: string; qty: number }[];
  fiches_by_day: { date: string; count: number }[];
  by_statut: { name: string; value: number }[];
  top_tools: { name: string; count: number }[];
}

export interface Stats {
  total_fiches: number;
  total_products: number;
  total_work_orders: number;
  scanned_today: number;
  avg_confidence: number | null;
  by_statut: { extrait: number; en_revue: number; valide: number };
  recent: FicheListItem[];
}

export interface Field<T = unknown> {
  value: T | null;
  confidence: number;
  raw_text?: string | null;
  source?: string | null;
}

export interface OperationRow {
  partie: string;
  nom_operation: string;
  ordre: number;
  applicable: Field<boolean>;
  date_op: Field<string>;
  date_fin: Field<string>;
  heure_debut: Field<string>;
  heure_fin: Field<string>;
  qte_realisee: Field<number>;
  outillage: Field<string>;
  matricule_operateur: Field<string>;
}

export interface ControlRow extends OperationRow {
  type_controle: string;
  methode: Field<{ value: string } | string>;
  resultat: Field<boolean>;
}

export interface Extraction {
  header: {
    ref_produit: Field<string>;
    n_of: Field<string>;
    qte: Field<number>;
    annotation_serie: Field<string>;
  };
  operations: OperationRow[];
  controls: ControlRow[];
  items: { numero_serie: Field<string> }[];
  meta: { model_name: string; overall_confidence: number; processing_ms: number | null };
}

export interface ValidationIssue {
  scope: string;
  location: string;
  field: string;
  level: "error" | "warning";
  code: string;
  message: string;
}

export interface FicheDetail {
  fiche_id: number;
  statut: Statut;
  date_creation: string;
  created_by: string | null;
  overall_confidence: number | null;
  product: { product_id: number; ref_produit: string; designation: string | null };
  work_order: { of_id: number; n_of: string; quantite: number | null };
  scan: { scan_id: number; uploaded_at: string } | null;
  extraction: Extraction | null;
  validation: ValidationIssue[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  stats: () => get<Stats>("/stats"),
  analytics: () => get<Analytics>("/analytics"),
  fiches: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return get<FicheListResponse>(`/fiches?${q.toString()}`);
  },
  fiche: (id: number) => get<FicheDetail>(`/fiches/${id}`),
  updateFiche: async (id: number, extraction: Extraction, validate: boolean) => {
    const r = await fetch(`${BASE}/fiches/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ extraction, validate }),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; statut: string }>;
  },
  scanUrl: (id: number) => `${BASE}/fiches/${id}/scan`,
  exportUrl: (id: number, format: "xlsx" | "pdf" | "csv") =>
    `${BASE}/fiches/${id}/export?format=${format}`,
  chatStream: async (
    question: string,
    history: { role: string; content: string }[],
    onToken: (chunk: string) => void
  ): Promise<void> => {
    const r = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    if (!r.ok || !r.body) throw new Error(`${r.status} ${r.statusText}`);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      onToken(decoder.decode(value, { stream: true }));
    }
  },
  scan: async (file: File): Promise<{ fiche_id: number }> => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/fiches/scan`, { method: "POST", body: fd });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || `${r.status} ${r.statusText}`);
    }
    return r.json();
  },
};
