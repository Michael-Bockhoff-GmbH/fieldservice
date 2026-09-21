// Zeitblatt wird erst beim Buchen angelegt (serverseitig, siehe hooks.py ->
// doc_events -> fieldservice.site_visit.site_visit.before_submit). Dieses
// Skript setzt nur Feld-Defaults und liefert nach dem Buchen einen Link
// dorthin - keine async Calls vor dem Buchen, um die Race Condition aus
// sales_order.js (Modul Zeit Projekt) nicht zu wiederholen.

frappe.ui.form.on('Site Visit', {
	onload(frm) {
		// Auftrag-Auswahl auf Auftraege des gewaehlten Kunden (und, falls
		// gesetzt, Projekts) einschraenken. Dynamischer Filter - wird bei
		// jedem Oeffnen des Dropdowns neu anhand des aktuellen frm.doc
		// ausgewertet. Ohne customer-Filter wurden hier bislang Auftraege
		// beliebiger Kunden angezeigt, sobald kein Projekt gesetzt war (oder
		// generell, da der Filter selbst bei gesetztem Projekt nie auf den
		// Kunden eingeschraenkt hat).
		frm.set_query('sales_order', () => {
			const filters = {};
			if (frm.doc.customer) filters.customer = frm.doc.customer;
			if (frm.doc.project) filters.project = frm.doc.project;
			return { filters };
		});

		// Artikel aus den in Site Visit Settings hinterlegten
		// Artikelgruppen (inkl. Untergruppen, i. d. R. die
		// Dienstleistungsartikel) sind als Zusatzartikel ausgeschlossen -
		// siehe item_query_extra_items in site_visit.py (leere Einstellung
		// = keine Einschraenkung).
		frm.set_query('item_code', 'extra_items', () => ({
			query: 'fieldservice.site_visit.site_visit.item_query_extra_items',
		}));

		// Start Address/Customer Site Address: freier Text statt eines
		// Address-Datensatzes, aber mit Sofortsuche waehrend der Eingabe -
		// ueber die eigene search_addresses() in mileage.py (direkte
		// Nominatim-Anbindung mit korrektem User-Agent-Header), NICHT
		// Frappes eingebaute Adress-Autovervollstaendigung: die schlaegt
		// bei Nominatim ohne User-Agent mit 403 Forbidden fehl (siehe
		// mileage.py fuer den Hintergrund). ignore_validation ist noetig,
		// da ControlAutocomplete sonst jeden Wert verwirft, der nicht
		// exakt einem der zuletzt geladenen Vorschlaege entspricht - z. B.
		// frei eingetippte Adressen ohne Vorschlagsauswahl. debounce_address_
		// field() buendelt die sonst pro Tastendruck ausgeloesten Anfragen -
		// siehe deren Definition unten fuer den Hintergrund.
		['start_address', 'customer_address_override'].forEach((fieldname) => {
			frm.set_query(fieldname, () => 'fieldservice.site_visit.mileage.search_addresses');
			const field = frm.get_field(fieldname);
			if (!field) return;
			field.df.ignore_validation = 1;
			debounce_address_field(field);
		});

		frappe.db.get_doc('Site Visit Settings').then((settings) => {
			frm.__site_visit_settings = settings;
			frm.trigger('refresh');
		});

		if (!frm.is_new()) return;
		if (!frm.doc.employee) {
			frappe.db.get_value('Employee', { user_id: frappe.session.user, status: 'Active' }, 'name')
				.then((r) => {
					if (r.message && r.message.name) frm.set_value('employee', r.message.name);
				});
		}
		// Kein automatischer Default fuer from_time mehr - das uebernimmt
		// jetzt der Timer (oder die manuelle Eingabe), siehe update_timer_toolbar
		// unten. Ein Default hier wuerde bei Formularoeffnung den falschen
		// Zeitpunkt festlegen, falls der Techniker den Einsatz erst spaeter
		// tatsaechlich beginnt.

		// Ueber die Verknuepfungen-Liste des Projekts angelegt ("+" bei Site
		// Visit): project ist dann schon vorbelegt, aber das Feldevent
		// project() unten feuert dabei nicht (Frappe setzt route_options beim
		// Neuanlegen direkt als Feldwert, nicht ueber set_value). Deshalb hier
		// dieselbe Logik einmal explizit anstossen.
		if (frm.doc.project) fill_from_project(frm);
	},

	project(frm) {
		if (!frm.doc.project) return;
		fill_from_project(frm);
	},

	sales_order(frm) {
		// Kunde (und, falls noch leer, Projekt) aus dem gewaehlten Auftrag
		// uebernehmen - derselbe Grund wie bei project(): der Techniker soll
		// das nicht doppelt eintragen muessen.
		if (!frm.doc.sales_order) return;
		frappe.db.get_value('Sales Order', frm.doc.sales_order, ['customer', 'project']).then((r) => {
			if (!r.message) return;
			if (r.message.customer) frm.set_value('customer', r.message.customer);
			if (r.message.project && !frm.doc.project) frm.set_value('project', r.message.project);
		});
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		update_timer_toolbar(frm);
		update_remote_ui(frm);
		update_feature_visibility(frm);
		if (frm.doc.docstatus === 0 && !frm.doc.customer_signature) {
			frm.dashboard.set_headline_alert(__('No customer signature captured yet.'), 'orange');
		}
		if (frm.doc.docstatus === 1 && frm.doc.timesheet) {
			frm.add_custom_button(__('Open Timesheet'), () => {
				frappe.set_route('Form', 'Timesheet', frm.doc.timesheet);
			});
		}
		const mileage_enabled = (frm.__site_visit_settings || {}).mileage_enabled !== 0;
		if (mileage_enabled && frm.doc.docstatus === 0 && !frm.is_new() && frm.doc.customer && !frm.doc.is_remote) {
			frm.add_custom_button(__('Calculate Mileage'), () => calculate_mileage(frm));
		}
	},

	is_remote(frm) {
		update_remote_ui(frm);
		update_feature_visibility(frm);
	},

	override_start_address(frm) {
		update_feature_visibility(frm);
	},

	ignore_customer_default_address(frm) {
		update_feature_visibility(frm);
	},

	// Schnelle, nicht-blockierende Vorwarnung waehrend der Eingabe - die
	// massgebliche Pruefung ist warn_schedule_conflicts() serverseitig
	// (validate()-Hook, site_visit.py), die nach dem Speichern zusaetzlich
	// die genauen ueberschneidenden Termine auflistet. Warnt nur, blockiert
	// nicht - siehe dort fuer die Begruendung.
	employee: check_schedule_conflict,
	scheduled_start: check_schedule_conflict,
	scheduled_end: check_schedule_conflict,
});

function check_schedule_conflict(frm) {
	if (!frm.doc.employee || !frm.doc.scheduled_start || !frm.doc.scheduled_end) return;
	frappe.call({
		method: 'fieldservice.site_visit.site_visit.check_schedule_conflict',
		args: {
			employee: frm.doc.employee,
			scheduled_start: frm.doc.scheduled_start,
			scheduled_end: frm.doc.scheduled_end,
			name: frm.doc.name,
		},
		callback(r) {
			const count = r.message || 0;
			if (!count) return;
			frappe.show_alert(
				{
					message: __('Scheduling conflict: {0} already has {1} overlapping visit(s).', [frm.doc.employee, count]),
					indicator: 'orange',
				},
				7
			);
		},
	});
}

// Frappes Autocomplete-Control (frappe/public/js/frappe/form/controls/
// autocomplete.js -> execute_query_if_exists) ruft die Suchmethode bei
// jedem Tastendruck ohne jegliches Debouncing auf - ohne dieses Wrapping
// muesste search_addresses() das serverseitig abfedern (frueher per
// time.sleep(), das dabei einen ganzen Worker blockierte, siehe mileage.py).
// Ueberschreibt hier nur die Methode auf der eigenen Feldinstanz, kein
// Patch am Frappe-Kern selbst.
function debounce_address_field(field, delay = 400) {
	let timer = null;
	const original = field.execute_query_if_exists.bind(field);
	field.execute_query_if_exists = function (term) {
		clearTimeout(timer);
		timer = setTimeout(() => original(term), delay);
	};
}

// Site Visit Settings -> Features: blendet ganze Funktionsbereiche aus, fuer
// Betriebe, die sie nicht brauchen (z. B. keine Kilometerabrechnung). Die
// mileage-/is_remote-abhaengigen Felder haben bereits ihr eigenes depends_on
// (site_visit.json) - dessen Bedingung wird hier dupliziert und mit dem
// jeweiligen Feature-Schalter UND-verknuepft statt sie zu ersetzen: Frappes
// eigene depends_on-Auswertung liefe sonst bei jeder Aenderung von is_remote/
// override_start_address/ignore_customer_default_address unabhaengig von
// dieser Funktion und wuerde ein wegen des Schalters ausgeblendetes Feld
// wieder einblenden (deshalb auch in den jeweiligen Feld-Handlern unten
// erneut aufgerufen, nicht nur in refresh()). Rein UI-seitig - die
// eigentliche Business-Logik (Kilometerabrechnung ueberspringen usw.) prueft
// dieselben Site Visit Settings-Felder serverseitig selbst.
function update_feature_visibility(frm) {
	const settings = frm.__site_visit_settings || {};
	const mileage_enabled = settings.mileage_enabled !== 0;
	const remote_enabled = settings.remote_visits_enabled !== 0;
	const photos_enabled = settings.photos_enabled !== 0;
	const additional_items_enabled = settings.additional_items_enabled !== 0;

	frm.toggle_display('override_start_address', mileage_enabled && !frm.doc.is_remote);
	frm.toggle_display('start_address', mileage_enabled && !frm.doc.is_remote && !!frm.doc.override_start_address);
	frm.toggle_display('ignore_customer_default_address', mileage_enabled && !frm.doc.is_remote);
	frm.toggle_display(
		'customer_address_override',
		mileage_enabled && !frm.doc.is_remote && !!frm.doc.ignore_customer_default_address
	);
	frm.toggle_display('distance_km', mileage_enabled && !frm.doc.is_remote);
	frm.toggle_display('one_way_only', mileage_enabled && !!frm.doc.distance_km && !frm.doc.is_remote);
	frm.toggle_display('section_break_remote', mileage_enabled || remote_enabled);
	frm.toggle_display('is_remote', remote_enabled);
	frm.toggle_display(['section_break_fotos', 'photos'], photos_enabled);
	frm.toggle_display(['section_break_items', 'extra_items'], additional_items_enabled);
}

// Fernarbeit: Unterschrift ausblenden ODER Link zum Unterzeichnen an den
// Kunden schicken - je nach Site Visit Settings -> Remote Visit Mode. Die
// eigentliche Pflicht-Pruefung (Site Visit Settings -> Signature Required)
// laeuft serverseitig in _validate_signature (site_visit.py) - hier nur
// Anzeige/Komfort.
function update_remote_ui(frm) {
	const settings = frm.__site_visit_settings || {};
	const hide_signature = frm.doc.is_remote && settings.remote_mode === 'Hide Signature';
	frm.toggle_display(['customer_signature', 'signee_name'], !hide_signature);

	if (frm.doc.docstatus !== 0 || frm.is_new()) return;
	if (!frm.doc.is_remote || settings.remote_mode !== 'Send Signing Link to Customer') return;
	if (frm.doc.customer_signature) return;
	if (!frm.doc.customer) return;

	frm.add_custom_button(__('Send Signing Link'), () => send_signing_link(frm));
	if (frm.doc.remote_signature_sent_at) {
		frm.dashboard.set_headline_alert(
			__('Signing link sent on {0}, not yet signed.', [frappe.datetime.str_to_user(frm.doc.remote_signature_sent_at)]),
			'blue'
		);
	}
}

function send_signing_link(frm) {
	frappe.call({
		method: 'fieldservice.site_visit.remote_signature.send_signing_link',
		args: { site_visit: frm.doc.name },
		freeze: true,
		freeze_message: __('Sending...'),
		callback(r) {
			if (!r.message) return;
			frappe.show_alert({ message: __('Signing link sent.'), indicator: 'green' }, 5);
			frm.reload_doc();
		},
	});
}

function calculate_mileage(frm) {
	frappe.call({
		method: 'fieldservice.site_visit.mileage.calculate_distance',
		args: { site_visit: frm.doc.name },
		freeze: true,
		freeze_message: __('Calculating...'),
		callback(r) {
			if (r.message === undefined) return;
			frappe.show_alert({ message: __('Distance: {0} km', [r.message]), indicator: 'green' }, 5);
			frm.reload_doc();
		},
	});
}

// Timer fuer die Einsatzzeit - reine Komfortfunktion obendrauf auf from_time/
// to_time, die ganz normale, jederzeit von Hand editierbare Felder bleiben
// (kein read-only). "Start"/"Pause"/"Fortsetzen"/"Stopp" speichern sofort
// (wie ERPNexts eigener Timesheet-Timer in
// erpnext/public/js/projects/timer.js: frm.save() direkt nach dem Setzen von
// from_time) - deshalb sind customer/company/activity_type/sales_order/
// to_time nicht mehr reqd im Feld, sondern erst in before_submit
// (site_visit.py) Pflicht, sonst waere ein Entwurf mit nur laufendem Timer
// gar nicht speicherbar. Ohne das sofortige Speichern ginge der Timer bei
// einem Reload/Schliessen der Seite verloren, weil ein neues, ungespeichertes
// Dokument nur im Browser existiert. 1:1 uebernommen aus fahrtenbuch.js (dort
// ausfuehrlicher kommentiert).
//
// Pausen (Kaffeepause, Notfall bei einem anderen Kunden, ...) landen als
// eigene Zeilen im Feld "breaks" (Kindtabelle "Site Visit Break") statt den
// Zeitraum einfach zu unterbrechen - so bleibt from_time/to_time weiterhin
// der durchgehende Gesamtrahmen des Einsatzes, waehrend site_visit.py beim
// Buchen die Pausen herausrechnet und pro Arbeitsabschnitt einen eigenen
// Timesheet-Eintrag anlegt (siehe _get_work_segments dort).
function update_timer_toolbar(frm) {
	stop_ticking(frm);
	if (frm.doc.docstatus !== 0) return;

	if (!frm.doc.from_time) {
		frm.page.add_button(__('Start Timer'), () => {
			frm.set_value('from_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
		return;
	}
	if (frm.doc.to_time) return;

	if (get_open_break(frm)) {
		frm.page.add_button(__('Resume Timer'), () => resume_timer(frm));
	} else {
		frm.page.add_button(__('Pause Timer'), () => pause_timer(frm));
	}
	frm.page.add_button(__('Stop Timer'), () => stop_timer(frm));
	start_ticking(frm);
}

// Letzte Pausenzeile, falls sie noch laeuft (kein to_time) - es kann immer
// nur hoechstens eine offene Pause geben, da "Pause Timer" erst wieder
// anklickbar ist, nachdem die vorherige per "Resume Timer" geschlossen wurde.
function get_open_break(frm) {
	const breaks = frm.doc.breaks || [];
	const last = breaks[breaks.length - 1];
	return last && !last.to_time ? last : null;
}

function pause_timer(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __('Pause Timer'),
		fields: [
			{
				fieldname: 'reason',
				fieldtype: 'Select',
				label: __('Reason'),
				options: ['Break', 'Other Customer (Emergency)', 'Other'],
				default: 'Break',
				reqd: 1,
			},
			{
				fieldname: 'note',
				fieldtype: 'Small Text',
				label: __('Note'),
			},
		],
		primary_action_label: __('Pause'),
		primary_action(values) {
			frm.add_child('breaks', {
				from_time: frappe.datetime.now_datetime(),
				reason: values.reason,
				note: values.note,
			});
			frm.refresh_field('breaks');
			dialog.hide();
			frm.save();
		},
	});
	dialog.show();
}

function resume_timer(frm) {
	const open_break = get_open_break(frm);
	if (!open_break) return;
	frappe.model.set_value(open_break.doctype, open_break.name, 'to_time', frappe.datetime.now_datetime());
	frm.save();
}

// Stoppt auch dann, wenn gerade pausiert ist - eine noch offene Pause wird
// dabei auf denselben Zeitpunkt geschlossen wie to_time. Ein "Fortsetzen"
// vor dem Stoppen zu erzwingen, waere reine Schikane, wenn der Einsatz z. B.
// waehrend einer Pause endgueltig endet (der Notfall beim anderen Kunden
// dauert den Rest des Tages).
function stop_timer(frm) {
	const now = frappe.datetime.now_datetime();
	const open_break = get_open_break(frm);
	if (open_break) {
		frappe.model.set_value(open_break.doctype, open_break.name, 'to_time', now);
	}
	frm.set_value('to_time', now).then(() => frm.save());
}

function start_ticking(frm) {
	const tick = () => {
		const state = get_timer_state(frm, Date.now());
		// clear_headline() zuerst: show_message() im Frappe-Layout haengt bei
		// jedem Aufruf nur einen neuen Block an, statt den alten zu ersetzen -
		// ohne das Clear stapeln sich die Meldungen im Sekundentakt.
		frm.dashboard.clear_headline();
		if (state.paused) {
			frm.dashboard.set_headline_alert(
				__('Timer paused ({0}) - worked so far: {1}', [__(state.pause_reason), format_duration(state.worked_ms)]),
				'blue'
			);
		} else {
			frm.dashboard.set_headline_alert(__('Timer running: {0}', [format_duration(state.worked_ms)]), 'orange');
		}
	};
	tick();
	frm.__site_visit_timer = setInterval(tick, 1000);
}

function stop_ticking(frm) {
	if (frm.__site_visit_timer) {
		clearInterval(frm.__site_visit_timer);
		frm.__site_visit_timer = null;
	}
}

// Rechnet die bislang tatsaechlich gearbeitete Zeit aus from_time und den
// (ggf. noch offenen) Pausen zusammen - Pausenzeit zaehlt nicht mit. Reiner
// Anzeigewert fuer den Timer im Browser; die massgebliche Berechnung beim
// Buchen macht _get_work_segments in site_visit.py.
function get_timer_state(frm, now) {
	const breaks = (frm.doc.breaks || [])
		.slice()
		.sort((a, b) => frappe.datetime.str_to_obj(a.from_time) - frappe.datetime.str_to_obj(b.from_time));

	let cursor = frappe.datetime.str_to_obj(frm.doc.from_time).getTime();
	let worked_ms = 0;

	for (const row of breaks) {
		const break_from = frappe.datetime.str_to_obj(row.from_time).getTime();
		worked_ms += Math.max(0, break_from - cursor);
		if (!row.to_time) {
			return { paused: true, pause_reason: row.reason, worked_ms };
		}
		cursor = frappe.datetime.str_to_obj(row.to_time).getTime();
	}

	worked_ms += Math.max(0, now - cursor);
	return { paused: false, pause_reason: null, worked_ms };
}

function format_duration(total_ms) {
	const total_seconds = Math.max(0, Math.floor(total_ms / 1000));
	const h = String(Math.floor(total_seconds / 3600)).padStart(2, '0');
	const m = String(Math.floor((total_seconds % 3600) / 60)).padStart(2, '0');
	const s = String(total_seconds % 60).padStart(2, '0');
	return `${h}:${m}:${s}`;
}

// Betrag in der Zusatzartikel-Tabelle ist reine Anzeige (qty * rate) - der
// verknuepfte Auftrag rechnet beim Uebernehmen selbst neu (Steuern,
// Preisregeln usw., siehe site_visit.py -> _sync_sales_order/_create_sales_order).
frappe.ui.form.on('Site Visit Item', {
	qty(frm, cdt, cdn) {
		update_extra_item_amount(cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		update_extra_item_amount(cdt, cdn);
	},
});

function update_extra_item_amount(cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	const qty = Number(row.qty) || 0;
	const rate = Number(row.rate) || 0;
	frappe.model.set_value(cdt, cdn, 'amount', qty * rate);
}

function fill_from_project(frm) {
	if (!frm.doc.customer) {
		frappe.db.get_value('Project', frm.doc.project, 'customer').then((r) => {
			if (r.message && r.message.customer) frm.set_value('customer', r.message.customer);
		});
	}
	// Genau ein passender Auftrag zum gewaehlten Projekt? Dann gleich
	// uebernehmen. Bei mehreren eine Auswahl anzeigen, statt den Techniker
	// selbst im (durch onload() bereits gefilterten) Dropdown suchen zu
	// lassen - sales_order bleibt trotzdem Pflicht erst beim Buchen (siehe
	// before_submit in site_visit.py), damit ein Entwurf mit nur laufendem
	// Timer weiterhin speicherbar ist.
	if (!frm.doc.sales_order) {
		frappe.db.get_list('Sales Order', {
			filters: { project: frm.doc.project, docstatus: ['!=', 2] },
			fields: ['name'],
			limit: 20,
		}).then((rows) => {
			if (rows.length === 1) {
				frm.set_value('sales_order', rows[0].name);
			} else if (rows.length > 1) {
				show_select_sales_order_dialog(frm, rows);
			}
		});
	}
}

function show_select_sales_order_dialog(frm, orders) {
	const dialog = new frappe.ui.Dialog({
		title: __('Select Sales Order'),
		fields: [
			{
				fieldname: 'sales_order',
				fieldtype: 'Select',
				label: __('This Project has multiple Sales Orders - please pick one'),
				options: orders.map((o) => o.name),
				reqd: 1,
			},
		],
		primary_action_label: __('Select'),
		primary_action(values) {
			dialog.hide();
			frm.set_value('sales_order', values.sales_order);
		},
	});
	dialog.show();
}
