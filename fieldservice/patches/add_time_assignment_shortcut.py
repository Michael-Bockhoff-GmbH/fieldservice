from fieldservice.install import _home_workspace_enable, _site_visits_workspace_links_enable


def execute():
	"""Neue Seite "Time Assignment": Home-Shortcut und Verknuepfung auf der
	"Site Visits"-Workspace nachtragen - beide Funktionen sind idempotent
	(ueberspringen vorhandene Labels). post_model_sync, da die Page vorher
	noch nicht existiert."""
	_home_workspace_enable()
	_site_visits_workspace_links_enable()
