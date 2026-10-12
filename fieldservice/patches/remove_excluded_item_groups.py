import frappe


def execute():
	"""Die Einstellung "Excluded Item Groups" (samt Kindtabelle) entfaellt:
	die Dienstleistungs-Artikelgruppe "Services" ist jetzt fest im Code
	ausgeschlossen (EXCLUDED_ITEM_GROUP in site_visit.py). Loescht den nun
	unbenutzten Kind-Doctype - idempotent, ignore_missing."""
	frappe.delete_doc("DocType", "Site Visit Excluded Item Group", force=True, ignore_missing=True)
