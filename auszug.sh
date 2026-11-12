#!/bin/bash
# Ganzer Auszug in einem Ordner: Download von Geofabrik, Filtern mit osmium, auszug.py.
#   auszug.sh <region> <arbeitsordner>
# Ergebnis im Arbeitsordner: ausgabe/osm-adressen.csv.gz, ausgabe/stand.json, osm-stand.txt.
# Läuft im Container aus dem Dockerfile (bau-auszug.sh), geht aber auch mit osmium-tool und
# Python (requirements.txt) direkt.
set -euo pipefail
REGION=${1:?Region fehlt, z. B. europe/germany}
HIER=$(cd "$(dirname "$0")" && pwd)
cd "${2:?Arbeitsordner fehlt}"
osmium --version | head -1
df -h . | tail -1
free -g | head -2

echo "== Download (Geofabrik): $REGION"
quelle="https://download.geofabrik.de/${REGION}-latest.osm.pbf"
# Abgebrochene Übertragungen setzen dort fort, wo sie standen (-C -). Fortschritt alle paar Sekunden,
# damit der Bau-Server einen langsamen Download nicht für hängend hält.
for versuch in 1 2 3 4 5; do
  curl -fSL --no-progress-meter -C - -A 'adressreferenz-osm (https://github.com/bobbykr/adressreferenz-osm)' \
    -o region.osm.pbf "$quelle" & lader=$!
  while kill -0 "$lader" 2>/dev/null; do sleep 20; kill -0 "$lader" 2>/dev/null && echo "  … $(du -h region.osm.pbf 2>/dev/null | cut -f1)"; done
  wait "$lader" && break
  [ "$versuch" = 5 ] && { echo "Download fünfmal abgebrochen" >&2; exit 1; }
  echo "Download abgebrochen (Versuch $versuch), setze fort …"; sleep 30
done
# Für Deutschland gibt es keine -latest.md5 (nur Monatsstände); dann schützen die zlib-Prüfsummen
# der PBF-Blöcke – osmium bricht bei kaputter Datei ab.
if curl -fsSL --retry 3 -o region.osm.pbf.md5 "${quelle}.md5"; then
  echo "$(cut -d' ' -f1 region.osm.pbf.md5)  region.osm.pbf" | md5sum -c -
else
  echo "Keine MD5-Datei für ${REGION}, Prüfung über osmium"
fi
osmium fileinfo -g header.option.osmosis_replication_timestamp region.osm.pbf > osm-stand.txt || echo unbekannt > osm-stand.txt
ls -la region.osm.pbf
echo "OSM-Stand: $(cat osm-stand.txt)"

echo "== Filtern (osmium)"
# Adressen, alle Wege (ohne access-Filter) und PLZ-Gebiete samt referenzierter Knoten.
osmium tags-filter region.osm.pbf nwr/addr:housenumber w/highway r/boundary=postal_code -o adressen.osm.pbf
osmium tags-filter adressen.osm.pbf r/boundary=postal_code -o plz.osm.pbf
rm region.osm.pbf
ls -la ./*.osm.pbf

echo "== Auszug"
args=(--plz plz.osm.pbf --adressen adressen.osm.pbf --ziel ausgabe)
case "$REGION" in
  europe/germany)
    # Untergrenzen gegen kaputte Läufe: ein unvollständiger Auszug wird nie „latest“.
    # Erster Lauf 07.10.2026: 8.413 PLZ, 1.355.918 Straßen je PLZ, 20.037.792 Hausnummern.
    args+=(--min-plz 8000 --min-strassen 1250000 --min-hausnummern 18000000 --pruefe 'Winkelstraße|42551|10') ;;
  */duesseldorf-regbez|*/nordrhein-westfalen)
    args+=(--pruefe 'Winkelstraße|42551|10') ;;
esac
/usr/bin/time -v python3 "$HIER/auszug.py" "${args[@]}" 2> >(tee zeit.txt >&2)
grep -E 'Maximum resident|Elapsed' zeit.txt || true
rm -f ./*.osm.pbf
