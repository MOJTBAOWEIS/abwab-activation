/* شاشة المبيعات — قائمة الاتصال هي قائمة العمل، والدرج يسجّل نتيجة الاتصال.
   وقت الاتصال يُختم لحظة الحفظ، حتى لا يكون مؤشر 24 ساعة كلاماً فقط. */

(function () {
  "use strict";

  var CFG = window.CFG;
  var $ = function (id) { return document.getElementById(id); };
  var leads = [];
  var current = null;
  var picked = { status: null };

  var pickedProducts = [];

  /* القيم مخزّنة بالإنجليزية؛ العرض فقط بالعربي. */
  function L(kind, value) {
    if (!value) return "";
    var m = (CFG.labels || {})[kind] || {};
    if (kind === "product" && typeof value === "string" && value.indexOf(",") !== -1) {
      return value.split(",").map(function (s) {
        var trimmed = s.trim();
        return m[trimmed] || trimmed;
      }).join("، ");
    }
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
      "New": "neutral",
      "Interested": "warn",
      "Not Interested": "bad",
      "Wrong Number": "bad",
      "No Answer": "bad",
      "Converted": "good",
      "Contacted": "neutral",
      "Follow-up": "warn",
      "Not Converted": "bad",
      "Invalid / Unreachable": "bad"
    }[s] || "mute";
    return "<span class='pill " + tone + "'>" + esc(L("status", s)) + "</span>";
  }

  var rawQueue = [];

  function formatArabicDate(dateStr) {
    if (!dateStr) return "تاريخ غير محدد";
    var parts = dateStr.split("-");
    if (parts.length !== 3) return dateStr;
    var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));

    var todayObj = new Date();
    var todayStr = todayObj.getFullYear() + "-"
      + String(todayObj.getMonth() + 1).padStart(2, '0') + "-"
      + String(todayObj.getDate()).padStart(2, '0');
    
    var yestObj = new Date();
    yestObj.setDate(yestObj.getDate() - 1);
    var yestStr = yestObj.getFullYear() + "-"
      + String(yestObj.getMonth() + 1).padStart(2, '0') + "-"
      + String(yestObj.getDate()).padStart(2, '0');

    var days = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
    var dayName = days[d.getDay()];

    if (dateStr === todayStr) {
      return "اليوم — " + dayName + " (" + dateStr + ")";
    } else if (dateStr === yestStr) {
      return "أمس — " + dayName + " (" + dateStr + ")";
    } else {
      return dayName + " (" + dateStr + ")";
    }
  }

  function getDateRange(mode, customFrom, customTo) {
    var todayObj = new Date();
    var todayStr = todayObj.getFullYear() + "-"
      + String(todayObj.getMonth() + 1).padStart(2, '0') + "-"
      + String(todayObj.getDate()).padStart(2, '0');

    if (mode === "today") {
      return { from: todayStr, to: todayStr };
    } else if (mode === "yesterday") {
      var yestObj = new Date();
      yestObj.setDate(yestObj.getDate() - 1);
      var yestStr = yestObj.getFullYear() + "-"
        + String(yestObj.getMonth() + 1).padStart(2, '0') + "-"
        + String(yestObj.getDate()).padStart(2, '0');
      return { from: yestStr, to: yestStr };
    } else if (mode === "week") {
      var day = todayObj.getDay();
      var diffToSat = (day + 1) % 7;
      var sat = new Date(todayObj);
      sat.setDate(todayObj.getDate() - diffToSat);
      var satStr = sat.getFullYear() + "-"
        + String(sat.getMonth() + 1).padStart(2, '0') + "-"
        + String(sat.getDate()).padStart(2, '0');
      return { from: satStr, to: todayStr };
    } else if (mode === "custom") {
      return { from: customFrom || null, to: customTo || null };
    }
    return { from: null, to: null };
  }

  function matchesDate(dateStr, range) {
    if (!dateStr) return true;
    var d = dateStr.slice(0, 10);
    if (range.from && d < range.from) return false;
    if (range.to && d > range.to) return false;
    return true;
  }

  function updateExportLinks() {
    var qFilterMode = $("queueDateFilter") ? $("queueDateFilter").value : "all";
    var qCustomFrom = $("queueDateFrom") ? $("queueDateFrom").value : "";
    var qCustomTo = $("queueDateTo") ? $("queueDateTo").value : "";
    var qRange = getDateRange(qFilterMode, qCustomFrom, qCustomTo);

    var qParams = ["queue=1"];
    if (qRange.from) qParams.push("from=" + encodeURIComponent(qRange.from));
    if (qRange.to) qParams.push("to=" + encodeURIComponent(qRange.to));
    var qBtn = $("exportQueueBtn");
    if (qBtn) {
      qBtn.href = "/api/export/leads.csv?" + qParams.join("&");
    }

    var lFilterMode = $("leadsDateFilter") ? $("leadsDateFilter").value : "all";
    var lCustomFrom = $("leadsDateFrom") ? $("leadsDateFrom").value : "";
    var lCustomTo = $("leadsDateTo") ? $("leadsDateTo").value : "";
    var lRange = getDateRange(lFilterMode, lCustomFrom, lCustomTo);
    var sf = $("statusFilter") ? $("statusFilter").value : "";

    var lParams = [];
    if (lRange.from) lParams.push("from=" + encodeURIComponent(lRange.from));
    if (lRange.to) lParams.push("to=" + encodeURIComponent(lRange.to));
    if (sf) lParams.push("status=" + encodeURIComponent(sf));
    var lBtn = $("exportLeadsBtn");
    if (lBtn) {
      lBtn.href = "/api/export/leads.csv" + (lParams.length ? "?" + lParams.join("&") : "");
    }
  }

  /* ---------------- قائمة الاتصال ---------------- */
  function renderQueue(rows) {
    if (rows) { rawQueue = rows; }
    var filterMode = $("queueDateFilter") ? $("queueDateFilter").value : "all";
    var customFrom = $("queueDateFrom") ? $("queueDateFrom").value : "";
    var customTo = $("queueDateTo") ? $("queueDateTo").value : "";
    var range = getDateRange(filterMode, customFrom, customTo);

    var filtered = rawQueue.filter(function (r) {
      var dateStr = r.date || (r.ts ? r.ts.slice(0, 10) : "");
      return matchesDate(dateStr, range);
    });

    var summaryEl = $("queueSummary");
    if (summaryEl) {
      summaryEl.textContent = "إجمالي ليدات قائمة الاتصال في هذه التصفية: " + filtered.length + " ليد"
        + (filterMode !== "all" ? " (مقسمة حسب التواريخ)" : "");
    }

    updateExportLinks();

    var host = $("queue");
    if (!filtered.length) {
      host.innerHTML = '<div class="empty">القائمة فاضية — لا توجد ليدات مطابقة للتصفية المحددة.</div>';
      return;
    }

    var groups = {};
    filtered.forEach(function (r) {
      var d = r.date || (r.ts ? r.ts.slice(0, 10) : "غير محدد");
      if (!groups[d]) { groups[d] = []; }
      groups[d].push(r);
    });

    var dates = Object.keys(groups).sort().reverse();
    var html = "";
    dates.forEach(function (dateKey) {
      var dayRows = groups[dateKey];
      html += "<div class='date-group'>"
        + "<div class='date-group-header'>"
        + "<span>📅 " + esc(formatArabicDate(dateKey)) + "</span>"
        + "<span class='pill primary'>" + dayRows.length + " ليد</span>"
        + "</div>"
        + "<div class='tw'><table><thead><tr><th>المهلة</th><th>الزبون</th><th class='n'>الهاتف</th>"
        + "<th>الصف</th><th>الحاجة</th><th>ملاحظة المروّج</th>"
        + "<th>المروّج</th><th>الفرع</th></tr></thead><tbody>";

      dayRows.forEach(function (r) {
        var left = r.hours_remaining < 0
          ? "متأخر " + Math.abs(r.hours_remaining).toFixed(1) + " س"
          : "باقي " + r.hours_remaining.toFixed(1) + " س";
        var phoneCell = r.callable
          ? esc(r.phone)
          : "<span class='pill bad'>" + esc(r.issue) + "</span>"
            + (r.phone ? "<div class='sub'>" + esc(r.phone) + "</div>" : "");
        html += "<tr class='qrow " + r.state + (r.callable ? "" : " broken")
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

      html += "</tbody></table></div></div>";
    });

    host.innerHTML = html;
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
    var filterMode = $("leadsDateFilter") ? $("leadsDateFilter").value : "all";
    var customFrom = $("leadsDateFrom") ? $("leadsDateFrom").value : "";
    var customTo = $("leadsDateTo") ? $("leadsDateTo").value : "";
    var range = getDateRange(filterMode, customFrom, customTo);

    var rows = leads.filter(function (l) {
      if (sf && l.status !== sf) { return false; }
      if (!matchesDate(l.date, range)) { return false; }
      if (!q) { return true; }
      return [l.lead_id, l.customer_name, l.phone, l.promoter, l.branch, l.date,
        L("grade", l.grade), L("interest", l.interest), L("status", l.status),
        l.promoter_note || ""]
        .join(" ").toLowerCase().indexOf(q) >= 0;
    });

    var summaryEl = $("leadsSummary");
    if (summaryEl) {
      var totalRev = rows.reduce(function (a, l) { return a + (l.revenue || 0); }, 0);
      var totalConv = rows.filter(function (l) { return l.purchase; }).length;
      summaryEl.textContent = "إجمالي الليدات المعروضة: " + rows.length + " ليد | تم الشراء: " + totalConv + " (الإيراد: " + money(totalRev) + ")";
    }

    updateExportLinks();

    var host = $("leads");
    if (!rows.length) { host.innerHTML = '<div class="empty">لا توجد نتائج مطابقة للتصفية.</div>'; return; }

    var groups = {};
    rows.slice(0, 300).forEach(function (l) {
      var d = l.date || "غير محدد";
      if (!groups[d]) { groups[d] = []; }
      groups[d].push(l);
    });

    var dates = Object.keys(groups).sort().reverse();
    var html = "";
    dates.forEach(function (dateKey) {
      var dayRows = groups[dateKey];
      html += "<div class='date-group'>"
        + "<div class='date-group-header'>"
        + "<span>📅 " + esc(formatArabicDate(dateKey)) + "</span>"
        + "<span class='pill primary'>" + dayRows.length + " ليد</span>"
        + "</div>"
        + "<div class='tw'><table><thead><tr><th>رقم الليد</th><th>الزبون</th><th class='n'>الهاتف</th>"
        + "<th>الصف</th><th>الحاجة</th><th>المروّج</th><th>الحالة</th>"
        + "<th>24 ساعة</th><th>ملاحظة المروّج</th>"
        + "<th class='n'>الإيراد</th><th></th></tr></thead><tbody>";

      dayRows.forEach(function (l) {
        var w = l.within_24h;
        var wp = w === "Yes" ? "good" : (w === "Pending" ? "warn" : "bad");
        var wt = { "Yes": "نعم", "No": "لا", "Pending": "بالانتظار" }[w] || w;
        html += "<tr><td class='mono' style='font-size:11px'>" + esc(l.lead_id) + "</td>"
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

      html += "</tbody></table></div></div>";
    });

    host.innerHTML = html;
    Array.prototype.forEach.call(host.querySelectorAll("button[data-id]"), function (b) {
      b.addEventListener("click", function () { openDrawer(b.dataset.id); });
    });
  }

  function renderProductChips() {
    var host = $("productChips");
    if (!host) return;
    host.innerHTML = "";
    CFG.products.forEach(function (p) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = L("product", p);
      if (pickedProducts.indexOf(p) !== -1) {
        b.setAttribute("aria-pressed", "true");
      }
      b.addEventListener("click", function () {
        var idx = pickedProducts.indexOf(p);
        if (idx === -1) {
          pickedProducts.push(p);
          b.setAttribute("aria-pressed", "true");
        } else {
          pickedProducts.splice(idx, 1);
          b.setAttribute("aria-pressed", "false");
        }
      });
      host.appendChild(b);
    });
  }

  /* ---------------- درج التسجيل ---------------- */
  function openDrawer(leadId) {
    current = leads.filter(function (l) { return l.lead_id === leadId; })[0];
    if (!current) { return; }
    picked.status = null;
    if (current.product) {
      pickedProducts = current.product.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    } else {
      pickedProducts = [];
    }
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

    renderProductChips();

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
      if (pickedProducts.length === 0) {
        return msg($("drawerMsg"), "اختر باقة أو منهج واحد على الأقل.", "err");
      }
      body.purchase = true;
      body.revenue = $("dRevenue").value;
      body.product = pickedProducts.join(", ");
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

    var qdf = $("queueDateFilter");
    if (qdf) {
      qdf.addEventListener("change", function () {
        var isCustom = qdf.value === "custom";
        $("queueDateFrom").classList.toggle("hide", !isCustom);
        $("queueDateTo").classList.toggle("hide", !isCustom);
        renderQueue();
      });
      $("queueDateFrom").addEventListener("change", function () { renderQueue(); });
      $("queueDateTo").addEventListener("change", function () { renderQueue(); });
      $("queueDateFrom").addEventListener("input", function () { renderQueue(); });
      $("queueDateTo").addEventListener("input", function () { renderQueue(); });
    }

    var ldf = $("leadsDateFilter");
    if (ldf) {
      ldf.addEventListener("change", function () {
        var isCustom = ldf.value === "custom";
        $("leadsDateFrom").classList.toggle("hide", !isCustom);
        $("leadsDateTo").classList.toggle("hide", !isCustom);
        renderLeads();
      });
      $("leadsDateFrom").addEventListener("change", function () { renderLeads(); });
      $("leadsDateTo").addEventListener("change", function () { renderLeads(); });
      $("leadsDateFrom").addEventListener("input", function () { renderLeads(); });
      $("leadsDateTo").addEventListener("input", function () { renderLeads(); });
    }

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
