/* Promoter surface — optimised for one thing: capturing a qualified lead in
   under 25 seconds while the customer is still standing there. */

(function () {
  "use strict";

  var CFG = window.CFG;
  var code = window.PROMOTER || "";
  var state = { shift: null, today: "", qualified: 0, captured: 0,
               taps: 0, lead: {}, editingLeadId: null, recentLeads: [] };

  var $ = function (id) { return document.getElementById(id); };

  /* Stored values stay English; only the display is Arabic. */
  function L(kind, value) {
    var m = (CFG.labels || {})[kind] || {};
    return m[value] || value;
  }

  function show(el, on) { el.classList.toggle("hide", !on); }

  function msg(el, text, kind) {
    el.className = "msg" + (kind ? " " + kind : "");
    el.textContent = text || "";
  }

  function api(path, body, method) {
    var opts = { headers: { "Content-Type": "application/json" } };
    if (body || method) { opts.method = method || "POST"; opts.body = body ? JSON.stringify(body) : undefined; }
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.error || "صار خطأ، حاول مرة ثانية"); }
        return j;
      });
    });
  }

  /* ---- conversations with no lead ------------------------------------
     Each tap goes to the server immediately, so the manager sees the top of
     the funnel live and an unclosed shift never loses the count.

     localStorage is now only a failure buffer: if a tap cannot be sent — dead
     signal inside the store — it waits there and is flushed with the next
     successful call. It is no longer the source of truth. */
  function pendingKey() { return "abwab_pending_" + code + "_" + state.today; }
  function getPending() { return parseInt(localStorage.getItem(pendingKey()) || "0", 10); }
  function setPending(n) {
    localStorage.setItem(pendingKey(), String(Math.max(0, n)));
    var el = $("pendingNote");
    if (el) {
      el.textContent = n > 0 ? "‏" + n + " محادثة لم تُرسل بعد — راح تُرسل تلقائياً" : "";
      el.classList.toggle("hide", n <= 0);
    }
  }

  // Server-side taps + today's leads. Every lead came from a conversation.
  function totalConversations() {
    return state.taps + getPending() + state.qualified;
  }

  function sendTaps(n) {
    return api("/api/shift/conversation", { n: n }).then(function (j) {
      state.taps = j.tap_conversations;
      setPending(0);
      paint();
    });
  }

  function flushPending() {
    var p = getPending();
    if (p > 0) { sendTaps(p).catch(function () { /* still offline */ }); }
  }

  /* ---- chip pickers --------------------------------------------------- */
  function buildChips(host, values, field, onPick, label, multiSelect) {
    host.innerHTML = "";
    values.forEach(function (v, idx) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = label ? label(v) : v;
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        if (multiSelect) {
          var pressed = b.getAttribute("aria-pressed") === "true";
          b.setAttribute("aria-pressed", pressed ? "false" : "true");

          var selected = [];
          Array.prototype.forEach.call(host.children, function (c, i) {
            if (c.getAttribute("aria-pressed") === "true") {
              selected.push(values[i]);
            }
          });
          state.lead[field] = selected;
          if (onPick) { onPick(selected); }
        } else {
          Array.prototype.forEach.call(host.children, function (c) {
            c.setAttribute("aria-pressed", "false");
          });
          b.setAttribute("aria-pressed", "true");
          state.lead[field] = v;
          if (onPick) { onPick(v); }
        }
      });
      host.appendChild(b);
    });
  }

  function shortGrade(g) {
    return (CFG.labels.grade_short[g] || g);
  }

  /* ---- render --------------------------------------------------------- */
  function paint() {
    $("mConv").textContent = totalConversations();
    $("mQual").textContent = state.qualified;
    $("mCap").textContent = state.captured;
    $("pConv").textContent = state.shift && state.shift.conversations != null
      ? Math.max(state.shift.conversations, totalConversations()) : totalConversations();
    $("pQual").textContent = state.qualified;
    $("pCap").textContent = state.captured;

    // لا توجد شاشة "ابدأ الشفت" — الشفت يُفتح تلقائياً عند الدخول
    var closed = state.shift && state.shift.end_ts;
    show($("onShift"), !closed);
    show($("postShift"), !!closed);

    if (state.shift) {
      $("shiftMeta").textContent = L("shift", state.shift.shift) + " · من "
        + state.shift.start_ts.slice(11, 16);
      var sel = $("branchSel");
      if (sel && sel.value !== state.shift.branch) { sel.value = state.shift.branch; }
    }
    var note = $("plannedNote");
    if (note) {
      note.textContent = state.planned
        ? "مجدول: " + L("shift", state.planned.shift_type)
        : "";
    }
  }

  function renderRecent(list) {
    var host = $("recent");
    if (!list.length) { host.innerHTML = '<div class="empty">لا توجد ليدات بعد.</div>'; return; }
    state.recentLeads = list;
    var html = '<div class="tw"><table><tbody>';
    list.slice(0, 8).forEach(function (l, idx) {
      html += "<tr><td>" + l.time + "</td>"
        + "<td><strong>" + (l.customer_name || "—") + "</strong><div class='sub'>"
        + shortGrade(l.grade) + " · " + L("interest", l.interest) + "</div></td>"
        + "<td class='right' style='white-space:nowrap'><span class='pill "
        + (l.outcome === "Captured" ? "good" : "mute") + "'>" + L("outcome", l.outcome)
        + "</span> <button class='btn xs edit-lead-btn' data-idx='" + idx
        + "' style='margin-inline-start:6px;padding:3px 8px;font-size:11px'>تعديل</button></td></tr>";
    });
    html += "</tbody></table></div>";
    host.innerHTML = html;

    var buttons = host.querySelectorAll(".edit-lead-btn");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-idx"), 10);
        var lead = state.recentLeads[idx];
        if (lead) { editLead(lead); }
      });
    });
  }

  function refreshRecent() {
    fetch("/api/leads?from=" + state.today + "&to=" + state.today)
      .then(function (r) { return r.json(); })
      .then(renderRecent)
      .catch(function () { /* the list is a convenience, never block on it */ });
  }

  function refresh() {
    return api("/api/shift/current")
      .then(function (j) {
        state.shift = j.shift;
        state.today = j.today;
        state.qualified = j.qualified;
        state.captured = j.captured;
        state.planned = j.planned;
        state.taps = j.taps || 0;
        if (j.branches) { fillBranches(j.branches, j.shift.branch); }
        setPending(getPending());
        paint();
        flushPending();
        if (state.shift && !state.shift.end_ts) { refreshRecent(); }
      });
  }

  /* ---- lead sheet ----------------------------------------------------- */
  function openLeadSheet() {
    state.editingLeadId = null;
    state.lead = { outcome: "Captured", customer_type: "Parent", grade: [] };
    msg($("leadMsg"), "");
    $("cName").value = "";
    $("cPhone").value = "";
    $("lNote").value = "";

    var h2 = $("leadSheet").querySelector("header h2");
    if (h2) { h2.textContent = "ليد جديد"; }

    buildChips($("gradeChips"), CFG.grades, "grade", null, shortGrade, true);
    buildChips($("interestChips"), CFG.interests, "interest", null,
      function (v) { return L("interest", v); });
    buildChips($("typeChips"), CFG.customer_types, "customer_type", null,
      function (v) { return L("customer_type", v); });
    buildChips($("outcomeChips"), CFG.outcomes, "outcome", function (v) {
      show($("captureFields"), v === "Captured");
      $("leadSave").textContent = v === "Captured" ? "حفظ الليد" : "حفظ — رفض";
    }, function (v) { return L("outcome", v); });
    preselect($("typeChips"), L("customer_type", "Parent"));
    preselect($("outcomeChips"), L("outcome", "Captured"));
    show($("captureFields"), true);
    $("leadSave").textContent = "حفظ الليد";
    show($("leadSheet"), true);
    window.scrollTo(0, 0);
  }

  function editLead(lead) {
    state.editingLeadId = lead.lead_id;
    state.lead = {
      outcome: lead.outcome,
      customer_type: lead.customer_type,
      interest: lead.interest,
      grade: [lead.grade]
    };
    msg($("leadMsg"), "");
    $("cName").value = lead.customer_name || "";
    $("cPhone").value = lead.phone || lead.phone_raw || "";

    var noteVal = lead.promoter_note || lead.note || "";
    noteVal = noteVal.replace(/^عدد الأطفال:\s*\d+\s*\([^\)]+\)\s*(·\s*)?/, "");
    $("lNote").value = noteVal;

    var h2 = $("leadSheet").querySelector("header h2");
    if (h2) { h2.textContent = "تعديل الليد (" + lead.lead_id + ")"; }

    buildChips($("gradeChips"), CFG.grades, "grade", null, shortGrade, true);
    buildChips($("interestChips"), CFG.interests, "interest", null,
      function (v) { return L("interest", v); });
    buildChips($("typeChips"), CFG.customer_types, "customer_type", null,
      function (v) { return L("customer_type", v); });
    buildChips($("outcomeChips"), CFG.outcomes, "outcome", function (v) {
      show($("captureFields"), v === "Captured");
      $("leadSave").textContent = "تحديث الليد";
    }, function (v) { return L("outcome", v); });

    preselect($("gradeChips"), shortGrade(lead.grade));
    preselect($("interestChips"), L("interest", lead.interest));
    preselect($("typeChips"), L("customer_type", lead.customer_type));
    preselect($("outcomeChips"), L("outcome", lead.outcome));

    show($("captureFields"), lead.outcome === "Captured");
    $("leadSave").textContent = "تحديث الليد";
    show($("leadSheet"), true);
    window.scrollTo(0, 0);
  }

  function preselect(host, value) {
    Array.prototype.forEach.call(host.children, function (c) {
      if (c.textContent === value) { c.setAttribute("aria-pressed", "true"); }
    });
  }

  function saveLead() {
    var l = state.lead;
    var selectedGrades = Array.isArray(l.grade) ? l.grade : (l.grade ? [l.grade] : []);
    if (selectedGrades.length === 0) { return msg($("leadMsg"), "اختر صف الطالب.", "err"); }
    if (!l.interest) { return msg($("leadMsg"), "اختر شنو يحتاج.", "err"); }

    if (l.outcome === "Captured") {
      if (!$("cName").value.trim()) {
        return msg($("leadMsg"), "اكتب اسم الزبون.", "err");
      }
      // Check here as well as on the server, so the promoter is told before
      // the request goes out and while the customer is still standing there.
      var digits = ($("cPhone").value || "").replace(/\D/g, "");
      if (digits.length !== CFG.phone_digits
          || digits.indexOf(CFG.phone_prefix) !== 0) {
        return msg($("leadMsg"), CFG.phone_error, "err");
      }
    }

    var primaryGrade = selectedGrades[0];
    var notesText = $("lNote").value.trim();
    if (selectedGrades.length > 1) {
      var gradesArabic = selectedGrades.map(function(g) { return shortGrade(g); }).join("، ");
      var autoNote = "عدد الأطفال: " + selectedGrades.length + " (" + gradesArabic + ")";
      if (notesText) {
        notesText = autoNote + " · " + notesText;
      } else {
        notesText = autoNote;
      }
    }

    var payload = {
      branch: state.shift ? state.shift.branch : null,
      grade: primaryGrade, interest: l.interest,
      customer_type: l.customer_type, outcome: l.outcome,
      customer_name: $("cName").value, phone: $("cPhone").value,
      note: notesText
    };

    var path = state.editingLeadId ? "/api/leads/" + state.editingLeadId : "/api/leads";
    var method = state.editingLeadId ? "PUT" : "POST";

    var btn = $("leadSave");
    btn.disabled = true;
    api(path, payload, method).then(function (j) {
      state.qualified = j.qualified_today;
      state.captured = j.captured_today;
      show($("leadSheet"), false);
      state.editingLeadId = null;
      paint();
      refreshRecent();
      if (j.duplicate_of) {
        msg($("msg"), "تم الحفظ — لكن هذا الرقم مسجّل سابقاً على "
          + j.duplicate_of + ". الإدارة راح تراجعه.", "warn");
      } else {
        msg($("msg"), method === "PUT" ? "تم تحديث الليد بنجاح." : ("تم حفظ الليد. " + j.lead_id), "ok");
        setTimeout(function () { msg($("msg"), ""); }, 3500);
      }
    }).catch(function (e) {
      msg($("leadMsg"), e.message, "err");
    }).then(function () { btn.disabled = false; });
  }

  /* ---- close sheet ---------------------------------------------------- */
  function openCloseSheet() {
    msg($("closeMsg"), "");
    $("cConv").value = totalConversations();
    show($("closeSheet"), true);
    window.scrollTo(0, 0);
  }

  function saveClose() {
    var n = parseInt($("cConv").value, 10);
    if (isNaN(n)) { return msg($("closeMsg"), "اكتب عدد المحادثات.", "err"); }
    if (n < state.qualified) {
      return msg($("closeMsg"), "سجّلت " + state.qualified + " ليد، يعني عندك "
        + state.qualified + " محادثة على الأقل. ارفع الرقم.", "err");
    }
    var btn = $("closeSave");
    btn.disabled = true;
    api("/api/shift/close", {
      conversations: n,
      gifts_issued: $("cGifts").value, note: $("cNote").value
    }).then(function (j) {
      localStorage.removeItem(pendingKey());
      show($("closeSheet"), false);
      return refresh();
    }).catch(function (e) {
      msg($("closeMsg"), e.message, "err");
    }).then(function () { btn.disabled = false; });
  }

  /* ---- boot ----------------------------------------------------------- */
  function fillBranches(branches, selected) {
    var sel = $("branchSel");
    if (!sel || sel.dataset.filled === "1") {
      if (sel && selected) { sel.value = selected; }
      return;
    }
    sel.innerHTML = "";
    Object.keys(branches).forEach(function (b) {
      var o = document.createElement("option");
      o.value = b;
      o.textContent = branches[b];
      sel.appendChild(o);
    });
    sel.dataset.filled = "1";
    if (selected) { sel.value = selected; }
  }

  function boot() {
    $("branchSel").addEventListener("change", function () {
      api("/api/shift/branch", { branch: $("branchSel").value })
        .then(function () {
          msg($("msg"), "تم تغيير الفرع.", "ok");
          setTimeout(function () { msg($("msg"), ""); }, 2500);
          return refresh();
        })
        .catch(function (e) { msg($("msg"), e.message, "err"); });
    });

    $("btnReopen").addEventListener("click", function () {
      api("/api/shift/reopen", {})
        .then(refresh)
        .catch(function (e) { msg($("msg"), e.message, "err"); });
    });

    $("btnConvo").addEventListener("click", function () {
      // Count it on screen at once — the promoter must not wait for the
      // network with a customer walking away.
      state.taps += 1;
      paint();
      $("btnConvo").textContent = "＋ محادثة بدون ليد   ✓";
      setTimeout(function () {
        $("btnConvo").textContent = "＋ محادثة بدون ليد";
      }, 500);

      api("/api/shift/conversation", { n: 1 + getPending() })
        .then(function (j) {
          state.taps = j.tap_conversations;
          setPending(0);
          paint();
        })
        .catch(function () {
          // Could not reach the server: hold it and try again on the next tap.
          state.taps -= 1;
          setPending(getPending() + 1);
          paint();
        });
    });

    $("cPhone").addEventListener("input", function () {
      var digits = ($("cPhone").value || "").replace(/\D/g, "");
      var hint = $("phoneHint");
      var need = CFG.phone_digits;
      if (!digits.length) {
        hint.textContent = "اقرأ الرقم للزبون قبل الحفظ.";
        hint.style.color = "";
      } else if (digits.length === need && digits.indexOf(CFG.phone_prefix) === 0) {
        hint.textContent = "الرقم مكتمل ✓";
        hint.style.color = "var(--good)";
      } else {
        hint.textContent = digits.length + " من " + need + " خانة";
        hint.style.color = "var(--bad)";
      }
    });

    $("btnLead").addEventListener("click", openLeadSheet);
    $("leadCancel").addEventListener("click", function () { show($("leadSheet"), false); });
    $("leadSave").addEventListener("click", saveLead);

    $("btnClose").addEventListener("click", openCloseSheet);
    $("closeCancel").addEventListener("click", function () { show($("closeSheet"), false); });
    $("closeSave").addEventListener("click", saveClose);

    refresh().catch(function (e) { msg($("msg"), e.message, "err"); });
  }

  boot();
})();
