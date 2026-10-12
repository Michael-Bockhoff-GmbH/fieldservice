import erpnext
from frappe.model.document import Document

from fieldservice.site_visit.site_visit import validate_extra_items, warn_schedule_conflicts


class SiteVisit(Document):
	def validate(self):
		if not self.company:
			self.company = erpnext.get_default_company()
		validate_extra_items(self)
		warn_schedule_conflicts(self)
