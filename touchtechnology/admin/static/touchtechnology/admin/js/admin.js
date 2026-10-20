/*
 * vitriolic admin: what the pages do once scripts run. Every page works
 * without this file; each part below only makes a working page quicker.
 *
 *   the rail     opening folders of the tree, the phone's menu and drill-down
 *   tabs         one pane at a time, remembered, by keyboard too
 *   popovers     a row's further actions, "add several"
 *   confirm      a question before a delete or an undo
 *   pickers      choosing one of many in a dialog with a search
 */
(function () {
	'use strict';

	var html = document.documentElement;

	function $(selector, root) { return (root || document).querySelector(selector); }
	function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }

	function fetchHTML(url) {
		return fetch(url, {
			credentials: 'same-origin',
			headers: { 'X-Requested-With': 'fetch' }
		}).then(function (response) {
			if (!response.ok) { throw new Error(response.status); }
			return response.text();
		});
	}

	/* ------------------------------------------------------------------
	 * The rail
	 */

	var rail = $('#rail');
	var menuButton = $('.dock-menu');
	var lastFocus = null;

	function openRail() {
		lastFocus = document.activeElement;
		html.classList.add('rail-open');
		if (menuButton) { menuButton.setAttribute('aria-expanded', 'true'); }
		var target = $('.drill-title', rail) || $('a', rail);
		if (target) { target.focus({ preventScroll: true }); }
	}

	function closeRail() {
		html.classList.remove('rail-open');
		if (menuButton) { menuButton.setAttribute('aria-expanded', 'false'); }
		if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
	}

	if (menuButton && rail) {
		menuButton.addEventListener('click', function () {
			if (html.classList.contains('rail-open')) { closeRail(); } else { openRail(); }
		});
		var closer = $('.rail-close', rail);
		if (closer) { closer.addEventListener('click', closeRail); }
		document.addEventListener('keydown', function (event) {
			if (event.key === 'Escape' && html.classList.contains('rail-open')) { closeRail(); }
		});
	}

	// Open and close a folder of the tree; one never opened before is fetched.
	document.addEventListener('click', function (event) {
		var twisty = event.target.closest('.twisty');
		if (!twisty) { return; }
		var list = document.getElementById(twisty.getAttribute('aria-controls'));
		if (!list) { return; }
		var open = twisty.getAttribute('aria-expanded') === 'true';
		twisty.setAttribute('aria-expanded', open ? 'false' : 'true');
		list.hidden = open;
		if (!open && twisty.hasAttribute('data-lazy')) {
			var tree = twisty.closest('[data-endpoint]');
			var node = twisty.closest('.node');
			twisty.removeAttribute('data-lazy');
			node.classList.add('loading');
			fetchHTML(tree.getAttribute('data-endpoint') + '?node=' + encodeURIComponent(twisty.getAttribute('data-node')))
				.then(function (text) { list.innerHTML = text; })
				.catch(function () { twisty.setAttribute('data-lazy', ''); })
				.then(function () { node.classList.remove('loading'); });
		}
	});

	// The phone's drill-down: into a folder, or back up, without leaving the page.
	document.addEventListener('click', function (event) {
		var link = event.target.closest('[data-drill]');
		if (!link) { return; }
		var drill = link.closest('#drill');
		if (!drill) { return; }
		event.preventDefault();
		var url = drill.getAttribute('data-endpoint') + '?mode=drill&node=' + encodeURIComponent(link.getAttribute('data-drill'));
		drill.setAttribute('aria-busy', 'true');
		fetchHTML(url).then(function (text) {
			drill.innerHTML = text;
			var title = $('.drill-title', drill);
			if (title) { title.focus({ preventScroll: true }); }
			drill.scrollIntoView({ block: 'nearest' });
		}).catch(function () {
			if (link.href && link.getAttribute('href') !== '#') { window.location = link.href; }
		}).then(function () { drill.removeAttribute('aria-busy'); });
	});

	// Keep the open folder of the tree in view.
	var here = $('.tree .node.here > .node-row');
	if (here && here.scrollIntoView) {
		var scroller = $('.rail-scroll');
		if (scroller && here.offsetTop > scroller.clientHeight - 80) {
			scroller.scrollTop = here.offsetTop - scroller.clientHeight / 3;
		}
	}

	/* ------------------------------------------------------------------
	 * Messages
	 */

	document.addEventListener('click', function (event) {
		var button = event.target.closest('.message-close');
		if (button) { button.closest('.message').remove(); }
	});

	/* ------------------------------------------------------------------
	 * Tabs
	 */

	function tabsOf(list) { return $$('[role="tab"]', list); }

	// Buttons that act on one pane (Save, for the details) show with it.
	function syncPanelButtons() {
		$$('[data-for-panel]').forEach(function (element) {
			var panel = document.getElementById(element.getAttribute('data-for-panel'));
			element.hidden = !!(panel && panel.hasAttribute('data-tab-panel') && !panel.classList.contains('is-active'));
		});
		html.classList.toggle('has-form-buttons', !!$('.form-buttons:not([hidden])'));
	}

	function selectTab(tab, focus) {
		var list = tab.closest('[role="tablist"]');
		tabsOf(list).forEach(function (other) {
			var selected = other === tab;
			other.setAttribute('aria-selected', selected ? 'true' : 'false');
			other.tabIndex = selected ? 0 : -1;
			var panel = document.getElementById(other.getAttribute('aria-controls'));
			if (panel) { panel.classList.toggle('is-active', selected); }
		});
		if (focus) { tab.focus(); }
		syncPanelButtons();
		var id = tab.getAttribute('aria-controls');
		try { sessionStorage.setItem('admin-tab:' + location.pathname, id); } catch (e) { /* private mode */ }
		if (history.replaceState) { history.replaceState(null, '', '#' + id); }
		var panel = document.getElementById(id);
		if (panel && window.htmx && panel.hasAttribute('hx-get') && !panel.dataset.loaded) {
			panel.dataset.loaded = '1';
			htmx.trigger(panel, 'shown');
		}
	}

	function initialTab(list) {
		var tabs = tabsOf(list);
		var byPanel = function (id) {
			return tabs.filter(function (tab) { return tab.getAttribute('aria-controls') === id; })[0];
		};
		if (location.hash) {
			var fromHash = byPanel(decodeURIComponent(location.hash.slice(1)));
			if (fromHash) { return fromHash; }
		}
		// Coming back from an object a pane lists shows that pane again.
		if (document.referrer) {
			var there;
			try { there = new URL(document.referrer); } catch (e) { there = null; }
			if (there && there.origin === location.origin && there.pathname !== location.pathname) {
				var found = null;
				tabs.forEach(function (tab) {
					var panel = document.getElementById(tab.getAttribute('aria-controls'));
					if (!found && panel && $$('a[href]', panel).some(function (a) {
						return a.pathname === there.pathname;
					})) { found = tab; }
				});
				if (found) { return found; }
				if (there.pathname.indexOf(location.pathname) === 0) {
					var last = null;
					try { last = sessionStorage.getItem('admin-tab:' + location.pathname); } catch (e) { /* private mode */ }
					if (last && byPanel(last)) { return byPanel(last); }
				}
			}
		}
		return tabs.filter(function (tab) { return tab.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
	}

	$$('[role="tablist"][data-tabs]').forEach(function (list) {
		var tabs = tabsOf(list);
		if (!tabs.length) { return; }
		var start = initialTab(list);
		tabs.forEach(function (tab) {
			tab.addEventListener('click', function (event) {
				event.preventDefault();
				selectTab(tab);
			});
		});
		list.addEventListener('keydown', function (event) {
			var index = tabs.indexOf(document.activeElement);
			if (index < 0) { return; }
			var next = null;
			if (event.key === 'ArrowRight') { next = tabs[(index + 1) % tabs.length]; }
			if (event.key === 'ArrowLeft') { next = tabs[(index - 1 + tabs.length) % tabs.length]; }
			if (event.key === 'Home') { next = tabs[0]; }
			if (event.key === 'End') { next = tabs[tabs.length - 1]; }
			if (next) { event.preventDefault(); selectTab(next, true); }
		});
		// The first pane a page shows is chosen without touching the address.
		tabs.forEach(function (tab) {
			var selected = tab === start;
			tab.setAttribute('aria-selected', selected ? 'true' : 'false');
			tab.tabIndex = selected ? 0 : -1;
			var panel = document.getElementById(tab.getAttribute('aria-controls'));
			if (panel) { panel.classList.toggle('is-active', selected); }
		});
		syncPanelButtons();
		var startPanel = document.getElementById(start.getAttribute('aria-controls'));
		if (startPanel && window.htmx && startPanel.hasAttribute('hx-get')) {
			startPanel.dataset.loaded = '1';
			// htmx sets itself up when the document is parsed, before this runs.
			var load = function () { htmx.trigger(startPanel, 'shown'); };
			if (document.readyState === 'loading') {
				document.addEventListener('DOMContentLoaded', load);
			} else {
				load();
			}
		}
	});

	/* ------------------------------------------------------------------
	 * Popovers: a button with aria-expanded that shows the element it controls
	 */

	function closePopovers(except) {
		$$('[data-popover][aria-expanded="true"]').forEach(function (button) {
			if (button === except) { return; }
			button.setAttribute('aria-expanded', 'false');
			var panel = document.getElementById(button.getAttribute('aria-controls'));
			if (panel) { panel.hidden = true; }
		});
	}

	document.addEventListener('click', function (event) {
		var button = event.target.closest('[data-popover]');
		if (button) {
			var panel = document.getElementById(button.getAttribute('aria-controls'));
			var open = button.getAttribute('aria-expanded') === 'true';
			closePopovers(button);
			button.setAttribute('aria-expanded', open ? 'false' : 'true');
			if (panel) {
				panel.hidden = open;
				if (!open) {
					var first = $('input:not([type="hidden"]), a, button', panel);
					if (first) { first.focus(); if (first.select) { first.select(); } }
				}
			}
			return;
		}
		if (!event.target.closest('.menu-panel, .add-many-form')) { closePopovers(); }
	});

	document.addEventListener('keydown', function (event) {
		if (event.key !== 'Escape') { return; }
		var open = $('[data-popover][aria-expanded="true"]');
		if (open) { closePopovers(); open.focus(); }
	});

	// Hidden until scripts can open them; without scripts they stay on show.
	function preparePopovers(root) {
		$$('[data-popover]', root).forEach(function (button) {
			var panel = document.getElementById(button.getAttribute('aria-controls'));
			if (panel && button.getAttribute('aria-expanded') !== 'true') { panel.hidden = true; }
		});
	}

	// "Add several": ask how many in a dialog rather than following the link.
	document.addEventListener('click', function (event) {
		var opener = event.target.closest('[data-add-many]');
		if (opener) {
			var box = document.getElementById(opener.getAttribute('data-add-many'));
			if (box && box.showModal) {
				event.preventDefault();
				box.showModal();
				var count = $('input[type="number"]', box);
				if (count) { count.focus(); count.select(); }
			}
			return;
		}
		var closer = event.target.closest('dialog [data-close]');
		if (closer) { closer.closest('dialog').close(); }
	});

	// Another blank row of a formset, from its empty form.
	document.addEventListener('click', function (event) {
		var button = event.target.closest('[data-add-row]');
		if (!button) { return; }
		var prefix = button.getAttribute('data-add-row');
		var total = document.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
		var template = document.getElementById(prefix + '-empty-row');
		var body = $('[data-formset="' + prefix + '"] tbody');
		if (!total || !template || !body) { return; }
		var index = parseInt(total.value, 10);
		var row = document.createElement('tbody');
		row.innerHTML = template.innerHTML.replace(/__prefix__/g, index);
		var tr = row.firstElementChild;
		body.appendChild(tr);
		total.value = index + 1;
		enhance(tr);
		var first = $('input:not([type="hidden"]), select, textarea', tr);
		if (first) { first.focus(); }
	});

	/* ------------------------------------------------------------------
	 * Confirm: a delete, an undo, anything that cannot be taken back
	 */

	var dialog = $('#confirm-dialog');
	var pending = null;

	document.addEventListener('submit', function (event) {
		var form = event.target;
		if (!form.hasAttribute || !form.hasAttribute('data-confirm') || !dialog || !dialog.showModal) { return; }
		if (form.dataset.confirmed) { return; }
		event.preventDefault();
		closePopovers();
		pending = form;
		$('#confirm-title', dialog).textContent = form.getAttribute('data-confirm-title') || $('#confirm-title', dialog).getAttribute('data-default') || $('#confirm-title', dialog).textContent;
		$('#confirm-body', dialog).textContent = form.getAttribute('data-confirm');
		$('#confirm-ok', dialog).textContent = form.getAttribute('data-confirm-label') || 'Delete';
		dialog.showModal();
		$('#confirm-ok', dialog).focus();
	}, true);

	if (dialog) {
		// Submit as the button is pressed, so the page starts to change at once.
		$('#confirm-ok', dialog).addEventListener('click', function (event) {
			event.preventDefault();
			var form = pending;
			pending = null;
			dialog.close('confirm');
			if (form) {
				form.dataset.confirmed = '1';
				HTMLFormElement.prototype.submit.call(form);
			}
		});
		dialog.addEventListener('close', function () { pending = null; });
	}

	/* ------------------------------------------------------------------
	 * Pickers: a select of many options becomes a button that opens a
	 * dialog with a search. The select stays in the form and is what posts.
	 */

	var MANY = 10;
	var pickerDialog = null;
	var pickerCount = 0;

	function labelFor(select) {
		var label = select.id && document.querySelector('label[for="' + select.id + '"]');
		if (label && !label.id) { label.id = select.id + '-label'; }
		return label;
	}

	function optionText(option) { return option.textContent.trim(); }

	function realOptions(select) {
		return Array.prototype.filter.call(select.options, function (option) { return option.value !== ''; });
	}

	function buildPickerDialog() {
		if (pickerDialog) { return pickerDialog; }
		pickerDialog = document.createElement('dialog');
		pickerDialog.className = 'picker-dialog';
		pickerDialog.setAttribute('aria-labelledby', 'picker-title');
		pickerDialog.innerHTML =
			'<div class="picker-head"><h2 id="picker-title"></h2>' +
			'<button type="button" class="button quiet icon-only picker-close"><svg class="icon" aria-hidden="true"><use href="' + iconHref('x') + '"></use></svg><span class="visually-hidden">Close</span></button></div>' +
			'<div class="picker-search"><input type="search" autocomplete="off" aria-label="Search" placeholder="Type to search" aria-controls="picker-options"></div>' +
			'<ul class="picker-options" id="picker-options" role="listbox"></ul>';
		document.body.appendChild(pickerDialog);
		$('.picker-close', pickerDialog).addEventListener('click', function () { pickerDialog.close(); });
		return pickerDialog;
	}

	function iconHref(name) {
		var use = $('svg.icon use');
		var base = use ? use.getAttribute('href').split('#')[0] : '';
		return base + '#' + name;
	}

	function openPicker(select, button, refresh) {
		var dlg = buildPickerDialog();
		var label = labelFor(select);
		var search = $('input', dlg);
		var list = $('.picker-options', dlg);
		var active = -1;
		var shown = [];
		$('#picker-title', dlg).textContent = label ? label.textContent.trim() : 'Choose';
		list.setAttribute('aria-multiselectable', select.multiple ? 'true' : 'false');
		search.value = '';

		function render() {
			var terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
			list.innerHTML = '';
			shown = [];
			var group = null;
			realOptions(select).forEach(function (option) {
				var text = optionText(option);
				var hay = text.toLowerCase();
				if (!terms.every(function (term) { return hay.indexOf(term) >= 0; })) { return; }
				var parent = option.parentNode;
				if (parent.tagName === 'OPTGROUP' && parent !== group) {
					group = parent;
					var heading = document.createElement('li');
					heading.className = 'picker-heading';
					heading.setAttribute('role', 'presentation');
					heading.textContent = parent.label;
					list.appendChild(heading);
				}
				var item = document.createElement('li');
				item.setAttribute('role', 'option');
				item.id = 'picker-option-' + shown.length;
				item.setAttribute('aria-selected', option.selected ? 'true' : 'false');
				item.textContent = text;
				item.addEventListener('click', function () { choose(option); });
				list.appendChild(item);
				shown.push({ item: item, option: option });
			});
			if (!shown.length) {
				var empty = document.createElement('li');
				empty.className = 'picker-empty';
				empty.textContent = 'Nothing matches.';
				list.appendChild(empty);
			}
			setActive(shown.length ? 0 : -1);
		}

		function setActive(index) {
			if (active >= 0 && shown[active]) { shown[active].item.classList.remove('focused'); }
			active = index;
			if (active >= 0 && shown[active]) {
				shown[active].item.classList.add('focused');
				shown[active].item.scrollIntoView({ block: 'nearest' });
				search.setAttribute('aria-activedescendant', shown[active].item.id);
			} else {
				search.removeAttribute('aria-activedescendant');
			}
		}

		function choose(option) {
			if (select.multiple) {
				option.selected = !option.selected;
			} else {
				select.value = option.value;
			}
			select.dispatchEvent(new Event('change', { bubbles: true }));
			refresh();
			dlg.close();
		}

		search.oninput = render;
		search.onkeydown = function (event) {
			if (event.key === 'ArrowDown') { event.preventDefault(); setActive(Math.min(active + 1, shown.length - 1)); }
			if (event.key === 'ArrowUp') { event.preventDefault(); setActive(Math.max(active - 1, 0)); }
			if (event.key === 'Enter') {
				event.preventDefault();
				if (active >= 0 && shown[active]) { choose(shown[active].option); }
			}
		};
		dlg.onclose = function () {
			button.setAttribute('aria-expanded', 'false');
			button.focus();
		};
		render();
		button.setAttribute('aria-expanded', 'true');
		dlg.showModal();
		search.focus();
	}

	function enhancePicker(select) {
		if (select.dataset.picker === 'off' || select.closest('[data-no-picker]')) { return; }
		var many = realOptions(select).length > MANY;
		if (!(select.multiple || many || select.dataset.picker === 'on')) { return; }
		if (select.size > 1 && !select.multiple) { return; }
		var label = labelFor(select);
		var id = 'picker-' + (++pickerCount);
		var button = document.createElement('button');
		button.type = 'button';
		button.className = 'picker-button';
		button.id = id;
		button.setAttribute('role', 'combobox');
		button.setAttribute('aria-haspopup', 'dialog');
		button.setAttribute('aria-expanded', 'false');
		button.innerHTML = '<span class="picker-value" id="' + id + '-value"></span>' +
			'<svg class="icon" aria-hidden="true"><use href="' + iconHref('search') + '"></use></svg>';
		if (label) { button.setAttribute('aria-labelledby', label.id + ' ' + id + '-value'); }
		if (select.getAttribute('aria-invalid')) { button.setAttribute('aria-invalid', 'true'); }
		var chips = document.createElement('div');
		chips.className = 'picker-chips';

		function refresh() {
			var value = $('.picker-value', button);
			var chosen = Array.prototype.filter.call(select.options, function (o) { return o.selected && o.value !== ''; });
			if (select.multiple) {
				value.textContent = chosen.length ? chosen.length + ' chosen, add another' : 'Choose';
				value.classList.toggle('placeholder', !chosen.length);
				chips.innerHTML = '';
				chosen.forEach(function (option) {
					var chip = document.createElement('span');
					chip.className = 'chip';
					chip.textContent = optionText(option);
					var remove = document.createElement('button');
					remove.type = 'button';
					remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="' + iconHref('x') + '"></use></svg><span class="visually-hidden">Remove ' + optionText(option).replace(/</g, '&lt;') + '</span>';
					remove.addEventListener('click', function () {
						option.selected = false;
						select.dispatchEvent(new Event('change', { bubbles: true }));
						refresh();
					});
					chip.appendChild(remove);
					chips.appendChild(chip);
				});
			} else {
				var current = chosen[0];
				value.textContent = current ? optionText(current) : (optionText(select.options[0] || document.createElement('option')) || 'Choose');
				value.classList.toggle('placeholder', !current);
			}
		}

		// The select stays in the form, hidden; the server checks what it needs.
		select.removeAttribute('required');
		select.classList.add('picker-native');
		select.tabIndex = -1;
		select.setAttribute('aria-hidden', 'true');
		select.parentNode.insertBefore(button, select);
		if (select.multiple) { select.parentNode.insertBefore(chips, select.nextSibling); }
		if (label) {
			label.addEventListener('click', function (event) { event.preventDefault(); button.focus(); });
		}
		button.addEventListener('click', function () { openPicker(select, button, refresh); });
		button.addEventListener('keydown', function (event) {
			if (event.key === 'ArrowDown' || (event.key.length === 1 && !event.ctrlKey && !event.metaKey)) {
				event.preventDefault();
				openPicker(select, button, refresh);
				if (event.key.length === 1) {
					var search = $('input', pickerDialog);
					search.value = event.key;
					search.dispatchEvent(new Event('input'));
				}
			}
		});
		select.addEventListener('change', refresh);
		refresh();
	}

	/* ------------------------------------------------------------------
	 * Small things
	 */

	document.addEventListener('click', function (event) {
		var button = event.target.closest('[data-copy]');
		if (!button || !navigator.clipboard) { return; }
		navigator.clipboard.writeText(button.getAttribute('data-copy')).then(function () {
			var label = $('.copy-label', button);
			if (!label) { return; }
			var was = label.textContent;
			label.textContent = button.getAttribute('data-copied') || 'Copied';
			setTimeout(function () { label.textContent = was; }, 2000);
		});
	});

	// A select that goes somewhere when changed (a day, a division).
	document.addEventListener('change', function (event) {
		var select = event.target.closest('select[data-navigate]');
		if (select && select.value) { window.location = select.value; }
	});

	/* ------------------------------------------------------------------
	 * Lists that can be filtered and sorted where they are, for the pages
	 * that ask for it (data-filterable-lists), however their panes arrive.
	 */

	function cellValue(row, index) {
		var cell = row.cells[index];
		return cell ? cell.textContent.replace(/\s+/g, ' ').trim() : '';
	}

	function sortBy(table, index, th) {
		var body = table.tBodies[0];
		var rows = Array.prototype.slice.call(body.rows).filter(function (row) { return row.cells.length > 1; });
		var ascending = th.getAttribute('aria-sort') !== 'ascending';
		var numeric = rows.every(function (row) { var v = cellValue(row, index); return v === '' || !isNaN(parseFloat(v)); });
		rows.sort(function (a, b) {
			var x = cellValue(a, index), y = cellValue(b, index);
			var order = numeric ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : x.localeCompare(y, undefined, { numeric: true, sensitivity: 'base' });
			return ascending ? order : -order;
		});
		rows.forEach(function (row) { body.appendChild(row); });
		$$('th[aria-sort]', table).forEach(function (other) { other.removeAttribute('aria-sort'); });
		th.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
	}

	function enhanceLists(root) {
		var scope = root.closest ? root.closest('[data-filterable-lists]') : null;
		var tables = scope ? $$('table.listing', root) : $$('[data-filterable-lists] table.listing', root);
		tables.forEach(function (table) {
			if (table.hasAttribute('data-enhanced') || !table.tBodies[0]) { return; }
			table.setAttribute('data-enhanced', '');
			var wrap = table.closest('.table-wrap') || table;
			var heading = wrap.parentNode.querySelector('.list-head h2');
			var filter = document.createElement('input');
			filter.type = 'search';
			filter.className = 'filter-box';
			filter.placeholder = 'Filter';
			filter.setAttribute('aria-label', 'Filter ' + (heading ? heading.textContent.trim().toLowerCase() : 'the list'));
			filter.addEventListener('input', function () {
				var terms = filter.value.toLowerCase().trim();
				Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
					row.hidden = terms !== '' && row.textContent.toLowerCase().indexOf(terms) < 0;
				});
			});
			wrap.parentNode.insertBefore(filter, wrap);
			$$('thead th', table).forEach(function (th, index) {
				if (th.classList.contains('actions-cell') || !th.textContent.trim()) { return; }
				var button = document.createElement('button');
				button.type = 'button';
				button.className = 'sort';
				while (th.firstChild) { button.appendChild(th.firstChild); }
				th.appendChild(button);
				button.addEventListener('click', function () { sortBy(table, index, th); });
			});
		});
	}

	// The number beside a tab: the rows its pane lists, once they are there.
	function countTabs() {
		$$('[data-count-of]').forEach(function (badge) {
			var pane = document.getElementById(badge.getAttribute('data-count-of'));
			var body = pane && $('table.listing tbody', pane);
			if (!body || $('.pager', pane)) { return; }
			var rows = Array.prototype.filter.call(body.rows, function (row) { return !$('.empty-state', row); });
			badge.textContent = rows.length;
			badge.hidden = false;
		});
	}

	function enhance(root) {
		countTabs();
		enhanceLists(root);
		preparePopovers(root);
		$$('select', root).forEach(enhancePicker);
	}

	enhance(document);
	syncPanelButtons();
	document.body.addEventListener('htmx:load', function (event) {
		if (event.target !== document.body) { enhance(event.target); }
	});

	window.vitriolicAdmin = { enhance: enhance, closeRail: closeRail };
})();
