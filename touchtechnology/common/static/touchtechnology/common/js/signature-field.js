/*
 * The drawing of a SignatureField (touchtechnology.common): a canvas that
 * Signature Pad draws on, over a hidden input that carries the signature to
 * the server as a PNG data URL. The input is empty until something is drawn,
 * and again after Clear, so the server can tell that nothing was signed.
 */
(function () {
  "use strict";

  function setUp(field) {
    if (field.signaturePad) {
      return;
    }
    var canvas = field.querySelector("canvas");
    var input = field.querySelector('input[type="hidden"]');
    var clear = field.querySelector("[data-signature-clear]");
    // An opaque background, so the image reads the same on any page.
    var pad = new SignaturePad(canvas, { backgroundColor: "rgb(255, 255, 255)" });
    field.signaturePad = pad;

    function store() {
      input.value = pad.isEmpty() ? "" : pad.toDataURL("image/png");
    }

    // The canvas is as many pixels as the screen has for its box, so the
    // strokes are sharp. Resizing a canvas clears it, so its strokes are
    // drawn again; a signature that came from the server is an image, which
    // is drawn again from the input.
    function fit() {
      var ratio = Math.max(window.devicePixelRatio || 1, 1);
      var strokes = pad.toData();
      canvas.width = canvas.offsetWidth * ratio;
      canvas.height = canvas.offsetHeight * ratio;
      canvas.getContext("2d").scale(ratio, ratio);
      pad.clear();
      if (strokes.length) {
        pad.fromData(strokes);
      } else if (input.value) {
        pad.fromDataURL(input.value, {
          width: canvas.offsetWidth,
          height: canvas.offsetHeight,
        });
      }
    }

    pad.addEventListener("endStroke", store);
    clear.addEventListener("click", function () {
      pad.clear();
      input.value = "";
    });
    window.addEventListener("resize", fit);
    fit();

    if (input.disabled) {
      pad.off();
      clear.disabled = true;
    }
  }

  function setUpAll(root) {
    root.querySelectorAll("[data-signature-field]").forEach(setUp);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setUpAll(document);
    });
  } else {
    setUpAll(document);
  }
  // A form swapped into the page by htmx has its fields set up too.
  document.addEventListener("htmx:afterSwap", function (event) {
    setUpAll(event.target);
  });
})();
