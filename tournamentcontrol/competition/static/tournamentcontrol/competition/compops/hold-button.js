// A submit button with data-hold="<ms>" submits its form only after being
// held down for that long. A tap does nothing, so a knocked elbow cannot
// end a broadcast. Works with Datastar's data-on:submit because
// requestSubmit() dispatches a real submit event.
//
// The press is captured to the button, so releasing anywhere (or the
// browser taking the pointer away) ends it and cancels the hold. Only the
// primary button counts: a right-click hold does nothing.
//
// From the keyboard, holding Space or Enter on the focused button is the
// same hold: the key's auto-repeat is ignored, and releasing the key or
// moving focus away cancels it. The button's own click, whichever way it
// comes, never submits.
(function () {
	var timer = null;
	var pressed = null;
	function cancel() {
		if (timer) { clearTimeout(timer); timer = null; }
		if (pressed) { pressed.classList.remove("pressing"); pressed = null; }
	}
	function start(button) {
		cancel();
		pressed = button;
		button.classList.add("pressing");
		timer = setTimeout(function () {
			cancel();
			button.form.requestSubmit(button);
		}, parseInt(button.dataset.hold, 10) || 1500);
	}
	function isHoldKey(event) {
		return event.key === " " || event.key === "Enter";
	}
	document.addEventListener("pointerdown", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (!button || button.disabled || event.button !== 0) { return; }
		event.preventDefault();
		cancel();
		try { button.setPointerCapture(event.pointerId); } catch (error) { /* not capturable */ }
		start(button);
	});
	["pointerup", "pointercancel", "lostpointercapture"].forEach(function (name) {
		document.addEventListener(name, cancel, true);
	});
	document.addEventListener("keydown", function (event) {
		var button = event.target.closest && event.target.closest("button[data-hold]");
		if (!button || !isHoldKey(event)) { return; }
		event.preventDefault();
		if (event.repeat || button.disabled) { return; }
		start(button);
	});
	document.addEventListener("keyup", function (event) {
		if (pressed && isHoldKey(event) && event.target === pressed) { cancel(); }
	});
	document.addEventListener("focusout", function (event) {
		if (pressed && event.target === pressed) { cancel(); }
	}, true);
	document.addEventListener("click", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (button) { event.preventDefault(); }
	});
})();
