// A submit button with data-hold="<ms>" submits its form only after being
// held down for that long. A tap does nothing, so a knocked elbow cannot
// end a broadcast. Works with Datastar's data-on:submit because
// requestSubmit() dispatches a real submit event.
(function () {
	var timer = null;
	function cancel(button) {
		if (timer) { clearTimeout(timer); timer = null; }
		button.classList.remove("pressing");
	}
	document.addEventListener("pointerdown", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (!button || button.disabled) { return; }
		event.preventDefault();
		button.classList.add("pressing");
		timer = setTimeout(function () {
			cancel(button);
			button.form.requestSubmit(button);
		}, parseInt(button.dataset.hold, 10) || 1500);
	});
	["pointerup", "pointerleave", "pointercancel"].forEach(function (name) {
		document.addEventListener(name, function (event) {
			var button = event.target.closest && event.target.closest("button[data-hold]");
			if (button) { cancel(button); }
		});
	});
	document.addEventListener("click", function (event) {
		var button = event.target.closest("button[data-hold]");
		if (button) { event.preventDefault(); }
	});
})();
