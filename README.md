# adressreferenz-osm

Monatlicher Auszug aller Straßen und Hausnummern Deutschlands aus OpenStreetMap
für die Adressprüfung von VorgangsHub. Die rechenintensive Arbeit
(4,85-GB-Download, Filtern, PLZ-Zuordnung über die Lage) läuft hier im
GitHub-Runner. Der Server lädt nur noch die fertige Tabelle.

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

`.github/workflows/auszug.yml`: am 2. jedes Monats; der Server holt am 5. ab.
Probelauf mit kleiner Region (Vorabversion, nie `latest`):

```
gh workflow run auszug.yml -f region=europe/germany/nordrhein-westfalen/duesseldorf-regbez
```

Lokal (Python ≥ 3.10, `pip install -r requirements.txt`):

```
python auszug.py --plz region.osm.pbf --adressen region.osm.pbf --ziel ausgabe --pruefe "Winkelstraße|42551|10"
```

## Lizenz

Die Daten stammen von OpenStreetMap – © OpenStreetMap-Mitwirkende, verfügbar
unter der [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Die abgeleitete Tabelle steht unter derselben Lizenz. Quelle der Rohdaten:
[Geofabrik](https://download.geofabrik.de/).
