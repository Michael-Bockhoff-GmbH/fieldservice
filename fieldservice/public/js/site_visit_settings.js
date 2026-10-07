// Default Start Address: derselbe Freitext-mit-Sofortsuche-Mechanismus wie
// start_address/customer_address_override auf Site Visit (siehe dort für
// die ausführliche Begründung, inkl. warum die eigene search_addresses()
// statt Frappes eingebauter Adress-Autovervollständigung verwendet wird)
// - kein Address-Datensatz nötig.
frappe.ui.form.on('Site Visit Settings', {
	onload(frm) {
		frm.set_query('default_start_address', () => 'fieldservice.site_visit.mileage.search_addresses');
		const field = frm.get_field('default_start_address');
		if (field) {
			field.df.ignore_validation = 1;
			debounce_address_field(field);
		}

		// Die oberste Artikelgruppe ("Alle Artikelgruppen") waere als
		// Ausschluss sinnlos - sie schliesst ueber ihre Untergruppen jeden
		// Artikel aus. Dafuer gibt es die Checkbox "Exclude all Item Groups".
		const hide_root_group = () => ({ filters: { parent_item_group: ['is', 'set'] } });
		frm.set_query('excluded_item_groups', hide_root_group);
		frm.set_query('item_group', 'excluded_item_groups', hide_root_group);

		// Dieselbe Zeitzonenliste wie Frappes eigene System Settings -> "Time
		// Zone" (siehe get_timezone_options() in site_visit_settings.py) - das
		// Select-Feld hat bewusst keine statische options-Liste im DocType,
		// IANA-Zeitzonennamen aendern sich gelegentlich.
		frappe.call('fieldservice.site_visit.doctype.site_visit_settings.site_visit_settings.get_timezone_options').then((r) => {
			frm.set_df_property('time_zone', 'options', r.message || []);
			frm.refresh_field('time_zone');
		});
	},
});

// Siehe site_visit.js fuer die ausfuehrliche Begruendung.
function debounce_address_field(field, delay = 400) {
	let timer = null;
	const original = field.execute_query_if_exists.bind(field);
	field.execute_query_if_exists = function (term) {
		clearTimeout(timer);
		timer = setTimeout(() => original(term), delay);
	};
}
