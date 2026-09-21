"""Kilometerberechnung ueber die OpenRouteService-API (openrouteservice.org).

Zwei Schritte pro Berechnung: Geocoding (Adresstext -> Koordinaten) ueber
den /geocode/search-Endpunkt, dann die eigentliche Route ueber
/v2/directions/driving-car. Beides mit demselben API-Key (Site Visit
Settings -> OpenRouteService API Key).

Start- und Zieladresse sind reiner Freitext (Felder start_address/
customer_address_override auf Site Visit, default_start_address auf Site
Visit Settings - alle drei "Autocomplete" statt "Link (Address)"), keine
ERPNext-Address-Datensaetze noetig. Die Formularfelder bieten trotzdem eine
Sofortsuche waehrend der Eingabe, ueber search_addresses() unten - eine
eigene, direkte Anbindung an Nominatim (OpenStreetMap, kostenlos/offen,
kein eigener API-Key noetig), NICHT Frappes eingebaute Adress-
Autovervollstaendigung (Kern-Doctype "Geolocation Settings"): deren
Nomatim-Anbieter schickt keinen User-Agent-Header mit, was Nominatims
Nutzungsbedingungen (https://operations.osmfoundation.org/policies/nominatim/)
verlangen - ohne Kennung lehnt der Dienst jede Anfrage mit 403 Forbidden ab
(am 17.09.2026 reproduziert, siehe auch Traceback vom Nutzer). Ein Fehler
im Frappe-Kern, den diese App nicht patcht - stattdessen die eigene
Anbindung mit korrektem User-Agent.

Bewusst kein Caching von Koordinaten hier - Adressen aendern sich selten
genug, dass der zusaetzliche Code (inkl. Invalidierung) den API-Aufruf
nicht aufwiegt. Ein Fehlschlag (kein Key, Adresse nicht gefunden, Netzwerk)
wirft frappe.ValidationError mit einer fuer den Techniker verstaendlichen
Meldung - die Kilometerberechnung ist eine Komfortfunktion, kein Teil der
before_submit-Pflichtpruefung, ein Site Visit laesst sich auch ohne
Kilometer buchen."""

import time

import frappe
from frappe import _

GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_TIMEOUT = 10

# search_addresses(): siehe deren Docstring - Nominatims Nutzungsbedingungen
# erlauben maximal 1 Anfrage pro Sekunde, insgesamt fuer die ganze Site.
SEARCH_MIN_CHARS = 3
SEARCH_MIN_INTERVAL_SECONDS = 1.1
SEARCH_CACHE_SECONDS = 300


def get_start_text(doc):
	"""Startadresse (Freitext) fuer die Kilometerberechnung: Ueberschreibung
	am Site Visit selbst, sonst die in Site Visit Settings hinterlegte
	Standard-Startadresse, sonst die Standardadresse der Firma (dafuer noch
	ein echter Address-Datensatz - Firmenadressen sind stabil genug, dass
	sich ein eigener ERPNext-Datensatz dafuer lohnt).

	Das Freitextfeld start_address bleibt nach dem Entfernen des Hakens
	"Different Start Location" stehen (Frappes depends_on blendet nur die
	Anzeige aus, loescht den Feldwert nicht) - deshalb hier zusaetzlich das
	Gating-Feld selbst pruefen, statt dem Feldwert allein zu vertrauen."""
	if doc.override_start_address and doc.start_address:
		return doc.start_address

	settings = frappe.get_cached_doc("Site Visit Settings")
	if settings.default_start_address:
		return settings.default_start_address

	from frappe.contacts.doctype.address.address import get_default_address

	address_name = get_default_address("Company", doc.company)
	return _address_text(address_name) if address_name else None


def get_destination_text(doc):
	"""Zieladresse (Freitext): Ueberschreibung am Site Visit selbst (z. B.
	eine Aussenstelle/Remote Office des Kunden), sonst die Standardadresse
	des Kunden - ausser "Don't Use Customer's Default Address" ist
	angehakt, dann zaehlt ausschliesslich die Ueberschreibung (z. B. weil
	die hinterlegte Kundenadresse fuer diesen Einsatz bekanntermassen nicht
	stimmt) und es gibt ohne sie keine Zieladresse.

	customer_address_override bleibt nach dem Entfernen des Hakens stehen
	(siehe get_start_text oben) - deshalb hier ebenfalls zuerst das
	Gating-Feld pruefen, statt dem Feldwert allein zu vertrauen."""
	if doc.ignore_customer_default_address:
		return doc.customer_address_override or None

	from frappe.contacts.doctype.address.address import get_default_address

	address_name = get_default_address("Customer", doc.customer)
	return _address_text(address_name) if address_name else None


def calculate_distance_km(doc):
	"""Berechnet die Fahrstrecke (km, einfache Strecke) von der
	Startadresse zur Kundenadresse des Site Visit. Wirft
	frappe.ValidationError mit verstaendlicher Meldung bei fehlendem
	API-Key, fehlender/nicht auffindbarer Adresse oder API-Fehler."""
	settings = frappe.get_cached_doc("Site Visit Settings")
	if not settings.mileage_enabled:
		frappe.throw(_("Mileage calculation is disabled in Site Visit Settings."), title=_("Mileage"))

	api_key = settings.get_password("ors_api_key", raise_exception=False)
	if not api_key:
		frappe.throw(
			_("No OpenRouteService API key configured. Set one in Site Visit Settings."), title=_("Mileage")
		)

	start_text = get_start_text(doc)
	if not start_text:
		frappe.throw(
			_(
				"No start address found. Set a Start Address on the Site Visit, a Default Start "
				"Address in Site Visit Settings, or a default address on the Company."
			),
			title=_("Mileage"),
		)

	destination_text = get_destination_text(doc)
	if not destination_text:
		frappe.throw(
			_(
				"Customer {0} has no address on file. Set a Customer Site Address on the Site Visit instead."
			).format(doc.customer),
			title=_("Mileage"),
		)

	start_coords = _geocode(start_text, api_key)
	end_coords = _geocode(destination_text, api_key)
	return _route_distance_km(start_coords, end_coords, api_key)


def _address_text(address_name):
	address = frappe.get_cached_doc("Address", address_name)
	parts = [address.address_line1, address.address_line2, address.city, address.pincode, address.country]
	return ", ".join(part for part in parts if part)


def _geocode(text, api_key):
	response = requests_get(
		GEOCODE_URL,
		params={"api_key": api_key, "text": text, "size": 1},
	)
	features = response.get("features") or []
	if not features:
		frappe.throw(_("Could not find coordinates for address {0}.").format(text), title=_("Mileage"))
	# GeoJSON: [longitude, latitude]
	return features[0]["geometry"]["coordinates"]


def _route_distance_km(start_coords, end_coords, api_key):
	response = requests_post(
		DIRECTIONS_URL,
		headers={"Authorization": api_key, "Content-Type": "application/json"},
		json={"coordinates": [start_coords, end_coords]},
	)
	try:
		distance_m = response["routes"][0]["summary"]["distance"]
	except (KeyError, IndexError) as e:
		frappe.throw(_("OpenRouteService did not return a route between the two addresses."), title=_("Mileage"))
	return round(distance_m / 1000, 1)


def requests_get(url, params):
	import requests

	try:
		r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
		r.raise_for_status()
	except requests.RequestException as e:
		frappe.throw(_("OpenRouteService request failed: {0}").format(e), title=_("Mileage"))
	return r.json()


def requests_post(url, headers, json):
	import requests

	try:
		r = requests.post(url, headers=headers, json=json, timeout=REQUEST_TIMEOUT)
		r.raise_for_status()
	except requests.RequestException as e:
		frappe.throw(_("OpenRouteService request failed: {0}").format(e), title=_("Mileage"))
	return r.json()


@frappe.whitelist()
def search_addresses(txt):
	"""Adress-Sofortsuche fuer start_address/customer_address_override
	(site_visit.js) und default_start_address (site_visit_settings.js) -
	eigene, direkte Nominatim-Anbindung statt Frappes eingebauter
	Adress-Autovervollstaendigung, siehe Modul-Docstring oben fuer den
	Hintergrund (403 Forbidden ohne User-Agent-Header).

	Frappes Autocomplete-Control (frappe/public/js/frappe/form/controls/
	autocomplete.js) ruft diese Methode bei jedem Tastendruck neu auf, ganz
	ohne eigenes Debouncing oder Mindestlaenge - allein dadurch reisst schon
	das Tippen eines laengeren Adressnamens Nominatims Nutzungsbedingungen
	(max. 1 Anfrage/Sekunde), was zu einer voruebergehenden Sperre fuehrt
	("Suche ging kurz, dann nicht mehr"). Da dieses Control Frappe-Kern ist
	und nicht gepatcht wird, passiert das eigentliche Debouncing clientseitig
	(debounce_address_field() in site_visit.js/site_visit_settings.js) - ein
	frueherer Versuch, das stattdessen hier per time.sleep() abzufedern,
	blockierte dabei einen ganzen Web-Worker pro Tastendruck und war damit
	selbst ein Verfuegbarkeitsrisiko. Hier bleiben nur zwei einfache,
	nicht-blockierende Absicherungen:

	1. Text unter SEARCH_MIN_CHARS Zeichen wird gar nicht erst gesucht.
	2. Ergebnisse werden pro Suchtext eine Weile zwischengespeichert, damit
	   erneutes Tippen/Fokussieren desselben Texts keine neue Anfrage ausloest.
	3. Liegt die letzte tatsaechliche Nominatim-Anfrage noch keine
	   SEARCH_MIN_INTERVAL_SECONDS zurueck, wird gar nicht erst angefragt
	   (statt zu warten) - kein Vorschlag ist fuer diese Komfortfunktion
	   unkritischer als ein blockierter Request. Ohne Sperre gegen echte
	   Gleichzeitigkeit (kein Lock um den Cache-Zugriff) - bei wenigen
	   gleichzeitigen Technikern ein vertretbares Restrisiko.

	Gibt fertige, bereits lesbare Adresszeilen zurueck (label == value) -
	kein Nachformatieren im Formular noetig wie bei Frappes eigener
	Autovervollstaendigung, die stattdessen ein JSON-Objekt mit
	Adressbestandteilen liefert. Schlaegt bei einem Netzwerk-/API-Fehler
	still zu einer leeren Vorschlagsliste fehl, statt das Formular mit
	einem Fehlerdialog zu unterbrechen - es ist nur eine Sucheingabe-
	Komfortfunktion, freier Text bleibt jederzeit moeglich."""
	if not txt or len(txt) < SEARCH_MIN_CHARS:
		return []

	cache = frappe.cache()
	cache_key = f"site_visit_addr_search::{txt.lower()}"
	cached = cache.get_value(cache_key)
	if cached is not None:
		return cached

	last_call_key = "site_visit_addr_last_call"
	last_call = cache.get_value(last_call_key)
	now = time.time()
	if last_call is not None and now - last_call < SEARCH_MIN_INTERVAL_SECONDS:
		return []
	cache.set_value(last_call_key, now, expires_in_sec=10)

	import requests

	headers = {"User-Agent": f"fieldservice-erpnext ({frappe.utils.get_url()})"}
	try:
		r = requests.get(
			NOMINATIM_SEARCH_URL,
			params={"q": txt, "format": "json", "limit": 5, "addressdetails": 0},
			headers=headers,
			timeout=REQUEST_TIMEOUT,
		)
		r.raise_for_status()
	except requests.RequestException:
		return []

	results = [{"label": result["display_name"], "value": result["display_name"]} for result in r.json()]
	cache.set_value(cache_key, results, expires_in_sec=SEARCH_CACHE_SECONDS)
	return results


@frappe.whitelist()
def calculate_distance(site_visit):
	"""Fuer den "Kilometer berechnen"-Knopf im Formular."""
	doc = frappe.get_doc("Site Visit", site_visit)
	doc.check_permission("write")
	km = calculate_distance_km(doc)
	doc.db_set("distance_km", km)
	return km
