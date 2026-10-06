/*
 * Reusable JavaScript to be used on list.html and edit.html templates to
 * provide modal dialog before performing deletion.
 *
 * Lists can arrive after the page has loaded (the tabs of an edit page are
 * fetched when they are first shown with HTMX admin tabs), so the links are
 * prepared again as content arrives and the dialog is handled by delegation.
 */

// Update the link to target # instead of full URL, so that Bootstrap opens the
// dialog in the page rather than loading the URL into it.
function prepareDeleteLinks(root) {
  $(root).find('a[data-target^="#deleteModal"]').attr('href', '#')
}

prepareDeleteLinks(document)

document.addEventListener('htmx:load', function(event) {
  prepareDeleteLinks(event.target)
})

$(document).on('show.bs.modal', '.modal.delete', function(event) {
  var button = $(event.relatedTarget)
  var modal = $(this)

  // Extract value for the modal title from the data-* attributes to replace
  // into the concrete modal dialog.
  var title = button.data('title')

  // TRICK: having nested form tags won't work, so in the template we mark
  // where we want the form to be with a div.form and then use the jQuery.wrap
  // function to turn it into a real form on the concrete modal dialog.
  var form = modal.find('.form')
  if (!form.parent().is('form')) {
    form.wrap('<form method="post"></form>')
  }
  form.parent().attr('action', button.data('action'))

  // Set the modal dialog title and warning text.
  modal.find('.modal-title').text('Delete ' + title)
  modal.find('.modal-body strong').text(title)
})
