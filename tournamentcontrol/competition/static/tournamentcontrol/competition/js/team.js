/* Name a new team after the club it is chosen from. */
document.addEventListener("change", function (e) {
	if (e.target.id !== "id_club") return;
	var title = document.getElementById("id_title");
	var option = e.target.options[e.target.selectedIndex];
	if (title && option) title.value = option.text;
});
