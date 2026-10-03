#!/usr/bin/env bash
# Installerar offline-Wikipedia (Kiwix), offline-kartor (GPXSee + Mapsforge),
# överlevnadsguiden och automatisk avstängning vid lågt batteri.
#
# Kör på Raspberry Pi:n som vanlig användare (inte med sudo):
#   bash setup.sh
#
# Skriptet kan köras om – påbörjade nedladdningar fortsätter där de slutade.
set -euo pipefail

# Kartor att ladda ner från download.mapsforge.org (lägg till t.ex. "norway finland").
MAPS="sweden"

KIWIX_ZIM="https://download.kiwix.org/zim"
MAPSFORGE="https://download.mapsforge.org/maps/v5/europe"
OFFLINE="$HOME/offline"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

if [ "$(id -u)" -eq 0 ]; then
  echo "Kör skriptet som vanlig användare, inte med sudo." >&2
  exit 1
fi

ask() {  # ask "Fråga" -> 0 om ja
  local svar
  read -r -p "$1 [j/N] " svar
  [[ "$svar" =~ ^[jJyY] ]]
}

human() {  # byte -> "12.3 GB"
  awk -v b="${1:-0}" 'BEGIN { printf "%.1f GB", b / 1e9 }'
}

remote_size() {
  curl -sIL "$1" | grep -i '^content-length' | tail -1 | awk '{print $2}' | tr -d '\r' || true
}

free_bytes() {
  df --output=avail -B1 "$OFFLINE" | tail -1
}

# download URL MÅLFIL BESKRIVNING
download() {
  local url="$1" dest="$2" desc="$3" size free
  size="$(remote_size "$url")"
  free="$(free_bytes)"
  echo
  echo "$desc"
  echo "  $url"
  echo "  Storlek: $(human "$size")   Ledigt på kortet: $(human "$free")"
  if [ -n "$size" ] && [ "$size" -gt "$free" ] && [ ! -f "$dest" ]; then
    echo "  Får inte plats – hoppar över."
    return 0
  fi
  if ask "  Ladda ner?"; then
    wget -c --show-progress -q -O "$dest" "$url"
  fi
}

# zim KATALOG PREFIX NAMN BESKRIVNING
# Hittar senaste versionen och sparar den med ett fast namn (NAMN.zim), så att
# länkarna i överlevnadsguiden fungerar oavsett version.
zim() {
  local dir="$1" prefix="$2" name="$3" desc="$4" latest dest
  latest="$(curl -s "$KIWIX_ZIM/$dir/" | grep -oE "${prefix}_[0-9]{4}-[0-9]{2}\.zim" | sort -u | tail -1 || true)"
  if [ -z "$latest" ]; then
    echo "Hittade ingen fil som börjar med $prefix i $KIWIX_ZIM/$dir/ – hoppar över."
    return 0
  fi
  dest="$OFFLINE/zim/$name.zim"
  # Ny version på servern: börja om i stället för att fortsätta på den gamla filen
  if [ -f "$dest" ] && [ "$(cat "$dest.version" 2>/dev/null)" != "$latest" ]; then
    if ask "Det finns en nyare version ($latest). Ta bort den gamla och ladda ner den nya?"; then
      rm -f "$dest"
    else
      return 0
    fi
  fi
  download "$KIWIX_ZIM/$dir/$latest" "$dest" "$desc"
  [ -f "$dest" ] && echo "$latest" > "$dest.version"
  return 0
}

echo "== 1/6 Installerar program =="
sudo apt-get update
sudo apt-get install -y kiwix-tools gpxsee python3-gpiozero wget curl

mkdir -p "$OFFLINE/zim" "$OFFLINE/maps"

echo
echo "== 2/6 Offline-Wikipedia och uppslagsverk (Kiwix) =="
echo "Tips: stora filer går fortare att ladda ner på en dator och kopiera till"
echo "$OFFLINE/zim/ – men döp dem då till samma namn som nedan."
echo
echo "Svenska Wikipedia:"
echo "  1) med bilder (maxi) – störst, bäst för att känna igen bär och svamp"
echo "  2) utan bilder (nopic) – mindre"
echo "  3) hoppa över"
read -r -p "Välj 1, 2 eller 3: " val
case "$val" in
  1) zim wikipedia wikipedia_sv_all_maxi wikipedia_sv "Svenska Wikipedia med bilder" ;;
  2) zim wikipedia wikipedia_sv_all_nopic wikipedia_sv "Svenska Wikipedia utan bilder" ;;
  *) echo "Hoppar över svenska Wikipedia." ;;
esac
zim wikipedia wikipedia_en_medicine_maxi wikimed_en "WikiMed – engelska medicinartiklar från Wikipedia"
zim other zimgit-post-disaster_en post-disaster_en "Post-disaster – engelska handböcker för kris och överlevnad"
zim other zimgit-water_en water_en "Water – engelska handböcker om vatten och vattenrening"

echo
echo "== 3/6 Startar Kiwix som tjänst (http://localhost:8080) =="
KIWIX_SERVE="$(command -v kiwix-serve)"
sudo tee /etc/systemd/system/kiwix.service >/dev/null <<EOF
[Unit]
Description=Kiwix offline-Wikipedia
After=local-fs.target

[Service]
User=$USER
ExecStart=/bin/sh -c 'exec $KIWIX_SERVE --port=8080 --address=127.0.0.1 $OFFLINE/zim/*.zim'
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable kiwix.service
sudo systemctl restart kiwix.service || true

echo
echo "== 4/6 Offline-kartor (Mapsforge) =="
GPXSEE_MAPS="$HOME/.local/share/gpxsee/maps"
mkdir -p "$GPXSEE_MAPS"
for land in $MAPS; do
  download "$MAPSFORGE/$land.map" "$OFFLINE/maps/$land.map" "Karta: $land"
  [ -f "$OFFLINE/maps/$land.map" ] && ln -sf "$OFFLINE/maps/$land.map" "$GPXSEE_MAPS/$land.map"
done

echo
echo "== 5/6 Överlevnadsguide och genvägar =="
mkdir -p "$HOME/survival"
cp "$SCRIPT_DIR/survival/index.html" "$HOME/survival/index.html"

mkdir -p "$HOME/Desktop" "$HOME/.local/share/applications"
shortcut() {  # shortcut FILNAMN NAMN KOMMANDO IKON
  local f="$1.desktop"
  cat > "$HOME/.local/share/applications/$f" <<EOF
[Desktop Entry]
Type=Application
Name=$2
Exec=$3
Icon=$4
Terminal=false
EOF
  cp "$HOME/.local/share/applications/$f" "$HOME/Desktop/$f"
  chmod +x "$HOME/Desktop/$f"
}
shortcut overlevnad "Överlevnadsguide" "x-www-browser file://$HOME/survival/index.html" help-browser
shortcut wikipedia "Wikipedia (offline)" "x-www-browser http://localhost:8080/" accessories-dictionary
shortcut kartor "Kartor (offline)" "gpxsee" gpxsee

echo
echo "== 6/6 Automatisk avstängning vid lågt batteri (GPIO26) =="
sudo install -m 755 "$SCRIPT_DIR/lowbatt.py" /usr/local/bin/lowbatt.py
sudo tee /etc/systemd/system/lowbatt.service >/dev/null <<EOF
[Unit]
Description=Stäng av vid lågt batteri

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/lowbatt.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now lowbatt.service

echo
echo "Klart!"
echo "  Överlevnadsguide:  ikonen på skrivbordet, eller file://$HOME/survival/index.html"
echo "  Wikipedia:         http://localhost:8080/"
echo "  Kartor:            starta GPXSee och välj kartan i menyn Map"
ls -lh "$OFFLINE/zim" "$OFFLINE/maps" 2>/dev/null || true
