/*
 * Console: the behaviour the admin adds to plain HTML forms and links.
 *
 * Everything here is an enhancement. Every form posts and every link goes
 * somewhere without it. No framework; htmx (loaded before this file) fetches
 * the jump results and lazily loaded tabs.
 */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var ICONS = (doc.querySelector('link[rel="stylesheet"][href*="console.css"]') || {}).href;
  ICONS = ICONS ? ICONS.replace(/console\.css.*$/, "icons.svg") : "";

  function $(sel, scope) { return (scope || doc).querySelector(sel); }
  function $$(sel, scope) { return Array.prototype.slice.call((scope || doc).querySelectorAll(sel)); }
  function icon(name) {
    return '<svg class="i" aria-hidden="true" focusable="false"><use href="' + ICONS + "#i-" + name + '"></use></svg>';
  }
  function each(scope, sel, fn) {
    if (scope.matches && scope.matches(sel)) fn(scope);
    $$(sel, scope).forEach(fn);
  }
  function typing(target) {
    return target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
  }

  /* ------------------------------------------------------------------ rail */

  var STORE = "console:rail:";
  function setGroup(button, open) {
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }
  $$(".rail__head").forEach(function (button) {
    var key = STORE + button.getAttribute("aria-controls");
    var group = button.closest(".rail__group");
    var stored = null;
    try { stored = sessionStorage.getItem(key); } catch (e) {}
    if (!group.hasAttribute("data-current") && stored === "open") setGroup(button, true);
    button.addEventListener("click", function () {
      var open = button.getAttribute("aria-expanded") !== "true";
      setGroup(button, open);
      try { sessionStorage.setItem(key, open ? "open" : "closed"); } catch (e) {}
    });
  });

  var rail = $("#rail");
  var opener = $("[data-rail-open]");
  function openRail() {
    root.classList.add("rail-open");
    if (opener) opener.setAttribute("aria-expanded", "true");
    var current = $(".rail__items a[aria-current]", rail) || $(".jump-trigger", rail);
    if (current) current.focus();
  }
  function closeRail() {
    if (!root.classList.contains("rail-open")) return;
    root.classList.remove("rail-open");
    if (opener) { opener.setAttribute("aria-expanded", "false"); opener.focus(); }
  }
  if (opener) opener.addEventListener("click", openRail);
  $$("[data-rail-close]").forEach(function (b) { b.addEventListener("click", closeRail); });
  doc.addEventListener("click", function (e) {
    if (root.classList.contains("rail-open") && rail && !rail.contains(e.target) && !e.target.closest("[data-rail-open]")) closeRail();
  });

  /* ------------------------------------------------------------------ tabs */

  var TAB_KEY = "console:tab:" + location.pathname;

  function showTab(tab, focus, remember) {
    var list = tab.closest('[role="tablist"]');
    $$('[role="tab"]', list).forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.setAttribute("tabindex", on ? "0" : "-1");
      var pane = doc.getElementById(t.getAttribute("aria-controls"));
      if (pane) {
        pane.classList.toggle("is-active", on);
        if (on && window.htmx) htmx.trigger(pane, "console:shown");
      }
    });
    if (focus) tab.focus();
    if (remember) {
      try { sessionStorage.setItem(TAB_KEY, tab.getAttribute("aria-controls")); } catch (e) {}
      if (history.replaceState) history.replaceState(null, "", "#" + tab.getAttribute("aria-controls"));
    }
  }

  function tabFor(id) {
    return id ? $('[role="tab"][aria-controls="' + CSS.escape(id) + '"]') : null;
  }

  function initTabs(scope) {
    each(scope, '[role="tablist"]', function (list) {
      if (list.dataset.ready) return;
      list.dataset.ready = "1";
      var tabs = $$('[role="tab"]', list);
      if (!tabs.length) { list.hidden = true; $$('[role="tabpanel"]').forEach(function (p) { p.classList.add("is-active"); }); return; }
      list.addEventListener("click", function (e) {
        var tab = e.target.closest('[role="tab"]');
        if (!tab) return;
        e.preventDefault();
        showTab(tab, false, true);
      });
      list.addEventListener("keydown", function (e) {
        var i = tabs.indexOf(doc.activeElement);
        if (i < 0) return;
        var next = null;
        if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        else if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        else if (e.key === "Home") next = tabs[0];
        else if (e.key === "End") next = tabs[tabs.length - 1];
        if (next) { e.preventDefault(); showTab(next, true, true); }
      });
      // Which tab to show: the address says, or the one last used on this page
      // when coming back to it from something listed in a tab, or an error.
      var chosen = tabFor(location.hash.slice(1));
      if (!chosen) {
        var ref = null;
        try { ref = new URL(doc.referrer); } catch (e) {}
        if (ref && ref.origin === location.origin && ref.pathname !== location.pathname &&
            ref.pathname.indexOf(location.pathname) === 0) {
          var last = null;
          try { last = sessionStorage.getItem(TAB_KEY); } catch (e) {}
          chosen = tabFor(last);
        }
      }
      var invalid = $('[role="tabpanel"] [aria-invalid="true"], [role="tabpanel"] .non-field-errors');
      if (invalid) chosen = tabFor(invalid.closest('[role="tabpanel"]').id) || chosen;
      showTab(chosen || tabs[0], false, false);
    });
  }

  // A link inside a tab remembers that tab, so coming back shows it again.
  doc.addEventListener("click", function (e) {
    var a = e.target.closest("a[href]");
    var pane = a && a.closest('[role="tabpanel"]');
    if (pane) { try { sessionStorage.setItem(TAB_KEY, pane.id); } catch (err) {} }
  }, true);

  /* ------------------------------------------------------------------ jump */

  var jump = $("#jump");
  function openJump(text) {
    if (!jump || jump.open) return;
    closeRail();
    jump.showModal();
    var input = $('input[name="q"]', jump);
    if (typeof text === "string") input.value = text;
    input.focus();
    input.select();
  }
  doc.addEventListener("click", function (e) {
    var t = e.target.closest("[data-jump-open]");
    if (t && jump) { e.preventDefault(); openJump(); }
  });
  if (jump) {
    var hits = function () { return $$(".jump__hit", jump); };
    var move = function (step) {
      var list = hits();
      if (!list.length) return;
      var i = list.findIndex(function (a) { return a.getAttribute("aria-selected") === "true"; });
      list.forEach(function (a) { a.removeAttribute("aria-selected"); });
      var next = list[(i + step + list.length) % list.length];
      next.setAttribute("aria-selected", "true");
      next.scrollIntoView({ block: "nearest" });
      $('input[name="q"]', jump).setAttribute("aria-activedescendant", next.id || "");
    };
    jump.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter" && e.target.name === "q") {
        var chosen = $('.jump__hit[aria-selected="true"]', jump) || hits()[0];
        if (chosen) { e.preventDefault(); location.href = chosen.href; }
      }
    });
    jump.addEventListener("htmx:afterSwap", function () {
      hits().forEach(function (a, n) { a.id = "jump-hit-" + n; });
      var first = hits()[0];
      if (first) first.setAttribute("aria-selected", "true");
    });
    jump.addEventListener("click", function (e) { if (e.target === jump) jump.close(); });
  }
  $$("[data-dialog-close]").forEach(function (b) {
    b.addEventListener("click", function () { b.closest("dialog").close(); });
  });

  doc.addEventListener("keydown", function (e) {
    if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openJump(); return; }
    if (e.key === "/" && !typing(e.target) && !e.metaKey && !e.ctrlKey && !e.altKey && !doc.querySelector("dialog[open]")) {
      e.preventDefault(); openJump();
      return;
    }
    if (e.key === "Escape") closeRail();
    if ((e.key === "s" || e.key === "S") && (e.metaKey || e.ctrlKey)) {
      var save = $("[data-save]");
      if (save) { e.preventDefault(); save.click(); }
    }
  });

  /* --------------------------------------------------------------- confirm */

  var confirmBox = $("#confirm");
  var pending = null;
  doc.addEventListener("click", function (e) {
    var button = e.target.closest("[data-confirm]");
    if (!button || !confirmBox) return;
    if (button.dataset.confirmed) { delete button.dataset.confirmed; return; }
    e.preventDefault();
    $("#confirm-title").textContent = button.dataset.confirm;
    $("#confirm-text").textContent = button.dataset.confirmText || "";
    $("[data-confirm-go]", confirmBox).textContent = button.dataset.confirmLabel || button.textContent.trim();
    // Coming back from a delete shows the tab it was made in.
    var pane = button.closest('[role="tabpanel"]');
    if (pane && button.name === "next" && button.value.indexOf("#") < 0) button.value += "#" + pane.id;
    pending = button;
    var menu = button.closest("[popover]");
    if (menu && menu.hidePopover) { try { menu.hidePopover(); } catch (err) {} }
    confirmBox.showModal();
    $("[data-confirm-go]", confirmBox).focus();
  });
  if (confirmBox) {
    // The confirming click submits at once, so the page moves on with it.
    $("[data-confirm-go]", confirmBox).addEventListener("click", function (e) {
      e.preventDefault();
      var button = pending;
      pending = null;
      confirmBox.close();
      if (!button) return;
      button.dataset.confirmed = "1";
      var form = button.form;
      delete button.dataset.confirmed;
      if (form && form.requestSubmit) form.requestSubmit(button);
      else { button.dataset.confirmed = "1"; button.click(); }
    });
    confirmBox.addEventListener("close", function () { pending = null; });
  }

  /* ------------------------------------------------------------- row menus */

  doc.addEventListener("beforetoggle", function (e) {
    var menu = e.target;
    if (!menu.classList || !menu.classList.contains("row-menu") || e.newState !== "open") return;
    var invoker = $('[popovertarget="' + CSS.escape(menu.id) + '"]');
    if (!invoker) return;
    var r = invoker.getBoundingClientRect();
    menu.style.visibility = "hidden";
    requestAnimationFrame(function () {
      var w = menu.offsetWidth, h = menu.offsetHeight;
      var top = r.bottom + 4;
      if (top + h > innerHeight - 8) top = Math.max(8, r.top - h - 4);
      var left = Math.min(Math.max(8, r.right - w), innerWidth - w - 8);
      menu.style.top = top + "px";
      menu.style.left = left + "px";
      menu.style.visibility = "";
      var first = $("a, button", menu);
      if (first) first.focus();
    });
  }, true);

  /* ------------------------------------------------------------ bulk create */

  doc.addEventListener("click", function (e) {
    var a = e.target.closest("[data-bulk]");
    if (!a) return;
    var dialog = doc.getElementById(a.dataset.bulk);
    if (!dialog) return;
    e.preventDefault();
    dialog.showModal();
    var input = $('input[type="number"]', dialog);
    input.focus();
    input.select();
  });

  function bulkGo(dialog) {
    var input = $("[data-bulk-count]", dialog);
    var count = parseInt(input.value, 10);
    if (count >= 1 && count <= 50) location.href = dialog.dataset.url + "?count=" + count;
    else input.focus();
  }
  function initBulk(scope) {
    each(scope, "dialog[data-bulk-dialog]", function (dialog) {
      if (dialog.dataset.ready) return;
      dialog.dataset.ready = "1";
      // Out of any form on the page, so Enter cannot submit that form.
      doc.body.appendChild(dialog);
      $("[data-bulk-go]", dialog).addEventListener("click", function () { bulkGo(dialog); });
      $("[data-bulk-count]", dialog).addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); bulkGo(dialog); }
      });
      $$("[data-dialog-close]", dialog).forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
    });
  }

  /* ---------------------------------------------------------------- pickers */

  var pickerSeq = 0;

  function optionText(o) { return o.textContent.replace(/\s+/g, " ").trim(); }

  function labelFor(select) {
    var label = select.id && doc.querySelector('label[for="' + CSS.escape(select.id) + '"]');
    return label ? label.textContent.replace(/\s+/g, " ").trim() : select.name;
  }

  function enhanceSelect(select) {
    if (select.dataset.pickerReady) return;
    select.dataset.pickerReady = "1";
    var multiple = select.multiple;
    var label = labelFor(select);
    var n = ++pickerSeq;
    var trigger = doc.createElement("button");
    trigger.type = "button";
    trigger.className = "picker-trigger";
    trigger.setAttribute("role", "combobox");
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    trigger.id = "picker-" + n;
    var labelEl = select.id && doc.querySelector('label[for="' + CSS.escape(select.id) + '"]');
    if (labelEl) {
      if (!labelEl.id) labelEl.id = select.id + "_label";
      labelEl.addEventListener("click", function (e) { e.preventDefault(); trigger.focus(); });
      trigger.setAttribute("aria-labelledby", labelEl.id + " picker-" + n + "-value");
    } else {
      trigger.setAttribute("aria-label", label);
    }
    if (select.getAttribute("aria-describedby")) trigger.setAttribute("aria-describedby", select.getAttribute("aria-describedby"));
    if (select.getAttribute("aria-invalid")) trigger.setAttribute("aria-invalid", "true");
    trigger.innerHTML = '<span class="picker-trigger__value" id="picker-' + n + '-value" data-empty="' +
      (multiple ? "None chosen" : "Choose…") + '"></span>' + icon(multiple ? "list" : "chevron-down");
    select.insertAdjacentElement("afterend", trigger);

    function render() {
      var value = $(".picker-trigger__value", trigger);
      value.innerHTML = "";
      var chosen = $$("option", select).filter(function (o) { return o.selected && o.value !== ""; });
      if (multiple) {
        chosen.forEach(function (o) {
          var t = doc.createElement("span");
          t.className = "tag tag--accent";
          t.textContent = optionText(o);
          value.appendChild(t);
        });
      } else if (chosen.length) {
        value.textContent = optionText(chosen[0]);
      }
    }
    render();
    select.addEventListener("change", render);

    trigger.addEventListener("click", function () { openPicker(select, trigger, label, render); });
  }

  function openPicker(select, trigger, label, render) {
    var multiple = select.multiple;
    var dialog = doc.createElement("dialog");
    dialog.className = "dialog dialog--picker";
    dialog.setAttribute("aria-label", label);
    dialog.innerHTML =
      '<div class="dialog__head"><h2>' + label.replace(/</g, "&lt;") + "</h2>" +
      '<button type="button" class="btn btn--ghost btn--icon" data-close aria-label="Close">' + icon("close") + "</button></div>" +
      '<div class="picker__search">' + icon("search") +
      '<input type="search" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true" aria-autocomplete="list" placeholder="Search…"></div>' +
      '<ul class="picker__list" role="listbox"' + (multiple ? ' aria-multiselectable="true"' : "") + "></ul>" +
      '<div class="picker__foot"><span>' + (multiple ? "Enter adds the highlighted item. Click to tick several." : "Enter chooses the highlighted item.") +
      '</span><button type="button" class="btn btn--primary btn--sm" data-close>Done</button></div>';
    doc.body.appendChild(dialog);
    var list = $(".picker__list", dialog);
    var input = $("input", dialog);
    var items = [];
    var lastGroup = null;
    $$("option", select).forEach(function (o, i) {
      if (o.value === "" && multiple) return;
      var group = o.parentElement.tagName === "OPTGROUP" ? o.parentElement.label : null;
      if (group && group !== lastGroup) {
        var g = doc.createElement("li");
        g.className = "picker__group";
        g.setAttribute("role", "presentation");
        g.textContent = group;
        list.appendChild(g);
        lastGroup = group;
      }
      var li = doc.createElement("li");
      li.className = "picker__option";
      li.setAttribute("role", "option");
      li.id = trigger.id + "-o" + i;
      li.innerHTML = '<svg class="i picker__tick" aria-hidden="true"><use href="' + ICONS + '#i-check"></use></svg><span></span>';
      li.lastChild.textContent = o.value === "" ? "— None —" : optionText(o);
      li.setAttribute("aria-selected", o.selected ? "true" : "false");
      li._option = o;
      li._text = optionText(o).toLowerCase();
      list.appendChild(li);
      items.push(li);
    });

    var active = null;
    function visible() { return items.filter(function (li) { return !li.hidden; }); }
    function setActive(li) {
      if (active) active.classList.remove("is-active");
      active = li;
      if (li) {
        li.classList.add("is-active");
        input.setAttribute("aria-activedescendant", li.id);
        li.scrollIntoView({ block: "nearest" });
      }
    }
    function filter() {
      var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      items.forEach(function (li) {
        li.hidden = !words.every(function (w) { return li._text.indexOf(w) >= 0; });
      });
      $$(".picker__group", list).forEach(function (g) {
        var next = g.nextElementSibling, any = false;
        while (next && !next.classList.contains("picker__group")) { if (!next.hidden) any = true; next = next.nextElementSibling; }
        g.hidden = !any;
      });
      setActive(visible()[0] || null);
    }
    function sync() {
      items.forEach(function (li) { li.setAttribute("aria-selected", li._option.selected ? "true" : "false"); });
      select.dispatchEvent(new Event("change", { bubbles: true }));
      render();
    }
    function choose(li, close) {
      if (!li) return;
      if (multiple) {
        li._option.selected = close ? true : !li._option.selected;
      } else {
        li._option.selected = true;
      }
      sync();
      if (close || !multiple) dialog.close();
    }
    list.addEventListener("click", function (e) {
      var li = e.target.closest(".picker__option");
      if (li) { setActive(li); choose(li, false); }
    });
    input.addEventListener("input", filter);
    input.addEventListener("keydown", function (e) {
      var v = visible(), i = v.indexOf(active);
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(v[Math.min(i + 1, v.length - 1)]); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(v[Math.max(i - 1, 0)]); }
      else if (e.key === "Enter") { e.preventDefault(); choose(active, true); }
    });
    $$("[data-close]", dialog).forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function () {
      trigger.setAttribute("aria-expanded", "false");
      dialog.remove();
      trigger.focus();
    });
    trigger.setAttribute("aria-expanded", "true");
    dialog.showModal();
    filter();
    var selected = items.filter(function (li) { return li._option.selected; })[0];
    if (selected && !multiple) setActive(selected);
    input.focus();
  }

  /* ------------------------------------------------------------- formsets */

  doc.addEventListener("click", function (e) {
    var add = e.target.closest("[data-formset-add]");
    if (!add) return;
    e.preventDefault();
    var prefix = add.dataset.formsetAdd;
    var total = doc.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
    var template = doc.getElementById(prefix + "-empty");
    var body = doc.getElementById(prefix + "-rows");
    if (!total || !template || !body) return;
    var n = parseInt(total.value, 10) || 0;
    var html = template.innerHTML.replace(/__prefix__/g, String(n));
    body.insertAdjacentHTML("beforeend", html);
    total.value = n + 1;
    var empty = $(".empty", body);
    if (empty) empty.remove();
    var row = body.lastElementChild;
    enhance(row);
    var first = $("input:not([type=hidden]), select", row);
    if (first) first.focus();
  });

  /* ----------------------------------------------------- unsaved changes */

  $$("form[data-watch]").forEach(function (form) {
    var hint = $(".actions-bar__state", form) || doc.querySelector('.actions-bar__state[data-for="' + form.id + '"]');
    if (!hint) return;
    form.addEventListener("input", function () { hint.hidden = false; });
    form.addEventListener("change", function () { hint.hidden = false; });
  });

  /* ------------------------------------------------------- copy to clipboard */

  doc.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy]");
    if (!b || !navigator.clipboard) return;
    navigator.clipboard.writeText(b.dataset.copy).then(function () {
      var was = b.getAttribute("aria-label") || b.textContent;
      b.classList.add("is-copied");
      var label = $(".label", b);
      if (label) label.textContent = "Copied";
      setTimeout(function () { b.classList.remove("is-copied"); if (label) label.textContent = was; }, 2000);
    });
  });

  /* ------------------------------------------- the phone's Save, in reach */

  var save = $("[data-save]");
  var appbar = $(".appbar");
  if (save && appbar && save.form) {
    if (!save.form.id) save.form.id = "console-form";
    var mobile = doc.createElement("button");
    mobile.type = "submit";
    mobile.className = "appbar__btn appbar__save";
    mobile.setAttribute("form", save.form.id);
    if (save.name) { mobile.name = save.name; mobile.value = save.value; }
    mobile.innerHTML = icon("check") + "<span>" + save.textContent.trim() + "</span>";
    var jumpButton = $("[data-jump-open]", appbar);
    appbar.insertBefore(mobile, jumpButton);
  }

  /* ----------------------------------------------------------------- start */

  function enhance(scope) {
    initTabs(scope);
    initBulk(scope);
    each(scope, "select[data-picker]", enhanceSelect);
  }
  enhance(doc);
  doc.addEventListener("htmx:load", function (e) { enhance(e.target); });
  doc.addEventListener("htmx:afterSwap", function (e) { e.target.removeAttribute("aria-busy"); });
})();
