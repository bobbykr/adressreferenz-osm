# adressreferenz-osm

Monatlicher Auszug aller Straßen und Hausnummern Deutschlands aus OpenStreetMap
für die Adressprüfung von VorgangsHub. Die rechenintensive Arbeit
(4,85-GB-Download, Filtern, PLZ-Zuordnung über die Lage) läuft seit dem
12.11.2026 wöchentlich auf unserem Bau-Server, nicht mehr in GitHub Actions.
Der Server lädt nur noch die fertige Tabelle.

## Ausgabe

Release-Datei `osm-adressen.csv.gz`, stabil abrufbar unter
`https://github.com/bobbykr/adressreferenz-osm/releases/latest/download/osm-adressen.csv.gz`

| Spalte | Inhalt |
|---|---|
| `Name` | `addr:street` (ersatzweise `addr:place`) einer Gebäudeadresse oder `name` eines benannten Wegs (`highway=*`) |
| `PostalCode` | `addr:postcode`; fehlt das Tag, das PLZ-Gebiet (`boundary=postal_code`), in dem die Adresse liegt bzw. das der Weg berührt |
| `Locality` | `addr:city`, leer wenn unbekannt |
| `HouseNumbers` | Hausnummern, `;`-getrennt, natürlich sortiert; leer bei Wegen ohne Gebäudeadresse |

Eine Zeile je Straße, PLZ und Ort. Dazu kommt `stand.json` mit Kennzahlen
(Anzahl Adressen, per Lage zugeordnete Adressen, Hausnummern, OSM-Stand).

## Regeln

- **Keine Privatweg-Filter:** kein `access`-Filter (private, forestry,
  military …) und keine highway-Positivliste. Ausgenommen sind nur Einträge,
  die keine Straße sind oder nicht (mehr) existieren: `proposed`, `planned`,
  `abandoned`, `disused`, `razed`, `dismantled`, `no`, `platform`, `bus_stop`,
  `rest_area`, `services`, `elevator`, `corridor`.
- **PLZ über die Lage:** Rund 6 % der Adressen in OSM haben kein
  `addr:postcode`, darunter ganze Neubaustraßen. Sie bekommen das PLZ-Gebiet,
  in dem der Knoten bzw. der Gebäudemittelpunkt liegt.
- **Untergrenzen:** Ein Deutschland-Lauf wird nur veröffentlicht, wenn er
  genug PLZ, Straßen und Hausnummern enthält und `Winkelstraße 10, 42551`
  findet. Sonst bleibt das letzte Release `latest`.

## Ablauf

Sonntags ab 02:30 Uhr baut die Prüfstraße des CRM den Auszug
(`scripts/pruefstrasse/osm-auszug.mjs`, Nachtschritt `osm-auszug`): Sie klont
dieses Repo, startet `bau-auszug.sh` per `bau` auf dem Bau-Server (Docker-Abbild
aus `Dockerfile` mit osmium und Python, darin `auszug.sh`) und veröffentlicht
das Ergebnis als Release `stand-JJJJ-MM-TT-HHMM`. Der CRM-Server holt es
sonntags um 04:23 Uhr ab. Fällt ein Sonntag aus, baut jede folgende Nacht nach;
ist der letzte Auszug älter als 9 Tage, wird der Nachtschritt rot.

Von Hand (auf einer Devbox mit `bau` und `gh`, im CRM-Checkout):

```
node scripts/pruefstrasse/osm-auszug.mjs --jetzt                         # Deutschland, wird „latest“
node scripts/pruefstrasse/osm-auszug.mjs --probe europe/germany/bremen   # Vorabversion, nie „latest“
```

Nur bauen, ohne Veröffentlichen: `BAU_ART=docker bau bash bau-auszug.sh europe/germany/bremen`
(Ergebnis als base64-tar auf stdout zwischen `@@osm:anfang@@` und `@@osm:ende@@`).
Ganz lokal mit osmium-tool und Python ≥ 3.10 (`pip install -r requirements.txt`):

```
mkdir arbeit && ./auszug.sh europe/germany/bremen arbeit
```

`.github/workflows/auszug.yml` ist der frühere Weg über GitHub Actions; Actions
sind für dieses Repo abgeschaltet.

## Lizenz

Die Daten stammen von OpenStreetMap – © OpenStreetMap-Mitwirkende, verfügbar
unter der [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Die abgeleitete Tabelle steht unter derselben Lizenz. Quelle der Rohdaten:
[Geofabrik](https://download.geofabrik.de/).
