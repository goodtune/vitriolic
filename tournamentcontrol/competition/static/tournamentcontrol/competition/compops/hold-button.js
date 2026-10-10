// A submit button with data-hold="<ms>" submits its form only after being
// held down for that long. A tap does nothing, so a knocked elbow cannot
// end a broadcast. Works with Datastar's data-on:submit because
// requestSubmit() dispatches a real submit event.
//
// The press is captured to the button, so releasing anywhere (or the
// browser taking the pointer away) ends it and cancels the hold. Only the
// primary button counts: a right-click hold does nothing.
(function () {
	var timer = null;
	var pressed = null;
	function cancel() {
		if (timer) { clearTimeout(timer); timer = null; }
		if (pressed) { pressed.classList.remove("pressing"); pressed = null; }
	}
	document.addEventListener("pointerdown", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (!button || button.disabled || event.button !== 0) { return; }
		event.preventDefault();
		cancel();
		try { button.setPointerCapture(event.pointerId); } catch (error) { /* not capturable */ }
		pressed = button;
		button.classList.add("pressing");
		timer = setTimeout(function () {
			cancel();
			button.form.requestSubmit(button);
		}, parseInt(button.dataset.hold, 10) || 1500);
	});
	["pointerup", "pointercancel", "lostpointercapture"].forEach(function (name) {
		document.addEventListener(name, cancel, true);
	});
	document.addEventListener("click", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (button) { event.preventDefault(); }
	});
})();
