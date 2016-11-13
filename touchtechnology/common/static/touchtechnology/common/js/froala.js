/*
 *  Activate the rich text editor for all our form fields which are derived
 *  from the HTMLWidget class.
 */

$(document).ready(function() {
  $(".html_widget textarea").each(function(idx, elem) {
    // convert back into a jQuery object
    var editor = $(elem)

    // retrieve the instantiation options from data-options attribute
    var options = editor.data('options')

    // initialise the editor using options
    editor.froalaEditor(options)
  })
});
