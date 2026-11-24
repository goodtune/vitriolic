/*
 * Whether the scorer's page asks who scored, for this scorer and this match.
 *
 * After "+" the page offers the scoring team's players (scorer.html). A
 * scorer who would rather not be asked turns the question off with the
 * button under the teams (#sc-ask); the choice is kept in this browser, for
 * the match, and nowhere on the server. Each "+" form carries a hidden "ask"
 * field, set here as it is sent: "0" and the server does not ask.
 *
 * Datastar's persist plugin is not in its free build, so it is done here.
 * The page's markup is replaced as it is updated, so the button is drawn
 * again from the stored choice whenever the page changes.
 */
(function () {
  "use strict";

  var PREFIX = "compops:scorer:ask:";

  function asking(match) {
    try {
      return window.localStorage.getItem(PREFIX + match) !== "off";
    } catch (error) {
      // A browser that keeps nothing asks every time.
      return true;
    }
  }

  function remember(match, on) {
    try {
      if (on) {
        window.localStorage.removeItem(PREFIX + match);
      } else {
        window.localStorage.setItem(PREFIX + match, "off");
      }
    } catch (error) {
      // Nothing to keep it in; the button still says what was chosen.
    }
  }

  function draw() {
    document.querySelectorAll("[data-ask-match]").forEach(function (toggle) {
      var pressed = asking(toggle.getAttribute("data-ask-match")) ? "true" : "false";
      if (toggle.getAttribute("aria-pressed") !== pressed) {
        toggle.setAttribute("aria-pressed", pressed);
      }
    });
  }

  function matchOf(element) {
    var scorer = element.closest("#scorer");
    var toggle = scorer && scorer.querySelector("[data-ask-match]");
    return toggle ? toggle.getAttribute("data-ask-match") : null;
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-ask-match]");
    if (!toggle) {
      return;
    }
    var match = toggle.getAttribute("data-ask-match");
    remember(match, !asking(match));
    draw();
  });

  // In the capture phase, before Datastar's own handler sends the form.
  document.addEventListener(
    "submit",
    function (event) {
      var ask = event.target.querySelector("input[name=ask]");
      var match = matchOf(event.target);
      if (ask && match !== null) {
        ask.value = asking(match) ? "1" : "0";
      }
    },
    true
  );

  function start() {
    draw();
    new MutationObserver(draw).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["aria-pressed"],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
