/* لوحة الإدارة — أربعة تبويبات، كل الأرقام تُحسب من الفلاتر في الأعلى. */

(function () {
  "use strict";

  var CFG = window.CFG;
  var D = null;
  var $ = function (id) { return document.getElementById(id); };

  /* القيم مخزّنة بالإنجليزية في قاعدة البيانات — العرض فقط بالعربي. */
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

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function pct(v, d) { return (v == null) ? "—" : (v * 100).toFixed(d == null ? 1 : d) + "%"; }
  function num(v, d) { return Number(v || 0).toFixed(d == null ? 0 : d); }
  function money(v) {
    return Number(v || 0).toLocaleString("en-US",
      { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + " " + CFG.currency;
  }
  function tile(k, v, s, tone) {
    var isText = typeof v === "string" && !/^[\d.,\s%A-Z]+$/.test(v);
    return "<div class='stat " + (tone || "") + "'><div class='k'>" + esc(k) + "</div>"
      + "<div class='v" + (isText ? " empty" : "") + "'>" + v + "</div>"
      + (s ? "<div class='s'>" + esc(s) + "</div>" : "") + "</div>";
  }
  function table(head, rows) {
    if (!rows.length) { return '<div class="empty">لا توجد بيانات في هذه الفترة.</div>'; }
    return "<div class='tw'><table><thead><tr>"
      + head.map(function (h) {
        return "<th" + (h.n ? " class='n'" : "") + ">" + esc(h.t) + "</th>";
      }).join("")
      + "</tr></thead><tbody>" + rows.join("") + "</tbody></table></div>";
  }
  function section(title, hint, body) {
    return "<div class='section'><header><h2>" + esc(title) + "</h2>"
      + (hint ? "<span class='hint'>" + hint + "</span>" : "") + "</header>" + body + "</div>";
  }
  function flagChips(flags) {
    if (!flags || !flags.length) { return "<span class='sub'>سليم</span>"; }
    return flags.map(function (f) {
      var row = (D.quality.flags || []).filter(function (r) { return r.flag === f; })[0];
      return "<span class='flagchip " + (row ? row.severity : "medium") + "' title='"
        + esc(L("flag", f)) + "'>" + esc(f) + "</span>";
    }).join("");
  }

  /* ============================== 1. نظرة عامة ============================== */
  function paintOverview() {
    var o = D.overview, q = D.quality, f = D.funnel;

    var tiles = [
      tile("المحادثات", num(o.conversations)),
      tile("ليدات مؤهلة", num(o.qualified)),
      tile("ليدات مسجّلة", num(o.captured), "إجمالي الليدات", "accent"),
      tile("مشتريات", num(o.purchases), "", "good"),
      tile("الإيراد", money(o.revenue), "", "good"),
      tile("نسبة التحويل", pct(o.overall_conversion, 2), "مشتريات ÷ محادثات")
    ];
    if (o.cost_per_lead != null) {
      tiles.push(tile("تكلفة الليد", money(o.cost_per_lead)));
      tiles.push(tile("تكلفة الاستحواذ", money(o.cost_per_acquisition)));
    } else {
      tiles.push(tile("تكلفة الليد", "لم تُدخل التكاليف", "أضفها في تبويب التكاليف"));
      tiles.push(tile("تكلفة الاستحواذ", "لم تُدخل التكاليف", "أضفها في تبويب التكاليف"));
    }

    var max = Math.max.apply(null, f.stages.map(function (s) { return s.value; })) || 1;
    var funnel = f.stages.map(function (s) {
      var w = Math.max((s.value / max) * 100, s.value ? 7 : 0);
      var meta = s.conversion == null
        ? "<span class='sub'>التقى بهم المروّج</span>"
        : "<b>−" + s.lost + "</b> ضاعوا · " + pct(s.conversion, 0);
      return "<div class='fstage'><div class='fn'>" + esc(L("stage", s.key)) + "</div>"
        + "<div class='ftrack'><div class='fbar' style='width:" + w + "%'>"
        + s.value + "</div></div><div class='fmeta'>" + meta + "</div></div>";
    }).join("");

    var calls = "";
    if (f.biggest_leak) {
      calls += "<div class='callout bad'><div class='k'>أكبر نقطة تسريب</div><div class='v'>"
        + esc(L("stage", f.biggest_leak)) + "</div><div class='sub'>"
        + esc(L("leak", f.biggest_leak)) + "</div></div>";
    }
    if (D.promoters.top) {
      calls += "<div class='callout good'><div class='k'>أفضل مروّج</div><div class='v'>"
        + esc(D.promoters.top.name) + "</div><div class='sub'>النتيجة "
        + num(D.promoters.top.score) + "</div></div>";
    }
    if (D.branches.top) {
      calls += "<div class='callout good'><div class='k'>أفضل فرع</div><div class='v'>"
        + esc(D.branches.top.name) + "</div><div class='sub'>الأداء "
        + num(D.branches.top.execution) + "</div></div>";
    }
    calls += "<div class='callout " + (q.critical_count ? "bad" : "good")
      + "'><div class='k'>يحتاج انتباه</div><div class='v'>" + q.critical_count
      + " أخطاء حرجة</div><div class='sub'>" + D.sla_queue.length
      + " ليد بانتظار أول اتصال</div></div>";

    var daily = D.daily.map(function (d) {
      return "<tr><td><strong>" + esc(d.date) + "</strong></td>"
        + "<td class='n'>" + num(d.hours, 1) + "</td>"
        + "<td class='n'>" + d.conversations + "</td>"
        + "<td class='n'>" + d.qualified + "</td>"
        + "<td class='n'>" + d.captured + "</td>"
        + "<td class='n'>" + d.purchases + "</td>"
        + "<td class='n'>" + num(d.revenue) + "</td></tr>";
    });

    $("tab-overview").innerHTML =
      "<div class='grid g3'>" + tiles.join("") + "</div>"
      + attendanceBlock()
      + section("القمع", "أين نخسر الزبائن بين البوث والبيع.",
        "<div class='card pad'><div class='funnel'>" + funnel + "</div></div>")
      + section("أهم النقاط", "", "<div class='grid g4'>" + calls + "</div>")
      + section("حسب اليوم", "",
        table([{ t: "التاريخ" }, { t: "ساعات", n: 1 }, { t: "محادثات", n: 1 },
          { t: "مؤهّل", n: 1 }, { t: "مسجّل", n: 1 }, { t: "مشتريات", n: 1 },
          { t: "الإيراد", n: 1 }], daily));
  }

  /* --------------------------- مناوبات اليوم --------------------------- */
  function attendanceBlock() {
    var A = D.attendance;
    if (!A) { return ""; }

    var STATE = {
      absent:    ["لم يحضر", "bad"],
      late:      ["متأخر", "warn"],
      unplanned: ["بدون جدولة", "warn"],
      on_time:   ["في الموعد", "good"]
    };

    var rows = A.rows.map(function (r) {
      var st = STATE[r.state] || ["", "mute"];
      var late = (r.minutes_late != null && r.minutes_late > 0)
        ? " <span class='sub'>+" + r.minutes_late + " د</span>" : "";
      return "<tr>"
        + "<td><strong>" + esc(r.promoter_name) + "</strong></td>"
        + "<td>" + (r.planned_shift
            ? esc(L("shift", r.planned_shift)) + " <span class='sub'>"
              + esc(r.planned_start) + "</span>"
            : "<span class='sub'>—</span>") + "</td>"
        + "<td class='sub'>" + esc(r.planned_branch || "—") + "</td>"
        + "<td>" + (r.actual_start ? esc(r.actual_start) + late : "<span class='sub'>—</span>")
        + "</td>"
        + "<td class='sub'>" + esc(r.actual_branch || "—") + "</td>"
        + "<td class='n'>" + (r.conversations == null ? "—" : r.conversations) + "</td>"
        + "<td class='n'>" + r.captured + "</td>"
        + "<td><span class='pill " + st[1] + "'>" + st[0] + "</span>"
        + (r.open_now ? " <span class='pill neutral'>شغّال الآن</span>" : "") + "</td>"
        + "</tr>";
    });

    var summary = "<div class='grid g4' style='margin-bottom:12px'>"
      + tile("مجدولون اليوم", num(A.planned))
      + tile("حاضرون", num(A.present), "", A.present ? "good" : "")
      + tile("لم يحضروا", num(A.absent), "", A.absent ? "bad" : "good")
      + tile("متأخرون", num(A.late), "بعد " + A.grace + " دقيقة سماح",
        A.late ? "warn" : "good")
      + "</div>";

    return section("مناوبات اليوم — " + A.date,
      "الخطة مقابل الواقع. المروّج يقدر يبدأ بأي وقت بدون إذن، وهذا الجدول يبيّن لك "
      + "مَن كان مفروض يشتغل ومَن اشتغل فعلاً.",
      summary + table([{ t: "المروّج" }, { t: "الشفت المجدول" }, { t: "الفرع المجدول" },
        { t: "بدأ فعلاً" }, { t: "الفرع الفعلي" }, { t: "محادثات", n: 1 },
        { t: "مسجّل", n: 1 }, { t: "الحالة" }], rows));
  }

  /* ============================ 2. المروّجون والفروع ============================ */
  function paintTeam() {
    var prows = D.promoters.rows.map(function (r, i) {
      var badge = !r.eligible
        ? "<span class='pill mute'>شفتات قليلة</span>"
        : "<span class='pill " + r.tone + "'>" + esc(L("score_band", r.band)) + "</span>";
      return "<tr><td class='rank'>" + (r.eligible ? i + 1 : "—") + "</td>"
        + "<td><strong>" + esc(r.name) + "</strong><div class='sub'>" + esc(r.branch)
        + "</div></td>"
        + "<td class='n'>" + num(r.hours, 1) + "</td>"
        + "<td class='n'>" + r.conversations + "</td>"
        + "<td class='n'>" + r.qualified + "</td>"
        + "<td class='n'>" + r.captured + "</td>"
        + "<td class='n'>" + r.purchases + "</td>"
        + "<td class='n'>" + num(r.revenue) + "</td>"
        + "<td><div class='scorecell'><span class='n'>" + num(r.score) + "</span>"
        + badge + "</div></td></tr>";
    });

    var brows = D.branches.rows.map(function (r, i) {
      return "<tr><td class='rank'>" + (r.eligible ? i + 1 : "—") + "</td>"
        + "<td><strong>" + esc(r.name) + "</strong></td>"
        + "<td class='n'>" + num(r.hours, 1) + "</td>"
        + "<td class='n'>" + r.conversations + "</td>"
        + "<td class='n'>" + r.captured + "</td>"
        + "<td class='n'>" + r.purchases + "</td>"
        + "<td class='n'>" + num(r.revenue) + "</td>"
        + "<td><div class='scorecell'><span class='n'>" + num(r.execution) + "</span>"
        + (r.eligible ? "<span class='pill " + r.tone + "'>" + esc(L("score_band", r.band))
          + "</span>" : "<span class='pill mute'>تغطية قليلة</span>") + "</div></td>"
        + "<td class='n'>" + num(r.site_value) + "</td></tr>";
    });

    var weak = D.promoters.rows.filter(function (r) { return r.eligible && r.score < 90; });
    var coach = weak.map(function (r) {
      return "<tr><td><strong>" + esc(r.name) + "</strong></td>"
        + "<td><span class='pill " + r.tone + "'>" + num(r.score) + "</span></td>"
        + "<td>" + esc(L("metric", r.weakest)) + "</td></tr>";
    });

    $("tab-team").innerHTML =
      section("المروّجون",
        "الكمية تُقسم على ساعات العمل وتُقارن بالفرع نفسه، حتى لا يُظلم أحد بسبب شفت هادئ. "
        + "100 = المتوسط.",
        table([{ t: "#" }, { t: "المروّج" }, { t: "ساعات", n: 1 }, { t: "محادثات", n: 1 },
          { t: "مؤهّل", n: 1 }, { t: "مسجّل", n: 1 }, { t: "مشتريات", n: 1 },
          { t: "الإيراد", n: 1 }, { t: "النتيجة" }], prows))
      + (coach.length ? section("من يحتاج تدريب", "نقطة واحدة يُعمل عليها مع كل شخص.",
        table([{ t: "المروّج" }, { t: "النتيجة" }, { t: "أضعف نقطة" }], coach)) : "")
      + section("الفروع",
        "<strong>الأداء</strong> = هل الفريق هنا شغّال (لكل ساعة عمل). "
        + "<strong>قيمة الموقع</strong> = الإيراد مقابل ساعات العمل في الفرع.",
        table([{ t: "#" }, { t: "الفرع" }, { t: "ساعات", n: 1 }, { t: "محادثات", n: 1 },
          { t: "مسجّل", n: 1 }, { t: "مشتريات", n: 1 }, { t: "الإيراد", n: 1 },
          { t: "الأداء" }, { t: "قيمة الموقع", n: 1 }], brows));
  }

  /* ============================ 3. الليدات ============================ */
  function paintLeads() {
    var wanted = [
      ["Grade Band", "المرحلة الدراسية", "band"],
      ["Interest / Need", "الحاجة", "interest"],
      ["Customer Type", "نوع الزبون", "customer_type"],
      ["Branch", "الفرع", null]
    ];
    var blocks = wanted.map(function (w) {
      var rows = D.lead_quality[w[0]] || [];
      if (!rows.length) { return ""; }
      var max = Math.max.apply(null, rows.map(function (r) { return r.captured; })) || 1;
      var body = rows.map(function (r) {
        var label = w[2] ? L(w[2], r.key) : r.key;
        return "<div class='minibar'><div class='lb' title='" + esc(label) + "'>"
          + esc(label) + "</div>"
          + "<div class='bar'><i style='width:" + (r.captured / max * 100) + "%'></i></div>"
          + "<div class='n'>" + r.captured + "</div>"
          + "<div class='n pr'>" + (r.mature ? pct(r.purchase_rate, 0) : "—") + "</div></div>";
      }).join("");
      return "<div class='card pad'><div class='spread' style='margin-bottom:8px'>"
        + "<strong>" + esc(w[1]) + "</strong><span class='sub'>ليدات · نسبة الشراء</span>"
        + "</div>" + body + "</div>";
    }).join("");

    var queue = D.sla_queue.slice(0, 40).map(function (r) {
      var left = r.hours_remaining < 0
        ? "متأخر " + Math.abs(r.hours_remaining).toFixed(0) + " س"
        : "باقي " + r.hours_remaining.toFixed(0) + " س";
      var tone = r.state === "breached" ? "bad" : (r.state === "urgent" ? "warn" : "good");
      return "<tr><td><span class='pill " + tone + "'>" + left + "</span></td>"
        + "<td><strong>" + esc(r.customer_name) + "</strong></td>"
        + "<td class='n'>" + esc(r.phone) + "</td>"
        + "<td>" + esc(L("grade", r.grade)) + "</td>"
        + "<td>" + esc(L("interest", r.interest)) + "</td>"
        + "<td class='notecell'>" + esc(r.promoter_note || "") + "</td>"
        + "<td>" + esc(r.promoter_name) + "</td></tr>";
    });

    var rates = D.rates.map(function (r) {
      return "<tr><td><strong>" + esc(L("rate", r.key)) + "</strong></td>"
        + "<td class='n sub'>" + r.num + " / " + r.den + "</td>"
        + "<td style='width:140px'><div class='bar'><i style='width:"
        + Math.min(r.value * 100, 100) + "%'></i></div></td>"
        + "<td class='n'><strong>" + pct(r.value) + "</strong></td></tr>";
    });

    $("tab-leads").innerHTML =
      section("ماذا يريد الزبائن",
        "الرقم الأخضر هو نسبة الشراء الفعلية لكل فئة — هذا هو الرقم الذي يُبنى عليه القرار، "
        + "وليس عدد الليدات.",
        "<div class='grid g2'>" + blocks + "</div>")
      + section("نسب التحويل", "",
        table([{ t: "النسبة" }, { t: "العدد", n: 1 }, { t: "" }, { t: "%", n: 1 }], rates))
      + section("بانتظار أول اتصال",
        D.sla_queue.length + " ليد في القائمة. المبيعات تشتغل عليها.",
        table([{ t: "المهلة" }, { t: "الزبون" }, { t: "الهاتف", n: 1 }, { t: "الصف" },
          { t: "الحاجة" }, { t: "ملاحظة المروّج" }, { t: "المروّج" }], queue));
  }

  /* ============================ 4. البيانات والتكاليف ============================ */
  function paintData() {
    var q = D.quality;

    var tiles = "<div class='grid g4'>"
      + tile("جودة البيانات", pct(q.score), q.flagged + " من " + q.total + " سجل",
        q.score >= 0.95 ? "good" : (q.score >= 0.85 ? "warn" : "bad"))
      + tile("أخطاء حرجة", num(q.critical_count), "يجب أن تكون صفراً",
        q.critical_count ? "bad" : "good")
      + tile("مشاكل متابعة", num(q.ops_flagged), "مسؤولية المبيعات",
        q.ops_flagged ? "warn" : "good")
      + tile("شفتات مفتوحة", num(q.open_shifts.length), "بدون وقت إنهاء",
        q.open_shifts.length ? "warn" : "good")
      + "</div>";

    var flagRows = q.flags.map(function (f) {
      return "<tr><td><span class='flagchip " + f.severity + "'>" + esc(f.flag)
        + "</span></td><td class='n'><strong>" + f.count + "</strong></td>"
        + "<td>" + esc(L("severity", f.severity)) + "</td>"
        + "<td>" + esc(L("owner", f.owner)) + "</td>"
        + "<td>" + esc(L("flag", f.flag)) + "</td></tr>";
    });

    function leadRow(l) {
      return "<tr><td class='mono' style='font-size:11px'>" + esc(l.lead_id) + "</td>"
        + "<td class='sub'>" + esc(l.date) + "</td>"
        + "<td><strong>" + esc(l.customer_name || "—") + "</strong></td>"
        + "<td class='n'>" + esc(l.phone || "—") + "</td>"
        + "<td>" + esc(l.promoter) + "</td>"
        + "<td>" + esc(L("status", l.status)) + "</td>"
        + "<td>" + flagChips(l.flags) + "</td></tr>";
    }
    var lhead = [{ t: "رقم الليد" }, { t: "التاريخ" }, { t: "الزبون" },
      { t: "الهاتف", n: 1 }, { t: "المروّج" }, { t: "الحالة" }, { t: "المشاكل" }];

    function list(title, rows, tone) {
      if (!rows.length) { return ""; }
      return "<details class='exp'><summary>" + esc(title) + " <span class='pill "
        + (tone || "bad") + "'>" + rows.length + "</span></summary>"
        + table(lhead, rows.map(leadRow)) + "</details>";
    }

    var costForm =
      "<div class='card pad' style='margin-bottom:14px'>"
      + "<div class='row'>"
      + "<div><label class='f' for='kDate'>التاريخ</label><input id='kDate' type='date'></div>"
      + "<div><label class='f' for='kBranch'>الفرع</label><select id='kBranch'></select></div>"
      + "<div><label class='f' for='kType'>النوع</label><select id='kType'></select></div>"
      + "<div><label class='f' for='kAmount'>المبلغ</label>"
      + "<input id='kAmount' type='number' step='0.01' min='0'></div>"
      + "<div style='flex:0 0 auto; display:flex; align-items:flex-end'>"
      + "<button class='btn primary' id='kAdd'>إضافة</button></div>"
      + "</div><div id='kMsg' class='msg' style='margin:12px 0 0'></div></div>"
      + "<div id='costTable'></div>";

    $("tab-data").innerHTML =
      section("جودة البيانات",
        "النتيجة تقيس سلامة سجل الليد نفسه. مشاكل المتابعة معروضة أيضاً، لكنها مسؤولية "
        + "المبيعات ولا تؤثر أبداً على نتيجة المروّج.",
        tiles)
      + section("المشاكل الموجودة", "",
        table([{ t: "الكود" }, { t: "العدد", n: 1 }, { t: "الخطورة" }, { t: "المسؤول" },
          { t: "المعنى" }], flagRows))
      + section("عالج هذه", "",
        list("أخطاء حرجة", q.critical)
        + list("لم يُتصل بهم / متأخر", q.sla, "warn")
        + list("بدون تسجيل شفت", q.no_shift_log, "warn"))
      + section("التكاليف",
        "تكلفة الليد وتكلفة الاستحواذ تبقى مخفية حتى تُدخل مبالغ حقيقية هنا.",
        costForm);

    wireCosts();
    loadCosts();
  }

  /* ------------------------------ التكاليف ------------------------------ */
  function wireCosts() {
    $("kDate").value = iso(new Date());
    $("kBranch").innerHTML = "<option value=''>كل الفروع</option>"
      + Object.keys(CFG.branches).map(function (k) {
        return "<option value='" + k + "'>" + esc(CFG.branches[k]) + "</option>";
      }).join("");
    $("kType").innerHTML = CFG.cost_types.map(function (t) {
      return "<option value='" + esc(t) + "'>" + esc(L("cost_type", t)) + "</option>";
    }).join("");
    $("kAdd").addEventListener("click", function () {
      fetch("/api/costs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: $("kDate").value, branch: $("kBranch").value,
          cost_type: $("kType").value, amount: $("kAmount").value
        })
      }).then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) { throw new Error(j.error); }
          $("kMsg").className = "msg ok";
          $("kMsg").textContent = "تمت إضافة التكلفة.";
          $("kAmount").value = "";
          load();
        });
      }).catch(function (e) {
        $("kMsg").className = "msg err";
        $("kMsg").textContent = e.message;
      });
    });
  }

  function loadCosts() {
    fetch("/api/costs").then(function (r) { return r.json(); }).then(function (rows) {
      if (!$("costTable")) { return; }
      if (!rows.length) {
        $("costTable").innerHTML = '<div class="empty">لم تُدخل أي تكاليف بعد.</div>';
        return;
      }
      var total = rows.reduce(function (a, r) { return a + r.amount; }, 0);
      var html = rows.map(function (r) {
        return "<tr><td>" + esc(r.date) + "</td><td>"
          + esc(CFG.branches[r.branch] || "كل الفروع") + "</td>"
          + "<td>" + esc(L("cost_type", r.cost_type)) + "</td>"
          + "<td class='n'>" + num(r.amount, 2) + "</td></tr>";
      });
      html.push("<tr><td colspan='3'><strong>المجموع</strong></td><td class='n'><strong>"
        + num(total, 2) + "</strong></td></tr>");
      $("costTable").innerHTML = table([{ t: "التاريخ" }, { t: "الفرع" }, { t: "النوع" },
        { t: "المبلغ", n: 1 }], html);
    });
  }

  /* ------------------------------ الهيكل ------------------------------ */
  function iso(d) { return d.toISOString().slice(0, 10); }

  function filters() {
    var p = [];
    if ($("fFrom").value) { p.push("from=" + $("fFrom").value); }
    if ($("fTo").value) { p.push("to=" + $("fTo").value); }
    if ($("fBranch").value) { p.push("branch=" + $("fBranch").value); }
    return p.join("&");
  }

  function load() {
    var qs = filters();
    $("exportLeads").href = "/api/export/leads.csv" + (qs ? "?" + qs : "");
    return fetch("/api/dashboard" + (qs ? "?" + qs : ""))
      .then(function (r) {
        if (r.status === 401) { window.location = "/login"; return null; }
        return r.json();
      })
      .then(function (j) {
        if (!j) { return; }
        D = j;
        paintOverview();
        paintTeam();
        paintLeads();
        paintData();
      });
  }

  // If the database is on storage the host wipes each deploy, say so loudly
  // and permanently. Silent data loss is the worst failure this app can have.
  function checkStorage() {
    fetch("/api/storage").then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (st) {
      if (!st || st.persistent || !st.production) { return; }
      var el = document.getElementById("storageAlarm");
      el.innerHTML =
        "<strong>تحذير: البيانات غير محفوظة</strong><br>"
        + "قاعدة البيانات على تخزين مؤقت — كل نشر جديد يمسح كل الليدات. "
        + (st.configured ? "" : "المتغير <code>ABWAB_DB</code> غير مضبوط. ")
        + "الحل: اربط قرصاً دائماً على <code>/data</code> ثم اضبط "
        + "<code>ABWAB_DB=/data/abwab.db</code> في Railway."
        + "<div class='sub' style='margin-top:6px'>المسار الحالي: "
        + esc(st.path) + " · فيها الآن " + st.counts.leads + " ليد</div>";
      el.classList.remove("hide");
    }).catch(function () { /* never block the dashboard on this */ });
  }

  function boot() {
    checkStorage();
    $("fBranch").innerHTML = "<option value=''>كل الفروع</option>"
      + Object.keys(CFG.branches).map(function (k) {
        return "<option value='" + k + "'>" + esc(CFG.branches[k]) + "</option>";
      }).join("");

    [$("fBranch"), $("fFrom"), $("fTo")].forEach(function (el) {
      el.addEventListener("change", function () {
        Array.prototype.forEach.call($("presets").children, function (b) {
          b.classList.remove("on");
        });
        load();
      });
    });

    Array.prototype.forEach.call($("presets").children, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call($("presets").children, function (b) {
          b.classList.remove("on");
        });
        btn.classList.add("on");
        var d = parseInt(btn.dataset.days, 10);
        if (d === -1) { $("fFrom").value = ""; $("fTo").value = ""; }
        else if (d === 0) {
          $("fFrom").value = iso(new Date()); $("fTo").value = iso(new Date());
        } else {
          $("fFrom").value = iso(new Date(Date.now() - (d - 1) * 864e5));
          $("fTo").value = iso(new Date());
        }
        load();
      });
    });

    Array.prototype.forEach.call($("tabs").children, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call($("tabs").children, function (o) {
          o.classList.remove("on");
        });
        btn.classList.add("on");
        Array.prototype.forEach.call(document.querySelectorAll(".tabpane"), function (p) {
          p.classList.add("hide");
        });
        $("tab-" + btn.dataset.tab).classList.remove("hide");
        // الفلاتر لا معنى لها في تبويب الإعدادات
        document.querySelector(".controls").classList
          .toggle("hide", btn.dataset.tab === "setup");
        if (btn.dataset.tab === "setup" && window.renderSetup) {
          window.renderSetup();
        }
      });
    });

    window.reloadDashboard = load;

    // بعد تعديل الإعدادات، القوائم هنا لازم تعكس الأسماء الجديدة فوراً
    // بدون ما تضطر الإدارة تعمل تحديث للصفحة.
    window.refreshConfig = function () {
      return fetch("/api/config").then(function (r) { return r.json(); })
        .then(function (c) {
          if (!c || !c.branches) { return; }
          CFG = window.CFG = c;
          var keep = $("fBranch").value;
          $("fBranch").innerHTML = "<option value=''>كل الفروع</option>"
            + Object.keys(c.branches).map(function (k) {
              return "<option value='" + k + "'>" + esc(c.branches[k]) + "</option>";
            }).join("");
          if (c.branches[keep]) { $("fBranch").value = keep; }
          return load();
        });
    };

    load().catch(function (e) {
      $("msg").className = "msg err";
      $("msg").textContent = e.message;
    });
  }

  boot();
})();
