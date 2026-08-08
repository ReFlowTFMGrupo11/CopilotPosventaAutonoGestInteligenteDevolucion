import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function BackendBanner() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then((r) => alive && setOk(r))
        .catch(() => alive && setOk(false));
    check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (ok !== false) return null;
  return (
    <div className="bg-danger px-4 py-2 text-center text-sm font-medium text-danger-foreground">
      Backend desconectado — no se puede contactar con http://localhost:8000
    </div>
  );
}
