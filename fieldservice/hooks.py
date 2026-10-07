app_name = "fieldservice"
app_title = "IT Support mit Außendienst"
app_publisher = "Dein Name"
app_description = (
	"Kundeneinsaetze dokumentieren (Fotos, Unterschrift) und automatisch ein abrechenbares Zeitblatt erzeugen; "
	"Zeiterfassung als Einzelpositionen in der Ausgangsrechnung und automatische Projektanlage aus dem Auftrag"
)
app_email = "info@example.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Eigene App im Desk (Apps-Uebersicht + Logo oben links innerhalb der App)
#
# Entstanden aus dem Zusammenlegen von "site_visit" und "zeit_projekt" zu
# einer App (siehe README.md "Zusammenlegung") - deshalb bleiben beide
# Module ("Site Visit", "Zeit Projekt") unter eigenem Namen bestehen
# (modules.txt), nur die App drumherum ist jetzt eine gemeinsame.
# ---------------------------------------------------------------------------
app_logo_url = "/assets/fieldservice/images/fieldservice-logo.svg"

add_to_apps_screen = [
	{
		"name": "fieldservice",
		"logo": "/assets/fieldservice/images/fieldservice-logo.svg",
		"title": "IT Support mit Außendienst",
		"route": "/app/site-visit",
		"has_permission": "fieldservice.site_visit.site_visit.check_app_permission",
	}
]

# ---------------------------------------------------------------------------
# Formular-Skripte
#
# Als Dateien ausgeliefert statt als Client-Script-Datensaetze - verschwinden
# restlos mit der App, sind versionierbar, unterliegen nicht dem
# Client-Script-Cache im Browser.
# ---------------------------------------------------------------------------
app_include_js = "/assets/fieldservice/js/sidebar_memory.js"

doctype_js = {
	"Site Visit": "public/js/site_visit.js",
	"Site Visit Settings": "public/js/site_visit_settings.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	"Sales Order": "public/js/sales_order.js",
}

# ---------------------------------------------------------------------------
# Kalenderansicht fuer geplante Site Visits (scheduled_start/scheduled_end)
#
# site_visit_calendar.js liegt direkt im Doctype-Ordner und wird darueber
# allein durch den Dateinamen automatisch geladen (kein Eintrag in
# doctype_js noetig - derselbe Mechanismus wie bei ERPNexts eigenen
# task_calendar.js/job_card_calendar.js). Der Hook hier schaltet nur den
# "Calendar"-Ansichtswechsler in der Listenansicht frei.
# ---------------------------------------------------------------------------
calendars = ["Site Visit"]

# ---------------------------------------------------------------------------
# Serverseitige Logik im selben Request wie das jeweilige Buchen
#
# Beide Hooks laufen innerhalb derselben Transaktion wie das Setzen von
# docstatus=1 - kein separater Request davor, damit kein Zeitfenster fuer
# "has been modified after you have opened it" entsteht (bei einem
# frueheren, rein clientseitigen Ansatz produktiv aufgetreten). Greift
# dadurch auch bei API-Zugriffen und Massenbuchungen.
# ---------------------------------------------------------------------------
doc_events = {
	"Site Visit": {
		"before_submit": "fieldservice.site_visit.site_visit.before_submit",
		"on_cancel": "fieldservice.site_visit.site_visit.on_cancel",
	},
	"Sales Order": {
		"before_submit": "fieldservice.zeit_projekt.sales_order.before_submit",
	},
}

# ---------------------------------------------------------------------------
# PDF-Generator serverweit auf "chrome" erzwingen
#
# wkhtmltopdf (Frappe-Standard) scheitert auf diesem Server grundsaetzlich
# an jeder frisch erzeugten Druckvorlage, nicht nur an Site Visit - schon
# das von Frappe selbst eingebundene print.bundle.css (relative URL ohne
# Basis-Adresse) bricht mit "ProtocolUnknownError" ab. Reproduziert am
# 13.09.2026 fuer Sales Order, Sales Invoice und Site Visit gleichermassen.
# Alte, bereits vorhandene Rechnungs-PDFs stammen vermutlich noch aus der
# Frappe-Cloud-Migration und wurden nie auf diesem Server neu erzeugt -
# deshalb ist es vorher nicht aufgefallen.
#
# frappe.utils.print_format.download_pdf ignoriert das pdf_generator-Feld
# des Print Format und faellt hart auf "wkhtmltopdf" zurueck. Das
# eigentliche Ausleseglied dafuer liefert normalerweise die App
# print_designer (eigener before_request-Hook), die auf diesem Server aber
# bewusst nicht installiert ist (kein version-16-Branch,
# Stabilitaetsbedenken laut INSTALL-APPS.md). Statt der riskanten App nur
# den konkret benoetigten Mechanismus selbst nachgebaut - siehe
# force_chrome_pdf() in site_visit/site_visit.py fuer Details. Liegt in
# dieser App, wirkt aber (wie alle Hooks) serverweit fuer alle
# installierten Apps.
# ---------------------------------------------------------------------------
before_request = ["fieldservice.site_visit.site_visit.force_chrome_pdf"]

# ---------------------------------------------------------------------------
# Site Visit in der Verknuepfungen-Liste des Projekt-Formulars
#
# Additiv (siehe site_visit/project_dashboard.get_data) - ergaenzt nur einen
# Eintrag, ersetzt nicht die von ERPNext gelieferte Liste.
# ---------------------------------------------------------------------------
override_doctype_dashboards = {
	"Project": "fieldservice.site_visit.project_dashboard.get_data",
}

# ---------------------------------------------------------------------------
# Installation / Deinstallation
#
# Ein gemeinsames install.py fuer beide urspruenglichen Apps - siehe dort
# fuer die einzelnen Schritte (Custom Fields von "Zeit Projekt",
# PDF on Submit Settings-Eintrag von "Site Visit").
# ---------------------------------------------------------------------------
after_install = "fieldservice.install.after_install"
before_uninstall = "fieldservice.install.before_uninstall"

# Der pdf_on_submit-Patch fuer den automatischen PDF-Weg steht in
# fieldservice/__init__.py, nicht hier - siehe Kommentar dort fuer die
# Begruendung (hooks.py wird nicht zuverlaessig in jedem Prozesstyp beim
# Start importiert, das Paket-__init__.py dagegen schon).
