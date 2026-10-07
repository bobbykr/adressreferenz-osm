"""
OSM-Adressauszug für die Adressprüfung von VorgangsHub.

Liest einen OSM-Auszug (.osm.pbf) und schreibt osm-adressen.csv.gz mit den
Spalten Name,PostalCode,Locality,HouseNumbers – eine Zeile je Straße, PLZ und
Ort:

  Name          addr:street (ersatzweise addr:place) einer Gebäudeadresse oder
                name=* eines benannten Wegs (highway=*)
  PostalCode    addr:postcode; fehlt es, das PLZ-Gebiet über die Lage
  Locality      addr:city; leer, wenn unbekannt – den amtlichen Ortsnamen
                ergänzt der Import auf dem Server
  HouseNumbers  Hausnummern, „;“-getrennt und natürlich sortiert; leer bei
                Wegen ohne Gebäudeadresse

Nutzervorgabe 07.10.2026: Privatwege und ähnliche Wege werden NIE
herausgefiltert – kein access-Filter (private, forestry, military …) und keine
engere highway-Liste als nötig. Ausgenommen sind nur Einträge, die keine
Straße sind oder (noch/nicht mehr) nicht existieren, siehe KEIN_WEG.

Die PLZ einer Adresse kommt aus addr:postcode. Fehlt das Tag (bundesweit ≈ 6 %
der Adressen, z. B. die ganze Winkelstraße in 42551 Velbert), wird sie über
die Lage bestimmt: Punkt (Knoten bzw. Mittelpunkt des Gebäudes) im PLZ-Gebiet
(boundary=postal_code). Ein benannter Weg zählt in jedem PLZ-Gebiet, das er
berührt.

Aufruf:
  python auszug.py --plz plz.pbf --adressen adressen.pbf --ziel ausgabe/
  (lokal geht für beide Eingaben auch der ungefilterte Auszug)

Daten: © OpenStreetMap-Mitwirkende, ODbL 1.0.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
from array import array
from pathlib import Path

import numpy as np
import osmium
import shapely
from osmium.filter import EntityFilter, KeyFilter, TagFilter
from shapely.errors import GEOSException

PLZ_MUSTER = re.compile(r'^\d{5}$')
LEERRAUM = re.compile(r'\s+')
# highway-Werte ohne Straße: geplant, aufgegeben oder kein Weg (Haltestelle,
# Bahnsteig, Rastanlage, Aufzug, Gang in Gebäuden). Alles andere zählt –
# ausdrücklich auch Privat-, Forst- und Wirtschaftswege und Baustellen
# (Neubaugebiete).
KEIN_WEG = frozenset({
    'proposed', 'planned', 'abandoned', 'disused', 'razed', 'dismantled', 'no',
    'platform', 'bus_stop', 'rest_area', 'services', 'elevator', 'corridor',
})
WEGE_JE_DURCHGANG = 200_000
DATEINAME = 'osm-adressen.csv.gz'


def bereinige(wert: str | None) -> str:
    return LEERRAUM.sub(' ', wert or '').strip()


def lade_plz_gebiete(pfad: str) -> tuple[list[str], list, int]:
    """PLZ-Gebiete (boundary=postal_code) als Shapely-Geometrien und Zahl der unbrauchbaren."""
    plz_liste: list[str] = []
    geometrien: list = []
    unbrauchbar = 0
    wkb = osmium.geom.WKBFactory()
    verarbeiter = (
        osmium.FileProcessor(pfad)
        .with_locations('sparse_mem_array')
        .with_areas(TagFilter(('boundary', 'postal_code')))
        .with_filter(EntityFilter(osmium.osm.AREA))
        .with_filter(TagFilter(('boundary', 'postal_code')))
    )
    for flaeche in verarbeiter:
        plz = (flaeche.tags.get('postal_code') or '').strip()
        if not PLZ_MUSTER.match(plz):
            continue
        try:
            geometrie = shapely.from_wkb(wkb.create_multipolygon(flaeche))
        except (RuntimeError, osmium.InvalidLocationError, GEOSException):  # z. B. unvollständiger Ring
            unbrauchbar += 1
            continue
        if geometrie.is_empty:
            unbrauchbar += 1
            continue
        plz_liste.append(plz)
        geometrien.append(geometrie)
    return plz_liste, geometrien, unbrauchbar


def hausnummern_teilen(wert: str) -> list[str]:
    # intern: „1“, „2“ … kommen millionenfach vor und teilen sich so ein Objekt.
    return [sys.intern(teil) for teil in (bereinige(t) for t in re.split(r'[;,]', wert)) if teil]


def natuerlich(nummer: str):
    teile = re.match(r'^(\d+)(.*)$', nummer)
    return (0, int(teile.group(1)), teile.group(2)) if teile else (1, 0, nummer)


def main() -> int:
    argumente = argparse.ArgumentParser()
    argumente.add_argument('--plz', required=True, help='PBF mit den PLZ-Grenzen')
    argumente.add_argument('--adressen', required=True, help='PBF mit Adressen und Wegen samt Knoten')
    argumente.add_argument('--ziel', required=True, help='Ausgabeordner')
    argumente.add_argument('--min-plz', type=int, default=0, help='Abbruch, wenn weniger PLZ in der Datei')
    argumente.add_argument('--min-strassen', type=int, default=0, help='Abbruch, wenn weniger Straßen je PLZ')
    argumente.add_argument('--min-hausnummern', type=int, default=0, help='Abbruch, wenn weniger Hausnummern')
    argumente.add_argument('--pruefe', action='append', default=[], metavar='STRASSE|PLZ[|NUMMER]',
                           help='Muss in der Datei stehen (z. B. "Winkelstraße|42551|10")')
    args = argumente.parse_args()
    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    start = time.time()

    plz_liste, geometrien, unbrauchbar = lade_plz_gebiete(args.plz)
    print(f'PLZ-Gebiete: {len(geometrien)}, unbrauchbar: {unbrauchbar} ({time.time() - start:.0f} s)', flush=True)
    if not geometrien:
        print('Keine PLZ-Gebiete gefunden', file=sys.stderr)
        return 1
    baum = shapely.STRtree(geometrien)

    # (Straße, PLZ) → Ort (leer = unbekannt) → Hausnummern
    strassen: dict[tuple[str, str], dict[str, set[str]]] = {}
    ohne_plz_lon = array('d')
    ohne_plz_lat = array('d')
    ohne_plz: list[tuple[str, str, str]] = []
    zaehler = {
        'adressen': 0, 'mitPlzTag': 0, 'ohneStrasse': 0, 'ohneLage': 0, 'perLage': 0, 'ausserhalbPlzGebiet': 0,
        'wege': 0, 'wegeOhneLage': 0, 'wegeAusserhalbPlzGebiet': 0, 'strassenNurAusWegen': 0,
    }

    def merke(name: str, plz: str, ort: str, nummer: str) -> None:
        orte = strassen.setdefault((name, plz), {})
        orte.setdefault(ort, set()).update(hausnummern_teilen(nummer))

    # Benannte Wege gesammelt zuordnen (eine Abfrage je Durchgang statt je Weg).
    weg_namen: list[str] = []
    weg_linien: list = []

    def ordne_wege_zu() -> None:
        if not weg_linien:
            return
        eingabe, treffer = baum.query(weg_linien, predicate='intersects')
        zaehler['wegeAusserhalbPlzGebiet'] += len(weg_linien) - len(set(eingabe.tolist()))
        for index, gebiet in zip(eingabe.tolist(), treffer.tolist()):
            strassen.setdefault((weg_namen[index], plz_liste[gebiet]), {})
        weg_namen.clear()
        weg_linien.clear()

    verarbeiter = (
        osmium.FileProcessor(args.adressen)
        .with_locations('sparse_mem_array')
        .with_filter(KeyFilter('addr:housenumber', 'highway'))
    )
    for objekt in verarbeiter:
        tags = objekt.tags
        weg_typ = tags.get('highway')
        if weg_typ and objekt.is_way() and weg_typ not in KEIN_WEG:
            weg_name = bereinige(tags.get('name'))
            if weg_name:
                zaehler['wege'] += 1
                punkte = [(k.location.lon, k.location.lat) for k in objekt.nodes if k.location.valid()]
                if not punkte:
                    zaehler['wegeOhneLage'] += 1
                else:
                    weg_namen.append(weg_name)
                    weg_linien.append(shapely.LineString(punkte) if len(punkte) > 1 else shapely.Point(punkte[0]))
                    if len(weg_linien) >= WEGE_JE_DURCHGANG:
                        ordne_wege_zu()
        nummer = tags.get('addr:housenumber')
        if not nummer:
            continue
        zaehler['adressen'] += 1
        name = bereinige(tags.get('addr:street')) or bereinige(tags.get('addr:place'))
        if not name:
            zaehler['ohneStrasse'] += 1
            continue
        ort = bereinige(tags.get('addr:city'))
        plz = (tags.get('addr:postcode') or '').strip()
        if PLZ_MUSTER.match(plz):
            zaehler['mitPlzTag'] += 1
            merke(name, plz, ort, nummer)
            continue
        # Ohne gültiges PLZ-Tag: Lage bestimmen (Knoten oder Mittelpunkt der Gebäudeumrisse).
        lon = lat = None
        if objekt.is_node():
            if objekt.location.valid():
                lon, lat = objekt.location.lon, objekt.location.lat
        elif objekt.is_way():
            summe_lon = summe_lat = 0.0
            anzahl = 0
            for knoten in objekt.nodes:
                if knoten.location.valid():
                    summe_lon += knoten.location.lon
                    summe_lat += knoten.location.lat
                    anzahl += 1
            if anzahl:
                lon, lat = summe_lon / anzahl, summe_lat / anzahl
        if lon is None:
            zaehler['ohneLage'] += 1
            continue
        ohne_plz_lon.append(lon)
        ohne_plz_lat.append(lat)
        ohne_plz.append((name, ort, nummer))
    ordne_wege_zu()
    print(f'Adressen gelesen: {zaehler["adressen"]}, benannte Wege: {zaehler["wege"]} ({time.time() - start:.0f} s)', flush=True)

    if ohne_plz:
        punkte = shapely.points(np.frombuffer(ohne_plz_lon, dtype='d'), np.frombuffer(ohne_plz_lat, dtype='d'))
        eingabe, treffer = baum.query(punkte, predicate='within')
        # Liegt ein Punkt auf einer Grenze, zählt das erste Gebiet.
        _, erste = np.unique(eingabe, return_index=True)
        zugeordnet = dict(zip(eingabe[erste].tolist(), treffer[erste].tolist()))
        for index, (name, ort, nummer) in enumerate(ohne_plz):
            gebiet = zugeordnet.get(index)
            if gebiet is None:
                zaehler['ausserhalbPlzGebiet'] += 1
                continue
            zaehler['perLage'] += 1
            merke(name, plz_liste[gebiet], ort, nummer)
    print(f'PLZ zugeordnet ({time.time() - start:.0f} s)', flush=True)

    datei_pfad = ziel / DATEINAME
    zeilen = hausnummern = 0
    with gzip.open(datei_pfad, 'wt', encoding='utf-8', newline='') as datei:
        schreiber = csv.writer(datei, lineterminator='\n')
        schreiber.writerow(['Name', 'PostalCode', 'Locality', 'HouseNumbers'])
        for (name, plz) in sorted(strassen, key=lambda s: (s[1], s[0])):
            orte = strassen[(name, plz)]
            if not orte:
                zaehler['strassenNurAusWegen'] += 1
                orte = {'': set()}
            # Adressen ohne addr:city gehören zum Ort, wenn die Straße in dieser PLZ nur einen kennt.
            benannt = [ort for ort in orte if ort]
            if '' in orte and len(benannt) == 1:
                orte[benannt[0]].update(orte.pop(''))
            for ort in sorted(orte):
                nummern = sorted(orte[ort], key=natuerlich)
                hausnummern += len(nummern)
                schreiber.writerow([name, plz, ort, ';'.join(nummern)])
                zeilen += 1

    plz_mit_strassen = {plz for (_, plz) in strassen}
    stand = {
        **zaehler,
        'plzGebiete': len(geometrien),
        'plzGebieteUnbrauchbar': unbrauchbar,
        'plzMitStrassen': len(plz_mit_strassen),
        'strassenJePlz': len(strassen),
        'zeilen': zeilen,
        'hausnummern': hausnummern,
        'dateiBytes': datei_pfad.stat().st_size,
        'dauerSekunden': round(time.time() - start),
    }
    (ziel / 'stand.json').write_text(json.dumps(stand, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(stand, ensure_ascii=False, indent=2))

    fehler = []
    if len(plz_mit_strassen) < args.min_plz:
        fehler.append(f'zu wenige PLZ ({len(plz_mit_strassen)} < {args.min_plz})')
    if len(strassen) < args.min_strassen:
        fehler.append(f'zu wenige Straßen je PLZ ({len(strassen)} < {args.min_strassen})')
    if hausnummern < args.min_hausnummern:
        fehler.append(f'zu wenige Hausnummern ({hausnummern} < {args.min_hausnummern})')
    for eintrag in args.pruefe:
        name, plz, *nummer = eintrag.split('|')
        orte = strassen.get((name, plz))
        if orte is None:
            fehler.append(f'Pflichtstraße fehlt: {name} {plz}')
        elif nummer and not any(nummer[0] in n for n in orte.values()):
            fehler.append(f'Pflichtadresse fehlt: {name} {nummer[0]}, {plz}')
    for meldung in fehler:
        print(f'FEHLER: {meldung}', file=sys.stderr)
    return 1 if fehler else 0


if __name__ == '__main__':
    sys.exit(main())
