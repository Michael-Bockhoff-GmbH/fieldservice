# IT Support mit Außendienst

Frappe-App für ERPNext v15/v16, entstanden aus dem Zusammenlegen der beiden
vormals eigenständigen Apps **`site_visit`** und **`zeit_projekt`** in eine
gemeinsame App (`fieldservice`). Drei Funktionen:

1. **Site Visit** – ein Techniker dokumentiert einen Kundeneinsatz vor Ort
   (Zeitraum inkl. Pausen, Fotos, Kundenunterschrift) und bekommt beim Buchen
   automatisch ein abrechenbares **Timesheet** erzeugt und verknüpft.
2. **Zeiterfassung als Einzelpositionen** – Knopf in der Ausgangsrechnung,
   der abrechenbare Zeiten (u. a. aus den oben erzeugten Timesheets) als
   eigene Rechnungspositionen importiert.
3. **Projekt aus Auftrag** – Haken im Auftrag, der beim Bestätigen
   automatisch ein Projekt anlegt und verknüpft.

Ein **Auftrag** ist bei Site Visit Pflicht, da darüber abgerechnet wird –
gibt es noch keinen, lässt er sich direkt aus dem Site Visit heraus anlegen
(siehe "Auftrag" unten). Die beiden ursprünglichen Apps arbeiten lose über
Kern-Doctypes zusammen (Activity Type, Timesheet) – aus diesem
Zusammenspiel heraus kam der Wunsch, sie als eine App auszuliefern.

---

## Zusammenlegung: was sich geändert hat

`fieldservice` ist technisch weiterhin **zwei Frappe-Module** in einer App –
"Site Visit" und "Zeit Projekt" wurden unverändert aus den beiden
Ursprungs-Apps übernommen (gleicher Modulname, gleiche Doctypes, gleiche
Feldnamen). Nur die App drumherum (Name, `hooks.py`, `install.py`,
Übersichts-Kachel) ist jetzt eine gemeinsame. Wer eine der beiden alten Apps
(`site_visit`, `zeit_projekt` – siehe deren Repositories, jetzt archiviert)
bereits installiert hatte: dort erst `bench uninstall-app <alte-app>`, dann
`fieldservice` installieren, da beide Module sich nicht gleichzeitig zwei
Apps zuordnen lassen.

Alle Python-Pfade, die App-intern auf sich selbst verweisen (`doc_events`,
`before_request`, `override_doctype_dashboards`, aufgerufene
`frappe.call`-Methoden in den Formular-Skripten), wurden dabei von
`site_visit.*`/`zeit_projekt.*` auf `fieldservice.*` umgestellt – die
**Modulnamen** ("Site Visit", "Zeit Projekt") und alle **Doctype-/Feldnamen**
blieben unverändert.

---

## Aufbau

```
fieldservice/
├── pyproject.toml
├── license.txt
├── README.md
├── CLAUDE.md
└── fieldservice/
    ├── __init__.py           # Versionsnummer + pdf_on_submit-Chrome-Patch
    ├── hooks.py              # doctype_js + doc_events + Install-Hooks (beide Module)
    ├── install.py            # after_install/before_uninstall (beide Module)
    ├── modules.txt           # "Site Visit" und "Zeit Projekt"
    ├── patches.txt
    ├── public/
    │   ├── js/
    │   │   ├── site_visit.js      # Site Visit: Feld-Defaults, Timer, Neuer-Auftrag-Dialog
    │   │   ├── sales_order.js     # Zeit Projekt: Hinweise + Sprung zum Projekt nach dem Buchen
    │   │   └── sales_invoice.js   # Zeit Projekt: Import-Knopf und Positionslogik
    │   └── images/fieldservice-logo.svg
    ├── translations/
    │   └── de.csv               # Deutsche Übersetzungen fürs Modul "Site Visit" (siehe "Sprache")
    ├── workspace_sidebar/
    │   └── site_visits.json     # Eigene Sidebar (Site Visit + Timesheet, kein Home-Link)
    ├── site_visit/            # Modul "Site Visit"
    │   ├── doctype/
    │   │   ├── site_visit/          # Haupt-Doctype (submittable) + site_visit_calendar.js
    │   │   ├── site_visit_photo/    # Kindtabelle für Fotos
    │   │   ├── site_visit_item/     # Kindtabelle für Zusatzartikel
    │   │   ├── site_visit_break/    # Kindtabelle für Pausen (Timer)
    │   │   ├── site_visit_excluded_item_group/ # Kindtabelle für Excluded Item Groups
    │   │   └── site_visit_settings/ # Single-Doctype, App-Einstellungen
    │   ├── print_format/
    │   │   └── site_visit_report/   # PDF-Vorlage
    │   ├── workspace/
    │   │   └── site_visits/         # Desk-Seite
    │   ├── www/
    │   │   ├── site-visit-sign.py   # Kontext/Token-Pruefung fuer die Fernunterschrift
    │   │   └── site-visit-sign.html # Oeffentliche Unterschriften-Seite (kein Login)
    │   ├── site_visit.py            # before_submit/on_cancel/create_sales_order/item_query_extra_items/...
    │   ├── mileage.py               # Kilometerberechnung ueber OpenRouteService
    │   ├── remote_signature.py      # Signaturlink senden + oeffentliches Speichern der Unterschrift
    │   └── project_dashboard.py     # ergänzt "Site Visit" in den Projekt-Verknüpfungen
    └── zeit_projekt/           # Modul "Zeit Projekt"
        ├── doctype/
        │   └── zeit_projekt_einstellungen/
        ├── sales_order.py            # Projektanlage in before_submit (serverseitig)
        └── timesheet_import.py       # Zeiten fuer den Rechnungsimport (inkl. Auftrag/Filter)
```

`install.py` legt außer den drei Custom Fields von "Zeit Projekt" **keine**
weiteren Custom Fields oder sonstigen Datensätze auf Kern-Doctypes an – der
einzige weitere Zweck ist der optionale Eintrag in `PDF on Submit Settings`
(siehe "Automatische PDF-Erzeugung" unten), und auch der nur, wenn
`pdf_on_submit` installiert ist. Alles andere gehört zu den Modulen "Site
Visit"/"Zeit Projekt" und wird von `uninstall-app` bereits vollständig
entfernt.

Die Formular-Skripte sind **Dateien**, keine Client-Script-Datensätze. Sie
verschwinden restlos mit der App und unterliegen nicht dem
Client-Script-Cache im Browser.

## Sprache

Die beiden Module sind historisch unterschiedlich aufgebaut, das ist nach
der Zusammenlegung bewusst so geblieben:

- **Site Visit**: auf Englisch geschrieben (Feldbezeichnungen, Meldungen,
  Druckvorlage), Übersetzung über `fieldservice/translations/de.csv` (Frappes
  normales Verfahren – der englische Text im Code/in der Doctype-JSON
  bleibt die Quelle, die CSV-Datei übersetzt für Nutzer mit Sprache
  "Deutsch"). Standardbegriffe, die bereits über Frappe/ERPNext selbst
  übersetzt sind (z. B. "Customer", "Employee", "Project", "Sales Order",
  "Timesheet"), sind bewusst **nicht** nochmal in `de.csv` enthalten.
- **Zeit Projekt**: Feldbezeichnungen und Meldungen stehen direkt auf
  Deutsch im Code/in der Doctype-JSON, ohne eigene Übersetzungsdatei.

Nach Änderungen an Texten im Site-Visit-Code: neue/geänderte Strings auch in
`de.csv` ergänzen, sonst bleiben sie auf Deutsch unübersetzt (Englisch als
Fallback). Bei Zeit-Projekt-Texten direkt im Code ändern.

---

## Vor der Installation anpassen

In `pyproject.toml` und `fieldservice/hooks.py` Name, E-Mail und Beschreibung
eintragen. Willst du die App anders nennen, muss der Name an vier Stellen
konsistent sein: Ordnername, Paketordner, `app_name` in `hooks.py` und
`name` in `pyproject.toml` – dazu alle `fieldservice.*`-Pfade in `hooks.py`
(`doc_events`, `before_request`, `override_doctype_dashboards`,
`add_to_apps_screen`, `after_install`/`before_uninstall`) sowie die
`frappe.call`-Methodenpfade in `public/js/site_visit.js` und
`public/js/sales_invoice.js`.

---

## Installation (eigener Bench)

```bash
cd ~/frappe-bench
bench get-app https://github.com/<dein-user>/fieldservice.git
bench --site <deine-site> install-app fieldservice
bench build --app fieldservice
bench --site <deine-site> clear-cache
```

## Installation (Frappe Cloud)

Eigene Apps brauchen dort ein Git-Repository und eine eigene Bench-Gruppe
(auf den kleinen Shared-Plänen nicht möglich).

1. Repository auf GitHub anlegen und den Inhalt dieses Ordners hochladen
2. In Frappe Cloud: Bench-Gruppe → *Apps* → *Add App* → *From GitHub*
3. Deploy anstoßen, danach die App auf der Site installieren

---

## Deinstallation

```bash
bench --site <deine-site> uninstall-app fieldservice --dry-run   # nur anzeigen
bench --site <deine-site> uninstall-app fieldservice
```

**Was dabei entfernt wird:**

- die Doctype "Site Visit" und ihre Kindtabellen ("Site Visit Photo",
  "Site Visit Item", "Site Visit Break")
- die Doctype "Site Visit Settings" und ihre Kindtabelle "Site Visit
  Excluded Item Group"
- die Doctype "Zeit Projekt Einstellungen", die vier Custom Fields von
  "Zeit Projekt" (`before_uninstall`) und die Property Setter, die
  Customer Reference (Sales Order.po_no) verpflichtend macht
- beide Module ("Site Visit", "Zeit Projekt") und alles, was daran hängt
- die Formular-Skripte, da sie reiner Code sind
- die Zeile `Site Visit` in `PDF on Submit Settings` (nur falls
  `pdf_on_submit` installiert ist – `before_uninstall` räumt sie mit auf)
- die drei Shortcuts (Site Visit, Timesheet, Zeit Projekt Einstellungen)
  auf ERPNexts Standard-"Home"-Workspace (siehe "Eigene App im Desk")

**Was bewusst bestehen bleibt:**

- bereits gebuchte Site Visits inkl. Fotos und Unterschrift, bereits
  angelegte und gebuchte Timesheets, auch wenn das erzeugende Site Visit
  später storniert würde
- bereits fakturierte Timesheets – ein Site Visit mit fakturiertem
  Timesheet lässt sich nicht mehr stornieren (siehe `on_cancel` in
  `site_visit/site_visit.py`)
- bereits in Aufträge übernommene Zusatzartikel (die Auftragspositionen
  selbst gehören nicht zu dieser App)
- alle angelegten Projekte, alle geschriebenen Rechnungspositionen (auch in
  gebuchten Belegen), die Verknüpfungen zwischen Auftrag und Projekt

**Achtung:** Beim Löschen eines Custom Fields wird die Spalte aus der
Tabelle entfernt. Die Zuordnungen *Aktivitätsart → Dienstleistungsartikel*
sind danach weg. Frappe legt vor dem Deinstallieren automatisch ein Backup
an (außer mit `--no-backup`).

---

## Einrichtung

- Für jede genutzte **Activity Type** sollte ein sinnvoller Stundensatz
  hinterlegt sein, damit ein automatisch aus einem Site Visit erzeugtes
  Timesheet korrekt abgerechnet werden kann.
- Je Aktivitätsart einen **Dienstleistungsartikel** eintragen (für den
  Rechnungsimport), dafür einen **Verkaufspreis** in der
  Standard-Verkaufspreisliste hinterlegen.
- Prüfen, dass der Projekttyp **External** existiert (für die automatische
  Projektanlage aus dem Auftrag).

Unter **Zeit Projekt Einstellungen** (Suchleiste oder
`/app/zeit-projekt-einstellungen`) lässt sich das Verhalten des
Rechnungsimports umstellen:

**Erste Zeile der Positionsbeschreibung**

| Auswahl | Ergebnis in der Position |
|---|---|
| *Nur Datum und Uhrzeit* (Standard) | `05.05.2026 09:51-13:51 Uhr` – der Artikelname steht ohnehin schon in der Position |
| *Aktivitätsart voranstellen* | `Ausführung – 05.05.2026 09:51-13:51 Uhr` |
| *Bezeichnung für Rechnung, sonst Aktivitätsart* | nutzt das Feld `custom_rechnungstext` der Aktivitätsart, sonst deren Namen |

Die dritte Variante lohnt nur, wenn mehrere Aktivitätsarten auf denselben
Artikel zeigen – dann ist die Bezeichnung die einzige Unterscheidung auf der
Rechnung. In den ersten beiden Modi kann das Feld *Bezeichnung für Rechnung*
leer bleiben. Der Freitext aus der Zeitbuchung steht in allen drei Varianten
darunter.

**Liefertermin der Position:** Beginn (Standard) oder Ende der Zeitbuchung.
Relevant nur bei Buchungen über Mitternacht.

**Auftrag (optional, nur Filter):** schränkt die im Dialog geladenen Zeiten
zusätzlich auf einen bestimmten Auftrag des Projekts ein (z. B. um nur die
Zeiten eines bestimmten Auftrags zu sehen, wenn ein Projekt mehrere hat).
Leer gelassen kommen wie bisher **alle** abrechenbaren Zeiten des Projekts,
unabhängig vom Auftrag — der Filter ändert also nichts an der Abrechnung
selbst, nur an der Vorauswahl im Dialog. Technisch möglich, weil Site Visit
jede Zeitblatt-Zeile mit dem eigenen Auftrag verknüpft
(`custom_sales_order`, Custom Field auf "Timesheet Detail" — siehe
`install.py`); Zeiten ohne Site Visit (z. B. manuell erfasste
Timesheet-Zeilen) haben diesen Wert nicht gesetzt und tauchen bei einem
gesetzten Auftrags-Filter entsprechend nicht auf.

Aus demselben Feld übernimmt jede importierte Rechnungsposition den Auftrag
auch gleich in ihr eigenes, von ERPNext bereits mitgeliefertes Feld
`sales_order` (Sales Invoice Item) — die bislang fehlende Verknüpfung
zwischen Rechnung und Auftrag.

## Nach der Installation

Die App deaktiviert vorhandene Client Scripts mit den Namen
„Zeiterfassung als Einzelpositionen", „Auftrag: Projekt erstellen" und
„Auftrag: Kommission und Projekt", damit die Funktionen nicht doppelt
laufen. Löschen musst du sie selbst.

## Eigene App im Desk

Die App bringt ein eigenes Logo mit
(`public/images/fieldservice-logo.svg`) und registriert sich über
`add_to_apps_screen`/`app_logo_url` in `hooks.py` als eigene Kachel auf der
Apps-Übersicht (`/apps`), inklusive einer eigenen Workspace mit
Verknüpfungen zu "Site Visit" und "Timesheet".

Zusätzlich ergänzt `install.py` (`_home_workspace_enable`/
`_home_workspace_disable`) vier Shortcuts auf ERPNexts Standard-**"Home"**-
Workspace — **Site Visit**, **Timesheet**, **Zeit Projekt Einstellungen**,
**Dispatch Board** — damit die App auch von der normalen Startseite aus
auffindbar ist, ohne erst über die Apps-Übersicht zu gehen. Rein additiv:
bestehende Shortcuts/Karten auf Home bleiben unangetastet, `before_uninstall`
entfernt beim Deinstallieren exakt diese vier Einträge wieder (identifiziert
über ihr Label, siehe `HOME_SHORTCUTS` in `install.py`).

## Auftrag

`project` ist ebenfalls Pflicht (wie `customer`/`activity_type`/`sales_order`
erst beim Buchen selbst geprüft, nicht auf Feldebene – sonst wäre ein
Entwurf mit nur laufendem Timer nicht speicherbar, siehe "Timer" unten).

Jeder Einsatz muss einem Auftrag zugeordnet sein, da darüber (und über das
automatisch erzeugte Timesheet) abgerechnet wird – entweder ein bereits
bestehender (Feld `sales_order`), oder ein neuer, automatisch beim Buchen
angelegter. Gibt es noch keinen passenden Auftrag, **"Create Sales
Order"** ankreuzen (Checkbox, sichtbar solange kein Auftrag ausgewählt
ist) – dabei erscheint das Feld **Customer Reference**, das dann Pflicht
wird (Kunde/Firma/Projekt kommen vom Site Visit selbst). Der neue Auftrag
entsteht beim Buchen als **Entwurf** – Buchen des Auftrags selbst bleibt
Sache des Vertriebs, nicht des Technikers vor Ort – und übernimmt dabei
automatisch zwei Arten von Positionen (`_create_sales_order` in
`site_visit/site_visit.py`):

1. die **gearbeitete Zeit** als Position mit dem Dienstleistungsartikel der
   Aktivitätsart (`custom_dienstleistungsartikel`, aus Zeit Projekt) –
   Menge = Arbeitsstunden (ohne Pausen, siehe "Timer" unten), Preis wie
   beim Rechnungsimport: zuerst der Verkaufspreis des Artikels, sonst der
   Standard-Stundensatz der Aktivitätsart. Fehlt beides, bricht das Buchen
   mit einer klaren Fehlermeldung ab, statt eine Position ohne (oder mit
   falschem) Preis anzulegen.
2. alle bereits eingetragenen **Zusätzlichen Artikel** (siehe unten) –
   anders als früher ist dafür keine Mindestanzahl an Zeilen mehr nötig, da
   die Zeit-Position ohnehin immer mindestens eine Position liefert.

**Customer Reference** (`po_no` am Auftrag) ist außerdem **für jeden
Auftrag in ERPNext verpflichtend** – nicht nur für automatisch über Site
Visit angelegte, sondern generell, auch bei manuell angelegten Aufträgen.
Umgesetzt über eine Property Setter (`_po_no_required_enable`/
`_po_no_required_disable` in `install.py`), nicht über ein Custom Field, da
`po_no` bereits ein Kernfeld von Sales Order ist.

Hat das gewählte Projekt **mehrere** offene Aufträge, wählt `fill_from_project`
in `site_visit.js` nicht mehr automatisch (das ging bisher nur bei genau
einem Treffer) und zeigt stattdessen einen Auswahldialog mit allen
passenden Aufträgen. `sales_order` bleibt dabei absichtlich **nicht** auf
Feldebene Pflicht (siehe "Timer" unten, wegen des Timer-Entwurfs) – die
Pflicht wird weiterhin erst beim Buchen selbst geprüft (`before_submit`).

**Zusätzliche Artikel** (`extra_items`): vor Ort zusätzlich benötigtes
Material (z. B. ein USB-auf-LAN-Adapter), das noch nicht im Auftrag steht –
keine Dienstleistungsartikel. Das Artikel-Feld ist über
`item_query_extra_items` (`site_visit.py`) auf die in **Site Visit
Settings** hinterlegten **Excluded Item Groups** eingeschränkt: Artikel aus
diesen Gruppen (inkl. Untergruppen) sind **nicht** wählbar, alles andere
schon – ein Ausschluss- statt Einschluss-Filter, da meist nur die eigene(n)
Dienstleistungs-Artikelgruppe(n) ausgeschlossen werden müssen, statt
umgekehrt jede erlaubte Hardware-/Verbrauchsmaterial-Gruppe einzeln
aufzulisten. Ohne hinterlegte Gruppe gilt keine Einschränkung. Beim Buchen des Site
Visit werden neue (noch nicht übernommene) Zeilen automatisch in die
Positionen des verknüpften Auftrags aufgenommen – auch wenn der Auftrag
bereits gebucht ist (über
`erpnext.controllers.accounts_controller.update_child_qty_rate`, dieselbe
Funktion, die auch der "Update Items"-Dialog im Auftrag selbst verwendet;
bestehende Positionen, Steuern und Summen werden dabei korrekt neu
berechnet). Da Techniker i. d. R. keine eigenen Sales-Order-Rechte haben,
läuft das serverseitig kurzzeitig als Administrator – die eigentliche
Berechtigungsprüfung ist die auf den Site Visit selbst.

## Timer

"Start Timer"/"Stop Timer" im Site-Visit-Formular setzen nicht nur
`from_time`/`to_time`, sondern **speichern sofort** – genau wie ERPNexts
eigener Timesheet-Timer (`erpnext/public/js/projects/timer.js`, ruft nach
dem Setzen von `from_time` ebenfalls direkt `frm.save()` auf). Ohne das
sofortige Speichern ginge ein laufender Timer bei einem Reload oder
Schliessen der Seite verloren, weil ein neues, ungespeichertes Dokument nur
im Browser existiert.

Damit ein Entwurf mit nur laufendem Timer überhaupt speicherbar ist, sind
Kunde, Aktivitätsart, Auftrag und Endzeit **nicht auf Feldebene Pflicht** –
sie werden erst beim Buchen selbst geprüft (`before_submit` in
`site_visit/site_visit.py`), mit einer klaren Fehlermeldung, falls etwas
fehlt. `employee` ist ebenfalls nicht Pflicht (weder im Feld noch beim
Buchen) – bleibt es leer, entsteht das automatisch erzeugte Timesheet ohne
Mitarbeiter, genau wie bei einem von Hand angelegten Timesheet in ERPNext
selbst.

### Pausieren/Fortsetzen

Neben "Start Timer"/"Stop Timer" gibt es "Pause Timer"/"Resume Timer" — für
eine Kaffeepause vor Ort oder einen Notfall bei einem anderen Kunden, ohne
den Einsatz gleich ganz zu beenden. "Pause Timer" fragt per Dialog einen
**Grund** ab (`Break`, `Other Customer (Emergency)`, `Other`) und optional
eine **Notiz**, und legt damit eine Zeile in der Kindtabelle `breaks` an
(Doctype "Site Visit Break": `from_time`/`to_time`/`reason`/`note`) —
dieselbe Sofort-Speichern-Logik wie beim Start. "Resume Timer" schließt die
letzte offene Pausenzeile mit der aktuellen Zeit ab.

`from_time`/`to_time` am Site Visit selbst bleiben dabei unverändert der
durchgehende Gesamtrahmen des Einsatzes — die Pausen werden erst beim Buchen
herausgerechnet: `_get_work_segments()` in `site_visit/site_visit.py`
zerlegt den Zeitraum anhand der (dann alle geschlossenen) Pausen in einzelne
Arbeitsabschnitte und legt dafür je einen eigenen Timesheet-Eintrag an,
statt eines einzigen Blocks über die volle Dauer. So zählt die Pausenzeit
weder als Arbeitszeit, noch überschneidet sie sich mit einem
Timesheet-Eintrag, den derselbe Mitarbeiter währenddessen für einen anderen
Site Visit anlegt (z. B. den Notfall-Einsatz beim anderen Kunden).

"Stop Timer" funktioniert auch während einer laufenden Pause — eine noch
offene Pause wird dann auf denselben Zeitpunkt wie `to_time` geschlossen,
statt ein vorheriges "Resume Timer" zu erzwingen (falls der Einsatz z. B.
mitten in der Pause endgültig endet). Vor dem Buchen muss trotzdem jede
Pause geschlossen sein — sonst weist `before_submit` mit einer klaren
Fehlermeldung darauf hin.

## Site Visit Settings

Neue, eigene Single-Doctype (Suchleiste oder `/app/site-visit-settings`) für
die App-weiten Einstellungen von Site Visit:

| Bereich | Feld | Bedeutung |
|---|---|---|
| Allgemein | Time Zone | Zeitzone des Unternehmens (Standard **Europe/Berlin**, volle IANA-Liste wie in Frappes eigenen System Settings, Sommerzeit automatisch berücksichtigt) — bewusst getrennt von der site-weiten System-Settings-Zeitzone, siehe "## Terminplanung" für den Hintergrund. |
| Terminplanung | Calendar Tooltip Field | **Project** (Standard) oder **Sales Order** — welches Feld beim Überfahren eines geplanten Termins mit der Maus zusätzlich zur Uhrzeit angezeigt wird, in der Kalenderansicht und im Einsatzplan gleichermaßen. |
| Funktionen | Enable Mileage Calculation | Standard **an**. Aus = Kilometer-/Entfernungsfelder und "Calculate Mileage" verschwinden vom Site Visit, keine automatische Kilometerabrechnung mehr. |
| Funktionen | Enable Remote Visits | Standard **an**. Aus = der Haken "Remote Visit" verschwindet, jeder Einsatz gilt als vor Ort. |
| Funktionen | Enable Photos | Standard **an**. Aus = der Bereich "Photos" verschwindet vom Site Visit. |
| Funktionen | Enable Additional Items | Standard **an**. Aus = die Tabelle "Additional Items" (und die Einstellung "Excluded Item Groups" darunter) verschwindet vom Site Visit. |
| Kilometer | OpenRouteService API Key | Kostenloser Key von [openrouteservice.org](https://openrouteservice.org) — ohne Key funktioniert "Kilometer berechnen" nicht. Feldtyp **Password**, daher verschlüsselt gespeichert und im Formular maskiert. |
| Kilometer | Default Start Address | Freitext-Startpunkt, falls der Site Visit selbst keine eigene Startadresse hat. Leer = Standardadresse der Firma. |
| Kilometer | Mileage Item | Artikel, dessen Verkaufspreis pro Kilometer als Fahrtkosten-Position im Auftrag berechnet wird. Leer = keine automatische Fahrtkosten-Abrechnung. |
| Zusätzliche Artikel | Excluded Item Groups | Artikel aus diesen Gruppen (inkl. Untergruppen, i. d. R. die Dienstleistungs-Gruppe(n)) sind als Zusatzartikel **nicht** wählbar — alles andere schon. Leer = keine Einschränkung. |
| Fernarbeit | Remote Visit Mode | "Hide Signature" (Unterschriftsfelder ausblenden) oder "Send Signing Link to Customer" (Link per E-Mail). |
| Fernarbeit | Signature Required | Ohne Unterschrift nicht buchbar — außer bei Fernarbeit im Modus "Hide Signature". |

Die vier **Funktionen**-Schalter blenden die zugehörigen Bereiche im Site
Visit rein clientseitig aus (`update_feature_visibility()` in
`site_visit.js`, mit `frm.toggle_display()`) — für Kilometer/Fernarbeit
zusätzlich zur ohnehin schon bestehenden `depends_on`-Logik dieser Felder
(`!doc.is_remote` usw.), nicht anstelle davon, sonst würde Frappes eigene
`depends_on`-Auswertung ein wegen des Schalters ausgeblendetes Feld bei der
nächsten Änderung (z. B. an `is_remote`) wieder einblenden. Serverseitig
prüft `_mileage_billable()` (`site_visit/site_visit.py`) und
`calculate_distance_km()` (`mileage.py`) **Enable Mileage Calculation**
zusätzlich selbst — ausgeschaltet wird also auch dann nicht mehr
abgerechnet bzw. berechnet, wenn jemand die Felder trotzdem befüllt hätte
(z. B. über die API). Für Fernarbeit/Fotos/Zusätzliche Artikel reicht das
reine Ausblenden: eine leere Tabelle bzw. ein nie gesetztes `is_remote`
wirkt sich ohnehin nicht auf Timesheet/Auftrag aus.

## Kilometer

"Calculate Mileage" im Formular (sichtbar, solange der Site Visit gespeichert,
nicht gebucht, nicht als Fernarbeit markiert ist und ein Kunde gewählt ist —
bei Fernarbeit ist die ganze Kilometer-Sektion ausgeblendet, da dabei nicht
gefahren wird) berechnet die einfache Fahrstrecke von der Startadresse zur
Zieladresse über die [OpenRouteService](https://openrouteservice.org)-API:
zuerst Geocoding (Adresstext → Koordinaten) für beide Adressen, dann eine
Routenabfrage zwischen den Koordinaten (`site_visit/mileage.py`). Das
Ergebnis landet schreibgeschützt in `distance_km`.

**Start-/Zieladresse sind reiner Freitext** (Felder `start_address`/
`customer_address_override` am Site Visit, `default_start_address` in Site
Visit Settings — alle drei Feldtyp **Autocomplete** statt **Link
(Address)**) — es ist **kein eigener Address-Datensatz in ERPNext nötig**.
Während der Eingabe schlägt `search_addresses()` (`site_visit/mileage.py`)
passende Adressen von **Nominatim** (OpenStreetMap) vor — eine eigene,
direkte Anbindung dieser App, kostenlos und ohne eigenen API-Key nötig.
Bewusst **nicht** verwendet wird Frappes eingebaute Adress-Autovervoll-
ständigung (Kern-Doctype **Geolocation Settings**): deren mitgelieferter
Nominatim-Anbieter schickt keinen `User-Agent`-Header mit, wie es
[Nominatims Nutzungsbedingungen](https://operations.osmfoundation.org/policies/nominatim/)
verlangen, und wird deshalb mit `403 Forbidden` abgelehnt — ein Fehler in
Frappe selbst, siehe Modul-Docstring in `mileage.py`. `search_addresses()`
liefert bereits fertig lesbare Adresszeilen zurück, kein Nachformatieren
im Formular nötig. Schlägt die Suche fehl (Netzwerk-/API-Fehler), bleibt
die Vorschlagsliste einfach leer, statt das Formular zu unterbrechen —
frei eingetippter Text ohne Vorschlagsauswahl bleibt jederzeit nutzbar.

Frappes Autocomplete-Feld fragt bei **jedem** Tastendruck neu an, ganz ohne
eigenes Debouncing — was Nominatims Limit von maximal einer Anfrage pro
Sekunde (site-weit) beim Tippen eines längeren Adressnamens allein schon
reißen würde und zu einer vorübergehenden Sperre führt. Da das Frappe-Kern
ist und nicht gepatcht wird, bündelt `debounce_address_field()`
(`public/js/site_visit.js`, analog in `site_visit_settings.js`) die Anfragen
clientseitig, statt erst bei jedem Tastenanschlag zu suchen (ein früherer
serverseitiger Debounce-Versuch per `time.sleep()` blockierte dabei jeweils
einen ganzen Web-Worker und war selbst ein Verfügbarkeitsrisiko).
`search_addresses()` bleiben nur zwei einfache, nicht-blockierende
Absicherungen: Text unter 3 Zeichen wird ignoriert, Ergebnisse werden pro
Suchtext kurz zwischengespeichert, und liegt die letzte tatsächliche
Nominatim-Anfrage noch keine 1,1 Sekunden zurück, wird gar nicht erst
angefragt (statt zu warten).

Startadresse (in dieser Reihenfolge, erste gefundene gewinnt):

1. Feld **Start Address** direkt am Site Visit (Überschreibung für diesen
   einen Einsatz, z. B. wenn der Techniker von zuhause oder von einem
   anderen Einsatz aus direkt weiterfährt). Sichtbar erst, nachdem der
   Haken **"Different Start Location"** gesetzt wurde (sonst ausgeblendet,
   da im Normalfall — Start von der Firma bzw. der hinterlegten Default
   Start Address — nicht gebraucht)
2. **Default Start Address** in Site Visit Settings
3. Standardadresse der am Site Visit hinterlegten **Company** (dafür
   weiterhin ein echter ERPNext-Address-Datensatz — Firmenadressen sind
   stabil genug, dass sich das lohnt)

Zieladresse (in dieser Reihenfolge):

1. Feld **Customer Site Address** direkt am Site Visit — z. B. eine
   Außenstelle/ein Remote Office des Kunden, abweichend von dessen
   hinterlegter Standardadresse. Sichtbar erst, nachdem der Haken
   **"Don't Use Customer's Default Address"** gesetzt wurde (sonst
   ausgeblendet, da im Normalfall nicht gebraucht)
2. Standardadresse des am Site Visit gewählten **Customer** — außer der
   Haken **"Don't Use Customer's Default Address"** ist gesetzt (z. B.
   weil die hinterlegte Adresse für diesen Einsatz bekanntermaßen falsch
   ist); dann zählt ausschließlich Schritt 1, und ohne **Customer Site
   Address** lässt sich keine Kilometerzahl berechnen

Ohne konfigurierten API-Key oder ohne auffindbare Start-/Zieladresse
schlägt die Berechnung mit einer verständlichen Fehlermeldung fehl — die
Kilometerberechnung ist eine Komfortfunktion, kein Teil der
`before_submit`-Pflichtprüfung, ein Site Visit lässt sich auch ohne
Kilometer buchen.

### Fahrtkosten im Auftrag

Ist in Site Visit Settings ein **Mileage Item** hinterlegt, übernimmt
`_get_mileage_line()`/`_sync_sales_order()` in `site_visit/site_visit.py`
beim Buchen zusätzlich zu den Zusatzartikeln eine Fahrtkosten-Position in
den verknüpften Auftrag — Menge = Kilometer, Satz = Verkaufspreis des
Mileage Item aus der Preisliste des Auftrags (genau wie beim normalen
Hinzufügen eines Artikels im Auftrag). **Voreinstellung ist Hin- und
Rückweg** (`distance_km × 2`); der Haken **"One-Way Trip Only"** am Site
Visit rechnet stattdessen nur die einfache Strecke ab, z. B. wenn der
Techniker direkt zum nächsten Kunden weiterfährt statt zurückzufahren.
Auch das ist rein optional: ohne berechnete Kilometer oder ohne
konfiguriertes Mileage Item passiert nichts. Ein erneuter Sync-Lauf für
denselben Site Visit (z. B. nach einer Korrektur per Amend, siehe
"Stornieren & Amend" unten) aktualisiert die bestehende Fahrtkosten-Zeile
im Auftrag, statt eine weitere hinzuzufügen — verfolgt über das interne,
ausgeblendete Feld `mileage_sales_order_item`.

### Stornieren & Amend

Beim Stornieren wird das verknüpfte Timesheet mitstorniert (sofern noch
nicht fakturiert, sonst lehnt ERPNext die Stornierung ab). Wird der Site
Visit danach per Amend korrigiert (z. B. eine falsche `to_time`) und erneut
gebucht, prüft `before_submit()` den Docstatus des verknüpften Timesheets:
nur ein noch gebuchtes (docstatus 1) Timesheet zählt als gültig verknüpft
und wird übernommen. Zeigt `timesheet` (das Feld bleibt beim Amend
erhalten, `no_copy` hin oder her) stattdessen auf ein bereits storniertes
Timesheet, läuft die volle Prüfung/Anlage erneut: neues Timesheet, erneute
Unterschriftsprüfung, erneuter Sync des (unverändert verknüpften) Auftrags.

## Terminplanung

Ein Site Visit lässt sich auch **im Voraus** anlegen, bevor der Einsatz
stattfindet: die Felder **Scheduled Start**/**Scheduled End** (getrennt von
`from_time`/`to_time`, die weiterhin die *tatsächliche* Einsatzzeit über den
Timer festhalten) markieren ein geplantes Termin-Zeitfenster. Ein
Dispatcher/Projects Manager legt dazu einen Entwurf mit Kunde, Employee und
diesen beiden Feldern an — ohne `from_time` lässt sich der Entwurf trotzdem
speichern (siehe "Timer" oben), sodass daraus noch kein laufender Timer
wird. Der Techniker öffnet den vorbereiteten Site Visit später einfach und
klickt "Start Timer" wie gewohnt.

Über `hooks.py` → `calendars = ["Site Visit"]` plus
`site_visit/doctype/site_visit/site_visit_calendar.js` (automatisch anhand
des Dateinamens geladen, kein zusätzlicher Hook-Eintrag nötig — derselbe
Mechanismus wie bei ERPNexts eigenen `task_calendar.js`/
`job_card_calendar.js`) bekommt "Site Visit" in der Listenansicht einen
**Kalender**-Ansichtswechsler, gefiltert nach Employee/Customer. Bewusst
zunächst nur ein lokaler Kalender innerhalb von ERPNext — für eine spätere
Anbindung an Office 365/Outlook wären `scheduled_start`/`scheduled_end` die
Felder, die ein Sync-Job gegen die Microsoft-Graph-API abgleichen müsste;
das ist noch nicht gebaut.

### Zeitzone

Frappes eingebaute Kalenderansicht rechnet Termine standardmäßig zwischen
der site-weiten **System Settings → Time Zone** und der Zeitzone des
Nutzers um (`convert_to_user_tz`, Frappe-Kern). Stimmt System Settings
nicht mit der tatsächlichen Zeitzone des Unternehmens überein — am
18.09.2026 stand sie auf diesem Server auf "Asia/Kolkata" statt
"Europe/Berlin", vermutlich ein nie angepasster Installations-Standard —,
verschieben sich Termine im Kalender um Stunden oder fallen ganz aus dem
sichtbaren Tag heraus. Da diese App nicht die site-weite System-Settings-
Zeitzone ändern will (betrifft die ganze Site, nicht nur Site Visit),
schaltet `site_visit_calendar.js` diese Umrechnung für Site Visit gezielt
ab (`field_map.convertToUserTz = true`, siehe Kommentar dort) — Termine
werden als reiner Klartext-Zeitpunkt angezeigt, genau wie im Formular und
im Dispatch Board, unabhängig davon, was in System Settings steht.

**Site Visit Settings → Time Zone** (Standard **Europe/Berlin**, volle
IANA-Zeitzonenliste wie in Frappes eigenen System Settings, siehe
`get_timezone_options()` in `site_visit_settings.py`) ändert an dieser
Kalenderanzeige nichts direkt mehr — sie ist die für diese App
maßgebliche, korrekt vorbelegte Zeitzone, unabhängig von System Settings,
und der Anker für eine spätere Office-365/Outlook-Anbindung (die für
Outlooks Kalender-API einen echten Zeitzonennamen braucht). Berücksichtigt
die Sommerzeit automatisch, wie jeder IANA-Zeitzonenname.

Beim Überfahren eines Termins mit der Maus (Kalenderansicht wie
Einsatzplan) zeigt ein eigener Tooltip statt des eingebauten Browser-
Tooltips die korrekte Uhrzeit sowie, je nach **Site Visit Settings →
Calendar Tooltip Field**, zusätzlich das verknüpfte **Project** (Standard)
oder den verknüpften **Sales Order** — `eventDidMount` in
`site_visit_calendar.js` bzw. der `title`-Attribut-Aufbau in
`dispatch_board.js`, beide gespeist aus `data.tooltip_field`/derselben
Einstellung.

### Terminkonflikte

Überschneiden sich die geplanten Zeitfenster (`scheduled_start`/
`scheduled_end`) zweier Site Visits desselben Mitarbeiters, warnt die App
— blockiert das Speichern aber bewusst nicht, z. B. für einen kurzen
Telefontermin parallel zu einem laufenden Vor-Ort-Einsatz:

- **Im Formular**: sofort beim Ändern von Employee/Scheduled Start/
  Scheduled End ein kurzer Hinweis (`check_schedule_conflict` in
  `site_visit.js`), und nach dem Speichern eine ausführliche Meldung mit
  den betroffenen Terminen (`warn_schedule_conflicts()` im
  `validate()`-Hook, `site_visit/doctype/site_visit/site_visit.py` bzw.
  `site_visit/site_visit.py`) — greift dadurch auch bei API-Zugriffen und
  Datenimporten, nicht nur im Formular.
- **Im Einsatzplan** (siehe unten): überlappende Termine sind farblich
  markiert, mit derselben Prüfung (`_intervals_overlap`/`_find_conflicts`),
  damit Formular und Einsatzplan nie unterschiedliche Aussagen treffen.

Stornierte Site Visits blockieren keinen Slot mehr; ein Termin, der genau
dort endet, wo der nächste beginnt, gilt nicht als Konflikt.

### Einsatzplan (Dispatch Board)

Zusätzlich zur (nach Employee/Customer gefilterten) Kalenderansicht gibt es
unter **Dispatch Board** (Home-Seite, "Site Visits"-Workspace, ein Knopf
direkt oben in der normalen Site-Visit-Listenansicht — `site_visit_list.js`,
automatisch anhand des Dateinamens geladen —, oder direkt
`/app/dispatch-board`) einen Überblick über **alle Techniker an einem Tag
nebeneinander** — eine Zeile pro aktivem Mitarbeiter, die geplanten
Site Visits als Zeitblöcke auf einer gemeinsamen Zeitachse
(`site_visit/page/dispatch_board/`, Datenquelle
`site_visit/dispatch_board.py`). Nur für Rollen sichtbar, die ohnehin schon
alle Einsätze aller Mitarbeiter sehen dürfen (System Manager, Projects
Manager) — ein Techniker sieht dort keinen Überblick über die Einsätze
anderer.

Über die Ansicht-Auswahl oben lässt sich zwischen **Day**, **Work Week**
(Mo–Fr), **Week** (Mo–So) und **Month** wechseln — alle vier fragen
denselben Endpunkt nur mit unterschiedlichem Zeitraum ab
(`get_dispatch_board_data(start_date, end_date)`).

Day/Work Week/Week zeigen die volle 24-Stunden-Achse mit sichtbaren
Stunden-Rasterlinien (Tagesgrenzen zusätzlich hervorgehoben) in einem
festen Pixelraster statt auf die Bildschirmbreite gestaucht — dadurch
horizontal scrollbar, mit Sprung auf 07:00 als Startansicht. Die
Technikernamen-Spalte bleibt beim Scrollen sichtbar (`position: sticky`).

- **Day**: die Zeitachse wie gehabt, plus **Ziehen zum Anlegen** — bei
  gedrückter Maustaste über die Zeile eines Technikers ziehen spannt den
  gewünschten Zeitraum auf (auf 15 Minuten gerundet), beim Loslassen öffnet
  sich ein neuer Site Visit mit vorbelegtem Mitarbeiter, Start- und
  Endzeit. Ein einfacher Klick ohne nennenswerte Bewegung legt wie bisher
  einen Termin mit einer Stunde Standarddauer an.
- **Work Week/Week**: dieselbe Zeitachse über mehrere Tage gestreckt (ein
  Klick legt einen Termin mit Standarddauer an einer geschätzten Uhrzeit
  an) — Ziehen über mehrere Tage hinweg wäre mehrdeutig, dafür lieber kurz
  in die Tagesansicht wechseln.
- **Month**: pro Tag nur ein Zähl-Badge (rot bei mindestens einem
  Terminkonflikt an dem Tag) statt einer Zeitachse — ein Klick auf einen
  Tag springt direkt in dessen Tagesansicht.

Ein Klick auf einen bestehenden Termin öffnet ihn. **Kein Drag & Drop zum
Verschieben bestehender Termine** — bei einer Handvoll Technikern ist das
Öffnen und Ändern zweier Datumsfelder (was ohnehin dieselbe
Konfliktprüfung auslöst) genauso schnell, ohne den Mehraufwand für
Touch-Unterstützung und erneute Serverprüfung beim Ziehen eines
bestehenden Blocks. Aus demselben Grund keine FullCalendar-
Ressourcenansicht (mehrere Techniker als Spalten nebeneinander in einer
echten Kalenderbibliothek): die in diesem Frappe mitgelieferte
FullCalendar-Version enthält dafür kein Plugin — Ressourcenansichten sind
Teil von FullCalendars kommerziell lizenziertem Premium-Bundle.

## Fernarbeit

Ein Site Visit lässt sich als **Remote Visit** markieren (Haken `is_remote`)
— für Einsätze ohne physische Anwesenheit vor Ort. Was das für die
Unterschrift bedeutet, steuert **Site Visit Settings → Remote Visit Mode**:

- **Hide Signature**: die Felder "Customer Signature"/"Signee Name" werden
  im Formular ausgeblendet (`update_remote_ui` in `site_visit.js`) — für
  diesen Einsatz ist gar keine Unterschrift vorgesehen.
- **Send Signing Link to Customer** (Standard): Knopf **"Send Signing
  Link"** im Formular verschickt eine E-Mail mit einem öffentlichen,
  nicht angemeldeten Link an die im Kundendatensatz hinterlegte
  E-Mail-Adresse (`site_visit/remote_signature.py`). Unter dem Link kann
  der Kunde ohne eigenen Login unterschreiben (`www/site-visit-sign.html`,
  Signatur per Finger/Maus auf einem HTML-Canvas) — das speichert
  `customer_signature`/`signee_name` genau wie eine Unterschrift direkt im
  Formular, **bucht den Site Visit aber nicht**. Das Buchen bleibt weiterhin
  Sache des Technikers.

Der Link ist über ein zufälliges, langes Token abgesichert
(`remote_signature_token`, im Formular versteckt) und **30 Tage** ab dem
Versand gültig (`remote_signature_sent_at`); danach oder nach einer bereits
gespeicherten Unterschrift lehnt der Link weitere Versuche ab.

**Site Visit Settings → Signature Required**: ist dieser Haken gesetzt, blockt
`before_submit` das Buchen ohne gesetzte `customer_signature` — außer bei
einem Remote Visit im Modus "Hide Signature", wo gar keine Unterschrift
vorgesehen ist (`_validate_signature` in `site_visit/site_visit.py`).

## Automatische PDF-Erzeugung beim Buchen

Die App liefert ein eigenes, gestaltetes Print Format **"Site Visit Report"**
mit (Kopfbereich, Kundendaten, Fotogalerie, Pausenübersicht,
Unterschriftsblock) und setzt es als Standard-Druckformat für "Site Visit".
Das alleine erzeugt aber noch keine automatische PDF-Anlage beim Buchen –
dafür braucht es einen PDF-Automatisierungsmechanismus wie die App
[`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit) (bewusst
keine harte Abhängigkeit, `fieldservice` funktioniert auch ohne).

Ist `pdf_on_submit` zum Zeitpunkt der Installation bereits vorhanden, trägt
`install.py` automatisch die Zeile `Site Visit` / `Site Visit Report` in
dessen **PDF on Submit Settings** ein – kein manueller Schritt nötig. Wird
`pdf_on_submit` erst später installiert, einmalig von Hand nachtragen (die
gleiche Zeile in *Enabled For*) oder `bench execute
fieldservice.install.after_install` erneut laufen lassen.

`hooks.py` patcht zusätzlich `pdf_on_submit.attach_pdf.get_pdf_data()`,
damit die automatische PDF-Erzeugung über `frappe.get_print(...,
pdf_generator="chrome")` läuft statt über deren eigenen, direkten
wkhtmltopdf-Aufruf – auf Servern, auf denen wkhtmltopdf grundsätzlich
fehlschlägt (siehe `force_chrome_pdf` in `site_visit/site_visit.py`), würde
die automatische PDF-Anlage sonst im Hintergrund lautlos scheitern. Der
Patch greift nur, wenn `pdf_on_submit` tatsächlich installiert ist
(`try`/`except ImportError`), und liegt in `fieldservice/__init__.py` (siehe
Kommentar dort für die Begründung).

Ohne `pdf_on_submit` (oder eine ähnliche App) bleibt das Print Format
manuell nutzbar (Drucken/PDF-Button im Formular), nur eben nicht
automatisch.

## Berechtigungen

**Site Visit:**

| Rolle | Lesen | Schreiben | Anlegen | Buchen | Stornieren |
|---|---|---|---|---|---|
| System Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Projects Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee | eigene | eigene | ✓ | eigene | – |
| Projects User | ✓ | – | – | – | – |
| Accounts User | ✓ | – | – | – | – |

Ein gebuchter, unterschriebener Einsatz gilt als Bestätigung gegenüber dem
Kunden – nur Projects Manager/System Manager können ihn stornieren, nicht
der Techniker selbst. Es gibt bewusst keine eigene, engere Techniker-Rolle
als Fixture (Rollen sind nicht modulgebunden und würden beim Deinstallieren
als Karteileiche zurückbleiben); wer den Zugriff über die Standardrolle
"Employee" hinaus einschränken will, legt manuell eine eigene Rolle an.

**Zeit Projekt Einstellungen:** System Manager (voller Zugriff), Accounts
User/Accounts Manager/Projects User (nur lesen).

---

## Erweiterungsideen

- **Externes USB/Bluetooth-Signaturpad** (z. B. Wacom STU) statt Finger/Stift
  auf dem Touch-Bildschirm für die Kundenunterschrift bei Site Visit. Das
  Feld `customer_signature` speichert am Ende nur ein Bild – ein
  Hardware-Pad müsste nur dasselbe Feld befüllen (über Hersteller-SDK/
  Treiber im Browser), kein Umbau des Datenmodells nötig.
- Automatisches Zusammenfassen mehrerer Site Visits desselben Mitarbeiters
  zu einem Timesheet pro Zeitraum, statt eines neuen Timesheets je Einsatz.
- Automatisches Zusammenfassen mehrerer Pausen desselben Grundes im
  Einsatzbericht (aktuell wird jede einzeln aufgeführt).
- GPS/Standort-Erfassung beim Anlegen eines Site Visit.
- Direkte Rechnungs-/Angebotserstellung aus dem Site Visit heraus – aktuell
  läuft die Rechnungsstellung über den separaten Zeiterfassungs-Import in
  der Ausgangsrechnung.
- Custom Fields, die du später über die Oberfläche anlegst, gehören nicht
  automatisch der App. Trage sie in `CUSTOM_FIELDS` in `install.py` nach,
  dann werden sie beim Deinstallieren mitentfernt.
- Für Property Setter (geänderte Feldeigenschaften am Standard) gilt
  dasselbe: entweder im `after_install` erzeugen oder als Fixture
  exportieren und dabei das passende Modul setzen.
- **Offen:** automatisches Anpassen der Dienstleistungs-Positionsmenge im
  verknüpften Auftrag anhand der tatsächlich gearbeiteten Zeit eines Site
  Visit (zusätzlich zum bereits vorhandenen Übernehmen der `extra_items`).
  Noch zu klären: ob die Auftragsmenge dabei je Einsatz **addiert** oder auf
  die kumulierte Ist-Zeit **gesetzt** wird, und wie das mit dem separaten
  Rechnungsimport (Timesheet → Rechnungsposition) zusammenspielt, ohne
  Stunden doppelt zu zählen.
- **Zurückgestellt:** Offline-Fähigkeit (Timer/Fotos/Unterschrift auch ohne
  Netzverbindung nutzbar, mit Synchronisierung sobald wieder online). Kein
  Standard-Frappe-Verhalten (Desk-Oberfläche braucht durchgehend eine
  Verbindung) - würde eine eigene Service-Worker-/Offline-Queue-Architektur
  erfordern. Bewusst zurückgestellt, um zuerst Kilometer-Abrechnung und
  Terminplanung umzusetzen.
- Office-365/Outlook-Synchronisierung für die Terminplanung (siehe
  "Terminplanung" oben) - `scheduled_start`/`scheduled_end` sind als
  Andockpunkt für einen künftigen Sync-Job über die Microsoft-Graph-API
  gedacht, aber noch nicht angebunden.
