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
  auto_validated?: boolean;
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
  scope: { validated: number; total_fiches: number };
  kpis: {
    operations_done: number;
    conformity_pct: number | null;
    non_conformities: number;
    automation_pct: number | null;
    cycle_time_minutes: number | null;
    cycle_time_coverage_pct: number;
    flagged_rows: number;
    corrections: number;
    operators: number;
    serials: number;
    products: number;
  };
  review_funnel: { name: string; value: number }[];
  // 1. Conformity & defects
  conformity: { name: string; value: number }[];
  control_results_by_type: { type: string; ok: number; ko: number; na: number }[];
  non_conformities_by_product: { ref: string; count: number }[];
  // 2. Operation flow & bottlenecks
  operation_coverage: { name: string; value: number }[];
  coverage_by_operation: { name: string; applied: number; total: number; pct: number }[];
  cycle_time_by_operation: { name: string; avg_minutes: number; n: number }[];
  // 3. Operator performance
  operator_workload: { matricule: string; operations: number }[];
  operator_cycle_time: { name: string; avg_minutes: number; n: number }[];
  // 4. Quantity & traceability
  product_volumes: { ref: string; qty: number }[];
  serials_by_product: { ref: string; serials: number }[];
  timeline: { date: string; operations: number }[];
  top_tools: { name: string; count: number }[];
}

export interface OperationListItem {
  operation_id: number;
  fiche_id: number;
  n_of: string;
  ref_produit: string;
  designation: string | null;
  partie: string;
  nom_operation: string;
  ordre: number;
  applicable: boolean | null;
  date_op: string | null;
  date_fin: string | null;
  heure_debut: string | null;
  heure_fin: string | null;
  qte_realisee: number | null;
  outillage: string | null;
  matricule_operateur: string | null;
  statut_revue: string | null;
}

export interface OperationListResponse {
  total: number;
  page: number;
  page_size: number;
  items: OperationListItem[];
}

export interface OperationMatrixColumn {
  key: string;
  partie: string;
  ordre: number;
  nom_operation: string;
}

export interface OperationMatrixCell {
  applicable: boolean | null;
  heure_debut: string | null;
  heure_fin: string | null;
  matricule: string | null;
  qte_realisee: number | null;
}

export interface OperationMatrixRow {
  fiche_id: number;
  n_of: string;
  ref_produit: string;
  designation: string | null;
  qte: number | null;
  date_creation: string;
  cells: Record<string, OperationMatrixCell>;
}

export interface OperationMatrixResponse {
  columns: OperationMatrixColumn[];
  total: number;
  page: number;
  page_size: number;
  rows: OperationMatrixRow[];
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
  scan: { scan_id: number; uploaded_at: string; page_index: number; n_pages: number } | null;
  extraction: Extraction | null;
  validation: ValidationIssue[];
}

export type ScanResult =
  | { mode: "single"; scan_id: number; fiche_id: number; n_pages: number; statut: string }
  | { mode: "batch"; scan_id: number; n_pages: number; resumed?: boolean };

export interface ScanStatus {
  scan_id: number;
  n_pages: number;
  n_done: number;
  done: boolean;
  status: "processing" | "done" | "error" | "stopped";
  source: string;
  fiche_ids: number[];
}

export interface ScanRow {
  scan_id: number;
  original_name: string;
  uploaded_at: string;
  n_pages: number;
  n_done: number;
  status: "processing" | "done" | "error" | "stopped";
  source: string;
  done: boolean;
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
  operations: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return get<OperationListResponse>(`/operations?${q.toString()}`);
  },
  operationsMatrix: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return get<OperationMatrixResponse>(`/operations/matrix?${q.toString()}`);
  },
  updateFiche: async (id: number, extraction: Extraction, validate: boolean) => {
    const r = await fetch(`${BASE}/fiches/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ extraction, validate }),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; statut: string }>;
  },
  deleteFiche: async (id: number) => {
    const r = await fetch(`${BASE}/fiches/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; fiche_id: number }>;
  },
  resolveAlert: async (ficheId: number, key: string, resolved: boolean) => {
    const r = await fetch(`${BASE}/fiches/${ficheId}/resolve-alert`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, resolved }),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; resolved: number; total: number; all_resolved: boolean; statut: string }>;
  },
  bulkDeleteFiches: async (ids: number[]) => {
    const r = await fetch(`${BASE}/fiches/bulk-delete`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; deleted: number }>;
  },
  bulkArchiveFiches: async (ids: number[], archived = true) => {
    const r = await fetch(`${BASE}/fiches/bulk-archive`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids, archived }),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<{ ok: boolean; count: number }>;
  },
  scanUrl: (id: number) => `${BASE}/fiches/${id}/scan`,
  exportUrl: (id: number, format: "xlsx" | "pdf" | "csv") =>
    `${BASE}/fiches/${id}/export?format=${format}`,
  chatStream: async (
    question: string,
    history: { role: string; content: string }[],
    onToken: (chunk: string) => void
  ): Promise<void> => {
    // Stateless: context is the client-kept history; nothing is persisted, so the
    // chat resets on relaunch.
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
  scan: async (file: File): Promise<ScanResult> => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/fiches/scan`, { method: "POST", body: fd });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || `${r.status} ${r.statusText}`);
    }
    return r.json();
  },
  scanStatus: (scanId: number) => get<ScanStatus>(`/fiches/scan/${scanId}/status`),
  listScans: () => get<ScanRow[]>(`/fiches/scans`),
  scanRetry: async (scanId: number) => {
    const r = await fetch(`${BASE}/fiches/scan/${scanId}/retry`, { method: "POST" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  scanStop: async (scanId: number) => {
    const r = await fetch(`${BASE}/fiches/scan/${scanId}/stop`, { method: "POST" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  scanCancel: async (scanId: number) => {
    const r = await fetch(`${BASE}/fiches/scan/${scanId}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
};
