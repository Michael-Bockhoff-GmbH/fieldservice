import frappe
from frappe.model.document import Document


class SiteVisitSettings(Document):
	pass


@frappe.whitelist()
def get_timezone_options():
	"""Fuer das Select-Feld time_zone (site_visit_settings.js) - dieselbe
	Zeitzonenliste, die auch Frappes eigene System Settings -> "Time Zone"
	verwendet (siehe frappe.core.doctype.system_settings.system_settings.load),
	hier direkt statt ueber die dortige, auf System Manager beschraenkte
	Methode, da diese Liste selbst keine sensiblen Daten sind."""
	from frappe.utils.momentjs import get_all_timezones

	return get_all_timezones()
