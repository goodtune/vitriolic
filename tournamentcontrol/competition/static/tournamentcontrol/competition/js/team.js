/* Name the team after the club it is chosen from. */
(function () {
	'use strict';
	var club = document.getElementById('id_club');
	var title = document.getElementById('id_title');
	if (!club || !title) { return; }
	club.addEventListener('change', function () {
		var option = club.options[club.selectedIndex];
		if (option && option.value) { title.value = option.textContent.trim(); }
	});
})();
