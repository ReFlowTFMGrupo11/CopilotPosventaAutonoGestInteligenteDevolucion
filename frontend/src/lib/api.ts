export const API_BASE = "http://localhost:8000";

export type Stats = {
  total?: number;
  total_returns?: number;
  approved?: number;
  rejected?: number;
  pending?: number;
  approval_rate?: number;
  [k: string]: unknown;
};

export type PendingReturn = {
  thread_id: string;
  order_id: string;
  customer_id: string;
  refund_amount: number;
  reason: string;
  status?: string;
};

export type ReturnRow = PendingReturn & { created_at?: string };

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => fetch(`${API_BASE}/health`).then((r) => r.ok),
  stats: () => fetch(`${API_BASE}/api/stats`).then(json<Stats>),
  pending: () => fetch(`${API_BASE}/api/admin/pending`).then(json<PendingReturn[] | { items: PendingReturn[] }>),
  returns: (status: string) =>
    fetch(`${API_BASE}/api/admin/returns?status=${status === "all" ? "" : status}`).then(
      json<ReturnRow[] | { items: ReturnRow[] }>,
    ),
  order: (orderId: string) => fetch(`${API_BASE}/api/orders/${encodeURIComponent(orderId)}`).then(json<unknown>),
  approve: (threadId: string, reason: string) =>
    fetch(`${API_BASE}/api/admin/${encodeURIComponent(threadId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }).then(json<unknown>),
  reject: (threadId: string, reason: string) =>
    fetch(`${API_BASE}/api/admin/${encodeURIComponent(threadId)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }).then(json<unknown>),
  newChat: () =>
    fetch(`${API_BASE}/api/chat/new`, { method: "POST", headers: { "Content-Type": "application/json" } }).then(
      json<{ thread_id: string }>,
    ),
};

export function asList<T>(data: T[] | { items?: T[]; pending?: T[]; returns?: T[] } | null | undefined): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray((data as any).items)) return (data as any).items;
  if (Array.isArray((data as any).pending)) return (data as any).pending;
  if (Array.isArray((data as any).returns)) return (data as any).returns;
  return [];
}

export type SseEvent = {
  type: "agent_step" | "final" | "awaiting_admin" | "error" | string;
  agent?: string;
  message?: string;
  content?: string;
  [k: string]: unknown;
};

/** POST-based SSE consumption via fetch + ReadableStream reader. */
export async function streamChat(
  threadId: string,
  message: string,
  onEvent: (e: SseEvent) => void,
  signal?: AbortSignal,
) {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ thread_id: threadId, message }),
    signal: signal ?? null,
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleChunk = (raw: string) => {
    const payload = raw
      .split("\n")
      .map((l) => (l.startsWith("data:") ? l.slice(5).trim() : l.trim()))
      .filter(Boolean)
      .join("");
    if (!payload || payload === "[DONE]") return;
    try {
      onEvent(JSON.parse(payload) as SseEvent);
    } catch {
      onEvent({ type: "final", message: payload });
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.search(/\n\n|\r\n\r\n/)) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx).replace(/^(\n\n|\r\n\r\n)/, "");
      handleChunk(chunk);
    }
  }
  if (buffer.trim()) handleChunk(buffer);
}
