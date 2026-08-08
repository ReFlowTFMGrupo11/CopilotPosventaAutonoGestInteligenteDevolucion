import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api, asList, type PendingReturn, type ReturnRow, type Stats } from "@/lib/api";

export const Route = createFileRoute("/admin")({
  head: () => ({
    meta: [
      { title: "Panel de administración — ReFlow" },
      { name: "description", content: "KPIs, aprobación de devoluciones y búsqueda de pedidos en ReFlow." },
      { property: "og:title", content: "Panel de administración — ReFlow" },
      { property: "og:description", content: "KPIs, aprobación de devoluciones y búsqueda de pedidos en ReFlow." },
    ],
  }),
  component: AdminPage,
});

const STATUS_LABEL: Record<string, string> = {
  approved: "Aprobada",
  rejected: "Rechazada",
  pending_approval: "Pendiente",
};

function StatusBadge({ status }: { status?: string | undefined }) {
  const cls =
    status === "approved"
      ? "bg-success-soft text-success"
      : status === "rejected"
        ? "bg-danger-soft text-danger"
        : "bg-warning-soft text-warning-foreground";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {STATUS_LABEL[status ?? ""] ?? status ?? "—"}
    </span>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

function money(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? `${n.toFixed(2)} €` : "—";
}

function AdminPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [pending, setPending] = useState<PendingReturn[]>([]);
  const [rows, setRows] = useState<ReturnRow[]>([]);
  const [status, setStatus] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [orderId, setOrderId] = useState("");
  const [order, setOrder] = useState<unknown>(null);
  const [orderError, setOrderError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, p] = await Promise.all([api.stats(), api.pending()]);
      setStats(s);
      setPending(asList(p));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api
      .returns(status)
      .then((d) => setRows(asList(d)))
      .catch((e: Error) => setError(e.message));
  }, [status]);

  async function decide(threadId: string, kind: "approve" | "reject") {
    const reason = window.prompt(kind === "approve" ? "Motivo de la aprobación" : "Motivo del rechazo") ?? "";
    if (reason === null) return;
    setWorking(threadId);
    try {
      await (kind === "approve" ? api.approve(threadId, reason) : api.reject(threadId, reason));
      await load();
      setRows(asList(await api.returns(status)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(null);
    }
  }

  async function searchOrder(e: React.FormEvent) {
    e.preventDefault();
    if (!orderId.trim()) return;
    setOrder(null);
    setOrderError(null);
    try {
      setOrder(await api.order(orderId.trim()));
    } catch (err) {
      setOrderError(`No se encontró el pedido ${orderId.trim()}`);
    }
  }

  const rate = stats?.approval_rate;
  const rateText =
    typeof rate === "number" ? `${(rate <= 1 ? rate * 100 : rate).toFixed(0)}%` : "—";

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 space-y-8 px-4 py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Panel de administración</h1>

      {error && (
        <div className="rounded-lg border border-danger/40 bg-danger-soft px-4 py-2 text-sm text-danger">{error}</div>
      )}

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Total" value={String(stats?.total_returns ?? stats?.total ?? "—")} />
        <Kpi label="Aprobadas" value={String(stats?.approved ?? "—")} tone="text-success" />
        <Kpi label="Rechazadas" value={String(stats?.rejected ?? "—")} tone="text-danger" />
        <Kpi label="Pendientes" value={String(stats?.pending ?? "—")} tone="text-warning-foreground" />
        <Kpi label="Tasa aprobación" value={rateText} tone="text-brand" />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Pendientes de aprobación</h2>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5">Pedido</th>
                <th className="px-4 py-2.5">Cliente</th>
                <th className="px-4 py-2.5">Importe</th>
                <th className="px-4 py-2.5">Motivo</th>
                <th className="px-4 py-2.5 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {pending.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                    No hay devoluciones pendientes.
                  </td>
                </tr>
              )}
              {pending.map((r) => (
                <tr key={r.thread_id} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{r.order_id}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.customer_id}</td>
                  <td className="px-4 py-3">{money(r.refund_amount)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.reason}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => void decide(r.thread_id, "approve")}
                        disabled={working === r.thread_id}
                        className="rounded-md bg-success px-3 py-1.5 text-xs font-medium text-success-foreground disabled:opacity-50"
                      >
                        Aprobar
                      </button>
                      <button
                        onClick={() => void decide(r.thread_id, "reject")}
                        disabled={working === r.thread_id}
                        className="rounded-md bg-danger px-3 py-1.5 text-xs font-medium text-danger-foreground disabled:opacity-50"
                      >
                        Rechazar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Todas las devoluciones</h2>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-input bg-card px-3 py-1.5 text-sm"
            aria-label="Filtrar por estado"
          >
            <option value="all">Todas</option>
            <option value="approved">Aprobadas</option>
            <option value="rejected">Rechazadas</option>
            <option value="pending_approval">Pendientes</option>
          </select>
        </div>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5">Pedido</th>
                <th className="px-4 py-2.5">Cliente</th>
                <th className="px-4 py-2.5">Importe</th>
                <th className="px-4 py-2.5">Motivo</th>
                <th className="px-4 py-2.5">Estado</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                    Sin resultados.
                  </td>
                </tr>
              )}
              {rows.map((r, i) => (
                <tr key={r.thread_id ?? i} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{r.order_id}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.customer_id}</td>
                  <td className="px-4 py-3">{money(r.refund_amount)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.reason}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Buscador de pedidos</h2>
        <form onSubmit={searchOrder} className="flex gap-2">
          <input
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
            placeholder="order_id (p. ej. ORD-1024)"
            className="w-full max-w-xs rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-2 rounded-md bg-brand px-3 py-2 text-sm font-medium text-brand-foreground"
          >
            <Search className="size-4" /> Buscar
          </button>
        </form>
        {orderError && <p className="text-sm text-danger">{orderError}</p>}
        {order != null && (
          <pre className="overflow-x-auto rounded-xl border border-border bg-card p-4 text-xs">
            {JSON.stringify(order, null, 2)}
          </pre>
        )}
      </section>
    </main>
  );
}
