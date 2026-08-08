import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Bot, Send, User } from "lucide-react";
import { api, streamChat, type SseEvent } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Chat de devoluciones — ReFlow" },
      { name: "description", content: "Solicita y gestiona la devolución de tu pedido con el asistente ReFlow." },
      { property: "og:title", content: "Chat de devoluciones — ReFlow" },
      { property: "og:description", content: "Solicita y gestiona la devolución de tu pedido con el asistente ReFlow." },
    ],
  }),
  component: ChatPage,
});

type ChatItem =
  | { id: string; kind: "user" | "agent"; text: string }
  | { id: string; kind: "awaiting" }
  | { id: string; kind: "error"; text: string };

function ChatPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    console.log("[ReFlow] Iniciando chat, llamando a /api/chat/new...");
    api
      .newChat()
      .then((d) => {
        console.log("[ReFlow] thread_id obtenido:", d.thread_id);
        setThreadId(d.thread_id);
      })
      .catch((err) => {
        console.error("[ReFlow] Error al crear chat:", err);
        setItems((p) => [
          ...p,
          { id: crypto.randomUUID(), kind: "error", text: "No se pudo iniciar la conversación con el backend." },
        ]);
      });
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, step]);

  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy, threadId]);

  const push = (item: ChatItem) => setItems((p) => [...p, item]);

  async function send() {
    const text = input.trim();
    if (!text || busy || !threadId) return;
    setInput("");
    push({ id: crypto.randomUUID(), kind: "user", text });
    setBusy(true);
    setStep(null);
    try {
      await streamChat(threadId, text, (e: SseEvent) => {
        const body = (e.message ?? e.content ?? "") as string;
        if (e.type === "agent_step") setStep(e.agent ?? "desconocido");
        else if (e.type === "final") {
          setStep(null);
          push({ id: crypto.randomUUID(), kind: "agent", text: body || "(sin contenido)" });
        } else if (e.type === "awaiting_admin") {
          setStep(null);
          push({ id: crypto.randomUUID(), kind: "awaiting" });
        } else if (e.type === "error") {
          setStep(null);
          push({ id: crypto.randomUUID(), kind: "error", text: body || "Se ha producido un error." });
        }
      });
    } catch (err) {
      push({ id: crypto.randomUUID(), kind: "error", text: (err as Error).message });
    } finally {
      setStep(null);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-4 sm:py-6">
      <h1 className="sr-only">Chat de devoluciones ReFlow</h1>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {items.length === 0 && (
          <div className="mt-10 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
              <Bot className="size-6" />
            </div>
            <p className="mt-4 text-lg font-semibold">¿Necesitas devolver un pedido?</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Cuéntame tu número de pedido y el motivo, y me encargo del resto.
            </p>
          </div>
        )}

        {items.map((m) => {
          if (m.kind === "awaiting")
            return (
              <div
                key={m.id}
                className="mx-auto max-w-lg rounded-xl border border-warning/40 bg-warning-soft px-4 py-3 text-sm text-warning-foreground"
              >
                Tu solicitud está pendiente de revisión
              </div>
            );
          if (m.kind === "error")
            return (
              <div
                key={m.id}
                className="mx-auto max-w-lg rounded-xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger"
              >
                {m.text}
              </div>
            );
          const mine = m.kind === "user";
          return (
            <div key={m.id} className={`flex items-start gap-3 ${mine ? "flex-row-reverse" : ""}`}>
              <div
                className={`flex size-8 shrink-0 items-center justify-center rounded-full ${
                  mine ? "bg-secondary text-secondary-foreground" : "bg-brand text-brand-foreground"
                }`}
              >
                {mine ? <User className="size-4" /> : <Bot className="size-4" />}
              </div>
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  mine ? "bg-brand text-brand-foreground" : "border border-border bg-card text-card-foreground"
                }`}
              >
                {m.text}
              </div>
            </div>
          );
        })}

        {step && (
          <p className="pl-11 text-xs text-muted-foreground">
            <span className="mr-2 inline-block size-1.5 animate-pulse rounded-full bg-brand align-middle" />
            Agente {step} procesando...
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="sticky bottom-0 flex items-end gap-2 border-t border-border bg-background pb-4 pt-3"
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={threadId ? "Escribe tu mensaje..." : "Conectando..."}
          disabled={!threadId}
          className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-input bg-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={busy || !threadId || !input.trim()}
          className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand text-brand-foreground transition-opacity disabled:opacity-40"
          aria-label="Enviar mensaje"
        >
          <Send className="size-4" />
        </button>
      </form>
    </main>
  );
}
