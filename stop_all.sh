#!/usr/bin/env bash
# Cierra todo lo que levanta start_all.sh / start_all_win_gitbash.sh: las 4
# ventanas de Git Bash (MCP Supabase, MCP Logistics, API FastAPI y frontend
# Streamlit), no solo el proceso que corre dentro de cada una.
#
# Por qué no basta con matar el proceso que abre el puerto: al lanzarse,
# git-bash.exe se relanza a sí mismo y termina casi al instante, así que su
# PID no sirve para nada. Lo que queda vivo y sostiene la ventana es un
# bash.exe (o, si Git Bash usa mintty, un mintty.exe por encima de ese
# bash.exe) que quedó "huérfano" porque su lanzador ya murió. Así que para
# cada puerto del proyecto: se busca qué PID escucha ahí, se sube por la
# cadena de procesos padre hasta el ANTEPASADO MÁS ALTO que siga vivo (el
# huérfano, sea mintty.exe o bash.exe) y se cierra con //T, lo que mata todo
# lo que cuelga de él (bash, el recargador de uvicorn, el proceso real...) y
# cierra la ventana entera de golpe. Al matarlo así (no con la X de la
# ventana) tampoco aparece el aviso de mintty de "Close anyway?", porque ese
# aviso solo salta cuando se cierra la ventana a mano.
#
# Uso:  ./stop_all.sh
set -uo pipefail

KILLED=0

close_window_for_port() {
    local port="$1"
    local pids
    pids=$(powershell -NoProfile -Command "
        \$ErrorActionPreference = 'SilentlyContinue'
        function Find-WindowRoot(\$startPid) {
            \$cur = Get-CimInstance Win32_Process -Filter \"ProcessId=\$startPid\"
            if (-not \$cur) { return \$startPid }
            for (\$i = 0; \$i -lt 10; \$i++) {
                if (-not \$cur.ParentProcessId -or \$cur.ParentProcessId -eq 0) { return \$cur.ProcessId }
                \$parent = Get-CimInstance Win32_Process -Filter \"ProcessId=\$(\$cur.ParentProcessId)\"
                if (-not \$parent) { return \$cur.ProcessId }
                # Si el 'padre' se creó DESPUÉS que el hijo, Windows ha
                # reciclado ese PID para un proceso sin relación: no seguir
                # subiendo por ahí.
                if (\$parent.CreationDate -and \$cur.CreationDate -and \$parent.CreationDate -gt \$cur.CreationDate) { return \$cur.ProcessId }
                \$cur = \$parent
            }
            return \$cur.ProcessId
        }
        Get-NetTCPConnection -LocalPort $port -State Listen |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Find-WindowRoot \$_ }
    " 2>/dev/null | tr -d '\r')

    for pid in $pids; do
        [ -z "$pid" ] && continue
        echo "==> Puerto $port -> cerrando ventana (PID $pid)..."
        taskkill //F //T //PID "$pid" >/dev/null 2>&1 && KILLED=$((KILLED + 1))
    done
}

for port in 8000 8001 8002 8501; do
    close_window_for_port "$port"
done

if [ "$KILLED" -eq 0 ]; then
    echo "==> No se ha encontrado ninguna ventana de ReFlow en ejecución."
else
    echo "==> Listo. $KILLED ventana(s) cerradas."
fi
