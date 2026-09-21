// Kalenderansicht fuer geplante Termine (scheduled_start/scheduled_end) -
// unabhaengig von from_time/to_time, die die tatsaechliche Einsatzzeit
// festhalten (siehe site_visit.json). Ein Site Visit ohne scheduled_start
// taucht hier einfach nicht auf - reine Vorausplanung ist optional.
//
// convertToUserTz: true schaltet Frappes eingebaute Zeitzonen-Umrechnung
// ab (frappe/public/js/frappe/views/calendar/calendar.js -> prepare_events:
// "if (!me.field_map.convertToUserTz) d.convertToUserTz = 1;" - ohne diesen
// Wert hier wird IMMER umgerechnet). Diese Umrechnung geht von System
// Settings -> Time Zone aus, nicht von Site Visit Settings -> Time Zone -
// stimmt Erstere nicht mit der tatsaechlichen Zeitzone des Unternehmens
// ueberein, verschiebt sich ein Termin im Kalender um Stunden oder faellt
// sogar aus dem sichtbaren Tag heraus (genau so am 18.09.2026 beobachtet:
// System Settings stand auf "Asia/Kolkata"). Site Visit Settings -> Time
// Zone aendert daran bewusst nichts direkt - stattdessen wird hier einfach
// gar nicht erst umgerechnet, scheduled_start/scheduled_end werden als
// reiner Klartext-Zeitpunkt angezeigt, genau wie im Formular und im
// Dispatch Board (site_visit/page/dispatch_board/) - unabhaengig davon,
// was in System Settings steht.
// Eigener Hover-Tooltip (eventDidMount, siehe frappe.views.Calendar.
// setup_options/get_args: das "options"-Objekt hier wird per $.extend in
// Frappes cal_options gemischt und landet direkt bei FullCalendar) statt
// dem eingebauten Browser-Tooltip von FullCalendar - zeigt zusaetzlich zur
// (dank convertToUserTz:true oben bereits korrekten) Uhrzeit den Auftrag
// oder das Projekt an, je nach Site Visit Settings -> Calendar Tooltip
// Field. "fields" unten sorgt dafuer, dass sales_order/project ueberhaupt
// mitgeliefert werden - ohne eigene "fields"-Angabe fragt Frappes
// get_events() nur start/end/title/name ab (siehe frappe.desk.calendar.
// get_events in frappe-core).
// Bewusst kein gecachtes Promise ueber den Seitenaufruf hinaus: die
// Kalenderansicht bleibt beim Navigieren innerhalb von Frappes SPA im
// selben JS-Kontext geladen, ein einmal gecachter Wert wuerde also eine
// zwischenzeitliche Aenderung an Site Visit Settings -> Calendar Tooltip
// Field bis zu einem harten Browser-Reload ignorieren. frappe.db.
// get_single_value liest ohnehin gegen Frappes eigenen (serverseitigen)
// Document-Cache, ein erneuter Aufruf pro eingeblendetem Termin ist
// entsprechend billig.
function get_site_visit_tooltip_fieldname() {
	return frappe.db
		.get_single_value("Site Visit Settings", "calendar_tooltip_field")
		.then((value) => (value === "Sales Order" ? "sales_order" : "project"));
}

function format_site_visit_tooltip_time(event) {
	const pad = (n) => String(n).padStart(2, "0");
	const fmt = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
	return event.end ? `${fmt(event.start)} - ${fmt(event.end)}` : fmt(event.start);
}

frappe.views.calendar["Site Visit"] = {
	field_map: {
		start: "scheduled_start",
		end: "scheduled_end",
		id: "name",
		title: "customer_name",
		allDay: "allDay",
		convertToUserTz: true,
	},
	fields: ["name", "scheduled_start", "scheduled_end", "customer_name", "docstatus", "sales_order", "project"],
	filters: [
		{ fieldtype: "Link", fieldname: "employee", options: "Employee", label: __("Employee") },
		{ fieldtype: "Link", fieldname: "customer", options: "Customer", label: __("Customer") },
	],
	get_events_method: "frappe.desk.calendar.get_events",
	options: {
		eventDidMount(info) {
			get_site_visit_tooltip_fieldname().then((fieldname) => {
				const value = info.event.extendedProps[fieldname];
				const label = fieldname === "sales_order" ? __("Sales Order") : __("Project");
				const lines = [`${info.event.title || ""} (${format_site_visit_tooltip_time(info.event)})`];
				if (value) lines.push(`${label}: ${value}`);
				info.el.setAttribute("title", lines.join("\n"));
			});
		},
	},
};
