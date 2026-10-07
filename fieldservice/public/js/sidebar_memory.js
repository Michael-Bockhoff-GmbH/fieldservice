// Merkt sich pro Eintrag (z. B. "Timesheet"), in welcher Sidebar man ihn
// zuletzt benutzt hat, und stellt diese beim Neuladen der Seite wieder her.
//
// Hintergrund: "Timesheet" steht sowohl in der ERPNext-Sidebar "Projects" als
// auch in "Site Visits". Frappes eigenes Merken (localStorage
// "sidebar_item_map") greift hier nicht zuverlaessig - nach einem Reload
// landete man immer in "Projects". Der Core bleibt unangetastet; wir
// ergaenzen nur die Auswahl, wenn die Seite frisch geladen wurde.
(function () {
	const STORAGE_KEY = "fieldservice_sidebar_by_entity";

	function read_map() {
		try {
			return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
		} catch (e) {
			return {};
		}
	}

	function write_map(map) {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
		} catch (e) {
			// localStorage nicht verfuegbar - dann bleibt es beim Standardverhalten
		}
	}

	function patch() {
		const Sidebar = frappe.ui && frappe.ui.Sidebar;
		if (!Sidebar || Sidebar.prototype.__fieldservice_patched) return;
		Sidebar.prototype.__fieldservice_patched = true;

		const original_resolve = Sidebar.prototype.resolve_sidebar;
		Sidebar.prototype.resolve_sidebar = function (entity, module) {
			// Nur beim ersten Aufbau nach dem Laden eingreifen (noch keine Sidebar aktiv)
			if (!this.sidebar_title && entity) {
				const remembered = read_map()[entity];
				if (remembered && this.get_workspace_sidebars(entity).includes(remembered)) {
					this.preferred_sidebars = this.get_workspace_sidebars(entity);
					return remembered;
				}
			}
			return original_resolve.call(this, entity, module);
		};

		const original_set = Sidebar.prototype.set_workspace_sidebar;
		Sidebar.prototype.set_workspace_sidebar = function (router) {
			const result = original_set.call(this, router);
			try {
				const entity = this.entity_from_route(frappe.get_route());
				if (entity && this.sidebar_title && this.get_workspace_sidebars(entity).includes(this.sidebar_title)) {
					const map = read_map();
					if (map[entity] !== this.sidebar_title) {
						map[entity] = this.sidebar_title;
						write_map(map);
					}
				}
			} catch (e) {
				// reine Komfortfunktion - nie die Seite stoeren
			}
			return result;
		};
	}

	patch();
})();
