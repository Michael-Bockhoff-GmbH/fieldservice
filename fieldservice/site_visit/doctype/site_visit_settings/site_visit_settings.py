import frappe
from frappe.model.document import Document


class SiteVisitSettings(Document):
	def validate(self):
		# Die oberste Artikelgruppe (z. B. "Alle Artikelgruppen") schliesst
		# ueber ihre Untergruppen JEDEN Artikel aus - dafuer gibt es die
		# Checkbox exclude_all_item_groups. Das Auswahlfeld blendet sie schon
		# aus (site_visit_settings.js), hier zusaetzlich fuer API/Import.
		root_groups = set(frappe.get_all("Item Group", filters={"parent_item_group": ["in", ["", None]]}, pluck="name"))
		self.excluded_item_groups = [row for row in self.excluded_item_groups if row.item_group not in root_groups]


@frappe.whitelist()
def get_timezone_options():
	"""Fuer das Select-Feld time_zone (site_visit_settings.js) - dieselbe
	Zeitzonenliste, die auch Frappes eigene System Settings -> "Time Zone"
	verwendet (siehe frappe.core.doctype.system_settings.system_settings.load),
	hier direkt statt ueber die dortige, auf System Manager beschraenkte
	Methode, da diese Liste selbst keine sensiblen Daten sind."""
	from frappe.utils.momentjs import get_all_timezones

	return get_all_timezones()
