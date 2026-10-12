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
def set_billable(entries, billable):
	"""Nur "abrechenbar" aendern, die Zuordnung zum Auftrag bleibt (Popup der
	Seite beim Anklicken eines Eintrags)."""
	return assign_entries(entries, None, billable, keep_order=1)


@frappe.whitelist()
def assign_entries(entries, sales_order=None, billable=None, keep_order=0):
	"""Ordnet Zeiteintraege (Namen der Timesheet-Detail-Zeilen) einem Auftrag
	zu, hebt die Zuordnung auf oder aendert nur "abrechenbar":

	- sales_order gesetzt: Zuordnung zum Auftrag (Projekt des Auftrags wird
	  uebernommen); "abrechenbar" bleibt, wie es am Eintrag steht, ausser
	  billable ist ausdruecklich gesetzt
	- sales_order leer + billable=0: als nicht abrechenbar markieren
	- sales_order leer + billable=1/leer: Zuordnung aufheben
	- keep_order=1 (set_billable): nur "abrechenbar" aendern, Zuordnung bleibt

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
	affected_orders = {order.name} if order else set()
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
			if row.custom_sales_order:
				affected_orders.add(row.custom_sales_order)
			if cint(keep_order):
				row.is_billable = 1 if billable is None or cint(billable) else 0
			elif order:
				row.custom_sales_order = order.name
				if order.project:
					row.project = order.project
				if billable is not None:
					row.is_billable = 1 if cint(billable) else 0
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

	# Auftragszeilen nachziehen: neuer Auftrag und alle, aus denen Zeiten
	# weggenommen wurden (Zuordnung aufgehoben oder auf einen anderen Auftrag
	# gelegt, oder abrechenbar geaendert)
	for so_name in sorted(affected_orders):
		sync_order_time_lines(so_name)

	return changed


def sync_order_time_lines(so_name):
	"""Gleicht die Dienstleistungs-Zeilen eines Auftrags mit den ihm
	zugeordneten, abrechenbaren Zeiten ab: pro Dienstleistungsartikel eine
	Zeile (custom_fs_assigned_time) mit der Summe der Stunden - angelegt,
	angepasst oder entfernt, wenn nichts mehr zugeordnet ist.

	Zeiten aus Site-Visit-Zeitblaettern bleiben aussen vor: fuer die steht
	schon die Zeit-Position des jeweiligen Site Visit im Auftrag (siehe
	_sync_sales_order in site_visit.py) - sonst waere dieselbe Zeit doppelt
	berechnet. Aktivitaetsarten ohne Dienstleistungsartikel koennen nicht
	abgerechnet werden und werden mit einem Hinweis uebersprungen."""
	from erpnext.controllers.accounts_controller import update_child_qty_rate

	from fieldservice.site_visit.site_visit import _as_administrator, _fallback_warehouse, _service_item_line

	so = frappe.get_doc("Sales Order", so_name)
	if so.docstatus == 2 or so.status in CLOSED_ORDER_STATUS:
		return

	rows = frappe.db.sql(
		"""select tsd.activity_type, sum(if(tsd.billing_hours, tsd.billing_hours, tsd.hours)) as hours
		from `tabTimesheet Detail` tsd
		join `tabTimesheet` ts on ts.name = tsd.parent
		where ts.docstatus < 2 and tsd.custom_sales_order = %s and tsd.is_billable = 1
			and ts.name not in (select timesheet from `tabSite Visit` where ifnull(timesheet, '') != '')
		group by tsd.activity_type""",
		so_name,
		as_dict=True,
	)

	needed = {}
	skipped = []
	for row in rows:
		item_code = frappe.get_cached_value("Activity Type", row.activity_type, "custom_dienstleistungsartikel")
		if not item_code:
			skipped.append(row.activity_type)
			continue
		if item_code in needed:
			needed[item_code]["qty"] = round(needed[item_code]["qty"] + flt(row.hours), 2)
		else:
			needed[item_code] = _service_item_line(row.activity_type, flt(row.hours))

	if skipped:
		frappe.msgprint(
			_("No Dienstleistungsartikel configured for Activity Type {0} - its time was not added to {1}.").format(
				", ".join(skipped), so_name
			),
			indicator="orange",
			alert=True,
		)

	managed = {row.item_code: row for row in so.items if row.get("custom_fs_assigned_time")}
	names_before = {row.name for row in so.items}

	changed = False
	trans_items = []
	for row in so.items:
		if row.get("custom_fs_assigned_time"):
			line = needed.get(row.item_code)
			if not line:
				changed = True  # nichts mehr zugeordnet -> Zeile weglassen (= entfernen)
				continue
			item = row.as_dict()
			if flt(item.qty) != flt(line["qty"]):
				item["qty"] = line["qty"]
				changed = True
			item["docname"] = row.name
			trans_items.append(item)
		else:
			item = row.as_dict()
			item["docname"] = row.name
			trans_items.append(item)

	new_items = [line for item_code, line in needed.items() if item_code not in managed]
	for line in new_items:
		line["warehouse"] = _fallback_warehouse(so, line["item_code"])
		trans_items.append(line)
		changed = True

	if not changed:
		return

	with _as_administrator():
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)

	if new_items:
		so.reload()
		fresh = [row for row in so.items if row.name not in names_before]
		for line in new_items:
			match = next((row for row in fresh if row.item_code == line["item_code"]), None)
			if match:
				frappe.db.set_value("Sales Order Item", match.name, "custom_fs_assigned_time", 1)
				fresh.remove(match)
