/* Name a new team after the club it is chosen from, until the name is typed. */
(function () {
	'use strict';
	var club = document.getElementById('id_club');
	var title = document.getElementById('id_title');
	if (!club || !title) { return; }
	var suggested = title.value === '' ? '' : null;
	club.addEventListener('change', function () {
		if (suggested === null || title.value !== suggested) { return; }
		var option = club.options[club.selectedIndex];
		suggested = option && option.value ? option.textContent.trim() : '';
		title.value = suggested;
	});
})();
