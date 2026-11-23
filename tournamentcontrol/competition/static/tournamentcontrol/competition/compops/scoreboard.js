/*
 * The clock of a scoreboard (and of its scorer's page).
 *
 * Nothing pushes the clock. The server renders #sb-clock with the moment the
 * clock runs from and the lengths of the match's periods and breaks, and this
 * script counts from them: the time left, the phase's name and colour, the
 * period dots, and a horn when a period starts or ends. It is the same sum
 * as Clock.at in compops/scoreboard.py.
 *
 * The page's own clock may be wrong, so the server sends its time too
 * (data-now) and the script counts in the server's time.
 */
(function () {
  "use strict";

  // What the clock says when it is not in a period or a break. A period's
  // name and a break's come from the server (data-names): "1st Half", "Half
  // time", or nothing at all for the one period of a match that has one.
  var LABELS = {
    ready: "Ready",
    before: "Starts in",
    over: "Full time",
  };

  function labelOf(data, moment) {
    if (moment.index === null) {
      return LABELS[moment.kind];
    }
    try {
      var names = JSON.parse(data.names || "[]");
      if (typeof names[moment.index] === "string") {
        return names[moment.index];
      }
    } catch (error) {
      // A template that left the names out gets the plain ones.
    }
    return moment.kind === "break" ? "Break" : "Period " + moment.period;
  }
  var offset = null;
  var seen = null;
  var last = null;
  var audio = null;

  function phasesOf(periods, period, pause) {
    var phases = [];
    for (var number = 0; number < periods; number++) {
      if (number && pause) {
        phases.push(["break", pause]);
      }
      phases.push(["period", period]);
    }
    return phases;
  }

  function momentAt(data, now) {
    var period = Number(data.period);
    if (!data.start) {
      return { kind: "ready", index: null, period: 1, remaining: period, exact: period };
    }
    var elapsed = (now - Number(data.start)) / 1000;
    if (elapsed < 0) {
      return {
        kind: "before",
        index: null,
        period: 1,
        remaining: Math.ceil(-elapsed),
        exact: -elapsed,
      };
    }
    var phases = phasesOf(Number(data.periods), period, Number(data.pause));
    var played = 0;
    for (var index = 0; index < phases.length; index++) {
      var kind = phases[index][0];
      var seconds = phases[index][1];
      if (kind === "period") {
        played += 1;
      }
      if (elapsed < seconds) {
        return {
          kind: kind,
          index: index,
          period: played + (kind === "break" ? 1 : 0),
          remaining: Math.ceil(seconds - elapsed),
          exact: seconds - elapsed,
        };
      }
      elapsed -= seconds;
    }
    return { kind: "over", index: null, period: null, remaining: 0, exact: 0 };
  }

  function display(moment) {
    // The last minute of a period is shown to a tenth of a second, cut
    // short, not rounded: the clock reads 0.0 only when the period is over.
    if (moment.kind === "period" && moment.exact < 60) {
      return (Math.floor(moment.exact * 10) / 10).toFixed(1);
    }
    var remaining = moment.remaining;
    var seconds = remaining % 60;
    var minutes = Math.floor(remaining / 60) % 60;
    var hours = Math.floor(remaining / 3600);
    var pad = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return (hours ? hours + ":" : "") + pad(minutes) + ":" + pad(seconds);
  }

  function horn() {
    if (!audio) {
      return;
    }
    var at = audio.currentTime;
    var gain = audio.createGain();
    gain.connect(audio.destination);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(0.6, at + 0.05);
    gain.gain.setValueAtTime(0.6, at + 1.3);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 1.6);
    [196, 247, 294].forEach(function (frequency) {
      var tone = audio.createOscillator();
      tone.type = "sawtooth";
      tone.frequency.value = frequency;
      tone.connect(gain);
      tone.start(at);
      tone.stop(at + 1.6);
    });
  }

  // The template that drew the board. When a live update brings a board
  // drawn by another (the next match's division has its own, or this one
  // was edited), the rest of the page is the old template's, so the page
  // loads itself again.
  var drawnBy = null;

  function tick() {
    var board = document.getElementById("board");
    var template = board ? board.getAttribute("data-template") : null;
    if (drawnBy !== null && template !== null && template !== drawnBy) {
      drawnBy = template;
      window.location.reload();
      return;
    }
    if (template !== null) {
      drawnBy = template;
    }
    var clock = document.getElementById("sb-clock");
    if (!clock) {
      last = null;
      return;
    }
    var data = clock.dataset;
    if (data.now !== seen) {
      seen = data.now;
      // Each rendering took a moment to arrive, so its time reads early by
      // that much. The largest difference seen is the nearest to the truth.
      var difference = Number(data.now) - Date.now();
      offset = offset === null ? difference : Math.max(offset, difference);
    }
    var moment = momentAt(data, Date.now() + offset);
    var label = labelOf(data, moment);
    // A template of the project's, or one written in the admin, may leave
    // out the label or the dots; the time is what a clock is for.
    var time = document.getElementById("sb-time");
    var text = display(moment);
    if (time && time.textContent !== text) {
      time.textContent = text;
    }
    var name = document.getElementById("sb-label");
    if (name && name.textContent !== label) {
      name.textContent = label;
    }
    ["ready", "before", "period", "break", "over"].forEach(function (kind) {
      clock.classList.toggle(kind, kind === moment.kind);
    });
    var dots = document.querySelectorAll("#sb-dots li");
    dots.forEach(function (dot, index) {
      var done = moment.kind === "over" || (moment.index !== null && index < moment.index);
      dot.classList.toggle("done", done);
      dot.classList.toggle("on", moment.index === index);
    });
    // A horn when a period starts or ends: when the phase changes while the
    // same match's clock is on the page.
    var key = data.match + ":" + data.start;
    var phase = moment.kind + ":" + moment.index;
    if (last && last.key === key && last.phase !== phase && moment.kind !== "before") {
      horn();
    }
    last = { key: key, phase: phase };
  }

  function start() {
    tick();
    // Often enough for each tenth of a period's last minute to be seen.
    setInterval(tick, 50);
    // A browser plays no sound until the page has been touched.
    var sound = document.getElementById("sb-sound");
    if (sound) {
      sound.addEventListener("click", function () {
        var Context = window.AudioContext || window.webkitAudioContext;
        audio = audio || new Context();
        audio.resume();
        horn();
        sound.hidden = true;
        document.body.classList.add("sound-on");
      });
    }
  }

  // For the tests, and for a page that wants to sound the horn itself.
  window.compopsScoreboard = {
    momentAt: momentAt,
    display: display,
    labelOf: labelOf,
    horn: horn,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
