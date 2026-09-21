import frappe

from fieldservice.patches.add_feature_toggles import FEATURE_FIELDS


def execute():
	"""Korrigiert add_feature_toggles.py: dessen urspruengliche "nur falls
	noch nicht gesetzt"-Pruefung (in (None, "")) griff bei Check-Feldern nie
	(DB-Spalte ist NOT NULL DEFAULT 0, liest also sofort als 0), liess die
	vier Feature-Schalter dadurch faelschlich auf "deaktiviert" stehen statt
	auf dem beabsichtigten Standard "aktiviert". Setzt hier einfach erneut
	alle vier auf 1 - unbedingt, aus demselben Grund wie im korrigierten
	add_feature_toggles.py: diese Spalten sind gerade erst entstanden, es
	gibt keinen frueheren bewussten Nutzer-Wert, der ueberschrieben werden
	koennte."""
	settings = frappe.get_single("Site Visit Settings")
	for fieldname in FEATURE_FIELDS:
		settings.set(fieldname, 1)
	settings.save(ignore_permissions=True)
