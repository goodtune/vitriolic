window.addEvent('domready', function() {
	var forfeits = $$('#results tbody tr .forfeit');

	forfeits.each(function(el, idx) {
		var radios = el.getElements('.boolean_select input');
		var select = el.getElement('.select');

		/* only execute for table rows which have the forfeit selector */
		if (select != undefined) {
			var wrapper = select.getParent('.field_wrapper');

			function update() {
				var forfeit = radios[0].get('checked');
				var winner = select.getElement('select').get('value');
				var row = wrapper.getParent('tr');

				/* show/hide the winner selection list */
				wrapper.setStyle('display', forfeit ? '' : 'none');

				/* if a clear winner has been determined, set the forfeit scores */
				if (winner.length) {
					row.getElements('.html5_number_widget input').set('value', row.get('data-forfeit-against-score'));
					row.getElement('.team'+winner+' .html5_number_widget input').set('value', row.get('data-forfeit-for-score'));
				}
				/* when it's a double-forfeit, both teams receive the against score */
				else if (forfeit) {
					row.getElements('.html5_number_widget input').set('value', row.get('data-forfeit-against-score'));
				}

				/* if this match is not a forfeit, force the select list to it's empty value */
				if (!forfeit) {
					select.getElement('select').selectedIndex = 0;
				}
			}

			/* event handlers for updating the forfeit inputs */
			radios.addEvent('click', update);
			select.addEvent('change', update);

			/* initially update immediately */
			update();
		}
	});
});
