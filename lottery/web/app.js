/* A1 Lucky Spin — رابط وب فارسی (ورود -> چرخ -> نتیجه)
 *
 * از طریق call(method, params) با پایتون حرف می‌زند:
 *   - WebView اندروید (file://)  : location.hash = "rpc/<id>/<base64url json>"
 *                                  پاسخ از طریق window.__rpcReply(id, json)
 *   - dev server دسکتاپ (http:)  : fetch("/api")
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
      catch (e) { p.resolve({ ok: false, error: "پاسخ نامعتبر." }); }
    }
  };

  function rawCall(method, params) {
    return new Promise(function (resolve) {
      if (!viaHash) {
        fetch("/api", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ m: method, p: params || {} })
        }).then(function (r) { return r.json(); }).then(resolve)
          .catch(function () { resolve({ ok: false, error: "خطای اتصال." }); });
        return;
      }
      var id = ++rpcId;
      var timer = setTimeout(function () {
        if (pending && pending.id === id) {
          pending = null;
          resolve({ ok: false, error: "پاسخی از برنامه دریافت نشد. لطفاً دوباره تلاش کنید." });
        }
      }, 8000);
      pending = { id: id, resolve: resolve, timer: timer };
      location.hash = "rpc/" + id + "/" + b64url(JSON.stringify({ m: method, p: params || {} }));
    });
  }

  // یک درخواست هم‌زمان، تا تغییرهای hash روی هم نیفتند
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

  function toAsciiDigits(s) {
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
        if (!ok) { setError("چرخ بارگذاری نشد. لطفاً دوباره تلاش کنید."); return; }
        prepareWheel();
        show("wheel");
      });
    }).then(function () { submitBtn.disabled = false; },
            function () { submitBtn.disabled = false; setError("مشکلی پیش آمد."); });
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
    var revealEl = $("#prizeReveal");
    if (revealEl) revealEl.classList.remove("active"); // پاک کردن استیت انیمیشن
    show("login");
  }

  /* =====================  wheel drawing  ===================== */
  var wheel = $("#wheel"), wrap = $("#wheelWrap"), board = $("#board");
  var pointerEl = document.querySelector(".wheel-wrap .pointer");
  var CANVAS_FONT = 'Vazirmatn, "Segoe UI", Tahoma, sans-serif';

  function rgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function shade(hex, amt) {
    var c = rgb(hex);
    function clamp(v) { return Math.max(0, Math.min(255, Math.round(v))); }
    return "rgb(" + clamp(c[0] + 255 * amt) + "," +
                    clamp(c[1] + 255 * amt) + "," +
                    clamp(c[2] + 255 * amt) + ")";
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
    var outer = size / 2 - size * 0.03;
    var rimWidth = outer * 0.055;
    var rimInner = outer - rimWidth;
    var innerAccent = outer * 0.04;
    var radius = rimInner - innerAccent;
    var top = -Math.PI / 2;

    /* ۱) حلقهٔ طلایی بیرونی با گرادیان و سایه */
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.45)";
    ctx.shadowBlur = size * 0.04;
    ctx.shadowOffsetY = size * 0.015;
    var rimGrad = ctx.createLinearGradient(0, 0, size, size);
    rimGrad.addColorStop(0, "#F4D18A");
    rimGrad.addColorStop(0.35, "#E8B85A");
    rimGrad.addColorStop(0.7, "#C99A42");
    rimGrad.addColorStop(1, "#8C6B2A");
    ctx.fillStyle = rimGrad;
    ctx.beginPath(); ctx.arc(cx, cy, outer, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    /* ۲) حلقهٔ تیرهٔ داخلی (بِوِل) */
    ctx.fillStyle = "#0E1118";
    ctx.beginPath(); ctx.arc(cx, cy, rimInner, 0, Math.PI * 2); ctx.fill();

    /* ۳) نوار نازک طلایی داخلی */
    var accentGrad = ctx.createLinearGradient(0, 0, size, size);
    accentGrad.addColorStop(0, "#E8B85A");
    accentGrad.addColorStop(0.5, "#F4D18A");
    accentGrad.addColorStop(1, "#C99A42");
    ctx.fillStyle = accentGrad;
    ctx.beginPath(); ctx.arc(cx, cy, rimInner, 0, Math.PI * 2); ctx.fill();

    /* ۴) بستر تیرهٔ سکتورها */
    ctx.fillStyle = "#0A0C11";
    ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fill();

    /* ۵) سکتورها با گرادیان شعاعی (عمق) */
    for (var i = 0; i < n; i++) {
      var base = sectorColor(i);
      var grad = ctx.createRadialGradient(cx, cy, radius * 0.14, cx, cy, radius);
      grad.addColorStop(0, shade(base, -0.20));
      grad.addColorStop(0.55, base);
      grad.addColorStop(1, shade(base, 0.10));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, top + i * step, top + (i + 1) * step);
      ctx.closePath();
      ctx.fill();
    }

    /* ۶) جداکنندهٔ نازک (از مرکز تا لبه) */
    ctx.strokeStyle = "rgba(255,255,255,.10)";
    ctx.lineWidth = Math.max(0.8, outer * 0.0025);
    for (i = 0; i < n; i++) {
      var a = top + i * step;
      ctx.beginPath();
      ctx.moveTo(cx + radius * 0.08 * Math.cos(a), cy + radius * 0.08 * Math.sin(a));
      ctx.lineTo(cx + radius * Math.cos(a), cy + radius * Math.sin(a));
      ctx.stroke();
    }

    /* ۷) برچسب‌ها (فارسی، چرخیده و روی نیمهٔ چپ برگردانده) */
    var fs = Math.max(10, radius * 0.075);
    ctx.font = "700 " + fs + "px " + CANVAS_FONT;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (i = 0; i < n; i++) {
      var mid = top + (i + 0.5) * step, col = sectorColor(i);
      ctx.save();
      ctx.translate(cx + radius * 0.66 * Math.cos(mid), cy + radius * 0.66 * Math.sin(mid));
      ctx.rotate(mid + (Math.cos(mid) < 0 ? Math.PI : 0));
      ctx.fillStyle = labelColor(col);
      ctx.globalAlpha = gifts[i] === state.cfg.pooch ? 0.9 : 1;
      ctx.shadowColor = "rgba(0,0,0,.4)";
      ctx.shadowBlur = Math.max(1, fs * 0.18);
      ctx.fillText(gifts[i], 0, 0);
      ctx.restore();
    }

    /* ۸) میخ‌های طلایی روی رینگ */
    var pegR = outer - rimWidth * 0.5;
    var pegSize = Math.max(2.4, rimWidth * 0.24);
    for (i = 0; i < n; i++) {
      var b = top + i * step;
      var px = cx + pegR * Math.cos(b);
      var py = cy + pegR * Math.sin(b);
      ctx.fillStyle = "rgba(0,0,0,.5)";
      ctx.beginPath(); ctx.arc(px, py + 1, pegSize * 1.05, 0, Math.PI * 2); ctx.fill();
      var pegGrad = ctx.createRadialGradient(
        px - pegSize * 0.4, py - pegSize * 0.4, 0, px, py, pegSize
      );
      pegGrad.addColorStop(0, "#FFF6DE");
      pegGrad.addColorStop(0.55, "#F4D18A");
      pegGrad.addColorStop(1, "#8C6B2A");
      ctx.fillStyle = pegGrad;
      ctx.beginPath(); ctx.arc(px, py, pegSize, 0, Math.PI * 2); ctx.fill();
    }

    /* ۹) هایلایت لبهٔ بیرونی */
    ctx.strokeStyle = "rgba(255,255,255,.18)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, outer - 0.5, 0, Math.PI * 2); ctx.stroke();
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
    $("#welcome").textContent = "خوش آمدید، " + state.name;
    statusEl.textContent = "";
    spinBtn.disabled = false; spinBtn.textContent = "بچرخون!";
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
    p.velocity += (-p.stiffness * p.angle - p.damping * p.velocity) * dt;
    p.angle += p.velocity * dt;
    if (p.angle > p.maxTilt) { p.angle = p.maxTilt; if (p.velocity > 0) p.velocity = 0; }
    if (p.angle < -p.maxTilt) { p.angle = -p.maxTilt; if (p.velocity < 0) p.velocity = 0; }
    if (Math.abs(p.angle) < 0.001 && Math.abs(p.velocity) < 0.01) {
      p.angle = 0; p.velocity = 0;
    }
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
      SPIN.angle = Math.min(SPIN.target, SPIN.v0 * t - 0.5 * SPIN.friction * t * t);
      SPIN.velocity = Math.max(0, SPIN.v0 - SPIN.friction * t);
    }
    wheel.style.transform = "rotate(" + SPIN.angle.toFixed(2) + "deg)";

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

    var target = (prizeIndex + 0.5) * step + (Math.random() * 0.76 - 0.38) * step;
    var offset = ((360 - target) % 360 + 360) % 360;

    var turns = reduceMotion ? 2 : 7;
    var T = reduceMotion ? 1.4 : 5.5;
    var D = turns * 360 + offset;

    SPIN.target = D;
    SPIN.v0 = 2 * D / T;
    SPIN.friction = 2 * D / (T * T);
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
    spinBtn.textContent = "در حال چرخش...";
    statusEl.textContent = "";

    call("spin", { invoice: state.invoice }).then(function (r) {
      if (!r.ok) {
        state.busy = false; backBtn.disabled = false;
        spinBtn.textContent = "استفاده‌شده";
        statusEl.textContent = r.error;
        return;
      }
      
      SPIN.done = function () {
        statusEl.textContent = "چرخ ایستاد.";
        
        var isWin = r.prize !== state.cfg.pooch;
        var revealEl = $("#prizeReveal");
        var revealText = $("#revealPrizeText");
        
        revealText.textContent = isWin ? r.prize : "پوچ";
        revealEl.classList.toggle("is-lose", !isWin);
        
        // تاخیر کوتاه تا کاربر ببیند چرخ کجا ایستاده است
        setTimeout(function () {
          revealEl.classList.add("active");
          
          // زمان نمایش جایزه (۱.۸ ثانیه)
          setTimeout(function () {
            revealEl.classList.remove("active");
            
            setTimeout(function () {
              showResult(r.prize);
            }, 450); // هماهنگ با زمان محو شدن CSS
            
          }, reduceMotion ? 800 : 1800);
          
        }, 600);
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
      $("#r-title").textContent = "تبریک!";
      $("#r-sub").textContent = state.name + " عزیز، شما برنده شدید!";
      $("#r-prize").textContent = prize;
    } else {
      $("#r-title").textContent = "از بازی شما متشکریم!";
      $("#r-sub").textContent = state.name + " عزیز، امروز روز شما نیست...";
      $("#r-prize").textContent = "این بار برنده نشدید";
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

  // اگر فونت با تأخیر لود شد، چرخ را دوباره بکش تا برچسب‌ها با فونت فارسی رندر شوند
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      if (state.view === "wheel") drawWheel();
    }).catch(function () {});
  }
})();
