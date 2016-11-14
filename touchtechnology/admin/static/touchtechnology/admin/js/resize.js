function disable_noscript_stylesheets() {
	/* disable any style-sheets or noscript elements designed to correct non-javascript environments */
	$$('body div.noscript').each(function(el) { el.dispose(); });
	$$('head link.noscript').each(function(el) { el.disabled = true; });
}

window.addEvent('domready', function() {
	disable_noscript_stylesheets();
});
