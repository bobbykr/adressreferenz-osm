#!/bin/bash
# Auszug auf dem Bau-Server (seit 12.11.2026 statt GitHub Actions, Janis: „alle github actions durch unsere
# eigenen server ersetzen“). Aufruf aus einem Klon dieses Repos:
#   BAU_ART=docker BAU_MAX_MIN=75 bau bash bau-auszug.sh [region]
# Den Aufruf, das Veröffentlichen als Release und den Zeitplan übernimmt die Prüfstraße des CRM
# (scripts/pruefstrasse/osm-auszug.mjs, Nachtschritt osm-auszug); der Bau-Server hat keinen GitHub-Zugang.
#
# Alle Meldungen gehen auf stderr. Auf stdout steht nur das Ergebnis: eine Zeile @@osm:anfang@@, base64
# eines tar mit ausgabe/osm-adressen.csv.gz, ausgabe/stand.json und osm-stand.txt, eine Zeile @@osm:ende@@.
set -euo pipefail
REGION=${1:-europe/germany}
ARBEIT=$(mktemp -d "${TMPDIR:-/tmp}/osm-XXXXXX")
trap 'rm -rf "$ARBEIT"' EXIT
docker build --progress=plain -t adressreferenz-osm:auszug . >&2
# Eigener Nutzer im Container: Die Dateien im Arbeitsordner gehören dann dem Nutzer bau und lassen sich räumen.
# Speichergrenze über dem gemessenen Höchstwert (6,3 GB), damit ein Ausreißer nur diesen Lauf trifft.
docker run --rm --user "$(id -u):$(id -g)" --memory 12g -e HOME=/tmp \
  -v "$PWD:/repo:ro" -v "$ARBEIT:/arbeit" adressreferenz-osm:auszug bash /repo/auszug.sh "$REGION" /arbeit >&2
ls -la "$ARBEIT/ausgabe" >&2
echo '@@osm:anfang@@'
tar -C "$ARBEIT" -cf - ausgabe/osm-adressen.csv.gz ausgabe/stand.json osm-stand.txt | base64 -w 76
echo '@@osm:ende@@'
