var FormSet = new Class({
	initialize: function(container) {
		this.container = $(container);
		this.tbody = this.container.getElement('tbody');

		var empty = this.container.getElement('tr.empty').removeClass('empty');
		var total = this.container.getElement('input[name$=TOTAL_FORMS]');

		this.container.getElement('a.add').addEvent('click', function(event) {
			event.preventDefault();
			var element = empty.clone().addClass('last');
			var last = this.tbody.getElement('.last');
			element.getElements('input, select, textarea').each(function(el) {
				if (el.getAttribute('id'))
					el.setAttribute('id', el.getAttribute('id').replace(/__prefix__/, total.value));
				if (el.getAttribute('for'))
					el.setAttribute('for', el.getAttribute('for').replace(/__prefix__/, total.value));
				if (el.getAttribute('name'))
					el.setAttribute('name', el.getAttribute('name').replace(/__prefix__/, total.value));
			});
			if (last.getElement('td').hasClass('no_results')) {
				element.set('class', last.get('class'));
				last.dispose();
			}
			else {
				element.addClass(last.removeClass('last').hasClass('odd') ? 'even' : 'odd');
			}
			this.tbody.adopt(element);

			/* make IE redraw the table */
			document.body.style.display = 'none';
			document.body.style.display = 'block';

			total.value = parseInt(total.value) + 1;
		}.bind(this));
	}
});

FormSet.autodetect = function() {
	$$('.formset').each(function(container) {
		new FormSet(container);
	});
}

document.addEvent('domready', function() {
	FormSet.autodetect();
});
