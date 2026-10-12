"""Datenquelle fuer die Seite "Time Assignment" (site_visit/page/time_assignment):
Zeiten zuerst erfassen, danach per Drag & Drop einem Auftrag zuordnen (oder als
nicht abrechenbar markieren).

Arbeitet auf den einzelnen Zeiteintraegen (Timesheet Detail), nicht auf dem
Site Visit: ein Site Visit braucht beim Buchen ohnehin einen Auftrag (siehe
before_submit), die Zuordnung hier betrifft also Zeiten aus normal erfassten
Zeitblaettern. Die Zuordnung steckt in custom_sales_order (Custom Field von
Zeit Projekt) und is_billable - dieselben Felder, nach denen der Import in
der Rechnung filtert (zeit_projekt/timesheet_import.py). Ein bereits
fakturierter Eintrag (sales_invoice gesetzt) bleibt unangetastet."""

import frappe
from frappe import _
from frappe.utils import cint, flt

ROLES = ("System Manager", "Projects Manager")
CLOSED_ORDER_STATUS = ("Closed", "Completed", "Cancelled")


@frappe.whitelist()
def get_assignment_data(from_date=None, to_date=None, customer=None, project=None):
	"""Nicht zugeordnete Zeiten (noch kein Auftrag, nicht fakturiert) im
	Zeitraum plus die offenen Auftraege als Ablageziele - samt der Stunden, die
	ihnen bereits zugeordnet sind."""
	frappe.only_for(ROLES)

	ts = frappe.qb.DocType("Timesheet")
	tsd = frappe.qb.DocType("Timesheet Detail")

	query = (
		frappe.qb.from_(tsd)
		.join(ts)
		.on(tsd.parent == ts.name)
		.select(
			tsd.name,
			tsd.parent,
			ts.employee,
			ts.employee_name,
			tsd.from_time,
			tsd.to_time,
			tsd.hours,
			tsd.activity_type,
			tsd.project,
			tsd.description,
			tsd.is_billable,
		)
		.where(ts.docstatus < 2)
		.where(tsd.parenttype == "Timesheet")
		.where(tsd.sales_invoice.isnull() | (tsd.sales_invoice == ""))
		.where(tsd.custom_sales_order.isnull() | (tsd.custom_sales_order == ""))
		.orderby(tsd.from_time, order=frappe.qb.desc)
		.limit(500)
	)
	if from_date:
		query = query.where(tsd.from_time >= f"{from_date} 00:00:00")
	if to_date:
		query = query.where(tsd.from_time <= f"{to_date} 23:59:59")
	if project:
		query = query.where(tsd.project == project)
	entries = query.run(as_dict=True)

	order_filters = {"docstatus": ["<", 2], "status": ["not in", CLOSED_ORDER_STATUS]}
	if customer:
		order_filters["customer"] = customer
	if project:
		order_filters["project"] = project
	orders = frappe.get_all(
		"Sales Order",
		filters=order_filters,
		fields=["name", "customer", "customer_name", "project", "transaction_date", "docstatus"],
		order_by="transaction_date desc",
		limit=100,
	)

	if orders:
		hours_rows = frappe.db.sql(
			"""select tsd.custom_sales_order as sales_order, sum(tsd.hours) as hours, count(*) as entries
			from `tabTimesheet Detail` tsd
			join `tabTimesheet` ts on ts.name = tsd.parent
			where ts.docstatus < 2 and tsd.custom_sales_order in %(orders)s
			group by tsd.custom_sales_order""",
			{"orders": [o.name for o in orders]},
			as_dict=True,
		)
		assigned = {row.sales_order: row for row in hours_rows}
		for order in orders:
			row = assigned.get(order.name)
			order["assigned_hours"] = flt(row.hours, 2) if row else 0
			order["assigned_entries"] = row.entries if row else 0

		# Zugeordnete Zeiten je Auftrag, damit man sie per Ziehen zurueck in die
		# Liste "nicht zugeordnet" legen kann (Zuordnung aufheben).
		assigned_list = frappe.db.sql(
			"""select tsd.name, tsd.parent, ts.employee_name, tsd.from_time, tsd.to_time, tsd.hours,
				tsd.activity_type, tsd.description, tsd.is_billable, tsd.sales_invoice,
				tsd.custom_sales_order as sales_order
			from `tabTimesheet Detail` tsd
			join `tabTimesheet` ts on ts.name = tsd.parent
			where ts.docstatus < 2 and tsd.custom_sales_order in %(orders)s
			order by tsd.from_time desc limit 1000""",
			{"orders": [o.name for o in orders]},
			as_dict=True,
		)
	else:
		assigned_list = []

	return {"entries": entries, "orders": orders, "assigned": assigned_list}


@frappe.whitelist()
def assign_entries(entries, sales_order=None, billable=None):
	"""Ordnet Zeiteintraege (Namen der Timesheet-Detail-Zeilen) einem Auftrag
	zu, hebt die Zuordnung auf oder aendert nur "abrechenbar":

	- sales_order gesetzt: Zuordnung zum Auftrag (Projekt des Auftrags wird
	  uebernommen); abrechenbar, sofern billable nicht ausdruecklich 0 ist
	- sales_order leer + billable=0: als nicht abrechenbar markieren
	- sales_order leer + billable=1/leer: Zuordnung aufheben

	Gespeicherte (gebuchte) Zeitblaetter erlauben keine normale Aenderung -
	die Zeilen werden dann direkt aktualisiert und die Summen des
	Zeitblatts und des Projekts neu berechnet (wie ERPNext es beim Speichern
	selbst taete). Fakturierte Zeilen werden abgelehnt."""
	frappe.only_for(ROLES)

	entries = frappe.parse_json(entries) if isinstance(entries, str) else entries
	if not entries:
		return 0

	order = None
	if sales_order:
		order = frappe.db.get_value("Sales Order", sales_order, ["name", "project", "docstatus", "status"], as_dict=True)
		if not order or order.docstatus == 2 or order.status in CLOSED_ORDER_STATUS:
			frappe.throw(_("Sales Order {0} is not open.").format(sales_order))

	parents = {}
	for name in entries:
		parent = frappe.db.get_value("Timesheet Detail", name, "parent")
		if parent:
			parents.setdefault(parent, set()).add(name)

	changed = 0
	for parent, names in parents.items():
		ts = frappe.get_doc("Timesheet", parent)
		if ts.docstatus == 2:
			frappe.throw(_("Timesheet {0} is cancelled.").format(parent))

		old_projects = set()
		touched = []
		for row in ts.time_logs:
			if row.name not in names:
				continue
			if row.sales_invoice:
				frappe.throw(_("Time entry in {0} was already invoiced on {1}.").format(parent, row.sales_invoice))
			if row.project:
				old_projects.add(row.project)
			if order:
				row.custom_sales_order = order.name
				if order.project:
					row.project = order.project
				row.is_billable = 0 if billable is not None and not cint(billable) else 1
			elif billable is not None and not cint(billable):
				row.is_billable = 0
			else:
				row.custom_sales_order = None
			touched.append(row)
			changed += 1

		if not touched:
			continue

		if ts.docstatus == 0:
			ts.save()
		else:
			ts.calculate_total_amounts()
			for row in touched:
				row.db_update()
			ts.db_update()
			ts.update_task_and_project()

		for project in old_projects | {row.project for row in touched if row.project}:
			if frappe.db.exists("Project", project):
				frappe.get_doc("Project", project).update_project()

	return changed
