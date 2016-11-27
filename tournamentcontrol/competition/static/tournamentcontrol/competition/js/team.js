window.addEvent('domready', function() {
	$('id_club').addEvent('change', function(event) {
		var title = $('id_title');
		var select = event.target;
		var options = select.getElements('option');

		/* set the title to that of the club */
		title.set('value', options[select.selectedIndex].get('text'))
	});
});
