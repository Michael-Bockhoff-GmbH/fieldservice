import frappe

FEATURE_FIELDS = ("mileage_enabled", "remote_visits_enabled", "photos_enabled", "additional_items_enabled")


def execute():
	"""Site Visit Settings ist ein Single - neue Felder mit "default" im
	DocType-JSON fuellen sich fuer einen bereits bestehenden Single-Datensatz
	nicht von selbst. Traegt hier den Standardwert (alle vier Features an)
	nach, aber nur je Feld, falls noch keiner gesetzt ist - ein Nutzer, der
	zwischen dem Schema-Sync und diesem Patch bereits etwas abgeschaltet
	haben sollte, wird dadurch nicht ueberschrieben (in der Praxis passiert
	beides im selben migrate-Lauf, rein defensiv). Muss nach dem Schema-Sync
	laufen (post_model_sync), da die Spalten vorher noch nicht existieren."""
	settings = frappe.get_single("Site Visit Settings")
	changed = False
	for fieldname in FEATURE_FIELDS:
		if settings.get(fieldname) in (None, ""):
			settings.set(fieldname, 1)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)
