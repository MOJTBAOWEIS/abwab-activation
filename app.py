"""
Abwab Hypermarket Activation — tracking server.

Three surfaces, one database:
  /promoter?p=P01   phone-sized manual entry, one personal link per promoter
  /sales            follow-up logging and the live 24-hour SLA queue
  /manager          the full dashboard

Run:  python app.py      then open http://localhost:5000
"""

import csv
import functools
import io
import os
import re
from baghdad_time import datetime, timedelta

from flask import (Flask, jsonify, request, render_template, Response,
                   redirect, session, url_for)

import config
import db
import settings
import metrics

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.json.sort_keys = False

# Sessions: signed cookie, not readable by JavaScript, not sent cross-site, and
# HTTPS-only once ABWAB_ENV=production. PERMANENT_SESSION_LIFETIME keeps a
# promoter signed in across a whole shift without re-entering a password.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)


@app.before_request
def _secure_cookie_for_this_request():
    """Mark the session cookie Secure only when the request really is HTTPS.

    A blanket SESSION_COOKIE_SECURE=True is a trap: the moment the app is
    reached over plain HTTP — a misconfigured proxy, a health check, a local
    smoke test — the browser silently discards the cookie. Sign-in then
    "succeeds" and bounces straight back to the login form with no error at
    all, which is impossible to diagnose from the outside.
    """
    app.config["SESSION_COOKIE_SECURE"] = request.is_secure

if config.IS_PRODUCTION:
    # Behind a host's load balancer, so Flask sees the real scheme and host
    # rather than the proxy's.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@app.route("/healthz")
def healthz():
    """Liveness probe for the host. Deliberately reveals nothing to the public."""
    if BOOT_ERROR:
        return {"ok": False}, 503
    return {"ok": True}


@app.before_request
def _report_boot_failure():
    """A broken database must be visible, not a blank 502."""
    if not BOOT_ERROR or request.path in ("/healthz", "/static"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "الخادم ما يقدر يفتح قاعدة البيانات. "
                                 "راجع إعداد القرص الدائم."}), 503
    return Response(
        "<!doctype html><html lang=ar dir=rtl><meta charset=utf-8>"
        "<title>خطأ في التخزين</title>"
        "<body style='font-family:system-ui;max-width:600px;margin:60px auto;"
        "padding:0 20px;line-height:1.7'>"
        "<h1 style='color:#A63C19'>الخادم ما يقدر يفتح قاعدة البيانات</h1>"
        "<p>التطبيق شغّال، لكن مسار قاعدة البيانات غير صالح للكتابة.</p>"
        "<p><b>المسار:</b> <code>%s</code><br><b>الخطأ:</b> <code>%s</code></p>"
        "<p>في Railway: تأكد أن <b>Mount path</b> للقرص يطابق بداية "
        "<code>ABWAB_DB</code>. مثال: القرص على <code>/data</code> و"
        "<code>ABWAB_DB=/data/abwab.db</code>.</p>"
        "<p style='color:#637673'>لا تُفقد أي بيانات بسبب هذي الشاشة — "
        "التطبيق ما كتب شيئاً.</p></body></html>"
        % (db.DB_PATH, BOOT_ERROR), status=503, mimetype="text/html")


# ------------------------------------------------------------------- auth

def me():
    """The signed-in user, or None."""
    role = session.get("role")
    if not role:
        return None
    return {"role": role, "code": session.get("code"), "name": session.get("name")}


def require(*roles):
    """Gate a route. API routes get 401 JSON; pages get sent to the login."""
    def outer(fn):
        @functools.wraps(fn)
        def inner(*a, **kw):
            u = me()
            if not u or u["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "انتهت الجلسة — سجّل دخولك مرة أخرى"}), 401
                # Say *why*. A silent redirect back to the sign-in form is the
                # single most confusing thing this app can do to someone.
                reason = "expired" if not u else "role"
                return redirect(url_for("login", next=request.path, why=reason))
            return fn(*a, **kw)
        return inner
    return outer


def home_for(role):
    return {"manager": "/manager", "sales": "/sales"}.get(role, "/promoter")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        who = (request.form.get("who") or "").strip()
        pin = (request.form.get("pin") or "").strip()

        found = settings.check_login(who, pin)
        if found:
            session.permanent = True
            session.update(role=found[0], code=found[1], name=found[2])
        else:
            # Deliberately vague: never reveal which half was wrong.
            error = "كلمة السر غير صحيحة. راجع المشرف إذا نسيتها."

        if not error:
            nxt = request.args.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else
                            home_for(session["role"]))

    if not error:
        why = request.args.get("why")
        if why == "expired":
            error = ("انتهت جلستك أو المتصفح ما حفظ تسجيل الدخول. "
                     "سجّل دخولك مرة أخرى.")
        elif why == "role":
            error = "هذي الشاشة مو لحسابك. سجّل دخول بالحساب الصحيح."

    people = ([("MANAGER", "الإدارة", "Manager")]
              + [(c, settings.promoters()[c][0], "Promoter")
                 for c in settings.promoter_codes()]
              + [(c, settings.agents()[c], "Sales") for c in settings.agent_codes()])
    status = 401 if (error and request.method == "POST") else 200
    return render_template("login.html", people=people, error=error,
                           notice=request.args.get("why")), status


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ------------------------------------------------------------------ pages

@app.route("/")
def home():
    u = me()
    return redirect(home_for(u["role"]) if u else "/login")


@app.route("/promoter")
@require("promoter")
def promoter_page():
    # The promoter code comes from the session only. There is no ?p= override,
    # so no promoter can open another promoter's screen by editing the URL.
    return render_template("promoter.html", cfg=_client_config(),
                           promoter_code=session["code"], user=me())


@app.route("/sales")
@require("sales", "manager")
def sales_page():
    return render_template("sales.html", cfg=_client_config(),
                           agent=session.get("code", ""), user=me())


@app.route("/manager")
@require("manager")
def manager_page():
    return render_template("manager.html", cfg=_client_config(), user=me())


# ----------------------------------------------------------------- config

def _client_config():
    return {
        "project": config.PROJECT_NAME,
        "currency": settings.currency(),
        "branches": settings.branches(active_only=True),
        "promoters": {k: {"name": v[0], "branch": v[1]}
                      for k, v in settings.promoters(active_only=True).items()},
        "sales_agents": settings.agents(active_only=True),
        "grades": config.GRADES,
        "interests": config.INTERESTS,
        "customer_types": config.CUSTOMER_TYPES,
        "outcomes": config.OUTCOMES,
        "statuses": config.LEAD_STATUSES,
        "products": config.PRODUCTS,
        "cost_types": config.COST_TYPES,
        "sla_hours": settings.sla_hours(),
        "maturity_days": settings.maturity_days(),
        "max_attempts": settings.max_attempts(),
        "phone_digits": settings.phone_digits(),
        "phone_prefix": settings.phone_prefix(),
        "phone_error": settings.phone_error(),
        # Arabic display labels. Stored values stay English; only the
        # presentation is translated.
        "labels": {
            "grade": config.GRADE_LABELS,
            "grade_short": config.GRADE_SHORT,
            "band": config.BAND_LABELS,
            "interest": config.INTEREST_LABELS,
            "customer_type": config.CUSTOMER_TYPE_LABELS,
            "outcome": config.OUTCOME_LABELS,
            "status": config.STATUS_LABELS,
            "product": config.PRODUCT_LABELS,
            "cost_type": config.COST_TYPE_LABELS,
            "shift": config.SHIFT_LABELS,
            "score_band": config.BAND_SCORE_LABELS,
            "metric": config.METRIC_LABELS,
            "stage": config.STAGE_LABELS,
            "leak": config.LEAK_LABELS,
            "rate": config.RATE_LABELS,
            "owner": config.OWNER_LABELS,
            "severity": config.SEVERITY_LABELS,
            "flag": config.FLAG_LABELS,
        },
    }


@app.route("/api/config")
@require("promoter", "sales", "manager")
def api_config():
    return jsonify(_client_config())


# ------------------------------------------------------------------ shift

def my_promoter_code():
    """A promoter always acts as themselves. The request body is ignored, so
    editing it in the browser cannot write into someone else's day."""
    u = me()
    if u["role"] == "promoter":
        return u["code"]
    return None


def _ensure_shift(conn, code, when=None, branch=None):
    """Return today's shift row for this promoter, creating it if needed.

    The promoter is never gated behind a Start button: signing in is enough to
    start working. The shift row exists so the day still has a start time,
    a branch and an hours figure the dashboard can use.
    """
    when = when or datetime.now()
    today = when.strftime("%Y-%m-%d")
    key = "%s|%s" % (today, code)

    row = conn.execute("SELECT * FROM shifts WHERE shift_key = ?", (key,)).fetchone()
    if row:
        return row, False

    if not branch or branch not in settings.branches():
        # Prefer what the manager rostered for today, then the promoter's own
        # branch, then anything active — so the row is never left branchless.
        planned = conn.execute(
            "SELECT branch, shift_type FROM roster WHERE date=? AND promoter_code=?",
            (today, code)).fetchone()
        branch = ((planned["branch"] if planned else None)
                  or settings.promoters().get(code, (None, None))[1])
    if branch not in settings.branches():
        active = list(settings.branches(active_only=True))
        branch = active[0] if active else (list(settings.branches()) or [""])[0]

    conn.execute(
        """INSERT INTO shifts (shift_key, date, branch, promoter_code, shift, start_ts)
           VALUES (?,?,?,?,?,?)""",
        (key, today, branch, code, settings.shift_for(when),
         when.replace(microsecond=0).isoformat(sep=" ")))
    conn.commit()
    row = conn.execute("SELECT * FROM shifts WHERE shift_key = ?", (key,)).fetchone()
    return row, True


@app.route("/api/shift/current")
@require("promoter")
def shift_current():
    code = my_promoter_code()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    conn = db.connect()
    row, created = _ensure_shift(conn, code, now)
    leads = conn.execute(
        "SELECT outcome FROM leads WHERE date = ? AND promoter_code = ?",
        (today, code)).fetchall()
    planned = conn.execute(
        "SELECT branch, shift_type FROM roster WHERE date=? AND promoter_code=?",
        (today, code)).fetchone()
    conn.close()
    return jsonify({
        "shift": dict(row),
        "taps": row["tap_conversations"] or 0,
        "created": created,
        "today": today,
        "qualified": len(leads),
        "captured": sum(1 for l in leads if l["outcome"] == "Captured"),
        "planned": dict(planned) if planned else None,
        "branches": settings.branches(active_only=True),
    })


@app.route("/api/shift/branch", methods=["POST"])
@require("promoter")
def shift_branch():
    """Move today's shift to another branch — for a promoter covering elsewhere."""
    d = request.get_json(force=True)
    code = my_promoter_code()
    branch = (d.get("branch") or "").strip()
    if branch not in settings.branches():
        return jsonify({"error": "الفرع غير معروف"}), 400
    today = datetime.now().strftime("%Y-%m-%d")
    key = "%s|%s" % (today, code)

    conn = db.connect()
    _ensure_shift(conn, code)
    conn.execute("UPDATE shifts SET branch = ? WHERE shift_key = ?", (branch, key))
    conn.execute("UPDATE leads SET branch = ? WHERE date = ? AND promoter_code = ?",
                 (branch, today, code))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "branch": branch})


@app.route("/api/shift/conversation", methods=["POST"])
@require("promoter")
def shift_conversation():
    """Record conversations that produced no lead, as they happen.

    The phone sends these the moment they are tapped rather than holding them
    until the shift closes, so the manager sees the top of the funnel live and
    an unclosed shift no longer loses the count. `n` lets the phone flush a
    backlog it buffered while offline.
    """
    d = request.get_json(force=True) or {}
    try:
        n = int(d.get("n", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "قيمة غير صحيحة"}), 400
    if not (-50 <= n <= 200):
        return jsonify({"error": "قيمة خارج المدى"}), 400

    code = my_promoter_code()
    conn = db.connect()
    row, _ = _ensure_shift(conn, code)
    total = max(0, (row["tap_conversations"] or 0) + n)
    conn.execute("UPDATE shifts SET tap_conversations = ? WHERE shift_key = ?",
                 (total, row["shift_key"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "tap_conversations": total})


@app.route("/api/shift/reopen", methods=["POST"])
@require("promoter")
def shift_reopen():
    """Carry on after ending the day. Conversations already reported are kept."""
    code = my_promoter_code()
    key = "%s|%s" % (datetime.now().strftime("%Y-%m-%d"), code)
    conn = db.connect()
    conn.execute("UPDATE shifts SET end_ts = NULL WHERE shift_key = ?", (key,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/shift/close", methods=["POST"])
@require("promoter")
def shift_close():
    d = request.get_json(force=True)
    code = my_promoter_code()
    today = datetime.now().strftime("%Y-%m-%d")
    key = "%s|%s" % (today, code)

    try:
        conversations = int(d.get("conversations"))
    except (TypeError, ValueError):
        return jsonify({"error": "عدد المحادثات لازم يكون رقماً"}), 400
    if conversations < 0:
        return jsonify({"error": "عدد المحادثات لا يمكن أن يكون سالباً"}), 400
    gifts = d.get("gifts_issued")
    gifts = int(gifts) if str(gifts or "").strip() != "" else 0

    conn = db.connect()
    _ensure_shift(conn, code)

    qualified = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE date=? AND promoter_code=?",
        (today, code)).fetchone()["c"]
    warning = None
    if conversations < qualified:
        warning = ("سجّلت %d ليد مقابل %d محادثة فقط. "
                   "كل ليد جاء من محادثة — راجع العدّاد."
                   % (qualified, conversations))

    conn.execute(
        """UPDATE shifts SET end_ts=?, conversations=?, gifts_issued=?, note=?
           WHERE shift_key=?""",
        (db.now_iso(), conversations, gifts, (d.get("note") or "").strip(), key))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "warning": warning,
                    "qualified": qualified, "conversations": conversations})


# ------------------------------------------------------------------ leads

@app.route("/api/leads", methods=["POST"])
@require("promoter")
def create_lead():
    d = request.get_json(force=True)
    code = my_promoter_code()

    grade = (d.get("grade") or "").strip()
    interest = (d.get("interest") or "").strip()
    outcome = (d.get("outcome") or "").strip()
    ctype = (d.get("customer_type") or "").strip()

    # Qualification is a hard gate: no grade or no need means the customer
    # was never qualified, so no lead row should exist at all.
    if grade not in config.GRADES:
        return jsonify({"error": "صف الطالب مطلوب لتأهيل الليد"}), 400
    if interest not in config.INTERESTS:
        return jsonify({"error": "الحاجة مطلوبة لتأهيل الليد"}), 400
    if outcome not in config.OUTCOMES:
        return jsonify({"error": "النتيجة مطلوبة"}), 400
    if ctype not in config.CUSTOMER_TYPES:
        return jsonify({"error": "نوع الزبون مطلوب"}), 400

    name = (d.get("customer_name") or "").strip()
    phone_raw = (d.get("phone") or "").strip()
    # Optional, and kept short on purpose: it is a one-line hint for the sales
    # agent, not a place to retype what the structured fields already hold.
    note = (d.get("note") or "").strip()[:300]
    phone_norm = ""

    if outcome == "Captured":
        if not name:
            return jsonify({"error": "الاسم مطلوب لليد مسجّل"}), 400
        phone_norm = settings.normalise_phone(phone_raw)
        if not settings.phone_is_valid(phone_norm):
            return jsonify({"error": settings.phone_error()}), 400
    else:
        name, phone_raw = "", ""

    now = datetime.now()
    branch = d.get("branch") or settings.promoters()[code][1]
    conn = db.connect()

    # Warn on a repeat number, but still record the lead — the manager
    # decides, not the promoter standing in front of the customer.
    duplicate_of = None
    if phone_norm:
        prev = conn.execute(
            "SELECT lead_id, promoter_code FROM leads WHERE phone_norm=? ORDER BY ts LIMIT 1",
            (phone_norm,)).fetchone()
        if prev:
            duplicate_of = prev["lead_id"]

    lead_id = db.make_lead_id(now, code)
    # Same promoter, same second — nudge the timestamp rather than collide.
    while conn.execute("SELECT 1 FROM leads WHERE lead_id=?", (lead_id,)).fetchone():
        now += timedelta(seconds=1)
        lead_id = db.make_lead_id(now, code)

    conn.execute(
        """INSERT INTO leads (lead_id, ts, date, branch, promoter_code, shift,
                              grade, interest, customer_type, outcome,
                              customer_name, phone_raw, phone_norm, note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (lead_id, now.replace(microsecond=0).isoformat(sep=" "),
         now.strftime("%Y-%m-%d"), branch, code, db.shift_of(now),
         grade, interest, ctype, outcome, name, phone_raw, phone_norm, note))
    conn.commit()

    today = now.strftime("%Y-%m-%d")
    counts = conn.execute(
        "SELECT outcome, COUNT(*) c FROM leads WHERE date=? AND promoter_code=? GROUP BY outcome",
        (today, code)).fetchall()
    conn.close()

    tally = {r["outcome"]: r["c"] for r in counts}
    return jsonify({
        "ok": True, "lead_id": lead_id,
        "duplicate_of": duplicate_of,
        "captured_today": tally.get("Captured", 0),
        "qualified_today": sum(tally.values()),
    })


@app.route("/api/leads")
@require("promoter", "sales", "manager")
def list_leads():
    # A promoter's filter is forced to themselves, whatever they ask for.
    promoter = my_promoter_code() or request.args.get("promoter")
    conn = db.connect()
    data = metrics.load(conn, request.args.get("from"), request.args.get("to"),
                        request.args.get("branch"), promoter)
    conn.close()
    return jsonify([_lead_json(l) for l in reversed(data["leads"])])


def _lead_json(l):
    return {
        "lead_id": l["lead_id"], "date": l["date"], "time": l["time"],
        "branch": l["branch_name"], "promoter": l["promoter_name"],
        "customer_name": l["customer_name"], "phone": l["phone_norm"],
        "customer_type": l["customer_type"],
        "grade": l["grade"], "grade_band": l["grade_band"],
        "interest": l["interest"], "outcome": l["outcome"],
        "status": l["status"], "contacted": l["contacted"],
        "contact_ts": l["contact_ts"], "hours_to_contact": l["hours_to_contact"],
        "within_24h": l["within_24h"], "attempts": l["attempts"],
        "purchase": l["purchase"], "purchase_date": l["purchase_date"],
        "revenue": l["revenue"], "product": l["product"], "agent": l["agent"],
        "notes": l["notes"], "promoter_note": l["promoter_note"],
        "flags": l["flags"], "age_days": l["age_days"],
        "crm_ready": bool(l["is_crm_ready"]),
    }


# --------------------------------------------------------------- followup

@app.route("/api/followup", methods=["POST"])
@require("sales", "manager")
def create_followup():
    d = request.get_json(force=True)
    lead_id = (d.get("lead_id") or "").strip()
    status = (d.get("status") or "").strip()
    agent = (d.get("agent") or "").strip()

    if status not in config.LEAD_STATUSES or status == "New":
        return jsonify({"error": "اختر حالة صحيحة"}), 400
    if agent not in settings.agents():
        return jsonify({"error": "موظف المبيعات غير معروف"}), 400

    conn = db.connect()
    lead = conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return jsonify({"error": "رقم الليد غير موجود"}), 400
    if lead["outcome"] != "Captured":
        conn.close()
        return jsonify({"error": "هذا الزبون رفض إعطاء رقمه — "
                                 "لا يوجد ما يُتابع"}), 400

    attempts = int(d.get("attempts") or 1)
    purchase = bool(d.get("purchase"))
    revenue = float(d.get("revenue") or 0)
    purchase_date = (d.get("purchase_date") or "").strip()
    product = (d.get("product") or "").strip()

    if status == "Converted":
        purchase = True
        if revenue <= 0:
            conn.close()
            return jsonify({"error": "الشراء يحتاج المبلغ المدفوع فعلياً"}), 400
        if not purchase_date:
            purchase_date = datetime.now().strftime("%Y-%m-%d")
    if status == "Invalid / Unreachable" and attempts < settings.max_attempts():
        conn.close()
        return jsonify({"error": "لا تضعه «لا يرد» إلا بعد %d محاولات"
                                 % settings.max_attempts()}), 400
    if not purchase:
        revenue, purchase_date, product = 0.0, None, None

    # The contact time is the moment this is logged. A back-dated entry is
    # allowed but recorded as such, so the 24h metric stays auditable.
    contact_ts = (d.get("contact_ts") or "").strip()
    backdated = 0
    if contact_ts:
        parsed = db.parse_ts(contact_ts)
        if not parsed:
            conn.close()
            return jsonify({"error": "وقت الاتصال غير صحيح"}), 400
        contact_ts = parsed.replace(microsecond=0).isoformat(sep=" ")
        backdated = 1
    else:
        contact_ts = db.now_iso()

    conn.execute(
        """INSERT INTO followups (lead_id, contact_ts, sales_agent, attempts, status,
                                  purchase, purchase_date, revenue, product, notes,
                                  backdated, logged_ts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (lead_id, contact_ts, agent, attempts, status, 1 if purchase else 0,
         purchase_date, revenue, product, (d.get("notes") or "").strip(),
         backdated, db.now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "lead_id": lead_id, "status": status})


@app.route("/api/lead/phone", methods=["POST"])
@require("sales", "manager")
def fix_lead_phone():
    """Correct a phone number the promoter typed wrong.

    A lead whose number is short is not automatically lost — the agent may
    have the right one from a callback, the note, or a second attempt. Without
    this the only options were to leave it uncallable or delete it.
    """
    d = request.get_json(force=True)
    lead_id = (d.get("lead_id") or "").strip()
    raw = (d.get("phone") or "").strip()

    norm = settings.normalise_phone(raw)
    if not settings.phone_is_valid(norm):
        return jsonify({"error": settings.phone_error()}), 400

    conn = db.connect()
    lead = conn.execute("SELECT outcome FROM leads WHERE lead_id=?",
                        (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return jsonify({"error": "رقم الليد غير موجود"}), 400
    if lead["outcome"] != "Captured":
        conn.close()
        return jsonify({"error": "هذا الزبون رفض إعطاء رقمه"}), 400

    dup = conn.execute(
        "SELECT lead_id FROM leads WHERE phone_norm=? AND lead_id<>? ORDER BY ts LIMIT 1",
        (norm, lead_id)).fetchone()

    conn.execute("UPDATE leads SET phone_raw=?, phone_norm=? WHERE lead_id=?",
                 (raw, norm, lead_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "phone": norm,
                    "duplicate_of": dup["lead_id"] if dup else None})


@app.route("/api/sales/queue")
@require("sales", "manager")
def sales_queue():
    conn = db.connect()
    data = metrics.load(conn)
    conn.close()
    return jsonify(metrics.sla_queue(data))


# --------------------------------------------------------------- dashboard

def _costs(conn, date_from, date_to, branch):
    q = "SELECT branch, SUM(amount) a FROM costs WHERE 1=1"
    p = []
    if date_from:
        q += " AND date >= ?"; p.append(date_from)
    if date_to:
        q += " AND date <= ?"; p.append(date_to)
    if branch:
        q += " AND branch = ?"; p.append(branch)
    q += " GROUP BY branch"
    rows = conn.execute(q, p).fetchall()
    by_branch = {r["branch"]: float(r["a"] or 0) for r in rows}
    return by_branch, sum(by_branch.values())


@app.route("/api/dashboard")
@require("manager")
def dashboard():
    f = request.args.get("from") or None
    t = request.args.get("to") or None
    b = request.args.get("branch") or None
    p = request.args.get("promoter") or None

    conn = db.connect()
    data = metrics.load(conn, f, t, b, p)
    costs_by_branch, costs_total = _costs(conn, f, t, b)
    # The roster view always answers "today", whatever period is filtered —
    # it is an operational check, not a report.
    attendance = metrics.attendance(conn, data, request.args.get("day"))
    conn.close()

    fn = metrics.funnel(data)
    rt = metrics.rates(data, costs_total)
    ps = metrics.promoter_scores(data)
    bs = metrics.branch_scores(data, costs_by_branch)
    dq = metrics.data_quality(data)

    return jsonify({
        "filters": {"from": f, "to": t, "branch": b, "promoter": p},
        "overview": {
            "conversations": fn["totals"]["conversations"],
            "qualified": fn["totals"]["qualified"],
            "captured": fn["totals"]["captured"],
            "crm_ready": fn["totals"]["crm_ready"],
            "contacted": fn["totals"]["contacted"],
            "purchases": fn["totals"]["purchases"],
            "revenue": fn["totals"]["revenue"],
            "hours": fn["totals"]["hours"],
            "shifts": fn["totals"]["shift_count"],
            "declined": fn["totals"]["declined"],
            "overall_conversion": metrics._div(
                fn["totals"]["purchases"], fn["totals"]["conversations"]),
            "cost_total": costs_total,
            "cost_per_lead": rt["value"]["cost_per_lead"],
            "cost_per_acquisition": rt["value"]["cost_per_acquisition"],
        },
        "funnel": fn,
        "rates": rt["rates"],
        "value": rt["value"],
        "promoters": {
            "rows": [_promoter_json(r) for r in ps["rows"]],
            "top": _promoter_json(ps["top"]) if ps["top"] else None,
            "lowest": _promoter_json(ps["lowest"]) if ps["lowest"] else None,
        },
        "branches": {
            "rows": [_branch_json(r) for r in bs["rows"]],
            "top": _branch_json(bs["top"]) if bs["top"] else None,
            "lowest": _branch_json(bs["lowest"]) if bs["lowest"] else None,
            "best_value": _branch_json(bs["best_value"]) if bs["best_value"] else None,
        },
        "daily": metrics.daily(data),
        "quality": {
            "score": dq["score"], "flagged": dq["flagged"], "total": dq["total"],
            "ops_flagged": dq["ops_flagged"],
            "critical_count": dq["critical_count"],
            "flags": dq["flags"],
            "critical": [_lead_json(l) for l in dq["critical"][:50]],
            "duplicates": [dict(_lead_json(l), dup_of=l.get("dup_of", ""))
                           for l in dq["duplicates"][:50]],
            "no_shift_log": [_lead_json(l) for l in dq["no_shift_log"][:50]],
            "sla": [_lead_json(l) for l in dq["sla"][:50]],
            "open_shifts": [{"date": s["date"], "promoter": s["promoter_name"],
                             "branch": s["branch_name"], "start": s["start_ts"]}
                            for s in dq["open_shifts"]],
            "shift_issues": [{"date": s["date"], "promoter": s["promoter_name"],
                              "branch": s["branch_name"], "flags": s["flags"],
                              "conversations": s["conversations"],
                              "qualified": s["qualified"], "captured": s["captured"],
                              "gifts": s["gifts_issued"]}
                             for s in dq["shift_issues"]],
            "promoter_quality": dq["promoter_quality"],
        },
        "lead_quality": metrics.lead_quality(data),
        "sla_queue": metrics.sla_queue(data),
        "attendance": attendance,
    })


def _promoter_json(r):
    a = r["agg"]
    return {
        "code": r["promoter_code"], "name": r["promoter_name"],
        "branch": r["branch_name"],
        "shifts": a["shift_count"], "hours": a["hours"],
        "conversations": a["conversations"], "qualified": a["qualified"],
        "captured": a["captured"], "purchases": a["purchases"],
        "revenue": a["revenue"], "conversion_rate": r["conversion_rate"],
        "captured_per_hour": a["captured_per_hour"],
        "qualification_rate": a["qualification_rate"],
        "capture_rate": a["capture_rate"],
        "score": r["score"], "base_score": r["base_score"],
        "integrity": r["integrity"], "band": r["band"], "tone": r["tone"],
        "eligible": r["eligible"], "provisional": r["provisional"],
        "weakest": r["weakest"], "components": r["components"],
        "flagged": a["flagged"],
    }


def _branch_json(r):
    a = r["agg"]
    return {
        "code": r["branch"], "name": r["branch_name"],
        "hours": a["hours"], "conversations": a["conversations"],
        "qualified": a["qualified"], "captured": a["captured"],
        "purchases": a["purchases"], "revenue": a["revenue"],
        "conversion_rate": r["conversion_rate"],
        "captured_per_hour": a["captured_per_hour"],
        "qualification_rate": a["qualification_rate"],
        "execution": r["execution"], "band": r["band"], "tone": r["tone"],
        "site_value": r["site_value"], "site_basis": r["site_basis"],
        "footfall": r["footfall"], "eligible": r["eligible"],
        "components": r["components"], "cost": r["cost"],
    }


# ------------------------------------------------------------------ costs

@app.route("/api/costs", methods=["GET", "POST"])
@require("manager")
def costs():
    conn = db.connect()
    if request.method == "POST":
        d = request.get_json(force=True)
        try:
            amount = float(d.get("amount"))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "المبلغ لازم يكون رقماً"}), 400
        if d.get("cost_type") not in config.COST_TYPES:
            conn.close()
            return jsonify({"error": "نوع التكلفة غير معروف"}), 400
        conn.execute(
            "INSERT INTO costs (date, branch, cost_type, amount, note) VALUES (?,?,?,?,?)",
            (d.get("date") or datetime.now().strftime("%Y-%m-%d"),
             d.get("branch") or "", d["cost_type"], amount,
             (d.get("note") or "").strip()))
        conn.commit()
    rows = conn.execute("SELECT * FROM costs ORDER BY date DESC, id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ----------------------------------------------------------------- export

def _csv_utf8(rows, header):
    """Standard UTF-8 comma-separated CSV for CRM imports."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _csv_excel(rows, header):
    """UTF-16LE tab-separated file that Excel on both Windows and Mac opens perfectly."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter='\t')
    w.writerow(header)
    w.writerows(rows)
    return b'\xff\xfe' + buf.getvalue().encode('utf-16-le')


def _ar(kind, value):
    """The same Arabic label the dashboard shows, so the file matches the screen."""
    return {
        "grade": config.GRADE_LABELS,
        "band": config.BAND_LABELS,
        "interest": config.INTEREST_LABELS,
        "status": config.STATUS_LABELS,
        "outcome": config.OUTCOME_LABELS,
        "customer_type": config.CUSTOMER_TYPE_LABELS,
        "product": config.PRODUCT_LABELS,
        "flag": config.FLAG_LABELS,
    }.get(kind, {}).get(value, value or "")


@app.route("/api/export/crm.csv")
@require("sales", "manager")
def export_crm():
    """CRM-ready leads only, in import order. Invalid and duplicate numbers
    are excluded here rather than being sent to sales to fail on."""
    conn = db.connect()
    data = metrics.load(conn, request.args.get("from"), request.args.get("to"))
    conn.close()
    rows = [[l["lead_id"], l["customer_name"], l["phone_norm"],
             _ar("grade", l["grade"]), _ar("interest", l["interest"]),
             _ar("customer_type", l["customer_type"]), l["branch_name"],
             l["promoter_name"], l["date"], l["time"], l["promoter_note"]]
            for l in data["leads"] if l["is_crm_ready"]]
    return Response(
        _csv_utf8(rows, ["رقم الليد", "الاسم", "الهاتف", "الصف", "الحاجة",
                         "نوع الزبون", "الفرع", "المروّج", "التاريخ", "الوقت",
                         "ملاحظة المروّج"]),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=abwab_crm_export.csv"})


@app.route("/api/export/leads.csv")
@require("manager")
def export_leads():
    conn = db.connect()
    data = metrics.load(conn, request.args.get("from"), request.args.get("to"),
                        request.args.get("branch"), request.args.get("promoter"))
    conn.close()
    within = {"Yes": "نعم", "No": "لا", "Pending": "بالانتظار"}
    rows = [[l["lead_id"], l["date"], l["time"], l["branch_name"], l["promoter_name"],
             l["customer_name"], l["phone_norm"],
             _ar("customer_type", l["customer_type"]), _ar("grade", l["grade"]),
             _ar("band", l["grade_band"]), _ar("interest", l["interest"]),
             _ar("outcome", l["outcome"]), _ar("status", l["status"]),
             "نعم" if l["contacted"] else "لا", l["contact_ts"],
             l["hours_to_contact"] if l["hours_to_contact"] is not None else "",
             within.get(l["within_24h"], l["within_24h"]),
             "نعم" if l["purchase"] else "لا",
             l["purchase_date"], l["revenue"], l["promoter_note"],
             " · ".join(_ar("flag", f) for f in l["flags"])]
            for l in data["leads"]]
    return Response(
        _csv_utf8(rows, ["رقم الليد", "التاريخ", "الوقت", "الفرع", "المروّج",
                         "اسم الزبون", "الهاتف", "نوع الزبون", "الصف", "المرحلة",
                         "الحاجة", "النتيجة", "الحالة", "تم الاتصال", "وقت الاتصال",
                         "ساعات حتى الاتصال", "خلال 24 ساعة", "اشترى",
                         "تاريخ الشراء", "الإيراد", "ملاحظة المروّج", "المشاكل"]),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=abwab_leads.csv"})


# ---------------------------------------------------------------- settings
# Everything the manager can change without touching code. Manager-only.

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,10}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _in_use(conn, column, value):
    """Rows already recorded against this branch or promoter."""
    n = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE %s = ?" % column, (value,)).fetchone()["c"]
    n += conn.execute(
        "SELECT COUNT(*) c FROM shifts WHERE %s = ?" % column, (value,)).fetchone()["c"]
    return n


@app.route("/api/storage")
@require("manager")
def storage_status():
    """So the manager can see, before losing anything, whether the data is safe."""
    st = db.storage_report()
    conn = db.connect()
    counts = {t: conn.execute("SELECT COUNT(*) c FROM %s" % t).fetchone()["c"]
              for t in ("leads", "shifts", "followups")}
    conn.close()
    st["counts"] = counts
    st["production"] = config.IS_PRODUCTION
    return jsonify(st)


@app.route("/api/setup")
@require("manager")
def setup_read():
    conn = db.connect()
    used_b = {r["code"]: _in_use(conn, "branch", r["code"])
              for r in [{"code": c} for c in settings.branches()]}
    used_p = {r["code"]: _in_use(conn, "promoter_code", r["code"])
              for r in [{"code": c} for c in settings.promoters()]}
    used_a = {code: conn.execute(
        "SELECT COUNT(*) c FROM followups WHERE sales_agent = ?", (code,)
    ).fetchone()["c"] for code in settings.agents()}
    conn.close()
    return jsonify({
        "branches": [dict(r, used=used_b.get(r["code"], 0))
                     for r in settings.branch_rows()],
        # The password hash never leaves the server. The manager sets a new
        # password; nobody reads the old one back.
        "promoters": [dict(r, pin="", used=used_p.get(r["code"], 0))
                      for r in settings.promoter_rows()],
        "agents": [dict(r, pin="", used=used_a.get(r["code"], 0))
                   for r in settings.agent_rows()],
        "shifts": settings.shift_types(),
        "settings": dict(settings.all_settings(), manager_pin=""),
    })


@app.route("/api/setup/branch", methods=["POST"])
@require("manager")
def setup_branch():
    d = request.get_json(force=True)
    code = (d.get("code") or "").strip().upper()
    name = (d.get("name") or "").strip()
    if not CODE_RE.match(code):
        return jsonify({"error": "رمز الفرع: حروف وأرقام فقط، 2–10 خانات"}), 400
    if not name:
        return jsonify({"error": "اسم الفرع مطلوب"}), 400

    conn = db.connect()
    conn.execute(
        "INSERT INTO branches (code, name, active, sort) VALUES (?,?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET name=excluded.name, active=excluded.active",
        (code, name, 1 if d.get("active", True) else 0, int(d.get("sort") or 0)))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True})


@app.route("/api/setup/branch/delete", methods=["POST"])
@require("manager")
def setup_branch_delete():
    code = (request.get_json(force=True).get("code") or "").strip()
    conn = db.connect()
    used = _in_use(conn, "branch", code)
    if used:
        # Never orphan history. Deactivating hides it from every dropdown
        # while the past leads keep their branch name on the dashboard.
        conn.execute("UPDATE branches SET active = 0 WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        settings.invalidate()
        return jsonify({"ok": True, "deactivated": True, "used": used})
    conn.execute("DELETE FROM branches WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True, "deleted": True})


@app.route("/api/setup/promoter", methods=["POST"])
@require("manager")
def setup_promoter():
    d = request.get_json(force=True)
    code = (d.get("code") or "").strip().upper()
    name = (d.get("name") or "").strip()
    pin = (d.get("pin") or "").strip()
    branch = (d.get("branch") or "").strip()

    if not CODE_RE.match(code):
        return jsonify({"error": "رمز المروّج: حروف وأرقام فقط، 2–10 خانات"}), 400
    if not name:
        return jsonify({"error": "اسم المروّج مطلوب"}), 400
    existing = settings.promoters().get(code)
    if pin:
        if not settings.password_ok(pin):
            return jsonify({"error": settings.password_error()}), 400
        pin = settings.hash_password(pin)
    elif existing:
        pin = None                       # keep whatever is stored
    else:
        return jsonify({"error": settings.password_error()}), 400
    if branch and branch not in settings.branches():
        return jsonify({"error": "الفرع غير موجود"}), 400
    if code in settings.agents():
        return jsonify({"error": "هذا الرمز مستخدم لموظف مبيعات"}), 400

    conn = db.connect()
    if pin is None:
        conn.execute("UPDATE promoters SET name=?, branch=?, active=? WHERE code=?",
                     (name, branch, 1 if d.get("active", True) else 0, code))
    else:
        conn.execute(
            "INSERT INTO promoters (code, name, branch, pin, active) VALUES (?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, "
            "branch=excluded.branch, pin=excluded.pin, active=excluded.active",
            (code, name, branch, pin, 1 if d.get("active", True) else 0))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True, "password_changed": pin is not None})


@app.route("/api/setup/promoter/delete", methods=["POST"])
@require("manager")
def setup_promoter_delete():
    code = (request.get_json(force=True).get("code") or "").strip()
    conn = db.connect()
    used = _in_use(conn, "promoter_code", code)
    if used:
        conn.execute("UPDATE promoters SET active = 0 WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        settings.invalidate()
        return jsonify({"ok": True, "deactivated": True, "used": used})
    conn.execute("DELETE FROM promoters WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True, "deleted": True})


@app.route("/api/setup/agent", methods=["POST"])
@require("manager")
def setup_agent():
    d = request.get_json(force=True)
    code = (d.get("code") or "").strip().upper()
    name = (d.get("name") or "").strip()
    pin = (d.get("pin") or "").strip()
    if not CODE_RE.match(code):
        return jsonify({"error": "رمز الموظف: حروف وأرقام فقط، 2–10 خانات"}), 400
    if not name:
        return jsonify({"error": "اسم الموظف مطلوب"}), 400
    existing = settings.agents().get(code)
    if pin:
        if not settings.password_ok(pin):
            return jsonify({"error": settings.password_error()}), 400
        pin = settings.hash_password(pin)
    elif existing:
        pin = None
    else:
        return jsonify({"error": settings.password_error()}), 400
    if code in settings.promoters():
        return jsonify({"error": "هذا الرمز مستخدم لمروّج"}), 400

    conn = db.connect()
    if pin is None:
        conn.execute("UPDATE agents SET name=?, active=? WHERE code=?",
                     (name, 1 if d.get("active", True) else 0, code))
    else:
        conn.execute(
            "INSERT INTO agents (code, name, pin, active) VALUES (?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, "
            "pin=excluded.pin, active=excluded.active",
            (code, name, pin, 1 if d.get("active", True) else 0))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True, "password_changed": pin is not None})


@app.route("/api/setup/agent/delete", methods=["POST"])
@require("manager")
def setup_agent_delete():
    code = (request.get_json(force=True).get("code") or "").strip()
    conn = db.connect()
    used = conn.execute("SELECT COUNT(*) c FROM followups WHERE sales_agent = ?",
                        (code,)).fetchone()["c"]
    if used:
        conn.execute("UPDATE agents SET active = 0 WHERE code = ?", (code,))
    else:
        conn.execute("DELETE FROM agents WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True, "deactivated": bool(used)})


@app.route("/api/setup/shift", methods=["POST"])
@require("manager")
def setup_shift():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    start = (d.get("start_time") or "").strip()
    end = (d.get("end_time") or "").strip()
    if not name:
        return jsonify({"error": "اسم الشفت مطلوب"}), 400
    if not TIME_RE.match(start) or not TIME_RE.match(end):
        return jsonify({"error": "الوقت بصيغة HH:MM مثل 09:00"}), 400
    if start == end:
        return jsonify({"error": "وقت البداية والنهاية لا يمكن أن يكونا نفس الشيء"}), 400

    conn = db.connect()
    if d.get("id"):
        conn.execute(
            "UPDATE shift_types SET name=?, start_time=?, end_time=?, sort=? WHERE id=?",
            (name, start, end, int(d.get("sort") or 0), int(d["id"])))
    else:
        conn.execute(
            "INSERT INTO shift_types (name, start_time, end_time, sort) VALUES (?,?,?,?)",
            (name, start, end, int(d.get("sort") or 0)))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True})


@app.route("/api/setup/shift/delete", methods=["POST"])
@require("manager")
def setup_shift_delete():
    sid = request.get_json(force=True).get("id")
    conn = db.connect()
    remaining = conn.execute("SELECT COUNT(*) c FROM shift_types").fetchone()["c"]
    if remaining <= 1:
        conn.close()
        return jsonify({"error": "لازم يبقى شفت واحد على الأقل"}), 400
    conn.execute("DELETE FROM shift_types WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    settings.invalidate()
    return jsonify({"ok": True})


@app.route("/api/setup/roster", methods=["GET", "POST"])
@require("manager")
def setup_roster():
    if request.method == "POST":
        d = request.get_json(force=True)
        date = (d.get("date") or "").strip()
        code = (d.get("promoter_code") or "").strip()
        branch = (d.get("branch") or "").strip()
        shift_type = (d.get("shift_type") or "").strip()

        if not db.parse_ts(date):
            return jsonify({"error": "التاريخ غير صحيح"}), 400
        if code not in settings.promoters():
            return jsonify({"error": "المروّج غير معروف"}), 400
        if branch not in settings.branches():
            return jsonify({"error": "الفرع غير معروف"}), 400
        if shift_type not in settings.shift_names():
            return jsonify({"error": "الشفت غير معروف"}), 400

        settings.roster_set(date, code, branch, shift_type, (d.get("note") or "").strip())

    date_from = request.args.get("from")
    date_to = request.args.get("to")
    return jsonify(settings.roster(date_from, date_to))


@app.route("/api/setup/roster/delete", methods=["POST"])
@require("manager")
def setup_roster_delete():
    settings.roster_remove(request.get_json(force=True).get("id"))
    return jsonify({"ok": True})


# Only these keys may be written, and each is range-checked. A typo in the
# browser must not be able to put the scoring rules into an impossible state.
SETTING_RULES = {
    "currency": ("text", 1, 8),
    "phone_total_digits": ("int", 7, 15),
    "phone_prefix": ("text", 1, 4),
    "manager_pin": ("pin", config.PASSWORD_MIN, config.PASSWORD_MAX),
    "break_hours": ("float", 0, 4),
    "maturity_days": ("int", 0, 90),
    "sla_hours": ("int", 1, 168),
    "stale_days": ("int", 1, 90),
    "max_contact_attempts": ("int", 1, 10),
    "gift_gap_tolerance": ("float", 0, 1),
    "min_shifts_for_ranking": ("int", 1, 30),
    "min_hours_for_ranking": ("float", 0, 200),
    "min_branch_hours_for_ranking": ("float", 0, 500),
    "min_mature_leads": ("int", 0, 100),
    "late_grace_minutes": ("int", 0, 240),
}


@app.route("/api/setup/settings", methods=["POST"])
@require("manager")
def setup_settings():
    d = request.get_json(force=True)
    clean = {}
    for key, value in d.items():
        if key not in SETTING_RULES:
            continue
        kind, lo, hi = SETTING_RULES[key]
        value = str(value).strip()
        if kind == "text":
            if not (lo <= len(value) <= hi):
                return jsonify({"error": "قيمة غير صالحة لـ %s" % key}), 400
        elif kind == "pin":
            if not value:
                continue                 # left blank = leave it as it is
            if not settings.password_ok(value):
                return jsonify({"error": settings.password_error()}), 400
            value = settings.hash_password(value)
        else:
            try:
                num = float(value)
            except ValueError:
                return jsonify({"error": "قيمة غير رقمية لـ %s" % key}), 400
            if not (lo <= num <= hi):
                return jsonify({"error": "%s خارج المدى المسموح (%s–%s)"
                                         % (key, lo, hi)}), 400
            value = str(int(num)) if kind == "int" else str(num)
        clean[key] = value

    if clean:
        settings.set_many(clean)
    return jsonify({"ok": True, "saved": len(clean)})


BOOT_ERROR = None


def bootstrap():
    """Prepare the database. Safe to call repeatedly.

    Never raises. If the database cannot be opened — the usual cause is a
    volume mount path that does not match ABWAB_DB, or one the process cannot
    write to — the failure is recorded and reported on every page instead.
    Raising here kills the worker, the host restarts it, it dies again, and
    the only thing anyone sees is a 502 with no explanation anywhere.
    """
    global BOOT_ERROR
    try:
        db.init()
        settings.ensure_defaults()
        BOOT_ERROR = None
    except Exception as exc:                      # noqa: BLE001 - report anything
        BOOT_ERROR = "%s: %s" % (type(exc).__name__, exc)
        print("")
        print("!" * 70)
        print("STARTUP FAILED — the database could not be opened")
        print("  ABWAB_DB : %s" % os.environ.get("ABWAB_DB", "(not set)"))
        print("  resolved : %s" % db.DB_PATH)
        print("  error    : %s" % BOOT_ERROR)
        print("")
        print("  Usually the volume mount path does not match ABWAB_DB, or the")
        print("  process cannot write there. Check Volumes -> Mount path, and")
        print("  set ABWAB_DB to a file inside it.")
        print("!" * 70)
        print("")

    st = db.storage_report()
    if config.IS_PRODUCTION and not st["persistent"]:
        print("")
        print("!" * 70)
        print("DATA LOSS WARNING — the database is on temporary storage")
        print("  path: %s" % st["path"])
        if not st["configured"]:
            print("  ABWAB_DB is not set.")
        if st["inside_app_dir"]:
            print("  It sits inside the app directory, which this host replaces")
            print("  on every deploy.")
        print("")
        print("  Every lead will be destroyed the next time you deploy.")
        print("  Fix: attach a volume mounted at /data, then set")
        print("       ABWAB_DB=/data/abwab.db")
        print("!" * 70)
        print("")


bootstrap()


if __name__ == "__main__":
    import socket
    port = int(os.environ.get("PORT", "5000"))
    try:
        lan = socket.gethostbyname(socket.gethostname())
    except OSError:
        lan = "127.0.0.1"
    print("Abwab activation tracker")
    print("  on this machine : http://localhost:%d" % port)
    print("  on the network  : http://%s:%d" % (lan, port))
    app.run(host="0.0.0.0", port=port, debug=False)
