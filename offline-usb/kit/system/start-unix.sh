#!/usr/bin/env bash
# Starts the offline library from the drive on macOS and Linux.
# Called by START-MAC.command and START-LINUX.sh in the drive root.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PORT="${PORT:-8090}"

echo
echo " ============================================"
echo "   OFFLINE-BIBLIOTEK  (Wikipedia med mera)"
echo " ============================================"
echo " Ett uppslagsverk, inte en ersättning för 112 eller vården."
echo

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)              OS=mac-arm64 ;;
  Darwin-x86_64)             OS=mac-x64 ;;
  Linux-x86_64)              OS=linux-x64 ;;
  Linux-aarch64|Linux-arm64) OS=linux-arm64 ;;
  *)                         OS=unknown ;;
esac

open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
  else echo " Öppna i en webbläsare: $1"; fi
}

# exFAT has no exec bit, Linux may mount the stick noexec, and macOS quarantines
# downloaded programs. If the copy on the drive will not run, run one from /tmp.
find_kiwix() {
  local dir="$ROOT/kiwix/$OS"
  if [ -f "$dir/kiwix-serve" ]; then
    chmod +x "$dir/kiwix-serve" 2>/dev/null
    [ "$(uname -s)" = Darwin ] && xattr -dr com.apple.quarantine "$dir" 2>/dev/null
    if "$dir/kiwix-serve" --version >/dev/null 2>&1; then echo "$dir/kiwix-serve"; return 0; fi
    local copy="${TMPDIR:-/tmp}/offline-usb-kiwix"
    rm -rf "$copy" && cp -R "$dir" "$copy" && chmod +x "$copy/kiwix-serve"
    [ "$(uname -s)" = Darwin ] && xattr -dr com.apple.quarantine "$copy" 2>/dev/null
    if "$copy/kiwix-serve" --version >/dev/null 2>&1; then echo "$copy/kiwix-serve"; return 0; fi
  fi
  command -v kiwix-serve 2>/dev/null       # installed on this computer (apt install kiwix-tools)
}

shopt -s nullglob
ZIMS=("$ROOT"/library/*.zim)
if [ ${#ZIMS[@]} -eq 0 ]; then
  echo " Inga .zim-filer i library/. Nödkorten fungerar ändå."
  open_url "$ROOT/portal/index.html"
  exit 0
fi

KIWIX="$(find_kiwix)"
if [ -z "$KIWIX" ]; then
  echo " Hittar ingen kiwix-serve för $OS. Nödkorten öppnas ändå."
  echo " Linux: sudo apt install kiwix-tools   Annars: läs .zim-filerna med appen Kiwix."
  open_url "$ROOT/portal/index.html"
  exit 1
fi

# An earlier start that never shut down still holds the port.
pkill -f "kiwix-serve .*--port $PORT" 2>/dev/null && sleep 1

# Run inside library/ with bare file names: kiwix-serve names each book after the
# file, and the portal links to /content/<file name without .zim>.
LOG="${TMPDIR:-/tmp}/offline-usb-kiwix.log"
(cd "$ROOT/library" && exec "$KIWIX" --port "$PORT" "${ZIMS[@]##*/}") >"$LOG" 2>&1 &
PID=$!
trap 'echo; echo " Stänger biblioteket ..."; kill $PID 2>/dev/null; exit 0' INT TERM HUP

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fs "http://localhost:$PORT/" >/dev/null 2>&1; then break; fi
  if ! kill -0 $PID 2>/dev/null; then echo " kiwix-serve stoppade, se $LOG"; tail -5 "$LOG"; exit 1; fi
  sleep 1
done

echo " Bibliotek: ${#ZIMS[@]} arkiv på http://localhost:$PORT/"
IP=""
if command -v ipconfig >/dev/null 2>&1; then IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null); fi
[ -z "$IP" ] && command -v hostname >/dev/null 2>&1 && IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$IP" ] && echo " Från en mobil på samma wifi eller hotspot: http://$IP:$PORT/"
echo
echo " Låt det här fönstret vara öppet. Ctrl+C stänger biblioteket."
open_url "$ROOT/portal/index.html"
wait $PID
