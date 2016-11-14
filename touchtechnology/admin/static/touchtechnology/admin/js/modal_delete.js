/*
 * Reusable JavaScript to be used on list.html and edit.html templates to
 * provide modal dialog before performing deletion.
 */

// Update the link to target # instead of full URL
$('a[data-target^=#deleteModal]').attr('href', '#')

$('.modal.delete').on('show.bs.modal', function(event) {
  var button = $(event.relatedTarget)
  var modal = $(this)

  // Extract value for the modal title from the data-* attributes to replace
  // into the concrete modal dialog.
  var title = button.data('title')

  // TRICK: having nested form tags won't work, so in the template we mark
  // where we want the form to be with a div.form and then use the jQuery.wrap
  // function to turn it into a real form on the concrete modal dialog.
  modal.find('.form').wrap('<form method="post"></form>')
  modal.find('form').attr('action', button.data('action'))

  // Set the modal dialog title and warning text.
  modal.find('.modal-title').text('Delete ' + title)
  modal.find('.modal-body strong').text(title)
})
