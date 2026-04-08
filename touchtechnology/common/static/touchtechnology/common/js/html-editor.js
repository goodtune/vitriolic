document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".html_widget textarea").forEach(function (elem) {
    var options = {};
    var dataOptions = elem.getAttribute("data-options");
    if (dataOptions) {
      options = JSON.parse(dataOptions);
    }
    Jodit.make(elem, options);
  });
});
