/*
 * Workbook: the admin's enhancements. Every page works without this file;
 * it folds the menu away on a phone, turns the parts of an edit page into
 * tabs, opens a searchable dialog for long lists of choices, asks before a
 * delete, and keeps row menus beside the button that opened them.
 *
 * Plain JavaScript, no build step. Content that arrives later over htmx is
 * enhanced as it arrives.
 */
(function () {
	"use strict";

	var wide = window.matchMedia("(min-width: 64rem)");
	var uid = 0;

	function nextId(prefix) {
		uid += 1;
		return prefix + "-" + uid;
	}

	function each(root, selector, fn) {
		Array.prototype.forEach.call(root.querySelectorAll(selector), fn);
	}

	function text(el) {
		return (el.textContent || "").replace(/\s+/g, " ").trim();
	}

	/* ------------------------------------------------------------------
	 * The menu: the rail slides in over the page on a phone.
	 */

	function menu() {
		var rail = document.querySelector("[data-wb-rail]");
		var scrim = document.querySelector(".wb-scrim");
		var openers = document.querySelectorAll("[data-wb-menu]");
		if (!rail) {
			return;
		}

		function set(open) {
			rail.classList.toggle("is-open", open);
			if (scrim) {
				scrim.hidden = !open;
			}
			Array.prototype.forEach.call(openers, function (button) {
				button.setAttribute("aria-expanded", open ? "true" : "false");
			});
			document.documentElement.style.overflow = open && !wide.matches ? "hidden" : "";
			if (open) {
				var first = rail.querySelector(".wb-nav a");
				if (first) {
					first.focus({ preventScroll: true });
				}
			}
		}

		Array.prototype.forEach.call(openers, function (button) {
			button.addEventListener("click", function () {
				set(!rail.classList.contains("is-open"));
			});
		});
		each(document, "[data-wb-menu-close]", function (el) {
			el.addEventListener("click", function () {
				set(false);
				if (openers[0]) {
					openers[0].focus();
				}
			});
		});
		document.addEventListener("keydown", function (event) {
			if (event.key === "Escape" && rail.classList.contains("is-open")) {
				set(false);
				if (openers[0]) {
					openers[0].focus();
				}
			}
		});
		wide.addEventListener("change", function () {
			set(false);
		});
	}

	/* ------------------------------------------------------------------
	 * Tabs: one part of an object at a time. Without scripts every part is
	 * on the page, one after another, and the tabs are links to them.
	 */

	var tabSets = [];

	function tabsOf(list) {
		return Array.prototype.filter.call(list.querySelectorAll("[role=tab]"), function (tab) {
			return tab.closest("[role=tablist]") === list;
		});
	}

	function paneOf(tab) {
		var id = tab.getAttribute("aria-controls") || (tab.getAttribute("href") || "").replace(/^#/, "");
		return id ? document.getElementById(id) : null;
	}

	function select(list, tab, focus) {
		tabsOf(list).forEach(function (other) {
			var on = other === tab;
			other.setAttribute("aria-selected", on ? "true" : "false");
			other.setAttribute("tabindex", on ? "0" : "-1");
			var pane = paneOf(other);
			if (pane) {
				pane.hidden = !on;
			}
		});
		var pane = paneOf(tab);
		if (pane) {
			pane.dispatchEvent(new CustomEvent("wb:shown", { bubbles: true }));
		}
		if (focus) {
			tab.focus();
		}
		try {
			sessionStorage.setItem("wb-tab:" + location.pathname, tab.getAttribute("aria-controls"));
		} catch (err) {
			/* storage may be unavailable; the hash still says which tab */
		}
	}

	function tabFor(id) {
		for (var i = 0; i < tabSets.length; i += 1) {
			var tabs = tabsOf(tabSets[i]);
			for (var j = 0; j < tabs.length; j += 1) {
				if (tabs[j].id === id || tabs[j].getAttribute("aria-controls") === id) {
					return { list: tabSets[i], tab: tabs[j] };
				}
			}
		}
		return null;
	}

	/* The tab that holds the element with ``id``, whether a pane or inside one. */
	function showTarget(id, focus) {
		if (!id) {
			return false;
		}
		var found = tabFor(id);
		if (!found) {
			var el = document.getElementById(id);
			var pane = el && el.closest("[role=tabpanel]");
			found = pane ? tabFor(pane.id) : null;
		}
		if (found) {
			select(found.list, found.tab, focus);
			return true;
		}
		return false;
	}

	function tabs(root) {
		each(root, "[role=tablist][data-wb-tabs]", function (list) {
			if (list.dataset.wbReady) {
				return;
			}
			list.dataset.wbReady = "1";
			tabSets.push(list);
			var all = tabsOf(list);
			if (!all.length) {
				return;
			}
			var panes = list.parentNode.querySelector(".wb-panes");
			if (panes) {
				panes.classList.add("is-tabbed");
			}
			all.forEach(function (tab) {
				var pane = paneOf(tab);
				if (!tab.id) {
					tab.id = nextId("wb-tab");
				}
				if (pane) {
					tab.setAttribute("aria-controls", pane.id);
					pane.setAttribute("aria-labelledby", tab.id);
				}
				tab.addEventListener("click", function (event) {
					// The address stays as it is; the tab last shown is
					// remembered for coming back to the page.
					event.preventDefault();
					select(list, tab, false);
				});
				tab.addEventListener("keydown", function (event) {
					var index = all.indexOf(tab);
					var to = null;
					if (event.key === "ArrowRight" || event.key === "ArrowDown") {
						to = all[(index + 1) % all.length];
					} else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
						to = all[(index - 1 + all.length) % all.length];
					} else if (event.key === "Home") {
						to = all[0];
					} else if (event.key === "End") {
						to = all[all.length - 1];
					}
					if (to) {
						event.preventDefault();
						select(list, to, true);
					}
				});
			});

			// Which tab to show: the one the address names; else, coming back
			// from a page below this one, the tab last shown here; else the
			// first with a problem; else the one the page marked.
			var chosen = null;
			var hash = decodeURIComponent(location.hash.replace(/^#/, ""));
			if (hash) {
				var named = tabFor(hash);
				if (!named) {
					var target = document.getElementById(hash);
					var pane = target && target.closest("[role=tabpanel]");
					named = pane ? tabFor(pane.id) : null;
				}
				if (named && named.list === list) {
					chosen = named.tab;
				}
			}
			if (!chosen && document.referrer) {
				try {
					var there = new URL(document.referrer).pathname;
					if (there !== location.pathname && there.indexOf(location.pathname) === 0) {
						var last = sessionStorage.getItem("wb-tab:" + location.pathname);
						var remembered = last ? tabFor(last) : null;
						if (remembered && remembered.list === list) {
							chosen = remembered.tab;
						}
					}
				} catch (err) {
					/* a referrer that is not a URL, or no storage */
				}
			}
			if (!chosen) {
				all.some(function (tab) {
					var pane = paneOf(tab);
					if (pane && pane.querySelector("[aria-invalid=true], .wb-problems")) {
						chosen = tab;
						return true;
					}
					return false;
				});
			}
			if (!chosen) {
				chosen = all.filter(function (tab) {
					return tab.getAttribute("aria-selected") === "true";
				})[0] || all[0];
			}
			select(list, chosen, false);
			// The address named a tab: show the page from its top, with the
			// heading and the tabs, rather than jumping to the pane.
			if (hash && (chosen.id === hash || chosen.getAttribute("aria-controls") === hash)) {
				window.scrollTo(0, 0);
				window.addEventListener("load", function () {
					window.scrollTo(0, 0);
				});
			}
		});
	}

	function tabLinks() {
		// A link elsewhere on the page to a pane (a checklist step, say) shows it.
		document.addEventListener("click", function (event) {
			var link = event.target.closest && event.target.closest("a[href]");
			if (!link || link.getAttribute("role") === "tab") {
				return;
			}
			var url;
			try {
				url = new URL(link.href, location.href);
			} catch (err) {
				return;
			}
			if (url.pathname !== location.pathname || !url.hash) {
				return;
			}
			var id = decodeURIComponent(url.hash.slice(1));
			if (showTarget(id, false)) {
				event.preventDefault();
				if (history.replaceState) {
					history.replaceState(null, "", url.hash);
				}
				var el = document.getElementById(id);
				var tab = tabFor(id);
				var into = tab ? tab.list : el;
				if (into) {
					into.scrollIntoView({ block: "start", behavior: "smooth" });
				}
			}
		});
		window.addEventListener("hashchange", function () {
			showTarget(decodeURIComponent(location.hash.replace(/^#/, "")), false);
		});
	}

	/* ------------------------------------------------------------------
	 * Pickers: a long list of choices opens in a dialog with a search box.
	 * The select stays in the form and is what is submitted.
	 */

	var pickerDialog = null;

	function labelFor(control) {
		if (control.id) {
			var label = document.querySelector('label[for="' + control.id + '"]');
			if (label) {
				return label;
			}
		}
		return null;
	}

	function optionsOf(source) {
		var options = [];
		if (source.tagName === "SELECT") {
			Array.prototype.forEach.call(source.options, function (option) {
				if (option.value === "" && !source.multiple) {
					return;
				}
				var group = option.parentNode.tagName === "OPTGROUP" ? option.parentNode.label : "";
				options.push({ label: text(option), value: option.value, group: group, node: option });
			});
		} else {
			each(source, "input[type=checkbox]", function (input) {
				var label = input.closest("label") || labelFor(input);
				options.push({ label: label ? text(label) : input.value, value: input.value, group: "", node: input });
			});
		}
		return options;
	}

	function isChosen(option) {
		return option.node.tagName === "OPTION" ? option.node.selected : option.node.checked;
	}

	function setChosen(option, on) {
		if (option.node.tagName === "OPTION") {
			option.node.selected = on;
		} else {
			option.node.checked = on;
		}
	}

	function words(value) {
		return value.toLowerCase().split(/\s+/).filter(Boolean);
	}

	function ensurePickerDialog() {
		if (pickerDialog) {
			return pickerDialog;
		}
		var dialog = document.createElement("dialog");
		dialog.className = "wb-dialog wb-pick-dialog";
		dialog.setAttribute("aria-labelledby", "wb-pick-title");
		dialog.innerHTML =
			'<div class="wb-dialog-body">' +
			'<h2 class="wb-dialog-title" id="wb-pick-title"></h2>' +
			'<div class="wb-pick-search">' +
			'<input type="search" class="wb-input" autocomplete="off" aria-label="Search" aria-controls="wb-pick-list" aria-autocomplete="list">' +
			"</div>" +
			'<ul class="wb-pick-list" id="wb-pick-list" role="listbox"></ul>' +
			'<div class="wb-dialog-actions">' +
			'<p class="wb-pick-count" aria-live="polite"></p>' +
			'<button type="button" class="wb-button wb-button-quiet" data-wb-pick-clear>Clear</button>' +
			'<button type="button" class="wb-button wb-button-primary" data-wb-pick-done>Done</button>' +
			"</div></div>";
		document.body.appendChild(dialog);
		var icon = document.querySelector("svg.wb-icon use");
		if (icon) {
			var sprite = icon.getAttribute("href").split("#")[0];
			dialog.querySelector(".wb-pick-search").insertAdjacentHTML(
				"afterbegin",
				'<svg class="wb-icon" aria-hidden="true"><use href="' + sprite + '#search"></use></svg>'
			);
		}
		pickerDialog = dialog;
		return dialog;
	}

	function openPicker(picker) {
		var dialog = ensurePickerDialog();
		var source = picker.source;
		var multiple = picker.multiple;
		var options = optionsOf(source);
		var title = dialog.querySelector(".wb-dialog-title");
		var search = dialog.querySelector("input[type=search]");
		var list = dialog.querySelector(".wb-pick-list");
		var count = dialog.querySelector(".wb-pick-count");
		var clear = dialog.querySelector("[data-wb-pick-clear]");
		var done = dialog.querySelector("[data-wb-pick-done]");
		var shown = [];
		var active = -1;

		title.textContent = picker.title;
		search.value = "";
		search.setAttribute("aria-label", "Search " + picker.title.toLowerCase());
		list.classList.toggle("is-multiple", multiple);
		list.setAttribute("aria-multiselectable", multiple ? "true" : "false");
		clear.hidden = !picker.clearable;

		function draw() {
			var query = words(search.value);
			list.innerHTML = "";
			shown = [];
			var group = null;
			options.forEach(function (option, index) {
				var haystack = (option.label + " " + option.group).toLowerCase();
				var hit = query.every(function (word) {
					return haystack.indexOf(word) !== -1;
				});
				if (!hit) {
					return;
				}
				if (option.group && option.group !== group) {
					group = option.group;
					var heading = document.createElement("li");
					heading.className = "wb-pick-group";
					heading.setAttribute("role", "presentation");
					heading.textContent = group;
					list.appendChild(heading);
				}
				var item = document.createElement("li");
				item.id = "wb-pick-" + index;
				item.setAttribute("role", "option");
				item.setAttribute("aria-selected", isChosen(option) ? "true" : "false");
				item.textContent = option.label;
				item.addEventListener("click", function () {
					choose(option, item);
				});
				item.addEventListener("mousemove", function () {
					activate(shown.indexOf(item));
				});
				list.appendChild(item);
				shown.push(item);
			});
			if (!shown.length) {
				var none = document.createElement("li");
				none.className = "wb-pick-none";
				none.setAttribute("role", "presentation");
				none.textContent = "Nothing matches “" + search.value + "”.";
				list.appendChild(none);
			}
			var chosen = options.filter(isChosen).length;
			count.textContent = multiple ? chosen + " chosen" : shown.length + " of " + options.length;
			activate(shown.length ? 0 : -1);
		}

		function activate(index) {
			if (active >= 0 && shown[active]) {
				shown[active].classList.remove("is-active");
			}
			active = index;
			if (index >= 0 && shown[index]) {
				shown[index].classList.add("is-active");
				shown[index].scrollIntoView({ block: "nearest" });
				search.setAttribute("aria-activedescendant", shown[index].id);
			} else {
				search.removeAttribute("aria-activedescendant");
			}
		}

		function changed() {
			source.dispatchEvent(new Event("change", { bubbles: true }));
			picker.refresh();
		}

		function choose(option, item, close) {
			if (multiple) {
				setChosen(option, !isChosen(option));
				item.setAttribute("aria-selected", isChosen(option) ? "true" : "false");
				count.textContent = options.filter(isChosen).length + " chosen";
				changed();
				if (close) {
					finish();
				}
			} else {
				options.forEach(function (other) {
					setChosen(other, other === option);
				});
				changed();
				finish();
			}
		}

		function finish() {
			dialog.close();
		}

		search.oninput = draw;
		search.onkeydown = function (event) {
			if (event.key === "ArrowDown") {
				event.preventDefault();
				activate(Math.min(active + 1, shown.length - 1));
			} else if (event.key === "ArrowUp") {
				event.preventDefault();
				activate(Math.max(active - 1, 0));
			} else if (event.key === "Enter") {
				event.preventDefault();
				if (active >= 0 && shown[active]) {
					var index = parseInt(shown[active].id.replace("wb-pick-", ""), 10);
					choose(options[index], shown[active], true);
				} else {
					finish();
				}
			}
		};
		clear.onclick = function () {
			options.forEach(function (option) {
				setChosen(option, false);
			});
			if (!multiple && source.tagName === "SELECT") {
				source.value = "";
			}
			changed();
			draw();
			if (!multiple) {
				finish();
			}
		};
		done.onclick = finish;
		dialog.onclose = function () {
			picker.button.setAttribute("aria-expanded", "false");
			picker.closedAt = Date.now();
			// After the key that closed the dialog has finished with it, so an
			// Enter that chose an option does not press the button again.
			setTimeout(function () {
				picker.button.focus();
			}, 0);
		};

		draw();
		dialog.showModal();
		picker.button.setAttribute("aria-expanded", "true");
		search.focus();
	}

	function pickers(root) {
		var sources = [];
		each(root, "select[data-picker]", function (select) {
			sources.push(select);
		});
		// A long list of checkboxes is one control: find each list once.
		each(root, "input[type=checkbox][data-picker]", function (input) {
			var container = input.closest(".wb-control-wrap") || input.parentNode.parentNode;
			if (sources.indexOf(container) === -1) {
				sources.push(container);
			}
		});
		sources.forEach(function (source) {
			if (source.dataset.wbPicker) {
				return;
			}
			source.dataset.wbPicker = "1";
			var multiple = source.tagName !== "SELECT" || source.multiple;
			var control = source.tagName === "SELECT" ? source : source.querySelector("input");
			var label = labelFor(control) || (source.closest(".wb-field") || document).querySelector(".wb-label label, .wb-label .field_name");
			var title = label ? text(label).replace(/:$/, "") : "Choose";
			if (label && !label.id) {
				label.id = nextId("wb-label");
			}
			var button = document.createElement("button");
			var value = document.createElement("span");
			button.type = "button";
			button.className = "wb-picker";
			button.setAttribute("role", "combobox");
			button.setAttribute("aria-haspopup", "dialog");
			button.setAttribute("aria-expanded", "false");
			value.id = nextId("wb-picker-value");
			value.className = "wb-picker-value";
			button.setAttribute("aria-labelledby", (label ? label.id + " " : "") + value.id);
			button.appendChild(value);
			var sprite = document.querySelector("svg.wb-icon use");
			var caret = sprite
				? '<svg class="wb-icon" aria-hidden="true"><use href="' + sprite.getAttribute("href").split("#")[0] + '#chevron-down"></use></svg>'
				: "\u25be";
			button.insertAdjacentHTML("beforeend", '<span class="wb-picker-caret" aria-hidden="true">' + caret + "</span>");
			if (control.getAttribute("aria-describedby")) {
				button.setAttribute("aria-describedby", control.getAttribute("aria-describedby"));
			}
			if (control.getAttribute("aria-invalid")) {
				button.setAttribute("aria-invalid", control.getAttribute("aria-invalid"));
			}
			source.classList.add("wb-picker-native");
			source.setAttribute("tabindex", "-1");
			source.setAttribute("aria-hidden", "true");
			source.parentNode.insertBefore(button, source);
			if (source.tagName !== "SELECT") {
				source.hidden = true;
			}

			var picker = {
				source: source,
				button: button,
				multiple: multiple,
				title: title,
				clearable: multiple || (source.tagName === "SELECT" && !source.required),
				refresh: function () {
					var chosen = optionsOf(source).filter(isChosen).map(function (option) {
						return option.label;
					});
					if (!chosen.length) {
						value.textContent = multiple ? "None chosen" : "Choose…";
						value.classList.add("is-empty");
					} else {
						value.textContent = multiple && chosen.length > 2
							? chosen.slice(0, 2).join(", ") + " and " + (chosen.length - 2) + " more"
							: chosen.join(", ");
						value.classList.remove("is-empty");
					}
				}
			};
			picker.refresh();
			button.addEventListener("click", function () {
				if (picker.closedAt && Date.now() - picker.closedAt < 400) {
					return;
				}
				openPicker(picker);
			});
			if (label) {
				label.addEventListener("click", function (event) {
					event.preventDefault();
					button.focus();
				});
			}
			source.addEventListener("change", picker.refresh);
		});
	}

	/* ------------------------------------------------------------------
	 * Confirmation: a delete or an undo asks first, in a dialog.
	 */

	function confirms() {
		var dialog = document.getElementById("wb-confirm");
		if (!dialog) {
			return;
		}
		var message = dialog.querySelector("[data-wb-confirm-text]");
		var go = dialog.querySelector("[data-wb-confirm-go]");
		var title = dialog.querySelector(".wb-dialog-title");
		var pending = null;

		document.addEventListener("submit", function (event) {
			var form = event.target;
			if (!form.hasAttribute || !form.hasAttribute("data-wb-confirm") || form.dataset.wbConfirmed) {
				return;
			}
			event.preventDefault();
			pending = form;
			if (!form.id) {
				form.id = nextId("wb-form");
			}
			var menu = form.closest("[popover]");
			if (menu && menu.hidePopover) {
				try {
					menu.hidePopover();
				} catch (err) {
					/* already hidden */
				}
			}
			title.textContent = form.dataset.wbConfirmTitle || "Are you sure?";
			message.textContent = form.getAttribute("data-wb-confirm");
			go.textContent = form.dataset.wbConfirmLabel || "Delete";
			go.className = "wb-button " + (form.dataset.wbConfirmTone === "plain" ? "wb-button-primary" : "wb-button-danger");
			// The confirming button submits the form itself, so the page moves
			// on as the button is pressed.
			go.setAttribute("form", form.id);
			go.removeAttribute("value");
			dialog.showModal();
		}, true);

		go.addEventListener("click", function () {
			if (pending) {
				pending.dataset.wbConfirmed = "1";
			}
		});

		dialog.addEventListener("close", function () {
			go.removeAttribute("form");
			pending = null;
		});
	}

	/* ------------------------------------------------------------------
	 * Dialogs opened by a button: "Add several", for one.
	 */

	function dialogs(root) {
		each(root, "[data-wb-dialog]", function (button) {
			if (button.dataset.wbReady) {
				return;
			}
			button.dataset.wbReady = "1";
			var dialog = document.getElementById(button.getAttribute("data-wb-dialog"));
			if (!dialog) {
				return;
			}
			button.setAttribute("aria-haspopup", "dialog");
			// With scripts the button only opens the dialog, so pressing Enter
			// in the dialog submits with the dialog's own button.
			if (button.type === "submit") {
				button.type = "button";
			}
			button.addEventListener("click", function (event) {
				event.preventDefault();
				dialog.showModal();
				var first = dialog.querySelector("input:not([type=hidden]), select, textarea");
				if (first) {
					first.focus();
					if (first.select) {
						first.select();
					}
				}
			});
			each(dialog, "[data-wb-dialog-close]", function (close) {
				close.addEventListener("click", function () {
					dialog.close();
				});
			});
		});
	}

	/* ------------------------------------------------------------------
	 * Row menus: a popover beside the button that opened it.
	 */

	function menus(root) {
		each(root, "[popover].wb-menu", function (menu) {
			if (menu.dataset.wbReady) {
				return;
			}
			menu.dataset.wbReady = "1";
			var opener = root.querySelector('[popovertarget="' + menu.id + '"]') ||
				document.querySelector('[popovertarget="' + menu.id + '"]');
			menu.addEventListener("toggle", function (event) {
				var open = event.newState === "open";
				if (opener) {
					opener.setAttribute("aria-expanded", open ? "true" : "false");
				}
				if (open && opener) {
					var box = opener.getBoundingClientRect();
					var width = menu.offsetWidth;
					var height = menu.offsetHeight;
					var left = Math.max(8, Math.min(box.right - width, window.innerWidth - width - 8));
					var top = box.bottom + 6;
					if (top + height > window.innerHeight - 8) {
						top = Math.max(8, box.top - height - 6);
					}
					menu.style.left = left + "px";
					menu.style.top = top + "px";
					var first = menu.querySelector("a, button");
					if (first) {
						first.focus({ preventScroll: true });
					}
				}
			});
		});
	}

	/* ------------------------------------------------------------------
	 * A checklist is open at a desk and folded on a phone.
	 */

	function checklists(root) {
		each(root, "details[data-wb-fold-narrow]", function (details) {
			if (!wide.matches) {
				details.open = false;
			}
		});
	}

	/* ------------------------------------------------------------------
	 * Copy buttons: data-wb-copy holds the text to copy.
	 */

	function copies() {
		document.addEventListener("click", function (event) {
			var button = event.target.closest && event.target.closest("[data-wb-copy]");
			if (!button || !navigator.clipboard) {
				return;
			}
			navigator.clipboard.writeText(button.getAttribute("data-wb-copy")).then(function () {
				var label = button.querySelector("span");
				if (!label) {
					return;
				}
				var was = label.textContent;
				label.textContent = button.getAttribute("data-wb-copied") || "Copied";
				setTimeout(function () {
					label.textContent = was;
				}, 2000);
			});
		});
	}

	/* ------------------------------------------------------------------
	 * Formsets that grow: data-wb-formset holds a <template> of an empty
	 * form (data-wb-formset-empty) and a button that adds one.
	 */

	function formsets(root) {
		each(root, "[data-wb-formset]", function (container) {
			if (container.dataset.wbReady) {
				return;
			}
			container.dataset.wbReady = "1";
			var add = container.querySelector("[data-wb-formset-add]");
			var template = container.querySelector("template[data-wb-formset-empty]");
			var rows = container.querySelector("[data-wb-formset-rows]");
			var total = container.querySelector("input[name$='TOTAL_FORMS']");
			if (!add || !template || !rows || !total) {
				return;
			}
			var prefix = total.name.replace(/-TOTAL_FORMS$/, "");
			var pattern = new RegExp("^" + prefix + "-\\d+-");

			// After a row goes, the rows that follow are numbered down by one.
			function renumber() {
				var count = 0;
				Array.prototype.forEach.call(rows.children, function (row) {
					if (row.hasAttribute("data-wb-formset-none")) {
						return;
					}
					each(row, "[name], [id], label[for]", function (el) {
						["name", "id", "for"].forEach(function (attribute) {
							var value = el.getAttribute(attribute);
							if (value) {
								el.setAttribute(attribute, value.replace(pattern, prefix + "-" + count + "-").replace(new RegExp("^id_" + prefix + "-\\d+-"), "id_" + prefix + "-" + count + "-"));
							}
						});
					});
					count += 1;
				});
				total.value = count;
			}

			container.addEventListener("click", function (event) {
				var remove = event.target.closest && event.target.closest("[data-wb-formset-remove]");
				if (!remove) {
					return;
				}
				var row = remove.closest(".wb-row-form");
				if (row) {
					row.remove();
					renumber();
				}
			});

			add.addEventListener("click", function () {
				var index = parseInt(total.value, 10) || 0;
				var html = template.innerHTML.replace(/__prefix__/g, String(index));
				var none = rows.querySelector("[data-wb-formset-none]");
				if (none) {
					none.remove();
				}
				rows.insertAdjacentHTML("beforeend", html);
				total.value = index + 1;
				var added = rows.lastElementChild;
				enhance(added);
				var first = added && added.querySelector("input:not([type=hidden]), select, textarea, button.wb-picker");
				if (first) {
					first.focus();
				}
			});
		});
	}

	/* ------------------------------------------------------------------
	 * Lists that sort by any column, and long lists in a tab that filter as
	 * you type. The server's order and every row are there without scripts.
	 */

	function cellValue(row, index) {
		var cell = row.cells[index];
		var value = cell ? text(cell) : "";
		var number = parseFloat(value.replace(/[^0-9.\-]/g, ""));
		return { text: value.toLowerCase(), number: /^[-0-9.,\s/]+$/.test(value) && !isNaN(number) ? number : null };
	}

	function sortables(root) {
		each(root, "table[data-wb-sortable]", function (table) {
			if (table.dataset.wbReady || !table.tBodies[0]) {
				return;
			}
			table.dataset.wbReady = "1";
			var body = table.tBodies[0];
			if (body.rows.length < 2 || body.querySelector(".wb-table-empty")) {
				return;
			}
			each(table, "thead th", function (th) {
				var label = text(th);
				if (!label || th.querySelector(".wb-sr")) {
					return;
				}
				var index = th.cellIndex;
				var button = document.createElement("button");
				button.type = "button";
				button.className = "wb-sort";
				button.textContent = label;
				th.textContent = "";
				th.appendChild(button);
				button.addEventListener("click", function () {
					var ascending = th.getAttribute("aria-sort") !== "ascending";
					each(table, "thead th[aria-sort]", function (other) {
						other.removeAttribute("aria-sort");
					});
					th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
					var rows = Array.prototype.slice.call(body.rows);
					rows.sort(function (a, b) {
						var x = cellValue(a, index);
						var y = cellValue(b, index);
						var order = x.number !== null && y.number !== null
							? x.number - y.number
							: x.text.localeCompare(y.text, undefined, { numeric: true });
						return ascending ? order : -order;
					});
					rows.forEach(function (row) {
						body.appendChild(row);
					});
				});
			});
		});
	}

	function filters(root) {
		each(root, "input[data-wb-filter]", function (input) {
			if (input.dataset.wbReady) {
				return;
			}
			input.dataset.wbReady = "1";
			var scope = input.closest(".wb-pane, .wb-sheet") || document;
			input.addEventListener("input", function () {
				var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
				each(scope, "table tbody tr", function (row) {
					var haystack = text(row).toLowerCase();
					row.hidden = !words.every(function (word) {
						return haystack.indexOf(word) !== -1;
					});
				});
			});
		});
	}

	function enhance(root) {
		tabs(root);
		pickers(root);
		dialogs(root);
		menus(root);
		formsets(root);
		sortables(root);
		filters(root);
	}

	menu();
	copies();
	tabLinks();
	confirms();
	checklists(document);
	enhance(document);

	document.addEventListener("htmx:load", function (event) {
		enhance(event.target);
	});
})();
