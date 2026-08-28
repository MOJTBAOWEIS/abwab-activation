/* تبويب الإعدادات — الفروع، المروّجون، المبيعات، الشفتات وقواعد التشغيل.
   كل شي هنا يُحفظ في قاعدة البيانات فوراً، بدون إعادة تشغيل السيرفر. */

(function () {
  "use strict";

  var CFG = window.CFG;
  var S = null;                       // آخر نسخة من /api/setup
  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function say(text, kind) {
    var el = $("setupMsg");
    if (!el) { return; }
    el.className = "msg" + (kind ? " " + kind : "");
    el.textContent = text || "";
    if (kind === "ok") {
      setTimeout(function () { if (el.textContent === text) { el.textContent = ""; } }, 3000);
    }
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (r.status === 401) { window.location = "/login"; return; }
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.error || "تعذّر الحفظ"); }
        return j;
      });
    });
  }

  function inp(value, ph, cls, type) {
    return "<input class='" + (cls || "") + "' type='" + (type || "text")
      + "' value='" + esc(value == null ? "" : value) + "' placeholder='"
      + esc(ph || "") + "'>";
  }

  function branchOptions(selected) {
    return "<option value=''>— بدون —</option>" + S.branches.map(function (b) {
      return "<option value='" + esc(b.code) + "'"
        + (b.code === selected ? " selected" : "") + ">" + esc(b.name) + "</option>";
    }).join("");
  }

  function usedCell(n) {
    return n
      ? "<span class='sub' title='عدد السجلات المرتبطة'>" + n + " سجل</span>"
      : "<span class='sub'>—</span>";
  }

  // كلمات السر مخزّنة مشفّرة ولا تُقرأ أبداً — تُكتب الجديدة فقط
  function pwInput(existing) {
    return "<input class='f-pin mono' type='text' value='' placeholder='"
      + (existing ? "اتركه فارغاً بدون تغيير" : "8 خانات، حروف وأرقام")
      + "'>";
  }

  function activeBox(on) {
    return "<input type='checkbox' class='chk'" + (on ? " checked" : "") + ">";
  }

  /* ------------------------------------------------------------ الفروع */
  function branchesBlock() {
    var rows = S.branches.map(function (b) {
      return "<tr data-code='" + esc(b.code) + "'>"
        + "<td class='mono'>" + esc(b.code) + "</td>"
        + "<td>" + inp(b.name, "اسم الفرع", "f-name") + "</td>"
        + "<td style='text-align:center'>" + activeBox(b.active) + "</td>"
        + "<td>" + usedCell(b.used) + "</td>"
        + "<td class='acts'><button class='btn sm save'>حفظ</button>"
        + "<button class='btn sm del'>حذف</button></td></tr>";
    }).join("");

    rows += "<tr class='newrow' data-new='branch'>"
      + "<td>" + inp("", "B05", "f-code mono") + "</td>"
      + "<td>" + inp("", "اسم الفرع الجديد", "f-name") + "</td>"
      + "<td colspan='2' class='sub'>فرع جديد</td>"
      + "<td class='acts'><button class='btn sm primary add'>إضافة</button></td></tr>";

    return sect("الفروع",
      "الفرع المرتبط ببيانات سابقة لا يُحذف نهائياً — يُوقَف فقط، فيختفي من القوائم "
      + "وتبقى ليداته القديمة كما هي.",
      "<div class='tw'><table><thead><tr><th style='width:90px'>الرمز</th><th>الاسم</th>"
      + "<th style='width:60px'>فعّال</th><th style='width:90px'>مرتبط بـ</th>"
      + "<th style='width:150px'></th></tr></thead><tbody>" + rows
      + "</tbody></table></div>");
  }

  /* -------------------------------------------------------- المروّجون */
  function promotersBlock() {
    var rows = S.promoters.map(function (p) {
      return "<tr data-code='" + esc(p.code) + "'>"
        + "<td class='mono'>" + esc(p.code) + "</td>"
        + "<td>" + inp(p.name, "الاسم", "f-name") + "</td>"
        + "<td><select class='f-branch'>" + branchOptions(p.branch) + "</select></td>"
        + "<td>" + pwInput(true) + "</td>"
        + "<td style='text-align:center'>" + activeBox(p.active) + "</td>"
        + "<td>" + usedCell(p.used) + "</td>"
        + "<td class='acts'><button class='btn sm save'>حفظ</button>"
        + "<button class='btn sm del'>حذف</button></td></tr>";
    }).join("");

    rows += "<tr class='newrow' data-new='promoter'>"
      + "<td>" + inp("", "P07", "f-code mono") + "</td>"
      + "<td>" + inp("", "اسم المروّج", "f-name") + "</td>"
      + "<td><select class='f-branch'>" + branchOptions("") + "</select></td>"
      + "<td>" + pwInput(false) + "</td>"
      + "<td colspan='2' class='sub'>مروّج جديد</td>"
      + "<td class='acts'><button class='btn sm primary add'>إضافة</button></td></tr>";

    return sect("المروّجون",
      "الفرع هنا هو فرعه الافتراضي — يقدر يغيّره من شاشته إذا غطّى فرعاً آخر. "
      + "كلمات السر مخزّنة مشفّرة — حتى أنت ما تقدر تقرأها. اكتب كلمة سر جديدة "
      + "لتغييرها، أو اتركها فارغة لتبقى كما هي. 8 خانات على الأقل، حروف وأرقام.",
      "<div class='tw'><table><thead><tr><th style='width:80px'>الرمز</th><th>الاسم</th>"
      + "<th style='width:170px'>الفرع</th><th style='width:90px'>الرمز السري</th>"
      + "<th style='width:60px'>فعّال</th><th style='width:90px'>مرتبط بـ</th>"
      + "<th style='width:150px'></th></tr></thead><tbody>" + rows
      + "</tbody></table></div>");
  }

  /* ---------------------------------------------------- موظفو المبيعات */
  function agentsBlock() {
    var rows = S.agents.map(function (a) {
      return "<tr data-code='" + esc(a.code) + "'>"
        + "<td class='mono'>" + esc(a.code) + "</td>"
        + "<td>" + inp(a.name, "الاسم", "f-name") + "</td>"
        + "<td>" + pwInput(true) + "</td>"
        + "<td style='text-align:center'>" + activeBox(a.active) + "</td>"
        + "<td>" + usedCell(a.used) + "</td>"
        + "<td class='acts'><button class='btn sm save'>حفظ</button>"
        + "<button class='btn sm del'>حذف</button></td></tr>";
    }).join("");

    rows += "<tr class='newrow' data-new='agent'>"
      + "<td>" + inp("", "S03", "f-code mono") + "</td>"
      + "<td>" + inp("", "اسم الموظف", "f-name") + "</td>"
      + "<td>" + pwInput(false) + "</td>"
      + "<td colspan='2' class='sub'>موظف جديد</td>"
      + "<td class='acts'><button class='btn sm primary add'>إضافة</button></td></tr>";

    return sect("موظفو المبيعات", "",
      "<div class='tw'><table><thead><tr><th style='width:80px'>الرمز</th><th>الاسم</th>"
      + "<th style='width:150px'>كلمة السر</th><th style='width:60px'>فعّال</th>"
      + "<th style='width:90px'>مرتبط بـ</th><th style='width:150px'></th></tr></thead>"
      + "<tbody>" + rows + "</tbody></table></div>");
  }

  /* ----------------------------------------------------- الشفتات وأوقاتها */
  function shiftsBlock() {
    var rows = S.shifts.map(function (s) {
      return "<tr data-id='" + s.id + "'>"
        + "<td>" + inp(s.name, "اسم الشفت", "f-name") + "</td>"
        + "<td>" + inp(s.start_time, "09:00", "f-start mono", "time") + "</td>"
        + "<td>" + inp(s.end_time, "15:00", "f-end mono", "time") + "</td>"
        + "<td class='sub n'>" + hours(s.start_time, s.end_time) + " ساعة</td>"
        + "<td class='acts'><button class='btn sm save'>حفظ</button>"
        + "<button class='btn sm del'>حذف</button></td></tr>";
    }).join("");

    rows += "<tr class='newrow' data-new='shift'>"
      + "<td>" + inp("", "اسم الشفت", "f-name") + "</td>"
      + "<td>" + inp("", "", "f-start mono", "time") + "</td>"
      + "<td>" + inp("", "", "f-end mono", "time") + "</td>"
      + "<td class='sub'>شفت جديد</td>"
      + "<td class='acts'><button class='btn sm primary add'>إضافة</button></td></tr>";

    return sect("الشفتات وأوقاتها",
      "وقت بداية الشفت الذي يفتحه المروّج هو الذي يحدّد اسم شفته. تغيير الأوقات هنا "
      + "يطبّق على الشفتات الجديدة فقط — الشفتات المسجّلة سابقاً تحتفظ باسمها.",
      "<div class='tw'><table><thead><tr><th>الاسم</th><th style='width:130px'>من</th>"
      + "<th style='width:130px'>إلى</th><th style='width:100px'>الطول</th>"
      + "<th style='width:150px'></th></tr></thead><tbody>" + rows
      + "</tbody></table></div>");
  }

  function hours(a, b) {
    function m(t) {
      var p = String(t || "").split(":");
      return (parseInt(p[0], 10) || 0) * 60 + (parseInt(p[1], 10) || 0);
    }
    var d = m(b) - m(a);
    if (d < 0) { d += 24 * 60; }
    return (d / 60).toFixed(1);
  }

  /* ------------------------------------------------ جدول المناوبات */
  function rosterBlock() {
    var rows = (S.roster || []).map(function (r) {
      return "<tr data-rid='" + r.id + "'>"
        + "<td class='mono'>" + esc(r.date) + "</td>"
        + "<td>" + esc(promoterName(r.promoter_code)) + "</td>"
        + "<td>" + esc(branchName(r.branch)) + "</td>"
        + "<td>" + esc(r.shift_type) + "</td>"
        + "<td class='sub'>" + esc(r.note || "") + "</td>"
        + "<td class='acts'><button class='btn sm rdel'>حذف</button></td></tr>";
    }).join("");

    if (!rows) {
      rows = "<tr><td colspan='6' class='sub' style='padding:16px'>"
        + "لا توجد مناوبات مجدولة. أضف واحدة من السطر أدناه.</td></tr>";
    }

    var promoterOpts = S.promoters.filter(function (p) { return p.active; })
      .map(function (p) {
        return "<option value='" + esc(p.code) + "'>" + esc(p.name) + "</option>";
      }).join("");
    var shiftOpts = S.shifts.map(function (t) {
      return "<option value='" + esc(t.name) + "'>" + esc(t.name)
        + " (" + esc(t.start_time) + "–" + esc(t.end_time) + ")</option>";
    }).join("");

    rows += "<tr class='newrow' data-new='roster'>"
      + "<td>" + inp(today(), "", "r-date mono", "date") + "</td>"
      + "<td><select class='r-promoter'>" + promoterOpts + "</select></td>"
      + "<td><select class='r-branch'>" + branchOptions("") + "</select></td>"
      + "<td><select class='r-shift'>" + shiftOpts + "</select></td>"
      + "<td>" + inp("", "ملاحظة", "r-note") + "</td>"
      + "<td class='acts'><button class='btn sm primary radd'>إضافة</button></td></tr>";

    return sect("جدول المناوبات",
      "مَن المفروض يشتغل، متى، وبأي فرع. هذا الجدول لا يمنع أي مروّج من التسجيل — "
      + "المروّج يقدر يبدأ بأي وقت. الجدول موجود حتى تشوف أنت الفرق بين الخطة وما صار "
      + "فعلاً في «مناوبات اليوم» بتبويب نظرة عامة.",
      "<div class='tw'><table><thead><tr><th style='width:150px'>التاريخ</th>"
      + "<th>المروّج</th><th>الفرع</th><th style='width:170px'>الشفت</th>"
      + "<th>ملاحظة</th><th style='width:100px'></th></tr></thead><tbody>"
      + rows + "</tbody></table></div>");
  }

  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0")
      + "-" + String(d.getDate()).padStart(2, "0");
  }

  function promoterName(code) {
    var p = S.promoters.filter(function (x) { return x.code === code; })[0];
    return p ? p.name : code;
  }

  function branchName(code) {
    var b = S.branches.filter(function (x) { return x.code === code; })[0];
    return b ? b.name : code;
  }

  /* ------------------------------------------------- قواعد التشغيل */
  var RULES = [
    ["currency", "العملة", "text", "الرمز الذي يظهر بجانب كل مبلغ"],
    ["phone_total_digits", "عدد خانات الهاتف", "number",
      "العدد الكامل مع الصفر — 11 للعراق"],
    ["phone_prefix", "بداية الرقم", "text", "07 للعراق. الرقم يُرفض إذا ما بدأ بها"],
    ["sla_hours", "مهلة الاتصال (ساعة)", "number", "المهلة التي يجب أن تتصل المبيعات خلالها"],
    ["maturity_days", "عمر الليد الناضج (يوم)", "number",
      "لا يُحسب في نسبة الشراء قبل هذا العمر"],
    ["break_hours", "الاستراحة (ساعة)", "number", "تُخصم من طول كل شفت"],
    ["max_contact_attempts", "محاولات قبل «لا يرد»", "number", ""],
    ["stale_days", "أيام الركود", "number", "ليد قيد المتابعة بلا تحديث يُعلَّم بعدها"],
    ["gift_gap_tolerance", "فرق الهدايا المسموح", "number", "نسبة، مثل 0.15 تعني 15%"],
    ["min_shifts_for_ranking", "أقل عدد شفتات للترتيب", "number", ""],
    ["min_hours_for_ranking", "أقل عدد ساعات للترتيب", "number", ""],
    ["min_branch_hours_for_ranking", "أقل ساعات لترتيب الفرع", "number", ""],
    ["min_mature_leads", "أقل ليدات ناضجة للنتيجة", "number",
      "تحتها تُوزَّع أوزان الشراء وتُعلَّم النتيجة مبدئية"],
    ["manager_pin", "كلمة سر المدير الجديدة", "text",
      "اتركها فارغة لتبقى كما هي. 8 خانات على الأقل، حروف وأرقام معاً."],
    ["late_grace_minutes", "سماح التأخير (دقيقة)", "number",
      "بعدها تُحسب المناوبة متأخرة في تقرير الحضور"]
  ];

  function rulesBlock() {
    var body = RULES.map(function (r) {
      return "<div class='field' style='margin-bottom:12px'>"
        + "<label class='f' for='set-" + r[0] + "'>" + esc(r[1]) + "</label>"
        + "<input id='set-" + r[0] + "' data-key='" + r[0] + "' type='" + r[2]
        + "' step='any' value='" + esc(S.settings[r[0]] == null ? "" : S.settings[r[0]])
        + "'>"
        + (r[3] ? "<p class='sub' style='margin-top:5px'>" + esc(r[3]) + "</p>" : "")
        + "</div>";
    }).join("");

    return sect("قواعد التشغيل",
      "هذه الأرقام تدخل مباشرة في حساب القمع والنتائج. غيّرها بوعي — تغيير مهلة "
      + "الاتصال أو عمر الليد الناضج يعيد حساب كل الأرقام في اللوحة فوراً.",
      "<div class='card pad'><div class='grid g3'>" + body + "</div>"
      + "<button class='btn primary' id='saveRules' style='margin-top:6px'>حفظ القواعد</button>"
      + "</div>");
  }

  function sect(title, hint, body) {
    return "<div class='section'><header><h2>" + esc(title) + "</h2>"
      + (hint ? "<span class='hint'>" + esc(hint) + "</span>" : "")
      + "</header>" + body + "</div>";
  }

  /* ------------------------------------------------------------ الأحداث */
  function wire() {
    var host = $("tab-setup");

    host.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) { return; }
      var tr = btn.closest("tr");
      if (!tr) { return; }
      var q = function (sel) { return tr.querySelector(sel); };
      var val = function (sel) { var el = q(sel); return el ? el.value.trim() : ""; };
      var checked = function () { var c = q(".chk"); return c ? c.checked : true; };
      var kind = tr.dataset.new;

      // ---- الفروع
      if (tr.closest("table") === host.querySelectorAll("table")[0]) {
        if (btn.classList.contains("add")) {
          return send("/api/setup/branch",
            { code: val(".f-code"), name: val(".f-name"), active: true });
        }
        if (btn.classList.contains("save")) {
          return send("/api/setup/branch",
            { code: tr.dataset.code, name: val(".f-name"), active: checked() });
        }
        if (btn.classList.contains("del")) { return confirmDelete("branch", tr.dataset.code); }
      }

      // ---- المروّجون
      if (tr.closest("table") === host.querySelectorAll("table")[1]) {
        var pbody = {
          code: kind ? val(".f-code") : tr.dataset.code,
          name: val(".f-name"), branch: val(".f-branch"), pin: val(".f-pin"),
          active: kind ? true : checked()
        };
        if (btn.classList.contains("add") || btn.classList.contains("save")) {
          return send("/api/setup/promoter", pbody);
        }
        if (btn.classList.contains("del")) { return confirmDelete("promoter", tr.dataset.code); }
      }

      // ---- المبيعات
      if (tr.closest("table") === host.querySelectorAll("table")[2]) {
        var abody = {
          code: kind ? val(".f-code") : tr.dataset.code,
          name: val(".f-name"), pin: val(".f-pin"),
          active: kind ? true : checked()
        };
        if (btn.classList.contains("add") || btn.classList.contains("save")) {
          return send("/api/setup/agent", abody);
        }
        if (btn.classList.contains("del")) { return confirmDelete("agent", tr.dataset.code); }
      }

      // ---- جدول المناوبات
      if (btn.classList.contains("radd")) {
        return send("/api/setup/roster", {
          date: val(".r-date"), promoter_code: val(".r-promoter"),
          branch: val(".r-branch"), shift_type: val(".r-shift"),
          note: val(".r-note")
        });
      }
      if (btn.classList.contains("rdel")) {
        return send("/api/setup/roster/delete", { id: tr.dataset.rid });
      }

      // ---- الشفتات
      if (tr.closest("table") === host.querySelectorAll("table")[3]) {
        var sbody = {
          id: kind ? null : tr.dataset.id,
          name: val(".f-name"), start_time: val(".f-start"), end_time: val(".f-end")
        };
        if (btn.classList.contains("add") || btn.classList.contains("save")) {
          return send("/api/setup/shift", sbody);
        }
        if (btn.classList.contains("del")) {
          if (!window.confirm("حذف هذا الشفت؟")) { return; }
          return send("/api/setup/shift/delete", { id: tr.dataset.id });
        }
      }
    });

    var rules = $("saveRules");
    if (rules) {
      rules.addEventListener("click", function () {
        var body = {};
        host.querySelectorAll("input[data-key]").forEach(function (el) {
          body[el.dataset.key] = el.value.trim();
        });
        send("/api/setup/settings", body);
      });
    }
  }

  function confirmDelete(kind, code) {
    var label = { branch: "الفرع", promoter: "المروّج", agent: "الموظف" }[kind];
    if (!window.confirm("حذف " + label + " «" + code + "»؟\n"
      + "إذا كان مرتبطاً ببيانات سابقة سيتم إيقافه بدل حذفه.")) { return; }
    send("/api/setup/" + kind + "/delete", { code: code });
  }

  function send(path, body) {
    post(path, body).then(function (j) {
      if (!j) { return; }
      // الرسالة تُعرض بعد إعادة الرسم، لأن الرسم يستبدل محتوى التبويب كله
      var text = j.deactivated
        ? "مرتبط بـ " + j.used + " سجل — تم إيقافه بدل حذفه، والبيانات القديمة سليمة."
        : (j.password_changed
            ? "تم الحفظ وتغيير كلمة السر. سجّلها الآن — ما راح تظهر مرة ثانية."
            : "تم الحفظ.");
      return render().then(function () {
        say(text, j.deactivated ? "warn" : "ok");
      });
    }).catch(function (e) { say(e.message, "err"); });
  }

  /* ------------------------------------------------------------- العرض */
  function render() {
    return Promise.all([
      fetch("/api/setup").then(function (r) {
        if (r.status === 401) { window.location = "/login"; return null; }
        return r.json();
      }),
      fetch("/api/setup/roster").then(function (r) { return r.ok ? r.json() : []; })
    ]).then(function (res) {
      var j = res[0];
      if (!j) { return; }
      j.roster = res[1] || [];
      S = j;
      $("tab-setup").innerHTML =
        "<div id='setupMsg' class='msg'></div>"
        + branchesBlock() + promotersBlock() + agentsBlock()
        + shiftsBlock() + rosterBlock() + rulesBlock();
      wire();
      // القوائم في بقية اللوحة تعتمد على هذه القيم، فتُحدَّث معها
      if (window.refreshConfig) { window.refreshConfig(); }
    });
  }

  window.renderSetup = render;
})();
