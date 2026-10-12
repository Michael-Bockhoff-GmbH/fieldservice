from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from fieldservice.install import CUSTOM_FIELDS


def execute():
	"""Custom Field custom_fs_assigned_time auf Sales Order Item (siehe
	CUSTOM_FIELDS in install.py) fuer bereits installierte Benches nachtragen -
	after_install laeuft nur bei einer Neuinstallation."""
	create_custom_fields({"Sales Order Item": CUSTOM_FIELDS["Sales Order Item"]}, ignore_validate=True)
