function setContentContainer(element, callback) {
	if (typeof(callback) == "undefined")
		callback = null;
	contentContainerCallback = callback;
	if ($(element) != contentContainer) {
		if (contentContainer != null) {
			contentContainer.style.height = 'auto';
		}
		contentContainer = $(element);
	}
};

var TabHelper = new Object();
$extend(TabHelper, {

	initialize: function (tabControl, insertBefore, activeTab) {

		tabControl = $(tabControl);
		insertBefore = $(insertBefore);

		var tabs = document.createElement('div');
		tabs.className = 'tabs';
		insertBefore.parentNode.insertBefore(tabs, insertBefore);

		var tabPanes = $(tabControl).getElements('.tab_pane');
		tabPanes.each(function(tabPane, idx) {

			tabPane.tabPanes = tabPanes;
			var tab = tabPane.getElement('h2');

			var tabHasErrors = (tabPane.getElements('ul.errorlist').length > 0);
			if(tabHasErrors)
				tab.addClass('tab_errors');
			var a = $(document.createElement('a'));
			a.innerHTML = tab.innerHTML;
			a.href = '#' + tabPane.id;
			a.addEvent('click', function(event) {
				TabHelper.setFocus(tabPane);
				this.blur();
				(new Event(event)).stop();
			}.bindWithEvent(a));
			tab.innerHTML = '';
			tab.appendChild(a);
			tab.tabPane = tabPane;
			tab.tabPanes = tabPanes;
			tab.tabControl = tabControl;
			tabPane.tab = tab;
			tabs.appendChild(tab);

		});

		var errorTabs = tabs.getChildren('.tab_errors');
		var firstErrorTab = (errorTabs.length > 0) ? errorTabs[0] : null;
		TabHelper.setFocus($(activeTab) || (firstErrorTab && firstErrorTab.tabPane) || tabs.firstChild.tabPane);

	},

	setFocus: function(tabPane) {
		$A(tabPane.tabPanes).each(function(t) {
			if (tabPane == t) {
				$(t.tab).addClass('current');
				t.style.display = '';
			} else {
				$(t.tab).removeClass('current');
				t.style.display = 'none';
			}
		});
		var tabPaneElement = $(tabPane);
		//setContentContainer('outer');
	}

});

function initTabs() {
	if ($('form_tabs')) {
		TabHelper.initialize('form_tabs', 'outer');
	}
}

window.addEvent('domready', initTabs);
