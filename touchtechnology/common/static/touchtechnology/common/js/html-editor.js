document.addEventListener("DOMContentLoaded", function () {
  var buttons = [
    "bold", "italic", "underline", "strikethrough", "eraser", "|",
    "ul", "ol", "|",
    "left", "center", "right", "justify", "\n",
    "font", "fontsize", "paragraph", "lineHeight", "|",
    "outdent", "indent", "brush", "|",
    "link", "image", "table", "|",
    "undo", "redo", "|",
    "source", "dots"
  ];
  var defaults = {
    minHeight: 300,
    buttons: buttons,
    buttonsMD: buttons,
    buttonsSM: buttons,
    buttonsXS: buttons
  };

  document.querySelectorAll(".html_widget textarea").forEach(function (elem) {
    var options = Object.assign({}, defaults);
    var dataOptions = elem.getAttribute("data-options");
    if (dataOptions) {
      Object.assign(options, JSON.parse(dataOptions));
    }
    Jodit.make(elem, options);
  });
});
