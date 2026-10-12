// Zeitzuordnung: Zeiten zuerst erfassen, danach per Drag & Drop einem Auftrag
// zuordnen oder als nicht abrechenbar markieren - siehe time_assignment.py
// fuer das Datenmodell. Bewusst eine eigene Seite und NICHT Teil des
// Einsatzplans (dispatch_board): der Einsatzplan plant Termine, hier werden
// bereits erfasste Zeiten verteilt.
//
// Bedienung: Karte ziehen legt sie auf einen Auftrag (zuordnen) oder zurueck in
// die linke Liste (Zuordnung aufheben). Strg/Cmd-Klick waehlt mehrere Karten,
// die dann zusammen gezogen werden. Ein einfacher Klick oeffnet ein Popup mit
// den Details und dem Haken "Nicht abrechenbar" - die Zuordnung bleibt dabei,
// nur der Abrechenbar-Status aendert sich.

frappe.pages['time-assignment'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Time Assignment'),
		single_column: true,
	});

	const state = {
		from_date: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		to_date: frappe.datetime.get_today(),
		customer: null,
		project: null,
		selected: new Set(),
		data: { entries: [], orders: [], assigned: [] },
	};

	const make_field = (opts) => page.add_field(Object.assign({ change: () => reload(page, state) }, opts));
	const from_field = make_field({ fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date', default: state.from_date });
	const to_field = make_field({ fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date', default: state.to_date });
	const customer_field = make_field({ fieldname: 'customer', label: __('Customer'), fieldtype: 'Link', options: 'Customer' });
	const project_field = make_field({ fieldname: 'project', label: __('Project'), fieldtype: 'Link', options: 'Project' });
	page.__fields = { from_field, to_field, customer_field, project_field };

	page.add_inner_button(__('Refresh'), () => reload(page, state));

	page.main.append(`
		<div class="time-assignment">
			<div class="ta-column ta-source" data-drop="unassign">
				<div class="ta-heading">${__('Unassigned Time Entries')}</div>
				<div class="ta-list ta-entries"></div>
			</div>
			<div class="ta-column ta-targets">
				<div class="ta-heading">${__('Drop on a Sales Order')}</div>
				<div class="ta-list ta-orders"></div>
			</div>
		</div>`);

	wrapper.time_assignment = { page, state, first_show: true };
	reload(page, state);
};

frappe.pages['time-assignment'].on_page_show = function (wrapper) {
	const board = wrapper.time_assignment;
	if (!board) return;
	if (board.first_show) {
		board.first_show = false;
		return;
	}
	reload(board.page, board.state);
};

function reload(page, state) {
	const f = page.__fields;
	state.from_date = f.from_field.get_value();
	state.to_date = f.to_field.get_value();
	state.customer = f.customer_field.get_value();
	state.project = f.project_field.get_value();
	frappe.call({
		method: 'fieldservice.site_visit.time_assignment.get_assignment_data',
		args: {
			from_date: state.from_date,
			to_date: state.to_date,
			customer: state.customer,
			project: state.project,
		},
		callback(r) {
			state.data = r.message || { entries: [], orders: [], assigned: [] };
			state.selected.clear();
			render(page, state);
		},
	});
}

function entry_card(entry, extra_class = '') {
	const start = frappe.datetime.str_to_user(frappe.datetime.convert_to_user_tz(entry.from_time));
	const billable = entry.is_billable ? '' : `<span class="indicator-pill gray">${__('Not billable')}</span>`;
	const locked = entry.sales_invoice;
	return `
		<div class="ta-card ${extra_class} ${locked ? 'ta-locked' : ''}" draggable="${locked ? 'false' : 'true'}" data-name="${entry.name}">
			<div class="ta-card-title">${frappe.utils.escape_html(entry.employee_name || '')} ${billable}</div>
			<div class="text-muted small">${start} &middot; ${flt(entry.hours, 2)} h
				${entry.activity_type ? '&middot; ' + frappe.utils.escape_html(entry.activity_type) : ''}</div>
			${entry.description ? `<div class="small">${frappe.utils.escape_html(entry.description).slice(0, 120)}</div>` : ''}
		</div>`;
}

function render(page, state) {
	const $root = page.main.find('.time-assignment');
	const $entries = $root.find('.ta-entries');
	const $orders = $root.find('.ta-orders');

	$entries.html(
		state.data.entries.length
			? state.data.entries.map((e) => entry_card(e)).join('')
			: `<div class="text-muted padding">${__('No unassigned time entries.')}</div>`
	);

	const assigned_by_order = {};
	state.data.assigned.forEach((a) => (assigned_by_order[a.sales_order] = assigned_by_order[a.sales_order] || []).push(a));

	$orders.html(
		state.data.orders.length
			? state.data.orders
					.map(
						(o) => `
				<div class="ta-drop ta-order" data-drop="order" data-order="${o.name}">
					<div class="ta-order-head">
						<a href="/desk/sales-order/${o.name}">${o.name}</a>
						<span class="text-muted small">${frappe.utils.escape_html(o.customer_name || o.customer || '')}${o.project ? ' &middot; ' + o.project : ''}</span>
						<span class="ta-hours">${o.assigned_hours} h</span>
					</div>
					<div class="ta-order-entries">${(assigned_by_order[o.name] || []).map((a) => entry_card(a, 'ta-assigned')).join('')}</div>
				</div>`
					)
					.join('')
			: `<div class="text-muted padding">${__('No open Sales Orders.')}</div>`
	);

	wire_dnd(page, state, $root);
}

function wire_dnd(page, state, $root) {
	let dragged = [];

	$root.find('.ta-card').on('click', function (e) {
		const name = $(this).data('name');
		if (e.ctrlKey || e.metaKey) {
			if (state.selected.has(name)) state.selected.delete(name);
			else state.selected.add(name);
			$(this).toggleClass('ta-selected', state.selected.has(name));
			return;
		}
		open_entry_dialog(page, state, name);
	});

	$root.find('.ta-card').on('dragstart', function (e) {
		const name = $(this).data('name');
		// gezogene Karte gehoert zur Auswahl -> alle gewaehlten ziehen, sonst nur sie
		dragged = state.selected.has(name) ? Array.from(state.selected) : [name];
		e.originalEvent.dataTransfer.setData('text/plain', dragged.join(','));
		e.originalEvent.dataTransfer.effectAllowed = 'move';
	});

	$root.find('[data-drop]').on('dragover', function (e) {
		e.preventDefault();
		$(this).addClass('ta-over');
	});
	$root.find('[data-drop]').on('dragleave drop', function () {
		$(this).removeClass('ta-over');
	});
	$root.find('[data-drop]').on('drop', function (e) {
		e.preventDefault();
		e.stopPropagation();
		const kind = $(this).data('drop');
		const names = dragged.length ? dragged : (e.originalEvent.dataTransfer.getData('text/plain') || '').split(',').filter(Boolean);
		dragged = [];
		if (!names.length) return;

		const args = { entries: names };
		if (kind === 'order') args.sales_order = $(this).data('order');

		frappe.call({
			method: 'fieldservice.site_visit.time_assignment.assign_entries',
			args,
			freeze: true,
			callback() {
				frappe.show_alert({ message: __('{0} time entries updated', [names.length]), indicator: 'green' });
				reload(page, state);
			},
		});
	});
}

// Popup zu einem Zeiteintrag: Details und der Haken "Nicht abrechenbar".
function open_entry_dialog(page, state, name) {
	const entry = state.data.entries.concat(state.data.assigned).find((e) => e.name === name);
	if (!entry) return;
	const start = frappe.datetime.str_to_user(frappe.datetime.convert_to_user_tz(entry.from_time));
	const locked = !!entry.sales_invoice;

	const dialog = new frappe.ui.Dialog({
		title: __('Time Entry'),
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'info',
				options: `<div>
					<div><b>${frappe.utils.escape_html(entry.employee_name || '')}</b></div>
					<div class="text-muted">${start} &middot; ${flt(entry.hours, 2)} h
						${entry.activity_type ? '&middot; ' + frappe.utils.escape_html(entry.activity_type) : ''}</div>
					${entry.description ? `<div class="small">${frappe.utils.escape_html(entry.description)}</div>` : ''}
					${entry.sales_order ? `<div class="small">${__('Sales Order')}: ${entry.sales_order}</div>` : ''}
				</div>`,
			},
			{
				fieldtype: 'Check',
				fieldname: 'not_billable',
				label: __('Not billable'),
				default: entry.is_billable ? 0 : 1,
				read_only: locked ? 1 : 0,
			},
		],
		primary_action_label: __('Save'),
		primary_action(values) {
			dialog.hide();
			if (locked || !!values.not_billable === !entry.is_billable) return;
			frappe.call({
				method: 'fieldservice.site_visit.time_assignment.set_billable',
				args: { entries: [name], billable: values.not_billable ? 0 : 1 },
				freeze: true,
				callback() {
					frappe.show_alert({ message: __('{0} time entries updated', [1]), indicator: 'green' });
					reload(page, state);
				},
			});
		},
	});
	dialog.show();
}
