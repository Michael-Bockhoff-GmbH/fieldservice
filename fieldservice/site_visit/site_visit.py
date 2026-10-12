import copy
from contextlib import contextmanager

import frappe
from erpnext.projects.doctype.timesheet.timesheet import OverlapError
from frappe import _
from frappe.utils import get_datetime


@contextmanager
def _as_administrator():
	"""Fuehrt den with-Block als Administrator aus - fuer Sales-Order-Schritte,
	auf die der Techniker (Employee) i. d. R. keine eigenen Rechte hat. Die
	eigentliche Berechtigungspruefung ist die auf den Site Visit selbst.

	frappe.set_user() leert lokal u. a. local.form_dict komplett - ohne
	Sicherung wuerde das den umgebenden Request (z. B. das Buchen des Site
	Visit selbst, das nach diesem Hook weiterlaeuft) seiner eigenen Parameter
	berauben. Deshalb hier explizit gesichert und danach wiederhergestellt."""
	current_user = frappe.session.user
	form_dict_backup = copy.deepcopy(frappe.local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(current_user)
		frappe.local.form_dict = form_dict_backup


def _linked_timesheet_is_submitted(timesheet):
	"""Nur docstatus=1 zaehlt als gueltig verknuepft. Der eigentliche Schutz
	gegen ein stornogeloeschtes Timesheet ist das db_set("timesheet", None)
	in on_cancel() unten - diese Pruefung hier ist nur ein zusaetzliches
	Netz fuer den Fall, dass ein verknuepftes Timesheet auf einem anderen
	Weg als ueber die Stornierung dieses Site Visit storniert wurde (z. B.
	direkt am Timesheet), waehrend doc.timesheet noch darauf zeigt."""
	return frappe.db.get_value("Timesheet", timesheet, "docstatus") == 1


def before_submit(doc, method=None):
	"""Legt ein Timesheet an, bucht es und verknuepft es - im selben Request
	wie das Buchen des Site Visit selbst. Serverseitig, damit kein zweiter
	Request und damit kein Zeitfenster fuer "has been modified after you have
	opened it" entsteht (gleiche Begruendung wie
	fieldservice.zeit_projekt.sales_order.before_submit).

	activity_type/from_time/to_time sind absichtlich nicht reqd im Feld (siehe
	site_visit.json): ein Entwurf mit nur laufendem Timer (from_time gesetzt,
	"Start Timer" speichert sofort, siehe site_visit.js) oder eine reine
	Vorausplanung (scheduled_start/scheduled_end) waere sonst gar nicht
	speicherbar. Deshalb hier explizit vor dem Buchen geprueft.

	Kunde, Projekt und Auftrag sind beim Buchen optional: wer die Zeit zuerst
	erfasst und erst danach zuordnen will, bucht ohne alles davon (ein Kunde
	ist nur noetig, sobald Projekt, Auftrag oder "Create Sales Order" im Spiel ist) - das Timesheet entsteht
	dann ohne Auftrag/Projekt und wird spaeter ueber die Seite "Time
	Assignment" (time_assignment.py) einem Auftrag zugeordnet. Ist ein
	Projekt gewaehlt, braucht es dagegen weiterhin einen Auftrag (vorhanden
	oder per "Create Sales Order" automatisch angelegt, siehe
	_create_sales_order). Zusatzartikel und Kilometer lassen sich nur ueber
	einen Auftrag abrechnen und brauchen ihn daher immer."""
	if doc.timesheet and _linked_timesheet_is_submitted(doc.timesheet):
		return

	if not doc.customer and (doc.project or doc.sales_order or doc.create_sales_order):
		frappe.throw(_("Please select a Customer before submitting."))
	if not doc.activity_type:
		frappe.throw(_("Please select an Activity Type before submitting."))

	has_order = bool(doc.sales_order or doc.create_sales_order)
	if doc.project and not has_order:
		frappe.throw(_('Please select a Sales Order, or check "Create Sales Order", before submitting.'))
	if not has_order and ([row for row in doc.extra_items if not row.added_to_order] or _mileage_billable(doc)):
		frappe.throw(
			_("Additional items and mileage can only be billed through a Sales Order - please select one first.")
		)
	if not doc.from_time:
		frappe.throw(_("Please enter a start time before submitting."))
	if not doc.to_time:
		frappe.throw(_("Please enter an end time before submitting."))

	if get_datetime(doc.to_time) <= get_datetime(doc.from_time):
		frappe.throw(_("End time must be after the start time."))

	_validate_signature(doc)

	segments = _get_work_segments(doc)

	if not doc.sales_order and doc.create_sales_order:
		_create_sales_order(doc, segments)

	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": doc.employee,
			"company": doc.company,
			"time_logs": [
				{
					"activity_type": doc.activity_type,
					"from_time": segment_from,
					"to_time": segment_to,
					"project": doc.project or None,
					"description": doc.description or doc.name,
					"is_billable": 1,
					"custom_sales_order": doc.sales_order,
				}
				for segment_from, segment_to in segments
			],
		}
	)
	ts.insert()
	try:
		ts.submit()
	except OverlapError:
		# doc.employee ist nicht mehr Pflicht - ist es leer, prueft ERPNexts
		# Timesheet.validate_overlap() stattdessen ueber den Nutzer (self.user,
		# von Frappe immer gesetzt), siehe validate_overlap_for() in
		# erpnext/projects/doctype/timesheet/timesheet.py.
		frappe.throw(
			_("This time range overlaps an existing time entry for {0}.").format(doc.employee or frappe.session.user),
			title=_("Overlapping Time"),
		)

	doc.timesheet = ts.name
	frappe.msgprint(
		_("Timesheet {0} created and submitted.").format(f"<b>{ts.name}</b>"),
		indicator="green",
		alert=True,
	)

	if doc.sales_order:
		_sync_sales_order(doc, segments)


def _validate_signature(doc):
	"""Site Visit Settings -> "Signature Required": ein Fernbesuch im Modus
	"Unterschrift ausblenden" ist davon ausgenommen, da dort gar keine
	Unterschrift vorgesehen ist (siehe Site Visit Settings -> Remote Visit
	Mode). Alle anderen Faelle (vor Ort oder Fernbesuch mit Signierlink)
	brauchen bei aktivierter Einstellung eine gesetzte customer_signature -
	ob die per Finger im Formular oder per Fernlink (remote_signature.
	submit_remote_signature) zustande kam, spielt dafuer keine Rolle."""
	settings = frappe.get_cached_doc("Site Visit Settings")
	if not settings.signature_required:
		return

	if doc.is_remote and settings.remote_mode == "Hide Signature":
		return

	if not doc.customer_signature:
		frappe.throw(_("Please capture the customer's signature before submitting."))


def _intervals_overlap(a_start, a_end, b_start, b_end):
	"""Exklusive Intervallgrenzen - ein Termin, der genau dort endet, wo der
	naechste beginnt, gilt nicht als Konflikt (z. B. 10-11 Uhr gefolgt von
	11-12 Uhr fuer denselben Techniker)."""
	return get_datetime(a_start) < get_datetime(b_end) and get_datetime(b_start) < get_datetime(a_end)


def _find_conflicts(employee, scheduled_start, scheduled_end, exclude_name=None):
	"""Andere Site Visits desselben Mitarbeiters, deren geplantes Zeitfenster
	sich mit dem uebergebenen ueberschneidet - fuer die Terminkonflikt-Warnung
	(warn_schedule_conflicts unten, check_schedule_conflict fuer das Formular,
	dispatch_board.py fuer den Einsatzplan). Ohne Mitarbeiter oder ohne
	vollstaendiges Zeitfenster gibt es nichts zu pruefen. docstatus != 2:
	stornierte Termine blockieren keinen Slot mehr."""
	if not employee or not scheduled_start or not scheduled_end:
		return []
	return frappe.get_all(
		"Site Visit",
		filters={
			"employee": employee,
			"name": ["!=", exclude_name or ""],
			"docstatus": ["!=", 2],
			"scheduled_start": ["<", scheduled_end],
			"scheduled_end": [">", scheduled_start],
		},
		fields=["name", "customer_name", "scheduled_start", "scheduled_end"],
		order_by="scheduled_start",
	)


def warn_schedule_conflicts(doc):
	"""validate()-Hook (siehe doctype/site_visit/site_visit.py): warnt, blockiert
	aber nicht - der Dispatcher soll bewusst gegensteuern koennen, z. B. bei
	einem kurzen Telefontermin parallel zu einem laufenden Vor-Ort-Einsatz."""
	conflicts = _find_conflicts(doc.employee, doc.scheduled_start, doc.scheduled_end, exclude_name=doc.name)
	if not conflicts:
		return

	from frappe.utils import format_datetime

	lines = "".join(
		f"<li>{c.name} - {c.customer_name or ''} "
		f"({format_datetime(c.scheduled_start)} - {format_datetime(c.scheduled_end)})</li>"
		for c in conflicts
	)
	frappe.msgprint(
		_("This schedule overlaps {0} existing visit(s) for {1}:<ul>{2}</ul>").format(
			len(conflicts), doc.employee, lines
		),
		title=_("Scheduling Conflict"),
		indicator="orange",
	)


@frappe.whitelist()
def check_schedule_conflict(employee, scheduled_start, scheduled_end, name=None):
	"""Client-seitiger Vorab-Check (site_visit.js) - dieselbe Abfrage wie
	warn_schedule_conflicts() oben, nur als reine Anzahl statt der vollen
	Datensaetze: _find_conflicts nutzt frappe.get_all (keine Berechtigungs-
	pruefung, absichtlich, da ein Dispatcher/Techniker die Auslastung ANDERER
	Mitarbeiter sehen koennen muss, um ueberhaupt einen Konflikt zu erkennen).
	Diese Methode ist aber fuer jeden angemeldeten Nutzer frei aufrufbar, mit
	beliebigem employee/Zeitraum - anders als warn_schedule_conflicts() (nur
	als Nebeneffekt des tatsaechlichen Speicherns eines echten, konfliktenden
	Dokuments ausgeloest) waere die volle Konfliktliste hier ein bequemer Weg
	fuer z. B. einen Techniker mit reinem if_owner-Zugriff, sich Kundennamen
	und Termine anderer Mitarbeiter zusammenzusuchen, auf die er sonst keinen
	Lesezugriff haette. Der Formular-Hinweis (site_visit.js) braucht ohnehin
	nur die Anzahl."""
	return len(_find_conflicts(employee, scheduled_start, scheduled_end, exclude_name=name))


def _get_work_segments(doc):
	"""Zerlegt [from_time, to_time] anhand von doc.breaks in die tatsaechlich
	gearbeiteten Zeitfenster - eines pro Segment zwischen zwei Pausen (bzw.
	Start/Ende) statt eines einzigen durchgehenden Blocks. Pausen (Kaffee-
	pause, Notfall bei einem anderen Kunden, ...) werden so weder abgerechnet
	noch als "gearbeitet" ins Timesheet uebernommen - und ueberschneiden sich
	dadurch nicht mit einem Timesheet-Eintrag, den derselbe Mitarbeiter waehrend
	der Pause fuer einen anderen Site Visit anlegt (sonst wuerde ts.submit()
	unten mit OverlapError scheitern).

	Nur beim Buchen aufgerufen, deshalb wird hier zugleich geprueft, dass
	keine Pause noch laeuft und dass alle Pausen tatsaechlich innerhalb von
	[from_time, to_time] liegen - beides sollte durch "Pause Timer"/
	"Resume Timer" in site_visit.js ohnehin nie vorkommen, ist aber bei
	manueller Bearbeitung der Kindtabelle oder einem Import moeglich."""
	from_time = get_datetime(doc.from_time)
	to_time = get_datetime(doc.to_time)
	breaks = sorted(doc.breaks or [], key=lambda row: get_datetime(row.from_time))

	segments = []
	cursor = from_time
	for row in breaks:
		break_from = get_datetime(row.from_time)
		break_to = get_datetime(row.to_time) if row.to_time else None

		if not break_to:
			frappe.throw(_("Please resume the timer before submitting."))
		if break_from < from_time or break_to > to_time:
			frappe.throw(_("A break must lie within the visit's start and end time."))
		if break_to <= break_from:
			frappe.throw(_("A break's end time must be after its start time."))
		if break_from < cursor:
			frappe.throw(_("Breaks must not overlap each other."))

		if break_from > cursor:
			segments.append((cursor, break_from))
		cursor = max(cursor, break_to or break_from)

	if cursor < to_time:
		segments.append((cursor, to_time))

	return segments


def _sync_sales_order(doc, segments):
	"""Gleicht den verknuepften Auftrag mit dem Site Visit ab: ungebuchte
	Zusatzartikel (Feld extra_items), die gearbeitete Zeit (Dienstleistungs-
	Position) und, falls berechnet, eine Fahrtkosten-Position - im selben
	Request wie das Buchen, aus demselben Grund wie die Timesheet-Erstellung
	oben. Bereits mit added_to_order=1 markierte Zusatzartikel-Zeilen wurden
	schon ueber _create_sales_order() unten in einen neu angelegten Auftrag
	aufgenommen und werden hier uebersprungen.

	Die Zeit-Position (time_sales_order_item) und die Fahrtkosten-Position
	(mileage_sales_order_item) werden ueber den gemerkten Zeilennamen
	gefunden: ein erneuter Lauf (z. B. nach einem Amend mit geaenderter
	Endzeit) aktualisiert die Menge statt eine zweite Zeile anzuhaengen. Bei
	einem vorhandenen Auftrag, den der Techniker beim Site Visit ausgewaehlt
	hat, kommt die Zeit so ebenfalls in den Auftrag - frueher entstand die
	Zeit-Position nur beim automatisch angelegten Auftrag.

	Nutzt erpnext.controllers.accounts_controller.update_child_qty_rate -
	dieselbe Funktion, die auch der "Update Items"-Dialog im Auftrag selbst
	verwendet - statt den Auftrag hier von Hand zu veraendern: das uebernimmt
	auch bei bereits gebuchten Auftraegen korrekt Steuer-/Summenneuberechnung,
	Kreditlimitpruefung usw. Alle Positionsarten in einem Aufruf, damit der
	Auftrag dafuer nur einmal statt mehrfach hintereinander gespeichert wird."""
	from erpnext.controllers.accounts_controller import update_child_qty_rate
	from frappe.utils import flt

	pending_items = [row for row in doc.extra_items if not row.added_to_order]

	so = frappe.get_doc("Sales Order", doc.sales_order)
	time_line = _get_time_line(doc, segments, so)
	mileage_line = _get_mileage_line(doc, so)
	if not pending_items and not time_line and not mileage_line:
		return

	trans_items = []
	for row in so.items:
		item = row.as_dict()
		item["docname"] = row.name
		if time_line and time_line.get("docname") == row.name:
			item["qty"] = time_line["qty"]
		trans_items.append(item)
	for row in pending_items:
		trans_items.append({"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "rate": row.rate})
	if time_line and "docname" not in time_line:
		trans_items.append(time_line)
	if mileage_line:
		trans_items.append(mileage_line)

	# update_child_qty_rate() verlangt fuer JEDE neue Auftragszeile ein Lager
	# (is_warehouse_required_for_new_child_item: bei Sales Order immer) - auch
	# fuer Dienstleistungs- und Fahrtkostenartikel, die meist kein
	# Standardlager haben. Fehlt eines, ein Ersatzlager einsetzen.
	for line in trans_items:
		if "docname" not in line and not line.get("warehouse"):
			line["warehouse"] = _fallback_warehouse(so, line["item_code"])

	# Namen vorher merken: update_child_qty_rate() gibt nichts zurueck und
	# aktualisiert das hier geladene `so` nicht - fuer neu angelegte Zeilen
	# (kein docname) ist das die einzige Moeglichkeit, ihre Zeilennamen
	# danach wiederzufinden (siehe unten).
	names_before = {row.name for row in so.items}

	with _as_administrator():
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)

	for row in pending_items:
		row.added_to_order = 1

	new_lines = {
		"time_sales_order_item": time_line if time_line and "docname" not in time_line else None,
		"mileage_sales_order_item": mileage_line if mileage_line and "docname" not in mileage_line else None,
	}
	if mileage_line and "docname" in mileage_line:
		doc.mileage_sales_order_item = mileage_line["docname"]
	if time_line and "docname" in time_line:
		doc.time_sales_order_item = time_line["docname"]

	if any(new_lines.values()):
		so.reload()
		fresh_rows = [row for row in so.items if row.name not in names_before]
		for fieldname, line in new_lines.items():
			if not line:
				continue
			match = next((row for row in fresh_rows if row.item_code == line["item_code"]), None)
			if match:
				doc.set(fieldname, match.name)
				fresh_rows.remove(match)


def _fallback_warehouse(so, item_code):
	"""Lager fuer eine neue Auftragszeile: Standardlager des Artikels bzw. der
	Artikelgruppe, sonst das Lager des Auftrags (set_warehouse oder einer
	vorhandenen Zeile), sonst Stock Settings, sonst irgendein Blattlager der
	Firma. None, wenn es gar keins gibt - dann meldet ERPNext selbst den
	fehlenden Wert."""
	from erpnext.stock.get_item_details import get_item_defaults, get_item_group_defaults

	return (
		get_item_defaults(item_code, so.company).get("default_warehouse")
		or get_item_group_defaults(item_code, so.company).get("default_warehouse")
		or so.get("set_warehouse")
		or next((row.warehouse for row in so.items if row.warehouse), None)
		or frappe.db.get_single_value("Stock Settings", "default_warehouse")
		or frappe.db.get_value("Warehouse", {"company": so.company, "is_group": 0, "disabled": 0}, "name")
	)


def _get_time_line(doc, segments, so):
	"""Zeit-Position (Dienstleistungsartikel der Aktivitaetsart x Stunden) fuer
	den verknuepften Auftrag, oder None, wenn nichts zu tun ist:
	- Aktivitaetsart ohne Dienstleistungsartikel: keine Zeit-Position (bei einem
	  vom Techniker gewaehlten Auftrag war das schon immer erlaubt - nur beim
	  automatisch angelegten Auftrag ist der Artikel Pflicht, siehe
	  _get_time_item)
	- vorhandene Zeile mit unveraenderter Menge: nichts zu aktualisieren
	Sonst ein Dict mit "docname" (Menge der bestehenden Zeile aktualisieren)
	oder ohne (neue Zeile anhaengen)."""
	from frappe.utils import flt

	if not frappe.get_cached_doc("Activity Type", doc.activity_type).custom_dienstleistungsartikel:
		return None

	line = _get_time_item(doc, segments)
	existing = next((row for row in so.items if row.name == doc.time_sales_order_item), None)
	if existing and existing.item_code == line["item_code"]:
		if flt(existing.qty) == flt(line["qty"]):
			return None
		return {**line, "docname": existing.name}
	return line


def _mileage_billable(doc):
	"""Ob ueberhaupt eine Fahrtkosten-Position in Frage kommt - siehe
	_get_mileage_line fuer die Bedingungen. Getrennt von dort, damit
	_sync_sales_order oben den Auftrag nicht unnoetig laedt, wenn weder
	Zusatzartikel noch Kilometer etwas zu tun haben."""
	if not doc.distance_km:
		return False
	settings = frappe.get_cached_doc("Site Visit Settings")
	if not settings.mileage_enabled:
		return False
	return bool(settings.mileage_item)


def _get_mileage_line(doc, so):
	"""Fahrtkosten-Position (Kilometer x Fahrtkosten-Artikel) fuer den
	verknuepften Auftrag - siehe _mileage_billable fuer die Bedingungen.
	Abgerechnet wird standardmaessig Hin- und Rueckweg (2x distance_km) -
	"One-Way Trip Only" am Site Visit rechnet nur die einfache Strecke ab,
	z. B. wenn der Techniker direkt zum naechsten Kunden weiterfaehrt.

	Der Preis kommt aus der Standard-Verkaufspreisliste des Auftrags
	(dieselbe Preisfindung, die auch beim normalen Hinzufuegen eines
	Artikels im Auftrag greift) - kein manuell eingetragener Satz wie bei
	den Zusatzartikeln oben, da hier niemand von Hand einen Preis eintraegt.
	Ohne ermittelbaren Preis wird abgebrochen statt mit rate=0 stillschweigend
	umsonst abzurechnen (analog zu _get_time_item oben).

	Traegt "docname" ein, wenn fuer diesen Site Visit schon eine Fahrtkosten-
	Zeile im Auftrag existiert (mileage_sales_order_item) - sonst wuerde ein
	erneuter Lauf von _sync_sales_order() (z. B. nach einem Amend, siehe
	before_submit) bei jedem Aufruf eine weitere Zeile anhaengen statt die
	bestehende zu aktualisieren."""
	if not _mileage_billable(doc):
		return None

	from erpnext.stock.get_item_details import get_item_price

	settings = frappe.get_cached_doc("Site Visit Settings")
	item = frappe.get_cached_doc("Item", settings.mileage_item)
	billed_km = doc.distance_km if doc.one_way_only else doc.distance_km * 2

	prices = get_item_price({"price_list": so.selling_price_list, "uom": item.stock_uom}, item.name)
	if not prices:
		frappe.throw(_("No price found for {0} - required to bill mileage.").format(item.name))

	line = {"item_code": item.name, "qty": billed_km, "rate": prices[0]["price_list_rate"], "uom": item.stock_uom}

	existing_row = next((row for row in so.items if row.name == doc.mileage_sales_order_item), None)
	if existing_row and existing_row.item_code == item.name:
		line["docname"] = existing_row.name

	return line


# Artikelgruppe der Dienstleistungsartikel: als Zusatzartikel nie waehlbar.
# Die gearbeitete Zeit wird ueber den Dienstleistungsartikel der Aktivitaetsart
# abgerechnet (_get_time_item) - ein Dienstleistungsartikel unter den
# Zusatzartikeln wuerde dieselbe Leistung ein zweites Mal berechnen. Fest im
# Code statt als Einstellung: so kann sie nicht versehentlich verloren gehen.
EXCLUDED_ITEM_GROUP = "Services"


def _excluded_item_groups():
	"""EXCLUDED_ITEM_GROUP samt aller Untergruppen (leer, falls es die Gruppe
	nicht gibt)."""
	from frappe.utils.nestedset import get_descendants_of

	if not frappe.db.exists("Item Group", EXCLUDED_ITEM_GROUP):
		return []
	return [EXCLUDED_ITEM_GROUP, *get_descendants_of("Item Group", EXCLUDED_ITEM_GROUP)]


def validate_extra_items(doc, method=None):
	"""Serverseitiges Gegenstueck zu item_query_extra_items: die Auswahl im
	Formular laesst sich per API/Import/Duplizieren umgehen. Nur Zeilen, die
	noch nicht in den Auftrag uebernommen wurden, werden geprueft - bereits
	abgerechnete Altzeilen bleiben unangetastet."""
	excluded = _excluded_item_groups()
	if not excluded:
		return
	for row in doc.extra_items:
		if row.added_to_order or not row.item_code:
			continue
		if frappe.db.get_value("Item", row.item_code, "item_group") in excluded:
			frappe.throw(
				_("Row {0}: {1} belongs to the Item Group {2} and cannot be added as an Additional Item.").format(
					row.idx, row.item_code, EXCLUDED_ITEM_GROUP
				)
			)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query_extra_items(doctype, txt, searchfield, start, page_len, filters):
	"""Link-Query fuer das Feld "Item" in der Zusatzartikel-Tabelle (siehe
	frm.set_query in site_visit.js): blendet die Dienstleistungsartikel
	(EXCLUDED_ITEM_GROUP inkl. Untergruppen) aus, damit vor Ort nicht
	versehentlich eine Dienstleistung statt benoetigten Materials erfasst und
	doppelt berechnet wird. Alles andere (Hardware, Verbrauchsmaterial, ...)
	bleibt waehlbar. Nutzt ERPNexts eigene item_query weiter (respektiert
	disabled/is_sales_item usw.), ergaenzt nur den Gruppenfilter."""
	from erpnext.controllers.queries import item_query

	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	excluded = _excluded_item_groups()
	if excluded:
		filters["item_group"] = ["not in", excluded]

	return item_query(doctype, txt, searchfield, start, page_len, filters)


def _create_sales_order(doc, segments):
	"""Legt automatisch einen neuen Auftrag an und verknuepft ihn (doc.
	sales_order), wenn "Create Sales Order" angehakt ist - statt wie zuvor
	ueber einen eigenen "New Sales Order"-Dialog im Formular, ausgeloest
	durch einen Klick des Technikers. Laesst den Auftrag als Entwurf -
	Buchen bleibt weiterhin Sache des Vertriebs.

	Uebernimmt dabei gleich zwei Arten von Positionen:
	- die gearbeitete Zeit (_get_time_item), als Dienstleistungsartikel der
	  Aktivitaetsart
	- alle noch nicht uebernommenen Zusatzartikel (extra_items) - dieselben
	  Zeilen, die _sync_sales_order() sonst nachtraeglich in einen bereits
	  vorhandenen Auftrag einpflegen wuerde. Hier stecken sie gleich im neu
	  angelegten Auftrag, deshalb werden sie unten sofort als
	  added_to_order markiert, damit _sync_sales_order() sie nicht ein
	  zweites Mal hinzufuegt."""
	pending = [row for row in doc.extra_items if not row.added_to_order]

	so = frappe.new_doc("Sales Order")
	so.customer = doc.customer
	so.company = doc.company
	so.project = doc.project or None
	so.po_no = doc.customer_reference
	# transaction_date = delivery_date = Einsatzdatum, nicht "heute": der
	# Auftrag entsteht ja erst nachtraeglich beim Buchen. Ohne
	# delivery_date lehnt ERPNext den Auftrag mit "Please enter Delivery
	# Date" ab (validate_delivery_date in sales_order.py); waere
	# delivery_date < transaction_date (Default "heute"), kaeme stattdessen
	# "Expected Delivery Date should be after Sales Order Date".
	so.transaction_date = doc.date
	so.delivery_date = doc.date
	so.append("items", _get_time_item(doc, segments))
	for row in pending:
		so.append("items", {"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "rate": row.rate})

	with _as_administrator():
		so.set_missing_values()
		so.insert()

	doc.sales_order = so.name
	# Zeit-Position ist die erste Zeile (siehe oben) - Name merken, damit
	# _sync_sales_order() sie bei geaenderter Zeit aktualisiert.
	doc.time_sales_order_item = so.items[0].name
	for row in pending:
		row.added_to_order = 1

	frappe.msgprint(
		_("Sales Order {0} created and linked.").format(f"<b>{so.name}</b>"),
		indicator="green",
		alert=True,
	)


def _get_time_item(doc, segments):
	"""Dienstleistungsartikel-Position fuer die gearbeitete Zeit (siehe
	_create_sales_order) - Menge in Stunden aus den bereits um Pausen
	bereinigten Arbeitsabschnitten (segments, siehe _get_work_segments)."""
	hours = sum((segment_to - segment_from).total_seconds() for segment_from, segment_to in segments) / 3600
	return _service_item_line(doc.activity_type, hours)


def _service_item_line(activity_type_name, hours):
	"""Dienstleistungsartikel-Zeile (Artikel der Aktivitaetsart x Stunden).
	Preisfindung wie beim Rechnungsimport in
	zeit_projekt/public/js/sales_invoice.js: zuerst der Verkaufspreis des
	Artikels, sonst der Standard-Stundensatz der Aktivitaetsart. Ohne
	konfigurierten Dienstleistungsartikel oder ohne ermittelbaren Preis
	wird abgebrochen, statt eine Position ohne (oder mit falschem) Preis
	anzulegen. Auch von der Zeitzuordnung (time_assignment.py) genutzt."""
	activity_type = frappe.get_cached_doc("Activity Type", activity_type_name)
	if not activity_type.custom_dienstleistungsartikel:
		frappe.throw(
			_(
				"Activity Type {0} has no Dienstleistungsartikel configured - required to create a "
				"Sales Order automatically."
			).format(activity_type_name)
		)

	item = frappe.get_cached_doc("Item", activity_type.custom_dienstleistungsartikel)
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")

	from erpnext.stock.get_item_details import get_item_price

	prices = get_item_price({"price_list": price_list, "uom": item.stock_uom}, item.name)
	rate = prices[0]["price_list_rate"] if prices else activity_type.billing_rate
	if not rate:
		frappe.throw(
			_("No price found for {0}, and Activity Type {1} has no Default Billing Rate set.").format(
				item.name, activity_type_name
			)
		)

	return {"item_code": item.name, "qty": round(hours, 2), "uom": item.stock_uom, "rate": rate}


def on_cancel(doc, method=None):
	"""Storniert das verknuepfte Timesheet mit, sofern es noch nicht
	fakturiert wurde.

	Loescht anschliessend doc.timesheet (per db_set, nicht per doc.timesheet
	= None + save - der Site Visit ist ja schon storniert): timesheet ist
	no_copy, bleibt also bei einem spaeteren Amend erhalten - zeigt es dann
	auf das hier gerade stornierte Timesheet, wirft Frappes eigene
	_validate_links() beim Speichern des amendeten Entwurfs sofort
	"Cannot link cancelled document", noch bevor before_submit ueberhaupt
	laeuft (bestaetigt gegen frappe/model/document.py: _validate_links()
	laeuft in insert()/save() VOR jedem eigenen Hook). Ohne diese Zeile waere
	ein Amend nach einer Stornierung also gar nicht erst speicherbar."""
	if not doc.timesheet:
		return

	ts = frappe.get_doc("Timesheet", doc.timesheet)
	if ts.docstatus != 1:
		return

	for row in ts.time_logs:
		if row.sales_invoice:
			frappe.throw(
				_("Timesheet {0} was already invoiced on {1} and can no longer be cancelled.").format(
					ts.name, row.sales_invoice
				)
			)

	ts.cancel()
	doc.db_set("timesheet", None)


def check_app_permission():
	"""Fuer add_to_apps_screen in hooks.py: wer die App-Kachel im Desk sehen darf."""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return any(role in roles for role in ("System Manager", "Projects Manager", "Employee"))


def force_chrome_pdf():
	"""Vor download_pdf/printview: erzwingt pdf_generator=chrome fuer alle
	Doctypes auf diesem Server.

	wkhtmltopdf (der Frappe-Standard) scheitert hier grundsaetzlich an jeder
	frisch gerenderten Druckvorlage - schon das von Frappe selbst
	eingebundene <link ...print.bundle...css> ist eine relative URL ohne
	Basis-Adresse, die wkhtmltopdf im from_string-Modus nicht aufloesen kann
	("ProtocolUnknownError"). Betroffen sind nicht nur Vorlagen mit Bildern:
	am 13.09.2026 reproduziert fuer Sales Order, Sales Invoice und Site
	Visit gleichermassen, per echtem HTTP-Request wie im Browser. Bereits
	vorhandene PDFs (z. B. an alten Rechnungen) stammen vermutlich noch aus
	der Frappe-Cloud-Migration und wurden nie auf diesem Server neu erzeugt
	- deshalb ist es vorher nicht aufgefallen.

	Normalerweise liest die App print_designer das pdf_generator-Feld des
	Print Format aus und setzt es genau so vor dem eigentlichen Request -
	print_designer ist auf diesem Server aber bewusst nicht installiert
	(kein version-16-Branch, Stabilitaetsbedenken laut INSTALL-APPS.md).
	Statt der riskanten App nur den konkret benoetigten Mechanismus selbst
	nachgebaut - hier bewusst ohne Doctype-Einschraenkung, weil der
	zugrundeliegende wkhtmltopdf-Fehler alle Doctypes betrifft, nicht nur
	Site Visit."""
	request = getattr(frappe.local, "request", None)
	if not request or request.path not in (
		"/api/method/frappe.utils.print_format.download_pdf",
		"/printview",
	):
		return
	frappe.local.form_dict.pdf_generator = "chrome"
