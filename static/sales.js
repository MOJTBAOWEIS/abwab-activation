/* شاشة المبيعات — قائمة الاتصال هي قائمة العمل، والدرج يسجّل نتيجة الاتصال.
   وقت الاتصال يُختم لحظة الحفظ، حتى لا يكون مؤشر 24 ساعة كلاماً فقط. */

(function () {
  "use strict";

  var CFG = window.CFG;
  var $ = function (id) { return document.getElementById(id); };
  var leads = [];
  var current = null;
  var picked = { status: null };

  /* القيم مخزّنة بالإنجليزية؛ العرض فقط بالعربي. */
  function L(kind, value) {
    var m = (CFG.labels || {})[kind] || {};
    return m[value] || value;
  }

  function msg(el, text, kind) {
    el.className = "msg" + (kind ? " " + kind : "");
    el.textContent = text || "";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function money(v) { return Number(v || 0).toFixed(2) + " " + CFG.currency; }

  function api(path, body) {
    var opts = { headers: { "Content-Type": "application/json" } };
    if (body) { opts.method = "POST"; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      if (r.status === 401) { window.location = "/login"; }
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.error || "صار خطأ، حاول مرة ثانية"); }
        return j;
      });
    });
  }

  function statusPill(s) {
    var tone = {
      "New": "neutral", "Contacted": "neutral", "Follow-up": "warn",
      "Converted": "good", "Not Converted": "bad", "Invalid / Unreachable": "bad"
    }[s] || "mute";
    return "<span class='pill " + tone + "'>" + esc(L("status", s)) + "</span>";
  }

  /* ---------------- قائمة الاتصال ---------------- */
  function renderQueue(rows) {
    var host = $("queue");
    if (!rows.length) {
      host.innerHTML = '<div class="empty">القائمة فاضية — تم الاتصال بكل الليدات الجاهزة.</div>';
      return;
    }
    var h = "<table><thead><tr><th>المهلة</th><th>الزبون</th><th class='n'>الهاتف</th>"
      + "<th>الصف</th><th>الحاجة</th><th>ملاحظة المروّج</th>"
      + "<th>المروّج</th><th>الفرع</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      var left = r.hours_remaining < 0
        ? "متأخر " + Math.abs(r.hours_remaining).toFixed(1) + " س"
        : "باقي " + r.hours_remaining.toFixed(1) + " س";
      var phoneCell = r.callable
        ? esc(r.phone)
        : "<span class='pill bad'>" + esc(r.issue) + "</span>"
          + (r.phone ? "<div class='sub'>" + esc(r.phone) + "</div>" : "");
      h += "<tr class='qrow " + r.state + (r.callable ? "" : " broken")
        + "' data-id='" + esc(r.lead_id) + "'>"
        + "<td class='n rem'>" + left + "</td>"
        + "<td><strong>" + esc(r.customer_name) + "</strong></td>"
        + "<td class='n'>" + phoneCell + "</td>"
        + "<td>" + esc(L("grade", r.grade)) + "</td>"
        + "<td>" + esc(L("interest", r.interest)) + "</td>"
        + "<td class='notecell'>" + esc(r.promoter_note || "") + "</td>"
        + "<td>" + esc(r.promoter_name) + "</td>"
        + "<td>" + esc(r.branch_name) + "</td></tr>";
    });
    host.innerHTML = h + "</tbody></table>";
    Array.prototype.forEach.call(host.querySelectorAll(".qrow"), function (tr) {
      tr.addEventListener("click", function () { openDrawer(tr.dataset.id); });
    });
  }

  function renderTiles(queue) {
    var breached = queue.filter(function (r) { return r.state === "breached"; }).length;
    var urgent = queue.filter(function (r) { return r.state === "urgent"; }).length;
    var contacted = leads.filter(function (l) { return l.contacted; }).length;
    var converted = leads.filter(function (l) { return l.purchase; }).length;
    var revenue = leads.reduce(function (a, l) { return a + (l.revenue || 0); }, 0);

    var callable = queue.filter(function (r) { return r.callable; }).length;
    var broken = queue.length - callable;
    var tiles = [
      ["بانتظار أول اتصال", callable, "", callable ? "warn" : "good"],
      ["أرقام تحتاج تصحيح", broken, broken ? "صحّحها من القائمة" : "", broken ? "bad" : "good"],
      ["تجاوز المهلة", breached, "أكثر من " + CFG.sla_hours + " ساعة", breached ? "bad" : "good"],
      ["أقل من 6 ساعات", urgent, "اتصل بهم الآن", urgent ? "warn" : ""],
      ["تم الاتصال", contacted, "", ""],
      ["اشتروا", converted, "", "good"],
      ["الإيراد", money(revenue), "", "good"]
    ];
    $("tiles").innerHTML = tiles.map(function (t) {
      return "<div class='stat " + t[3] + "'><div class='k'>" + t[0] + "</div>"
        + "<div class='v'>" + t[1] + "</div>"
        + (t[2] ? "<div class='s'>" + t[2] + "</div>" : "") + "</div>";
    }).join("");
  }

  /* ---------------- كل الليدات ---------------- */
  function renderLeads() {
    var q = ($("search").value || "").toLowerCase();
    var sf = $("statusFilter").value;
    var rows = leads.filter(function (l) {
      if (sf && l.status !== sf) { return false; }
      if (!q) { return true; }
      return [l.lead_id, l.customer_name, l.phone, l.promoter, l.branch,
        L("grade", l.grade), L("interest", l.interest), L("status", l.status),
        l.promoter_note || ""]
        .join(" ").toLowerCase().indexOf(q) >= 0;
    });

    var host = $("leads");
    if (!rows.length) { host.innerHTML = '<div class="empty">لا توجد نتائج.</div>'; return; }
    var h = "<table><thead><tr><th>رقم الليد</th><th>الزبون</th><th class='n'>الهاتف</th>"
      + "<th>الصف</th><th>الحاجة</th><th>المروّج</th><th>الحالة</th>"
      + "<th>24 ساعة</th><th>ملاحظة المروّج</th>"
      + "<th class='n'>الإيراد</th><th></th></tr></thead><tbody>";
    rows.slice(0, 300).forEach(function (l) {
      var w = l.within_24h;
      var wp = w === "Yes" ? "good" : (w === "Pending" ? "warn" : "bad");
      var wt = { "Yes": "نعم", "No": "لا", "Pending": "بالانتظار" }[w] || w;
      h += "<tr><td class='mono' style='font-size:11px'>" + esc(l.lead_id) + "</td>"
        + "<td><strong>" + esc(l.customer_name || "—") + "</strong></td>"
        + "<td class='n'>" + esc(l.phone || "—") + "</td>"
        + "<td>" + esc(L("grade", l.grade)) + "</td>"
        + "<td>" + esc(L("interest", l.interest)) + "</td>"
        + "<td>" + esc(l.promoter) + "</td>"
        + "<td>" + statusPill(l.status) + "</td>"
        + "<td><span class='pill " + wp + "'>" + wt + "</span></td>"
        + "<td class='notecell'>" + esc(l.promoter_note || "") + "</td>"
        + "<td class='n'>" + (l.revenue ? Number(l.revenue).toFixed(2) : "—") + "</td>"
        + "<td><button class='btn sm' data-id='" + esc(l.lead_id) + "'>تسجيل</button></td></tr>";
    });
    host.innerHTML = h + "</tbody></table>";
    Array.prototype.forEach.call(host.querySelectorAll("button[data-id]"), function (b) {
      b.addEventListener("click", function () { openDrawer(b.dataset.id); });
    });
  }

  /* ---------------- درج التسجيل ---------------- */
  function openDrawer(leadId) {
    current = leads.filter(function (l) { return l.lead_id === leadId; })[0];
    if (!current) { return; }
    picked.status = null;
    msg($("drawerMsg"), "");
    $("dLeadId").textContent = current.lead_id;
    $("dName").textContent = current.customer_name || "(بدون اسم)";
    $("dMeta").textContent = current.phone + " · " + L("grade", current.grade) + " · "
      + L("interest", current.interest) + " · " + L("customer_type", current.customer_type);
    $("dSource").textContent = "سجّله " + current.promoter + " في " + current.branch
      + " بتاريخ " + current.date + " " + current.time
      + " · الحالة الآن: " + L("status", current.status);
    // ملاحظة المروّج هي أهم شي يقرأه الموظف قبل ما يضغط الاتصال
    // A number that cannot be dialled is the first thing to deal with.
    var badPhone = !current.phone || current.phone.length !== CFG.phone_digits
      || current.phone.indexOf(CFG.phone_prefix) !== 0;
    $("fixPhoneBox").classList.toggle("hide", !badPhone);
    $("dFixPhone").value = "";
    $("fixPhoneNow").textContent = current.phone || "(بدون رقم)";

    var pn = $("dPromoterNote");
    pn.innerHTML = current.promoter_note
      ? "<span class='k'>ملاحظة المروّج</span>" + esc(current.promoter_note)
      : "";
    pn.classList.toggle("hide", !current.promoter_note);
    $("dAttempts").value = Math.max(1, current.attempts || 1);
    $("dRevenue").value = "";
    $("dNotes").value = "";
    $("dContactTs").value = "";
    $("dPurchaseDate").value = new Date().toISOString().slice(0, 10);

    var host = $("statusChips");
    host.innerHTML = "";
    CFG.statuses.filter(function (s) { return s !== "New"; }).forEach(function (s) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = L("status", s);
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(host.children, function (c) {
          c.setAttribute("aria-pressed", "false");
        });
        b.setAttribute("aria-pressed", "true");
        picked.status = s;
        $("saleFields").classList.toggle("hide", s !== "Converted");
      });
      host.appendChild(b);
    });
    $("saleFields").classList.add("hide");
    $("drawer").classList.remove("hide");
  }

  function save() {
    if (!picked.status) { return msg($("drawerMsg"), "اختر نتيجة الاتصال.", "err"); }
    var body = {
      lead_id: current.lead_id, status: picked.status, agent: $("agentSel").value,
      attempts: $("dAttempts").value, notes: $("dNotes").value,
      contact_ts: $("dContactTs").value
    };
    if (picked.status === "Converted") {
      body.purchase = true;
      body.revenue = $("dRevenue").value;
      body.product = $("dProduct").value;
      body.purchase_date = $("dPurchaseDate").value;
    }
    $("dSave").disabled = true;
    api("/api/followup", body).then(function () {
      $("drawer").classList.add("hide");
      msg($("msg"), "تم حفظ المتابعة للّيد " + body.lead_id + ".", "ok");
      setTimeout(function () { msg($("msg"), ""); }, 3000);
      load();
    }).catch(function (e) {
      msg($("drawerMsg"), e.message, "err");
    }).then(function () { $("dSave").disabled = false; });
  }

  /* ---------------- التشغيل ---------------- */
  function load() {
    return Promise.all([
      fetch("/api/sales/queue").then(function (r) { return r.json(); }),
      fetch("/api/leads").then(function (r) { return r.json(); })
    ]).then(function (res) {
      leads = res[1];
      renderQueue(res[0]);
      renderTiles(res[0]);
      renderLeads();
    });
  }

  function boot() {
    var sel = $("agentSel");
    Object.keys(CFG.sales_agents).forEach(function (a) {
      var o = document.createElement("option");
      o.value = a; o.textContent = CFG.sales_agents[a];
      sel.appendChild(o);
    });
    // موظف المبيعات دائماً هو نفسه. الإدارة عند تغطية المكتب تختار باسم من يسجّل.
    if (window.AGENT && CFG.sales_agents[window.AGENT]) { sel.value = window.AGENT; }

    var sf = $("statusFilter");
    sf.innerHTML = "<option value=''>كل الحالات</option>"
      + CFG.statuses.map(function (s) {
        return "<option value='" + esc(s) + "'>" + esc(L("status", s)) + "</option>";
      }).join("");
    sf.addEventListener("change", renderLeads);
    $("search").addEventListener("input", renderLeads);

    $("dProduct").innerHTML = CFG.products.map(function (p) {
      return "<option value='" + esc(p) + "'>" + esc(L("product", p)) + "</option>";
    }).join("");
    Array.prototype.forEach.call(document.querySelectorAll(".cur"), function (e) {
      e.textContent = CFG.currency;
    });

    $("drawerClose").addEventListener("click", function () {
      $("drawer").classList.add("hide");
    });
    $("drawer").addEventListener("click", function (e) {
      if (e.target === $("drawer")) { $("drawer").classList.add("hide"); }
    });
    $("dSave").addEventListener("click", save);

    $("dFixSave").addEventListener("click", function () {
      api("/api/lead/phone", { lead_id: current.lead_id,
                               phone: $("dFixPhone").value })
        .then(function (j) {
          msg($("drawerMsg"), j.duplicate_of
            ? "تم التصحيح — لكن الرقم مسجّل على " + j.duplicate_of
            : "تم تصحيح الرقم إلى " + j.phone, j.duplicate_of ? "warn" : "ok");
          $("fixPhoneBox").classList.add("hide");
          load();
        })
        .catch(function (e) { msg($("drawerMsg"), e.message, "err"); });
    });

    load().catch(function (e) { msg($("msg"), e.message, "err"); });
    setInterval(load, 60000);   // القائمة حسّاسة للوقت
  }

  boot();
})();
