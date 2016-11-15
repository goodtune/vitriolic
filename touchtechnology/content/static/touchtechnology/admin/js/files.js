var FileManager = new Class({
	Implements: Options,

	options: {
		form: 'action',
		hooks: {
			folder: 'add_folder',
			file: 'add_file',
		},
		folderTitle: 'New folder',
		fileTitle: 'Upload file',
		submitValue: 'Save',
		width: 500
	},

	initialize: function(options) {
		this.setOptions(options);
		this.form = $(this.options.form);
	},

	showFolder: function() {
		var form = this.form.clone();
		form.getElement('.file').dispose();

		var box = new Facebox({
			title: this.options.folderTitle,
			message: form,
			submitValue: this.options.submitValue,
			submitFunction: function() { form.submit(); },
			width: this.options.width
		});

		box.show();
	},

	showFile: function() {
		var form = this.form.clone();
		form.getElement('.folder').dispose();

		var box = new Facebox({
			title: this.options.fileTitle,
			message: form,
			submitValue: this.options.submitValue,
			submitFunction: function() { form.submit(); },
			width: this.options.width
		});

		box.show();
	},

	startup: function() {
		if ($(this.options.hooks.file)) {
			$(this.options.hooks.file).addEvent('click', this.showFile.bind(this));
		}

		if ($(this.options.hooks.folder)) {
			$(this.options.hooks.folder).addEvent('click', this.showFolder.bind(this));
		}

		if (this.form.getElements('.folder .field_errors').length) {
			this.showFolder();
		}
		if (this.form.getElements('.file .field_errors').length) {
			this.showFile();
		}
	}
});

document.addEvent('domready', function() {
	var manager = new FileManager();
	manager.startup();
});
