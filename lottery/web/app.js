(function () {
  "use strict";

  var $ = function (s) { return document.querySelector(s); };
  var state = { 
    cfg: null, 
    name: "", 
    invoice: 0, 
    busy: false, 
    view: "login", 
    adminToken: null, 
    adminPage: 1, 
    adminSearch: "",
    wheelItems: []
  };
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

  /* =====================  helpers  ===================== */
  function toAsciiDigits(s) {
    return s.replace(/[\u06F0-\u06F9]/g, function (c) { return c.charCodeAt(0) - 0x06F0; })
            .replace(/[\u0660-\u0669]/g, function (c) { return c.charCodeAt(0) - 0x0660; });
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function fa(n) { return Number(n).toLocaleString("fa-IR"); }
  function icon(id) {
    return '<svg class="icon sm"><use href="#' + id + '"/></svg>';
  }
  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("show"); });
    setTimeout(function () {
      t.classList.remove("show");
      setTimeout(function () { t.remove(); }, 300);
    }, 2500);
  }
  function handleAuthFailure(r) {
    if (!r.ok && r.error && r.error.indexOf("غیرمجاز") !== -1) {
      state.adminToken = null;
      show("login");
      return true;
    }
    return false;
  }

  /* =====================  login  ===================== */
  var form = $("#form"), errorEl = $("#error"), submitBtn = $("#submit");

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
  function clearForm() { form.reset(); setError(""); }

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
      return ensureConfig(true).then(function (ok) {
        if (!ok) { setError("چرخ بارگذاری نشد. لطفاً دوباره تلاش کنید."); return; }
        prepareWheel();
        show("wheel");
      });
    }).then(function () { submitBtn.disabled = false; },
            function () { submitBtn.disabled = false; setError("مشکلی پیش آمد."); });
  });

  function ensureConfig(force) {
    if (state.cfg && !force) return Promise.resolve(true);
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
    if (revealEl) revealEl.classList.remove("active");
    show("login");
  }

  /* =====================  3-dot Menu ===================== */
  var menuBtn = $("#menuBtn");
  var dropdownMenu = $("#dropdownMenu");
  var openAdminBtn = $("#openAdminBtn");

  if (menuBtn) {
    menuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      dropdownMenu.hidden = !dropdownMenu.hidden;
    });
    document.addEventListener("click", function () {
      if (!dropdownMenu.hidden) dropdownMenu.hidden = true;
    });
  }

  openAdminBtn.addEventListener("click", function () {
    dropdownMenu.hidden = true;
    checkAdminStatus();
  });

  function checkAdminStatus() {
    call("admin_status").then(function (r) {
      if (r.ok) {
        if (!r.initialized) {
          $("#adminSetupSection").hidden = false;
          $("#adminAuthBtn").textContent = "راه‌اندازی و ورود";
        } else {
          $("#adminSetupSection").hidden = true;
          $("#adminAuthBtn").textContent = "ورود";
        }
        show("admin-login");
        $("#adminUser").value = "";
        $("#adminPass").value = "";
        $("#adminAuthError").textContent = "";
      }
    });
  }

  /* =====================  Admin Auth  ===================== */
  var adminAuthForm = $("#adminAuthForm");
  adminAuthForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var user = $("#adminUser").value;
    var pass = $("#adminPass").value;
    var btn = $("#adminAuthBtn");
    var errEl = $("#adminAuthError");
    
    btn.disabled = true;
    errEl.textContent = "";

    var method = $("#adminSetupSection").hidden ? "admin_login" : "admin_setup";
    
    call(method, { username: user, password: pass }).then(function (r) {
      btn.disabled = false;
      if (!r.ok) {
        errEl.textContent = r.error;
        return;
      }
      
      if (method === "admin_setup") {
        call("admin_login", { username: user, password: pass }).then(function (loginRes) {
          if (loginRes.ok) {
            state.adminToken = loginRes.token;
            loadAdminDashboard();
          }
        });
      } else {
        state.adminToken = r.token;
        loadAdminDashboard();
      }
    });
  });

  $("#backToLogin").addEventListener("click", function () {
    show("login");
  });

  /* =====================  Admin Dashboard  ===================== */
  var PER_PAGE = 10;

  function loadAdminDashboard() {
    state.adminPage = 1;
    state.adminSearch = "";
    $("#adminSearch").value = "";
    show("admin-dashboard");
    fetchDashboardData();
    fetchWheelItems();
  }

  function renderPrizes(prizes) {
    var list = $("#prizeList");
    list.innerHTML = "";
    if (!prizes.length) {
      list.appendChild(el("li", "prize-empty", "هنوز جایزه‌ای برده نشده است."));
      return;
    }
    var max = prizes[0].count || 1;
    prizes.forEach(function (p) {
      var color = (state.cfg && state.cfg.prizeColors[p.prize]) || "#888888";
      var li = el("li", "prize-row");
      var dot = el("span", "prize-dot");
      dot.style.background = color;
      var bar = el("span", "prize-bar");
      var fill = document.createElement("i");
      fill.style.width = Math.max(6, Math.round(p.count / max * 100)) + "%";
      fill.style.background = color;
      bar.appendChild(fill);
      li.appendChild(dot);
      li.appendChild(el("span", "prize-name", p.prize));
      li.appendChild(el("span", "prize-count", fa(p.count)));
      li.appendChild(bar);
      list.appendChild(li);
    });
  }

  function renderUsers(users, page) {
    var tbody = $("#adminTableBody");
    tbody.innerHTML = "";
    if (!users.length) {
      var empty = el("tr");
      var c = el("td", "empty-cell", "موردی یافت نشد.");
      c.colSpan = 7;
      empty.appendChild(c);
      tbody.appendChild(empty);
      return;
    }
    users.forEach(function (u, i) {
      var played = u.lottery_check === 1;
      var won = played && u.prize !== state.cfg.pooch;
      var row = el("tr");

      row.appendChild(el("td", "", fa((page - 1) * PER_PAGE + i + 1)));
      row.appendChild(el("td", "", ((u.first_name || "") + " " + (u.last_name || "")).trim() || "-"));

      var ph = el("td", "", u.phone || "-"); ph.dir = "ltr"; row.appendChild(ph);
      row.appendChild(el("td", "", String(u.factorID)));
      row.appendChild(el("td", "", won ? u.prize : "-"));

      var st = el("td");
      st.appendChild(el("span",
        "status-pill " + (played ? (won ? "status-win" : "status-used") : "status-pending"),
        played ? (won ? "برنده" : "پوچ") : "در انتظار"));
      row.appendChild(st);

      var act = el("td", "actions-cell");

      var editBtn = el("button", "icon-btn sm");
      editBtn.type = "button";
      editBtn.setAttribute("aria-label", "ویرایش");
      editBtn.innerHTML = icon("i-edit");
      editBtn.onclick = function () { openUserDialog(u); };

      var delBtn = el("button", "icon-btn sm danger");
      delBtn.type = "button";
      delBtn.setAttribute("aria-label", "حذف");
      delBtn.innerHTML = icon("i-trash");
      delBtn.onclick = function () { openUserDeleteDialog(u); };

      act.appendChild(editBtn);
      act.appendChild(delBtn);
      row.appendChild(act);

      tbody.appendChild(row);
    });
  }

  function renderPager(r) {
    var totalPages = Math.max(1, Math.ceil(r.total / PER_PAGE));
    $("#pageInfo").textContent =
      "صفحهٔ " + fa(r.page) + " از " + fa(totalPages) + " — " + fa(r.total) + " مورد";

    var box = $("#pageButtons");
    box.innerHTML = "";
    var prev = el("button", "page-btn");
    prev.type = "button"; prev.setAttribute("aria-label", "قبلی");
    prev.innerHTML = icon("i-chev-r");
    prev.disabled = r.page <= 1;
    prev.onclick = function () { state.adminPage = r.page - 1; fetchDashboardData(); };
    var next = el("button", "page-btn");
    next.type = "button"; next.setAttribute("aria-label", "بعدی");
    next.innerHTML = icon("i-chev-l");
    next.disabled = r.page >= totalPages;
    next.onclick = function () { state.adminPage = r.page + 1; fetchDashboardData(); };
    box.appendChild(prev);
    box.appendChild(next);
  }

  function fetchDashboardData() {
    if (!state.adminToken) return;
    ensureConfig(false).then(function () {
      return call("admin_dashboard", {
        token: state.adminToken, page: state.adminPage, search: state.adminSearch
      });
    }).then(function (r) {
      if (!r.ok) {
        handleAuthFailure(r);
        return;
      }
      state.adminPage = r.page;
      $("#statWins").textContent = fa(r.stats.total_wins);
      $("#statPlayed").textContent = fa(r.stats.total_played);
      $("#statPending").textContent = fa(r.stats.total_pending);
      $("#statRate").textContent = fa(r.stats.success_rate) + "٪";
      renderPrizes(r.prizes);
      renderUsers(r.users, r.page);
      renderPager(r);
    });
  }

  var searchTimeout;
  $("#adminSearch").addEventListener("input", function (e) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function () {
      state.adminSearch = e.target.value;
      state.adminPage = 1;
      fetchDashboardData();
    }, 500);
  });

  $("#adminLogoutBtn").addEventListener("click", function () {
    call("admin_logout", { token: state.adminToken }).then(function () {
      state.adminToken = null;
      show("login");
    });
  });

  /* =====================  Admin — User CRUD  ===================== */
  var editingUser = null;

  function uniquePrizeNames() {
    var seen = {};
    var result = [];
    (state.cfg.gifts || []).forEach(function (g) {
      if (!seen[g]) { seen[g] = true; result.push(g); }
    });
    return result;
  }

  function populatePrizeOptions(currentPrize) {
    var sel = $("#uf-prize");
    sel.innerHTML = "";
    var seen = {};
    var names = uniquePrizeNames();
    if (currentPrize && names.indexOf(currentPrize) === -1) {
      names.unshift(currentPrize);
    }
    names.forEach(function (p) {
      if (seen[p]) return;
      seen[p] = true;
      var opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      sel.appendChild(opt);
    });
  }

  function updatePrizeVisibility() {
    var played = $("#uf-played").value === "1";
    $("#uf-prize-field").style.display = played ? "" : "none";
  }

  function openUserDialog(user) {
    ensureConfig(false).then(function (ok) {
      if (!ok) { toast("خطا در بارگذاری تنظیمات."); return; }

      editingUser = user || null;
      var isEdit = !!editingUser;
      $("#userDialogTitle").textContent = isEdit ? "ویرایش کاربر" : "افزودن کاربر";

      $("#uf-invoice").value = isEdit ? String(editingUser.factorID) : "";
      $("#uf-invoice").readOnly = isEdit;

      $("#uf-first").value = isEdit ? (editingUser.first_name || "") : "";
      $("#uf-last").value = isEdit ? (editingUser.last_name || "") : "";
      $("#uf-phone").value = isEdit ? (editingUser.phone || "") : "";

      $("#uf-played").value = isEdit ? String(editingUser.lottery_check) : "0";

      populatePrizeOptions(isEdit ? editingUser.prize : null);
      $("#uf-prize").value = isEdit ? (editingUser.prize || state.cfg.pooch) : state.cfg.pooch;

      updatePrizeVisibility();
      $("#uf-error").textContent = "";
      $("#userDialogSubmit").disabled = false;

      $("#userDialog").showModal();
      setTimeout(function () {
        (isEdit ? $("#uf-first") : $("#uf-invoice")).focus();
      }, 50);
    });
  }

  function openUserDeleteDialog(user) {
    var name = ((user.first_name || "") + " " + (user.last_name || "")).trim() || "-";
    askConfirm(
      "حذف کاربر",
      'آیا از حذف «' + name + '» (فاکتور ' + user.factorID + ') مطمئن هستید؟',
      function () {
        return call("admin_delete_user", {
          token: state.adminToken,
          invoice: user.factorID
        }).then(function (r) {
          if (r.ok) { toast("کاربر حذف شد."); fetchDashboardData(); }
          return r;
        });
      }
    );
  }

  $("#addUserBtn").addEventListener("click", function () {
    openUserDialog(null);
  });

  $("#userDialogClose").addEventListener("click", function () {
    $("#userDialog").close();
  });
  $("#userDialogCancel").addEventListener("click", function () {
    $("#userDialog").close();
  });

  $("#uf-played").addEventListener("change", updatePrizeVisibility);

  $("#uf-phone").addEventListener("input", function (e) {
    e.target.value = toAsciiDigits(e.target.value).replace(/[^\d+]/g, "");
  });
  $("#uf-invoice").addEventListener("input", function (e) {
    e.target.value = toAsciiDigits(e.target.value).replace(/\D/g, "");
  });

  $("#userForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = $("#userDialogSubmit");
    if (btn.disabled) return;
    btn.disabled = true;
    $("#uf-error").textContent = "";

    var played = parseInt($("#uf-played").value, 10);
    var payload = {
      token: state.adminToken,
      invoice: $("#uf-invoice").value,
      first: $("#uf-first").value,
      last: $("#uf-last").value,
      phone: $("#uf-phone").value,
      played: played,
      prize: played === 1 ? $("#uf-prize").value : state.cfg.pooch
    };

    var method = editingUser ? "admin_update_user" : "admin_create_user";

    call(method, payload).then(function (r) {
      btn.disabled = false;
      if (!r.ok) {
        if (!handleAuthFailure(r)) {
          $("#uf-error").textContent = r.error;
        }
        return;
      }
      $("#userDialog").close();
      toast(editingUser ? "کاربر ویرایش شد." : "کاربر اضافه شد.");
      fetchDashboardData();
    }, function () {
      btn.disabled = false;
      $("#uf-error").textContent = "مشکلی پیش آمد. دوباره تلاش کنید.";
    });
  });

  /* =====================  Admin — Wheel Items  ===================== */
  var editingWheelItem = null;

  function fetchWheelItems() {
    if (!state.adminToken) return;
    call("admin_list_wheel", { token: state.adminToken }).then(function (r) {
      if (!r.ok) {
        handleAuthFailure(r);
        return;
      }
      state.wheelItems = r.items;
      renderWheelItems();
    });
  }

  function renderWheelItems() {
    var list = $("#wheelItemList");
    list.innerHTML = "";
    if (!state.wheelItems.length) {
      list.appendChild(el("li", "wheel-empty", "هیچ جایزه‌ای تعریف نشده است."));
      return;
    }
    state.wheelItems.forEach(function (item) {
      var li = el("li", "wheel-item-row");

      // Color swatches — pooch has two alternating colours.
      var swatchWrap = el("span", "wheel-item-swatches");
      if (item.is_pooch && item.color2) {
        var s1 = el("span", "wheel-item-color");
        s1.style.background = item.color;
        var s2 = el("span", "wheel-item-color");
        s2.style.background = item.color2;
        swatchWrap.appendChild(s1);
        swatchWrap.appendChild(s2);
      } else {
        var s = el("span", "wheel-item-color");
        s.style.background = item.color || "#888888";
        swatchWrap.appendChild(s);
      }
      li.appendChild(swatchWrap);

      var nameWrap = el("span", "wheel-item-name", item.name);
      if (item.is_pooch) {
        nameWrap.appendChild(el("span", "wheel-item-badge", "رزرو"));
      }
      li.appendChild(nameWrap);

      li.appendChild(el("span", "wheel-item-count", "× " + fa(item.count)));

      var editBtn = el("button", "icon-btn sm");
      editBtn.type = "button";
      editBtn.setAttribute("aria-label", "ویرایش");
      editBtn.innerHTML = icon("i-edit");
      editBtn.onclick = function () { openWheelItemDialog(item); };
      li.appendChild(editBtn);

      if (item.is_pooch) {
        // Pooch cannot be deleted — placeholder keeps row alignment.
        var locked = el("span", "icon-btn sm locked");
        locked.setAttribute("aria-hidden", "true");
        locked.title = "این جایزه رزرو است و حذف نمی‌شود";
        locked.innerHTML = icon("i-trash");
        li.appendChild(locked);
      } else {
        var delBtn = el("button", "icon-btn sm danger");
        delBtn.type = "button";
        delBtn.setAttribute("aria-label", "حذف");
        delBtn.innerHTML = icon("i-trash");
        delBtn.onclick = function () { openWheelDeleteDialog(item); };
        li.appendChild(delBtn);
      }

      list.appendChild(li);
    });
  }

  function openWheelItemDialog(item) {
    editingWheelItem = item || null;
    var isEdit = !!editingWheelItem;
    var isPooch = isEdit && !!editingWheelItem.is_pooch;

    $("#wheelItemDialogTitle").textContent = isEdit ? "ویرایش جایزه" : "افزودن جایزه";

    $("#wf-name").value = isEdit ? editingWheelItem.name : "";
    $("#wf-name").readOnly = isPooch;  // pooch name is reserved

    $("#wf-count").value = isEdit ? String(editingWheelItem.count) : "1";

    $("#wf-color").value = isEdit && editingWheelItem.color
      ? editingWheelItem.color : "#E8B85A";
    $("#wf-color2").value = isEdit && editingWheelItem.color2
      ? editingWheelItem.color2 : "#262B40";

    $("#wf-color2-field").hidden = !isPooch;
    $("#wf-color-label").textContent = isPooch ? "رنگ اول" : "رنگ";

    $("#wf-error").textContent = "";
    $("#wheelItemDialogSubmit").disabled = false;

    $("#wheelItemDialog").showModal();
    setTimeout(function () {
      (isEdit && !isPooch ? $("#wf-name") : $("#wf-count")).focus();
    }, 50);
  }

  function openWheelDeleteDialog(item) {
    askConfirm(
      "حذف جایزه",
      'آیا از حذف «' + item.name + '» از گردونه مطمئن هستید؟ ' +
      'جوایز برده‌شدهٔ قبلی حفظ می‌شوند.',
      function () {
        return call("admin_delete_wheel_item", {
          token: state.adminToken, id: item.id
        }).then(function (r) {
          if (r.ok) {
            toast("جایزه حذف شد.");
            refreshAfterWheelChange();
          }
          return r;
        });
      }
    );
  }

  function refreshAfterWheelChange() {
    call("config").then(function (r) {
      if (r.ok) state.cfg = r;
      fetchWheelItems();
      fetchDashboardData();
    });
  }

  $("#addWheelItemBtn").addEventListener("click", function () {
    openWheelItemDialog(null);
  });
  $("#wheelItemDialogClose").addEventListener("click", function () {
    $("#wheelItemDialog").close();
  });
  $("#wheelItemDialogCancel").addEventListener("click", function () {
    $("#wheelItemDialog").close();
  });

  $("#wheelItemForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = $("#wheelItemDialogSubmit");
    if (btn.disabled) return;
    btn.disabled = true;
    $("#wf-error").textContent = "";

    var isPooch = editingWheelItem && editingWheelItem.is_pooch;
    var payload = {
      token: state.adminToken,
      count: parseInt($("#wf-count").value, 10) || 1,
      color: $("#wf-color").value,
    };
    if (isPooch) {
      payload.id = editingWheelItem.id;
      payload.color2 = $("#wf-color2").value;
    } else {
      payload.name = $("#wf-name").value;
    }

    var method;
    if (!editingWheelItem) method = "admin_create_wheel_item";
    else if (isPooch) method = "admin_update_wheel_item";
    else { payload.id = editingWheelItem.id; method = "admin_update_wheel_item"; }

    call(method, payload).then(function (r) {
      btn.disabled = false;
      if (!r.ok) {
        if (!handleAuthFailure(r)) {
          $("#wf-error").textContent = r.error;
        }
        return;
      }
      $("#wheelItemDialog").close();
      toast(editingWheelItem ? "جایزه ویرایش شد." : "جایزه اضافه شد.");
      refreshAfterWheelChange();
    }, function () {
      btn.disabled = false;
      $("#wf-error").textContent = "مشکلی پیش آمد. دوباره تلاش کنید.";
    });
  });

  /* =====================  Generic Confirm  ===================== */
  var pendingConfirm = null;

  function askConfirm(title, message, action) {
    $("#confirmTitle").textContent = title;
    $("#confirmMessage").textContent = message;
    $("#confirmError").textContent = "";
    $("#confirmDelete").disabled = false;
    pendingConfirm = action;
    $("#confirmDialog").showModal();
  }

  $("#confirmCancel").addEventListener("click", function () {
    pendingConfirm = null;
    $("#confirmDialog").close();
  });

  $("#confirmDelete").addEventListener("click", function () {
    if (!pendingConfirm) return;
    var btn = $("#confirmDelete");
    btn.disabled = true;
    $("#confirmError").textContent = "";

    pendingConfirm().then(function (r) {
      btn.disabled = false;
      if (!r || !r.ok) {
        if (r && handleAuthFailure(r)) return;
        $("#confirmError").textContent = (r && r.error) || "مشکلی پیش آمد.";
        return;
      }
      pendingConfirm = null;
      $("#confirmDialog").close();
    }, function () {
      btn.disabled = false;
      $("#confirmError").textContent = "مشکلی پیش آمد. دوباره تلاش کنید.";
    });
  });

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
    if (!state.cfg || !state.cfg.gifts || !state.cfg.gifts.length) return;
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

    ctx.fillStyle = "#0E1118";
    ctx.beginPath(); ctx.arc(cx, cy, rimInner, 0, Math.PI * 2); ctx.fill();

    var accentGrad = ctx.createLinearGradient(0, 0, size, size);
    accentGrad.addColorStop(0, "#E8B85A");
    accentGrad.addColorStop(0.5, "#F4D18A");
    accentGrad.addColorStop(1, "#C99A42");
    ctx.fillStyle = accentGrad;
    ctx.beginPath(); ctx.arc(cx, cy, rimInner, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = "#0A0C11";
    ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fill();

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

    ctx.strokeStyle = "rgba(255,255,255,.10)";
    ctx.lineWidth = Math.max(0.8, outer * 0.0025);
    for (i = 0; i < n; i++) {
      var a = top + i * step;
      ctx.beginPath();
      ctx.moveTo(cx + radius * 0.08 * Math.cos(a), cy + radius * 0.08 * Math.sin(a));
      ctx.lineTo(cx + radius * Math.cos(a), cy + radius * Math.sin(a));
      ctx.stroke();
    }

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
      var maxW = radius * 0.56, tw = ctx.measureText(gifts[i]).width;
      if (tw > maxW) {
        ctx.font = "700 " + Math.max(8, fs * maxW / tw) + "px " + CANVAS_FONT;
      }
      ctx.fillText(gifts[i], 0, 0);
      ctx.restore();
    }

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

    ctx.strokeStyle = "rgba(255,255,255,.18)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, outer - 0.5, 0, Math.PI * 2); ctx.stroke();
  }

  function fitWheel() {
    if (state.view !== "wheel") return;
    var cs = getComputedStyle(board);
    var w = board.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
    var h = board.clientHeight - (parseFloat(cs.paddingTop) || 0) - (parseFloat(cs.paddingBottom) || 0);
    var s = Math.floor(Math.min(w, h, 900) * 0.94);
    s = Math.max(120, s);
    if (wrap.dataset.size === String(s)) return;
    wrap.dataset.size = String(s);
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
  var POINTER = { angle: 0, velocity: 0, stiffness: 620, damping: 26, maxTilt: 0.6 };

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

    // Refresh config right before spinning, so wheel matches backend.
    call("config").then(function (cfg) {
      var changed = false;
      if (cfg.ok) {
        changed = !state.cfg ||
                  JSON.stringify(state.cfg.gifts) !== JSON.stringify(cfg.gifts);
        state.cfg = cfg;
        if (changed && state.view === "wheel") drawWheel();
      }
      return call("spin", { invoice: state.invoice });
    }).then(function (r) {
      if (!r.ok) {
        state.busy = false; backBtn.disabled = false;
        spinBtn.textContent = "استفاده‌شده";
        statusEl.textContent = r.error;
        return;
      }

      // Guard against out-of-range index if config changed just now.
      if (!state.cfg.gifts || r.index >= state.cfg.gifts.length) {
        state.busy = false; backBtn.disabled = false;
        spinBtn.textContent = "دوباره";
        statusEl.textContent = "گردونه تغییر کرد. لطفاً دوباره تلاش کنید.";
        return;
      }

      SPIN.done = function () {
        statusEl.textContent = "چرخ ایستاد.";
        var isWin = r.prize !== state.cfg.pooch;
        var revealEl = $("#prizeReveal");
        var revealText = $("#revealPrizeText");

        revealText.textContent = isWin ? r.prize : "پوچ";
        revealEl.classList.toggle("is-lose", !isWin);

        setTimeout(function () {
          revealEl.classList.add("active");
          setTimeout(function () {
            revealEl.classList.remove("active");
            setTimeout(function () { showResult(r.prize); }, 450);
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
      $("#r-sub").textContent = state.name + " شما برنده شدید!";
      $("#r-prize").textContent = prize;
    } else {
      $("#r-title").textContent = "از بازی شما متشکریم!";
      $("#r-sub").textContent = state.name + " امیدواریم خرید خوبی را تجربه کرده باشید";
      $("#r-prize").textContent = "روز خوبی داشته باشید";
    }
    show("result");
    if (win && !reduceMotion) confetti.start();
  }
  $("#again").addEventListener("click", logout);

  /* =====================  confetti  ===================== */
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
    else if (state.view === "admin-login" || state.view === "admin-dashboard") show("login");
    else call("exit");
  };

  ensureConfig(true);

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      if (state.view === "wheel") drawWheel();
    }).catch(function () {});
  }
})();
