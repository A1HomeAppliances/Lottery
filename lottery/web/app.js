/* A1 Lucky Spin - web UI (login -> wheel -> result)
 *
 * Talks to Python through call(method, params):
 *   - Android WebView (file://)  : location.hash = "rpc/<id>/<base64url json>",
 *                                  answer arrives in window.__rpcReply(id, json)
 *   - desktop dev server (http:) : fetch("/api")
 */
(function () {
  "use strict";

  var $ = function (s) { return document.querySelector(s); };
  var state = { cfg: null, name: "", invoice: 0, busy: false, view: "login" };
  var reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* =====================  bridge to Python  ===================== */
  var viaHash = location.protocol === "file:";
  var rpcId = 0, pending = null, chain = Promise.resolve();

  function b64url(text) {
    var utf8 = unescape(encodeURIComponent(text));
    return btoa(utf8).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  window.__rpcReply = function (id, payload) {
    if (pending && pending.id === id) {
      var p = pending; pending = null;
      clearTimeout(p.timer);
      try { p.resolve(JSON.parse(payload)); }
      catch (e) { p.resolve({ ok: false, error: "Bad response." }); }
    }
  };

  function rawCall(method, params) {
    return new Promise(function (resolve) {
      if (!viaHash) {
        fetch("/api", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ m: method, p: params || {} })
        }).then(function (r) { return r.json(); }).then(resolve)
          .catch(function () { resolve({ ok: false, error: "Connection error." }); });
        return;
      }
      var id = ++rpcId;
      var timer = setTimeout(function () {
        if (pending && pending.id === id) {
          pending = null;
          resolve({ ok: false, error: "No response from the app. Please try again." });
        }
      }, 8000);
      pending = { id: id, resolve: resolve, timer: timer };
      location.hash = "rpc/" + id + "/" + b64url(JSON.stringify({ m: method, p: params || {} }));
    });
  }

  // one request at a time, so hash changes can never overwrite each other
  function call(method, params) {
    chain = chain.then(function () { return rawCall(method, params); });
    return chain;
  }

  /* =====================  views  ===================== */
  function show(name) {
    state.view = name;
    document.querySelectorAll(".view").forEach(function (v) {
      v.hidden = v.dataset.view !== name;
    });
    $("#app").scrollTop = 0;
    if (name !== "result") confetti.stop();
    if (name === "wheel") requestAnimationFrame(fitWheel);
  }

  /* =====================  login  ===================== */
  var form = $("#form"), errorEl = $("#error"), submitBtn = $("#submit");

  function toAsciiDigits(s) {            // Persian / Arabic-Indic -> 0-9
    return s.replace(/[\u06F0-\u06F9]/g, function (c) { return c.charCodeAt(0) - 0x06F0; })
            .replace(/[\u0660-\u0669]/g, function (c) { return c.charCodeAt(0) - 0x0660; });
  }
  $("#phone").addEventListener("input", function (e) {
    e.target.value = toAsciiDigits(e.target.value).replace(/[^\d+]/g, "");
  });
  $("#invoice").addEventListener("input", function (e) {
    e.target.value = toAsciiDigits(e.target.value).replace(/\D/g, "");
  });

  form.addEventListener("focusin", function (e) {
    if (e.target.tagName !== "INPUT") return;
    setTimeout(function () {
      e.target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
    }, 320);
  });

  function setError(msg) { errorEl.textContent = msg || ""; }

  function clearForm() {
    form.reset();
    setError("");
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (submitBtn.disabled) return;
    setError("");
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    submitBtn.disabled = true;

    call("register", {
      first: $("#first").value, last: $("#last").value,
      phone: $("#phone").value, invoice: $("#invoice").value
    }).then(function (r) {
      if (!r.ok) { setError(r.error); return null; }
      state.name = r.name; state.invoice = r.invoice;
      return ensureConfig().then(function (ok) {
        if (!ok) { setError("Could not load the wheel. Please try again."); return; }
        prepareWheel();
        show("wheel");
      });
    }).then(function () { submitBtn.disabled = false; },
            function () { submitBtn.disabled = false; setError("Something went wrong."); });
  });

  function ensureConfig() {
    if (state.cfg) return Promise.resolve(true);
    return call("config").then(function (r) {
      if (!r.ok) return false;
      state.cfg = r; return true;
    });
  }

  function logout() {
    state.busy = false;
    stopSpin();
    clearForm();
    show("login");
  }

  /* =====================  wheel drawing  ===================== */
  var wheel = $("#wheel"), wrap = $("#wheelWrap"), board = $("#board");
  var pointerEl = document.querySelector(".wheel-wrap .pointer");
  var SANS = getComputedStyle(document.body).fontFamily;

  function rgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function sectorColor(i) {
    var cfg = state.cfg, g = cfg.gifts[i];
    return g === cfg.pooch ? cfg.poochColors[(i >> 1) % 2] : (cfg.prizeColors[g] || "#888888");
  }
  function labelColor(hex) {
    var c = rgb(hex), lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255;
    return lum > 0.48 ? "#121417" : "#F2F1ED";
  }

  function drawWheel() {
    if (!state.cfg) return;
    var size = wrap.clientWidth;
    if (size < 40) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 3);
    wheel.width = wheel.height = Math.round(size * dpr);
    var ctx = wheel.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    var gifts = state.cfg.gifts, n = gifts.length, step = Math.PI * 2 / n;
    var cx = size / 2, cy = size / 2;
    var outer = size / 2 - size * 0.03, rim = outer * 0.05, radius = outer - rim;
    var top = -Math.PI / 2;               // sector 0 starts at 12 o'clock, clockwise

    // gold rim + soft drop shadow
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.28)"; ctx.shadowBlur = size * 0.035; ctx.shadowOffsetY = size * 0.012;
    var g = ctx.createLinearGradient(0, 0, size, size);
    g.addColorStop(0, "#F4D18A"); g.addColorStop(0.5, "#E8B85A"); g.addColorStop(1, "#C99A42");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(cx, cy, outer, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // dark inner ring
    ctx.fillStyle = "#121419";
    ctx.beginPath(); ctx.arc(cx, cy, outer - Math.max(2, outer * 0.012), 0, Math.PI * 2); ctx.fill();

    // sectors
    for (var i = 0; i < n; i++) {
      ctx.fillStyle = sectorColor(i);
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, top + i * step, top + (i + 1) * step);
      ctx.closePath(); ctx.fill();
    }

    // hairline dividers
    ctx.strokeStyle = "rgba(255,255,255,.10)"; ctx.lineWidth = Math.max(0.8, outer * 0.0025);
    for (i = 0; i < n; i++) {
      var a = top + i * step;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.lineTo(cx + radius * Math.cos(a), cy + radius * Math.sin(a)); ctx.stroke();
    }

    // labels - flipped on the left half so they are never upside-down
    var fs = Math.max(9, radius * 0.072);
    ctx.font = "700 " + fs + "px " + SANS;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (i = 0; i < n; i++) {
      var mid = top + (i + 0.5) * step, col = sectorColor(i);
      ctx.save();
      ctx.translate(cx + radius * 0.64 * Math.cos(mid), cy + radius * 0.64 * Math.sin(mid));
      ctx.rotate(mid + (Math.cos(mid) < 0 ? Math.PI : 0));
      ctx.fillStyle = labelColor(col);
      ctx.globalAlpha = gifts[i] === state.cfg.pooch ? 0.9 : 1;
      ctx.fillText(gifts[i], 0, 0);
      ctx.restore();
    }

    // rim dots (pegs)
    var dr = outer - rim / 2, dot = Math.max(1.5, rim * 0.16);
    ctx.fillStyle = "rgba(18,20,25,.9)";
    for (i = 0; i < n; i++) {
      var b = top + i * step;
      ctx.beginPath(); ctx.arc(cx + dr * Math.cos(b), cy + dr * Math.sin(b), dot, 0, Math.PI * 2); ctx.fill();
    }
  }
   function fitWheel() {
    if (state.view !== "wheel") return;
    var w = board.clientWidth;
    var pt = parseFloat(getComputedStyle(board).paddingTop) || 0;
    var h = board.clientHeight - pt;
    var s = Math.floor(Math.max(120, Math.min(w, h, 900)));
    wrap.style.setProperty("--wheel", s + "px");
    drawWheel();
   }
  if (window.ResizeObserver) new ResizeObserver(fitWheel).observe(board);
  window.addEventListener("resize", fitWheel);
  window.addEventListener("orientationchange", function () {
    setTimeout(fitWheel, 300);
  });

  /* =====================  spin — real physics  ===================== */
  /*
   * Wheel: constant angular deceleration (like a dry bearing)
   *   d = v0^2 / (2 f)        -> v0 = 2 d / T,  f = 2 d / T^2
   * Pointer: damped harmonic oscillator (spring + damper)
   *   Each peg crossing the pointer applies an impulse scaled by wheel speed.
   */
  var spinBtn = $("#spin"), backBtn = $("#back"), statusEl = $("#status");

  var SPIN = {
    angle: 0, velocity: 0, target: 0, duration: 0,
    v0: 0, friction: 0, elapsed: 0,
    active: false, lastPeg: 0, lastTime: 0, raf: 0, done: null, step: 10
  };

  var POINTER = {
    angle: 0, velocity: 0,
    stiffness: 620, damping: 26, maxTilt: 0.6
  };

  function resetRotation() {
    if (SPIN.raf) { cancelAnimationFrame(SPIN.raf); SPIN.raf = 0; }
    SPIN.active = false;
    SPIN.angle = 0; SPIN.velocity = 0; SPIN.elapsed = 0;
    SPIN.lastPeg = 0; SPIN.done = null;
    POINTER.angle = 0; POINTER.velocity = 0;
    wheel.style.transform = "rotate(0deg)";
    if (pointerEl) pointerEl.style.transform = "translateX(-50%) rotate(0deg)";
  }

  function prepareWheel() {
    $("#welcome").textContent = "Welcome, " + state.name;
    statusEl.textContent = "";
    spinBtn.disabled = false; spinBtn.textContent = "Spin!";
    backBtn.disabled = false;
    state.busy = false;
    resetRotation();
  }

  function stopSpin() {
    if (SPIN.raf) { cancelAnimationFrame(SPIN.raf); SPIN.raf = 0; }
    SPIN.active = false;
    SPIN.done = null;
  }

  function stepPointer(dt) {
    var p = POINTER;
    // spring force: -k*x  (toward rest) minus damping: -c*v
    p.velocity += (-p.stiffness * p.angle - p.damping * p.velocity) * dt;
    p.angle += p.velocity * dt;
    if (p.angle > p.maxTilt) { p.angle = p.maxTilt; if (p.velocity > 0) p.velocity = 0; }
    if (p.angle < -p.maxTilt) { p.angle = -p.maxTilt; if (p.velocity < 0) p.velocity = 0; }
    if (Math.abs(p.angle) < 0.001 && Math.abs(p.velocity) < 0.01) {
      p.angle = 0; p.velocity = 0;
    }
    // CSS rotate positive = tip left.  We want positive p.angle = tip right, so negate.
    var deg = -p.angle * 180 / Math.PI;
    if (pointerEl) pointerEl.style.transform = "translateX(-50%) rotate(" + deg.toFixed(2) + "deg)";
  }

  function tickSpin(now) {
    if (!SPIN.active) return;
    var last = SPIN.lastTime || now;
    var dt = Math.min((now - last) / 1000, 0.05);
    SPIN.lastTime = now;
    SPIN.elapsed += dt;

    if (SPIN.elapsed >= SPIN.duration) {
      SPIN.angle = SPIN.target;
      SPIN.velocity = 0;
    } else {
      var t = SPIN.elapsed;
      // analytic: x(t) = v0*t - 0.5*f*t^2   (clamped at target)
      SPIN.angle = Math.min(SPIN.target, SPIN.v0 * t - 0.5 * SPIN.friction * t * t);
      SPIN.velocity = Math.max(0, SPIN.v0 - SPIN.friction * t);
    }
    wheel.style.transform = "rotate(" + SPIN.angle.toFixed(2) + "deg)";

    // peg crossing -> pointer impulse
    var peg = Math.floor(SPIN.angle / SPIN.step);
    if (peg > SPIN.lastPeg) {
      var crossings = Math.min(peg - SPIN.lastPeg, 5);
      SPIN.lastPeg = peg;
      var speed = SPIN.velocity;
      var impulsePerPeg = Math.min(3.2, Math.max(0.6, speed / 280));
      POINTER.velocity += Math.min(8, crossings * impulsePerPeg);
    }

    stepPointer(dt);

    var pointerRest = Math.abs(POINTER.angle) < 0.002 && Math.abs(POINTER.velocity) < 0.02;
    if (SPIN.elapsed >= SPIN.duration && pointerRest) {
      SPIN.active = false;
      if (SPIN.done) { var cb = SPIN.done; SPIN.done = null; cb(); }
      return;
    }
    SPIN.raf = requestAnimationFrame(tickSpin);
  }

  function startSpin(prizeIndex) {
    var step = 360 / state.cfg.gifts.length;
    SPIN.step = step;

    // where the winning sector must end up so its centre sits under the pointer
    var target = (prizeIndex + 0.5) * step + (Math.random() * 0.76 - 0.38) * step;
    var offset = ((360 - target) % 360 + 360) % 360;

    var turns = reduceMotion ? 2 : 7;
    var T = reduceMotion ? 1.4 : 5.5;
    var D = turns * 360 + offset;

    SPIN.target = D;
    SPIN.v0 = 2 * D / T;             // initial velocity (deg/s)
    SPIN.friction = 2 * D / (T * T); // constant deceleration (deg/s^2)
    SPIN.duration = T;
    SPIN.elapsed = 0;
    SPIN.lastPeg = 0;
    SPIN.angle = 0;
    SPIN.velocity = SPIN.v0;
    SPIN.lastTime = 0;
    SPIN.active = true;
    POINTER.angle = 0; POINTER.velocity = 0;

    if (SPIN.raf) cancelAnimationFrame(SPIN.raf);
    SPIN.raf = requestAnimationFrame(tickSpin);
  }

  spinBtn.addEventListener("click", function () {
    if (state.busy) return;
    state.busy = true;
    spinBtn.disabled = true; backBtn.disabled = true;
    spinBtn.textContent = "Spinning...";
    statusEl.textContent = "";

    call("spin", { invoice: state.invoice }).then(function (r) {
      if (!r.ok) {
        state.busy = false; backBtn.disabled = false;
        spinBtn.textContent = "Used";
        statusEl.textContent = r.error;
        return;
      }
      SPIN.done = function () {
        statusEl.textContent = "The wheel has stopped.";
        setTimeout(function () { showResult(r.prize); }, 650);
      };
      startSpin(r.index);
    });
  });

  backBtn.addEventListener("click", function () { if (!state.busy) logout(); });

  /* =====================  result  ===================== */
  function showResult(prize) {
    var win = prize !== state.cfg.pooch;
    var box = $("#result");
    box.dataset.state = win ? "win" : "lose";

    $("#r-name").textContent = state.name;
    $("#r-invoice").textContent = "#" + state.invoice;
    $("#r-note").hidden = win;

    if (win) {
      $("#r-title").textContent = "Congratulations!";
      $("#r-sub").textContent = state.name + ", you are a winner!";
      $("#r-prize").textContent = prize.toUpperCase();
    } else {
      $("#r-title").textContent = "Thank you for playing!";
      $("#r-sub").textContent = state.name + ", today may not be your day...";
      $("#r-prize").textContent = "No prize this time";
    }
    show("result");
    if (win && !reduceMotion) confetti.start();
  }
  $("#again").addEventListener("click", logout);

  /* =====================  confetti (gold only)  ===================== */
  var confetti = (function () {
    var cv = $("#confetti"), ctx = cv.getContext("2d"), parts = [], raf = 0, W = 0, H = 0, t0 = 0, last = 0;
    var colors = ["#E8B85A", "#F4D18A", "#F2F1ED", "rgba(232,184,90,.6)"];

    function size() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      cv.width = W * dpr; cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function frame(now) {
      var dt = Math.min((now - last) / 1000, 0.05); last = now;
      ctx.clearRect(0, 0, W, H);
      var alive = false;
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        p.y += p.vy * dt;
        p.x += Math.sin(now / 400 + p.phase) * 40 * dt;
        if (p.y < H + 20) alive = true;
        ctx.fillStyle = p.c; ctx.fillRect(p.x, p.y, 7, 11);
      }
      if (alive && now - t0 < 6000) raf = requestAnimationFrame(frame); else stop();
    }
    function start() {
      stop(); size(); parts = [];
      for (var i = 0; i < 80; i++) {
        parts.push({ x: Math.random() * W, y: -Math.random() * H * 0.6,
                     vy: 90 + Math.random() * 200, phase: Math.random() * 6.28, c: colors[i % 4] });
      }
      t0 = last = performance.now();
      raf = requestAnimationFrame(frame);
    }
    function stop() {
      if (raf) cancelAnimationFrame(raf);
      raf = 0; parts = [];
      ctx.clearRect(0, 0, W || cv.width, H || cv.height);
    }
    return { start: start, stop: stop };
  })();

  /* =====================  Android back button  ===================== */
  window.__back = function () {
    if (state.view === "wheel") { if (!state.busy) logout(); }
    else if (state.view === "result") logout();
    else call("exit");
  };

  // warm the config in the background so the wheel opens instantly
  ensureConfig();
})();
