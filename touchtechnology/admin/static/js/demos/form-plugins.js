$(function () {

  /////////////////////////
  // Time Picker
  /////////////////////////

  $('#timepicker1').timepicker ()

  $('#timepicker2').timepicker ()

  $('#timepicker3').timepicker ({ template: 'modal' })

  $('#timepicker4').timepicker ({ template: false })

  $('#timepicker5').timepicker ({ showMeridian: false })

  $('#timepicker6').timepicker ({ showSeconds: true })


  /////////////////////////
  // Date Picker
  /////////////////////////

  $('#datepicker1').datepicker({
    autoclose: true,
    todayHighlight: true
  })

  $('#datepicker2').datepicker({
    autoclose: true,
    todayHighlight: true
  })

  $('#datepicker3').datepicker({
    autoclose: true,
    todayHighlight: true
  })


  /////////////////////////
  // Validation
  /////////////////////////

  $('#demo-validation').submit (function (e) {
    e.preventDefault ()
  })


  /////////////////////////
  // iCheck
  /////////////////////////

  $('.demo-icheck input').iCheck ({
    checkboxClass: 'ui-icheck icheckbox_minimal-grey',
    radioClass: 'ui-icheck iradio_minimal-grey'
  }).on ('ifChanged', function (e) {
    $(e.currentTarget).trigger ('change')
  })


  /////////////////////////
  // Select2
  /////////////////////////

  $('#s2_basic').select2 ({
    allowClear: true
    , placeholder: "Select..."
  })

  $('#s2_multi_value').select2 ({
    placeholder: "Select..."
  })

  $('#s2_tokenization').select2 ({
    placeholder: "Select...",
    tags:["red", "green", "blue", "black", "orange", "white"],
    tokenSeparators: [",", " "]
  })

  $("#e5").select2({
    minimumInputLength: 1,
    query: function (query) {
      var data = {results: []}, i, j, s;
      for (i = 1; i < 5; i++) {
      s = "";
      for (j = 0; j < i; j++) {s = s + query.term;}
      data.results.push({id: query.term + i, text: s});
      }
      query.callback(data);
    }
  })

  $("#e6").select2({
    placeholder: "Search for a repository",
    minimumInputLength: 2,
    ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
      url: "https://api.github.com/search/repositories",
      dataType: 'json',
      quietMillis: 250,
      data: function (term, page) {
        return {
          q: term, // search term
        }
      },
      results: function (data, page) { // parse the results into the format expected by Select2.
        // since we are using custom formatting functions we do not need to alter the remote JSON data
        return { results: data.items }
      },
      cache: true
    },
    initSelection: function(element, callback) {
      // the input tag has a value attribute preloaded that points to a preselected repository's id
      // this function resolves that id attribute to an object that select2 can render
      // using its formatResult renderer - that way the repository name is shown preselected
      var id = $(element).val()

      if (id !== "") {
        $.ajax("https://api.github.com/repositories/" + id, {
          dataType: "json"
        }).done(function(data) { callback(data); })
      }
    },
    formatResult: repoFormatResult, // omitted for brevity, see the source of this page
    formatSelection: repoFormatSelection,  // omitted for brevity, see the source of this page
    dropdownCssClass: "bigdrop", // apply css that makes the dropdown taller
    escapeMarkup: function (m) { return m } // we do not want to escape markup since we are displaying html in results
  })


})