import frappe

FEATURE_FIELDS = ("mileage_enabled", "remote_visits_enabled", "photos_enabled", "additional_items_enabled")


def execute():
	"""Site Visit Settings ist ein Single - neue Felder mit "default" im
	DocType-JSON fuellen sich fuer einen bereits bestehenden Single-Datensatz
	nicht von selbst. Traegt hier den Standardwert (alle vier Features an)
	nach.

	Anders als beim frueheren time_zone-Patch (Select/Data, "unset" == None/
	"") reicht hier keine "nur falls noch nicht gesetzt"-Pruefung: Check-
	Felder werden in der DB als NOT NULL DEFAULT 0 angelegt, eine frisch
	hinzugefuegte Spalte liest also sofort als 0 (nicht None/"") - eine
	Pruefung auf "in (None, '')" traf damit nie zu und liess alle vier
	Schalter faelschlich auf 0 (deaktiviert) stehen, siehe
	fix_feature_toggle_defaults.py fuer die Korrektur davon auf bereits
	migrierten Benches. Da diese Spalten hier zum ersten Mal ueberhaupt
	entstehen, kann kein Nutzer sie vorher bewusst abgeschaltet haben -
	deshalb hier direkt und bedingungslos auf 1 setzen. Muss nach dem
	Schema-Sync laufen (post_model_sync), da die Spalten vorher noch nicht
	existieren."""
	settings = frappe.get_single("Site Visit Settings")
	for fieldname in FEATURE_FIELDS:
		settings.set(fieldname, 1)
	settings.save(ignore_permissions=True)
