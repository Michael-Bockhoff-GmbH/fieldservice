import json

import click
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# ---------------------------------------------------------------------------
# Zeit Projekt: Custom Fields
#
# "module" ist wichtig: Damit gehoeren die Felder der App und wuerden selbst
# dann beim Deinstallieren geloescht, wenn before_uninstall nicht liefe.
# ---------------------------------------------------------------------------
ZEIT_PROJEKT_MODULE = "Zeit Projekt"

CUSTOM_FIELDS = {
	"Activity Type": [
		{
			"fieldname": "custom_dienstleistungsartikel",
			"label": "Dienstleistungsartikel",
			"fieldtype": "Link",
			"options": "Item",
			"insert_after": "billing_rate",
			"description": "Artikel, der bei der Rechnungsstellung fuer diese Aktivitaetsart verwendet wird",
			"module": ZEIT_PROJEKT_MODULE,
		},
		{
			"fieldname": "custom_rechnungstext",
			"label": "Bezeichnung für Rechnung",
			"fieldtype": "Data",
			"insert_after": "custom_dienstleistungsartikel",
			"description": "Optional: Text, der in der Rechnungsposition statt der Aktivitaetsart erscheint",
			"module": ZEIT_PROJEKT_MODULE,
		},
	],
	"Sales Order": [
		{
			"fieldname": "custom_projekt_erstellen",
			"label": "Projekt für diesen Auftrag erstellen",
			"fieldtype": "Check",
			"insert_after": "customer_name",
			"description": "Das Projekt wird angelegt und verknuepft, sobald der Auftrag bestaetigt (gebucht) wird",
			"module": ZEIT_PROJEKT_MODULE,
		},
	],
	# Traegt den Auftrag mit an die einzelne Zeitblatt-Zeile, statt nur ans
	# Projekt (Kern-Feld "project") - noetig, damit sich Zeiten beim
	# Rechnungsimport nach Auftrag filtern lassen und die Rechnungsposition
	# den Auftrag verknuepfen kann, auch wenn ein Projekt mehrere Auftraege
	# hat. Wird von site_visit/site_visit.py beim Anlegen des Timesheets
	# gesetzt (siehe _get_work_segments/before_submit dort) und von
	# zeit_projekt/timesheet_import.py gelesen.
	# Markiert die Auftragszeile, die die Zeitzuordnung (site_visit/
	# time_assignment.py) fuer eine Dienstleistung verwaltet - pro Auftrag und
	# Artikel hoechstens eine. So lassen sich diese Zeilen von Hand angelegten
	# und von den Site-Visit-Zeit-Positionen (time_sales_order_item) trennen.
	"Sales Order Item": [
		{
			"fieldname": "custom_fs_assigned_time",
			"label": "Time from Time Assignment",
			"fieldtype": "Check",
			"insert_after": "item_code",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"module": ZEIT_PROJEKT_MODULE,
		},
	],
	"Timesheet Detail": [
		{
			"fieldname": "custom_sales_order",
			"label": "Sales Order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"insert_after": "project",
			"module": ZEIT_PROJEKT_MODULE,
		},
	],
}

# Client Scripts aus der manuellen Einrichtung. Werden bei der Installation
# deaktiviert, damit die Funktionen nicht doppelt laufen (zwei Knoepfe).
ALTE_CLIENT_SCRIPTS = [
	"Zeiterfassung als Einzelpositionen",
	"Auftrag: Projekt erstellen",
	"Auftrag: Kommission und Projekt",
]

# ---------------------------------------------------------------------------
# Site Visit: optionale Kopplung an pdf_on_submit
# ---------------------------------------------------------------------------
SITE_VISIT_DOCTYPE = "Site Visit"
SITE_VISIT_PRINT_FORMAT = "Site Visit Report"

# ---------------------------------------------------------------------------
# Verknuepfungen auf ERPNexts Standard-"Home"-Workspace
#
# Zusaetzlich zur eigenen App-Kachel (add_to_apps_screen in hooks.py) sollen
# Site Visit/Zeit Projekt auch gleich auf der Startseite auffindbar sein,
# ohne extra ueber die Apps-Uebersicht zu gehen. label ist zugleich der
# eindeutige Schluessel, ueber den before_uninstall die hier ergaenzten
# Shortcuts wiederfindet - bestehende Shortcuts/Karten auf Home bleiben
# unangetastet.
# ---------------------------------------------------------------------------
HOME_WORKSPACE = "Home"
HOME_SHORTCUTS = [
	{"label": "Site Visit", "type": "DocType", "link_to": "Site Visit", "doc_view": "List", "color": "Blue"},
	{"label": "Timesheet", "type": "DocType", "link_to": "Timesheet", "doc_view": "List", "color": "Orange"},
	{"label": "Zeit Projekt Einstellungen", "type": "DocType", "link_to": "Zeit Projekt Einstellungen", "color": "Green"},
	{"label": "Dispatch Board", "type": "Page", "link_to": "dispatch-board", "color": "Purple"},
	{"label": "Time Assignment", "type": "Page", "link_to": "time-assignment", "color": "Cyan"},
]

# ---------------------------------------------------------------------------
# Verknuepfungen auf der eigenen "Site Visits"-Workspace
#
# Zusaetzlich zur bereits per JSON-Fixture ausgelieferten Karte (site_visit/
# workspace/site_visits/site_visits.json) - direkt per Python statt allein
# ueber die JSON-Datei, da Frappes Fixture-Sync bestehende Workspace-
# Datensaetze auf bereits installierten Benches nicht zuverlaessig neu
# einliest (frueher schon bei einer Sidebar-Bereinigung in dieser App
# beobachtet). Muss nach dem Schema-Sync laufen (post_model_sync-Patch),
# da "dispatch-board" (Page) vorher noch nicht existiert.
# ---------------------------------------------------------------------------
SITE_VISITS_WORKSPACE = "Site Visits"
SITE_VISITS_WORKSPACE_LINKS = [
	{"label": "Calendar", "link_type": "DocType", "link_to": "Site Visit", "doc_view": "Calendar"},
	{"label": "Dispatch Board", "link_type": "Page", "link_to": "dispatch-board"},
	{"label": "Time Assignment", "link_type": "Page", "link_to": "time-assignment"},
]

# ---------------------------------------------------------------------------
# Customer Reference (Sales Order.po_no) verpflichtend machen
#
# Gilt fuer JEDEN Auftrag in ERPNext, nicht nur fuer ueber Site Visit
# automatisch angelegte - eine bewusste Geschaeftsentscheidung, siehe
# README.md "Auftrag". Ueber eine Property Setter statt eines Custom
# Field, da po_no bereits ein Kernfeld von Sales Order ist - hier wird nur
# dessen "reqd"-Eigenschaft veraendert.
# ---------------------------------------------------------------------------


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	_deaktiviere_alte_client_scripts()
	click.secho("Zeit & Projekt: Felder angelegt.", fg="green")

	_pdf_on_submit_enable()
	_home_workspace_enable()
	_site_visits_workspace_links_enable()
	_po_no_required_enable()


def before_uninstall():
	# Kein frappe.db.commit() hier: bench haengt diesen Hook in seine eigene
	# Transaktion um `uninstall-app` ein. Ein eigener commit() wuerde die
	# Loeschung sofort fest schreiben - auch bei `--dry-run`, das sich sonst
	# auf ein Rollback am Ende verlaesst (beobachtet am 12.09.2026: drei
	# Felder blieben nach einem Dry-Run tatsaechlich geloescht).
	geloescht = 0
	for doctype, felder in CUSTOM_FIELDS.items():
		for feld in felder:
			name = f"{doctype}-{feld['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
				geloescht += 1

	click.secho(
		f"Zeit & Projekt: {geloescht} Felder entfernt. "
		"Hinweis: Die darin gepflegten Werte (z. B. die Artikelzuordnung je "
		"Aktivitaetsart) sind damit geloescht. Bereits angelegte Projekte und "
		"gebuchte Rechnungen bleiben unveraendert bestehen.",
		fg="yellow",
	)

	_pdf_on_submit_disable()
	_home_workspace_disable()
	_po_no_required_disable()


def _deaktiviere_alte_client_scripts():
	for name in ALTE_CLIENT_SCRIPTS:
		if frappe.db.exists("Client Script", name):
			frappe.db.set_value("Client Script", name, "enabled", 0)
			click.secho(
				f"Zeit & Projekt: Client Script '{name}' deaktiviert "
				"(Funktion kommt jetzt aus der App). Loeschen kannst du es selbst.",
				fg="yellow",
			)


def _pdf_on_submit_enable():
	"""Traegt Site Visit automatisch in PDF on Submit Settings ein, damit
	beim Buchen automatisch ein PDF am Einsatz haengt - nur falls die
	optionale App pdf_on_submit ueberhaupt installiert ist (siehe
	README.md "Automatische PDF-Erzeugung")."""
	if "pdf_on_submit" not in frappe.get_installed_apps():
		return

	settings = frappe.get_single("PDF on Submit Settings")
	if any(row.document_type == SITE_VISIT_DOCTYPE for row in settings.enabled_for):
		return

	settings.append("enabled_for", {"document_type": SITE_VISIT_DOCTYPE, "print_format": SITE_VISIT_PRINT_FORMAT})
	settings.save(ignore_permissions=True)
	click.secho(
		f"Site Visit: in PDF on Submit Settings eingetragen "
		f"({SITE_VISIT_DOCTYPE} / {SITE_VISIT_PRINT_FORMAT}).",
		fg="green",
	)


def _pdf_on_submit_disable():
	if "pdf_on_submit" not in frappe.get_installed_apps():
		return
	if not frappe.db.exists("DocType", "PDF on Submit Settings"):
		return

	settings = frappe.get_single("PDF on Submit Settings")
	remaining = [row for row in settings.enabled_for if row.document_type != SITE_VISIT_DOCTYPE]
	if len(remaining) == len(settings.enabled_for):
		return

	settings.enabled_for = []
	for row in remaining:
		settings.append("enabled_for", row)
	settings.save(ignore_permissions=True)
	click.secho("Site Visit: Eintrag in PDF on Submit Settings entfernt.", fg="yellow")


def _home_workspace_enable():
	"""Ergaenzt HOME_SHORTCUTS auf der "Home"-Workspace - rein additiv, damit
	Site Visit/Zeit Projekt gleich auf der Startseite auffindbar sind, ohne
	die bestehenden Shortcuts/Karten dort zu veraendern. Ueberspringt bereits
	vorhandene Eintraege (z. B. bei einer erneuten Installation)."""
	if not frappe.db.exists("Workspace", HOME_WORKSPACE):
		return

	home = frappe.get_doc("Workspace", HOME_WORKSPACE)
	existing_labels = {row.label for row in home.shortcuts}
	neu = [shortcut for shortcut in HOME_SHORTCUTS if shortcut["label"] not in existing_labels]
	if not neu:
		return

	for shortcut in neu:
		home.append("shortcuts", shortcut)

	content = json.loads(home.content)
	# Neue Shortcut-Bloecke direkt nach dem letzten bestehenden einfuegen,
	# damit sie in derselben Zeile wie "Item"/"Customer"/... erscheinen,
	# statt irgendwo anders auf der Seite aufzutauchen.
	insert_at = next((i for i in range(len(content) - 1, -1, -1) if content[i].get("type") == "shortcut"), -1) + 1
	for shortcut in neu:
		content.insert(
			insert_at,
			{"id": frappe.generate_hash(length=10), "type": "shortcut", "data": {"shortcut_name": shortcut["label"], "col": 3}},
		)
		insert_at += 1
	home.content = json.dumps(content)

	home.save(ignore_permissions=True)
	click.secho(
		f"IT Support mit Außendienst: {len(neu)} Verknuepfung(en) auf der Home-Seite ergaenzt "
		f"({', '.join(s['label'] for s in neu)}).",
		fg="green",
	)


def _home_workspace_disable():
	"""Entfernt genau die in HOME_SHORTCUTS gelisteten Eintraege wieder von
	Home - alles andere auf der Seite bleibt unangetastet."""
	if not frappe.db.exists("Workspace", HOME_WORKSPACE):
		return

	home = frappe.get_doc("Workspace", HOME_WORKSPACE)
	unsere_labels = {shortcut["label"] for shortcut in HOME_SHORTCUTS}
	verbleibend = [row for row in home.shortcuts if row.label not in unsere_labels]
	if len(verbleibend) == len(home.shortcuts):
		return

	home.shortcuts = []
	for row in verbleibend:
		home.append("shortcuts", row)

	content = json.loads(home.content)
	content = [
		block
		for block in content
		if not (block.get("type") == "shortcut" and block.get("data", {}).get("shortcut_name") in unsere_labels)
	]
	home.content = json.dumps(content)

	home.save(ignore_permissions=True)
	click.secho("IT Support mit Außendienst: Verknuepfungen von der Home-Seite entfernt.", fg="yellow")


def _site_visits_workspace_links_enable():
	"""Ergaenzt SITE_VISITS_WORKSPACE_LINKS auf der eigenen "Site Visits"-
	Workspace - ueberspringt bereits vorhandene Eintraege. Kein Gegenstueck
	fuer before_uninstall noetig: die ganze Workspace gehoert dieser App
	(eigenes Modul "Site Visit") und verschwindet beim Deinstallieren
	ohnehin komplett, anders als die gemeinsam genutzte "Home"-Workspace."""
	if not frappe.db.exists("Workspace", SITE_VISITS_WORKSPACE):
		return

	ws = frappe.get_doc("Workspace", SITE_VISITS_WORKSPACE)
	existing_labels = {row.label for row in ws.links}
	neu = [link for link in SITE_VISITS_WORKSPACE_LINKS if link["label"] not in existing_labels]
	if not neu:
		return

	for link in neu:
		ws.append(
			"links",
			{
				"type": "Link",
				"link_type": link["link_type"],
				"link_to": link["link_to"],
				"label": link["label"],
				"doc_view": link.get("doc_view", ""),
				"color": "Grey",
			},
		)
	ws.save(ignore_permissions=True)
	click.secho(
		f"IT Support mit Außendienst: {len(neu)} Verknuepfung(en) auf der Site-Visits-Workspace ergaenzt "
		f"({', '.join(link['label'] for link in neu)}).",
		fg="green",
	)


def _po_no_required_enable():
	"""Macht "Customer Reference" (Sales Order.po_no) fuer jeden Auftrag in
	ERPNext verpflichtend - ueberspringt, falls dafuer bereits irgendeine
	Property Setter existiert (eigene von einer frueheren Installation,
	oder eine manuell ueber "Customize Form" angelegte)."""
	if frappe.db.exists("Property Setter", {"doc_type": "Sales Order", "field_name": "po_no", "property": "reqd"}):
		return

	frappe.make_property_setter(
		{"doctype": "Sales Order", "fieldname": "po_no", "property": "reqd", "value": "1", "property_type": "Check"},
		module=ZEIT_PROJEKT_MODULE,
	)
	click.secho("Zeit & Projekt: Customer Reference (po_no) ist jetzt fuer jeden Auftrag Pflicht.", fg="green")


def _po_no_required_disable():
	name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Sales Order", "field_name": "po_no", "property": "reqd", "module": ZEIT_PROJEKT_MODULE},
	)
	if not name:
		return

	frappe.delete_doc("Property Setter", name, ignore_missing=True)
	click.secho("Zeit & Projekt: Customer Reference (po_no) ist wieder optional.", fg="yellow")
