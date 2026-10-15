$(function() {
	/* name the team after the club it is chosen from */
	$('#id_club').on('change', function() {
		$('#id_title').val($(this).find('option:selected').text());
	});
});
