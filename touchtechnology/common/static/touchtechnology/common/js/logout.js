/*
 * Django's LogoutView only accepts POST (since Django 5.0), so a link to it
 * must not simply be followed. A link marked with data-logout (holding the
 * CSRF token) posts to its own href instead.
 *
 * The form is built on click rather than written into the page, so pages
 * keep exactly the forms and submit buttons they had.
 */
document.addEventListener("click", function (event) {
	var link = event.target.closest("a[data-logout]");
	if (!link) {
		return;
	}
	event.preventDefault();

	var form = document.createElement("form");
	form.method = "post";
	form.action = link.href;
	form.hidden = true;

	var token = document.createElement("input");
	token.type = "hidden";
	token.name = "csrfmiddlewaretoken";
	token.value = link.dataset.logout;
	form.appendChild(token);

	document.body.appendChild(form);
	form.submit();
});
