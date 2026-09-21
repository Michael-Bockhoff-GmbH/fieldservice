"""Datenquelle fuer die Seite "Dispatch Board" (site_visit/page/dispatch_board):
alle Techniker nebeneinander statt der bisherigen, nach Mitarbeiter/Kunde
gefilterten Einzel-Kalenderansicht (site_visit_calendar.js) - fuer einen
Ueberblick "wer macht heute was", nicht als Ersatz fuer die Kalenderansicht.

Kein FullCalendar-Resource-Plugin (Ressourcen/Techniker als eigene Spalten
nebeneinander): der in diesem Frappe mitgelieferte FullCalendar-Kern
(@fullcalendar/core u. a., siehe frappe/package.json) enthaelt keine
Resource-Views - die sind Teil von FullCalendars kommerziell lizenziertem
Premium-Bundle. Stattdessen eine einfache eigene Seite mit einer Zeile pro
Techniker, ohne neue Abhaengigkeit. Tag/Arbeitswoche/Woche/Monat sind reine
Client-Ansichten desselben Zeitraum-Abrufs hier (siehe dispatch_board.js)."""

import frappe

from fieldservice.site_visit.site_visit import _intervals_overlap


@frappe.whitelist()
def get_dispatch_board_data(start_date, end_date=None, employees=None):
	"""Alle aktiven Mitarbeiter plus deren im Zeitraum [start_date, end_date]
	(beide Tage eingeschlossen; end_date fehlt -> nur start_date, fuer die
	Tagesansicht) geplante Site Visits, unabhaengig vom Erfassungsstatus,
	aber nicht storniert. Der Bereich deckt Tag/Arbeitswoche/Woche/Monat
	gleichermassen ab - welche Tage genau angezeigt werden, entscheidet die
	Seite (dispatch_board.js), hier zaehlt nur der Gesamtzeitraum.

	Nur fuer Rollen, die ohnehin schon alle Einsaetze aller Mitarbeiter sehen
	duerfen (siehe Berechtigungen in site_visit.json) - ein Techniker (Rolle
	"Employee") hat dort nur if_owner-Zugriff und soll hier keinen Ueberblick
	ueber die Einsaetze anderer Techniker bekommen.

	tooltip_field spiegelt Site Visit Settings -> Calendar Tooltip Field
	(Project/Sales Order) - steuert, welches Zusatzfeld dispatch_board.js im
	Hover-Tooltip eines Termins anzeigt, genau wie in der Kalenderansicht
	(site_visit_calendar.js)."""
	frappe.only_for(("System Manager", "Projects Manager"))

	from frappe.utils import add_to_date, get_datetime

	range_start = get_datetime(start_date).replace(hour=0, minute=0, second=0, microsecond=0)
	range_end = add_to_date(get_datetime(end_date or start_date).replace(hour=0, minute=0, second=0, microsecond=0), days=1)

	employee_filters = {"status": "Active"}
	if employees:
		employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
		employee_filters["name"] = ["in", employees]

	settings = frappe.get_cached_doc("Site Visit Settings")
	tooltip_field = settings.calendar_tooltip_field or "Project"

	technicians = frappe.get_all(
		"Employee", filters=employee_filters, fields=["name", "employee_name"], order_by="employee_name"
	)
	if not technicians:
		return {"technicians": [], "visits": [], "tooltip_field": tooltip_field}

	visits = frappe.get_all(
		"Site Visit",
		filters={
			"employee": ["in", [t.name for t in technicians]],
			"docstatus": ["!=", 2],
			"scheduled_start": ["<", range_end],
			"scheduled_end": [">", range_start],
		},
		fields=[
			"name",
			"employee",
			"customer",
			"customer_name",
			"scheduled_start",
			"scheduled_end",
			"docstatus",
			"sales_order",
			"project",
		],
		order_by="scheduled_start",
	)

	# has_conflict nutzt dieselbe Ueberschneidungs-Pruefung wie die Warnung
	# im Formular (warn_schedule_conflicts/site_visit.py) - eine einzige
	# Definition von "Konflikt", damit Board und Formular nie widersprechen.
	by_employee = {}
	for visit in visits:
		by_employee.setdefault(visit.employee, []).append(visit)
	for rows in by_employee.values():
		for visit in rows:
			visit["has_conflict"] = any(
				other.name != visit.name
				and _intervals_overlap(visit.scheduled_start, visit.scheduled_end, other.scheduled_start, other.scheduled_end)
				for other in rows
			)

	return {"technicians": technicians, "visits": visits, "tooltip_field": tooltip_field}
