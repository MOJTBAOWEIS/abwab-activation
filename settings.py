"""
Runtime settings — branches, promoters, sales agents, shift times and the
operating rules.

These used to live in config.py. They now live in the database so the manager
can change them from the dashboard without touching code or restarting the
server. config.py keeps the *defaults*: the tables are seeded from it the first
time the server starts, and after that the database is the source of truth.

Reads are cached in memory because every dashboard request touches them; the
cache is dropped whenever anything is written.
"""

import os
import re
import threading
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

import config
import db

_lock = threading.Lock()
_cache = {}


def invalidate():
    with _lock:
        _cache.clear()


def _cached(key, build):
    if key in _cache:
        return _cache[key]
    value = build()
    with _lock:
        _cache[key] = value
    return value


# ------------------------------------------------------------ first-run seed

_issued = []


def _new_password(code):
    """A random first password, remembered so it can be printed once."""
    import secrets
    import string
    body = "".join(secrets.choice(string.ascii_lowercase + string.digits)
                   for _ in range(8))
    pw = code.lower() + body                 # e.g. p01k4m2xq9t
    _issued.append((code, pw))
    return pw


def ensure_defaults():
    """Populate the settings tables from config.py, once."""
    conn = db.connect()
    have = conn.execute("SELECT COUNT(*) c FROM branches").fetchone()["c"]
    if not have:
        for i, (code, name) in enumerate(config.BRANCHES.items()):
            conn.execute(
                "INSERT INTO branches (code, name, active, sort) VALUES (?,?,1,?)",
                (code, name, i))
        for code, (name, branch) in config.PROMOTERS.items():
            conn.execute(
                "INSERT INTO promoters (code, name, branch, pin, active) VALUES (?,?,?,?,1)",
                (code, name, branch,
                 hash_password(config.PROMOTER_PINS.get(code) or _new_password(code))))
        for code, name in config.SALES_AGENTS.items():
            conn.execute(
                "INSERT INTO agents (code, name, pin, active) VALUES (?,?,?,1)",
                (code, name,
                 hash_password(config.SALES_PINS.get(code) or _new_password(code))))
        for i, (name, start, end) in enumerate(config.DEFAULT_SHIFTS):
            conn.execute(
                "INSERT INTO shift_types (name, start_time, end_time, sort) VALUES (?,?,?,?)",
                (name, start, end, i))

    for key, value in config.DEFAULT_SETTINGS.items():
        if key == "manager_pin":
            value = hash_password(str(value))
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)",
                     (key, str(value)))
    conn.commit()
    conn.close()
    invalidate()
    _upgrade_weak_passwords()
    hash_existing_passwords()
    if _issued:
        print("")
        print("=" * 58)
        print("FIRST-RUN PASSWORDS — copy these now, they are not shown again")
        print("=" * 58)
        for code, pw in _issued:
            print("   %-6s %s" % (code, pw))
        print("=" * 58)
        print("")
        _issued.clear()

    # The environment always wins for the manager password. Without this, a
    # deploy that sets the variable *after* the first boot would silently keep
    # the built-in default — the variable would look applied and not be.
    env_pw = os.environ.get("ABWAB_MANAGER_PASSWORD")
    if env_pw:
        if not password_ok(env_pw):
            print("WARNING: ABWAB_MANAGER_PASSWORD does not meet the policy "
                  "(%d+ chars, letters and digits). It was NOT applied."
                  % config.PASSWORD_MIN)
        else:
            stored = get("manager_pin")
            if not verify(stored, env_pw):
                conn = db.connect()
                conn.execute("UPDATE settings SET value=? WHERE key='manager_pin'",
                             (hash_password(env_pw),))
                conn.commit()
                conn.close()
                invalidate()
                print("Manager password set from ABWAB_MANAGER_PASSWORD.")
    elif config.IS_PRODUCTION:
        print("WARNING: ABWAB_MANAGER_PASSWORD is not set. The manager account "
              "is using the built-in default. Set the variable and redeploy.")


def _upgrade_weak_passwords():
    """Bring any password created under the old 4-digit rule up to policy.

    Rather than lock someone out, the old value is kept as the tail of the new
    one, so it is still recognisable to whoever has to hand it over. Every
    change is printed once at startup so the manager can redistribute them.
    """
    conn = db.connect()
    changed = []
    for table in ("promoters", "agents"):
        for r in conn.execute("SELECT code, pin FROM %s" % table).fetchall():
            if not is_hashed(r["pin"]) and not password_ok(r["pin"]):
                new = "abwab" + re.sub(r"\W", "", r["pin"] or "") or "abwab0000"
                while len(new) < config.PASSWORD_MIN:
                    new += "0"
                conn.execute("UPDATE %s SET pin = ? WHERE code = ?" % table,
                             (new, r["code"]))
                changed.append((r["code"], new))

    cur = conn.execute("SELECT value FROM settings WHERE key='manager_pin'").fetchone()
    if cur and not is_hashed(cur["value"]) and not password_ok(cur["value"]):
        new = "abwabmanager" + re.sub(r"\W", "", cur["value"] or "")
        conn.execute("UPDATE settings SET value=? WHERE key='manager_pin'", (new,))
        changed.append(("MANAGER", new))

    conn.commit()
    conn.close()
    if changed:
        invalidate()
        print("Passwords upgraded to the new %d-character policy:"
              % config.PASSWORD_MIN)
        for code, pw in changed:
            print("   %-8s %s" % (code, pw))


# ---------------------------------------------------------------- secrets
# Passwords are stored hashed. Nobody — not even the manager — can read one
# back; the manager sets a new one instead. This is what makes the app safe to
# put on the public internet, where the database is no longer sitting on one
# locked laptop.

def hash_password(plain):
    return generate_password_hash(plain)


def is_hashed(value):
    return bool(value) and value.startswith(
        ("scrypt:", "pbkdf2:", "argon2", "sha256$"))


def verify(stored, plain):
    if not stored or not plain:
        return False
    if is_hashed(stored):
        try:
            return check_password_hash(stored, plain)
        except ValueError:
            return False
    # A password left over from before hashing was introduced.
    return stored == plain


def check_login(who, plain):
    """Return (role, code, name) for a correct password, else None."""
    if who == "MANAGER":
        if verify(get("manager_pin", config.MANAGER_PIN), plain):
            return ("manager", "MANAGER", "الإدارة")
        return None
    for r in promoter_rows():
        if r["code"] == who and r["active"] and verify(r["pin"], plain):
            return ("promoter", r["code"], r["name"])
    for r in agent_rows():
        if r["code"] == who and r["active"] and verify(r["pin"], plain):
            return ("sales", r["code"], r["name"])
    return None


def hash_existing_passwords():
    """One-off: replace any plaintext password still in the database."""
    conn = db.connect()
    n = 0
    for table in ("promoters", "agents"):
        for r in conn.execute("SELECT code, pin FROM %s" % table).fetchall():
            if not is_hashed(r["pin"]):
                conn.execute("UPDATE %s SET pin = ? WHERE code = ?" % table,
                             (hash_password(r["pin"]), r["code"]))
                n += 1
    cur = conn.execute("SELECT value FROM settings WHERE key='manager_pin'").fetchone()
    if cur and not is_hashed(cur["value"]):
        conn.execute("UPDATE settings SET value=? WHERE key='manager_pin'",
                     (hash_password(cur["value"]),))
        n += 1
    conn.commit()
    conn.close()
    if n:
        invalidate()
        print("Hashed %d stored password(s)." % n)


def password_ok(value):
    """At least PASSWORD_MIN characters, containing both a letter and a digit."""
    v = value or ""
    if not (config.PASSWORD_MIN <= len(v) <= config.PASSWORD_MAX):
        return False
    if " " in v:
        return False
    return bool(re.search(r"[A-Za-z؀-ۿ]", v)) and bool(re.search(r"\d", v))


def password_error():
    return ("كلمة السر: %d أحرف على الأقل، وتحتوي حروفاً وأرقاماً معاً، بدون مسافات"
            % config.PASSWORD_MIN)


# ---------------------------------------------------------------- scalars

def all_settings():
    def build():
        conn = db.connect()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        return {r["key"]: r["value"] for r in rows}
    return _cached("settings", build)


def get(key, default=None):
    return all_settings().get(key, default)


def get_int(key, default=0):
    try:
        return int(float(all_settings().get(key, default)))
    except (TypeError, ValueError):
        return default


def get_float(key, default=0.0):
    try:
        return float(all_settings().get(key, default))
    except (TypeError, ValueError):
        return default


def set_many(pairs):
    conn = db.connect()
    for k, v in pairs.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(v)))
    conn.commit()
    conn.close()
    invalidate()


# ------------------------------------------------------------------ people

def _build_branches():
    conn = db.connect()
    rows = conn.execute("SELECT * FROM branches ORDER BY sort, code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def branches(active_only=False):
    """code -> name, in display order."""
    rows = _cached("branches", _build_branches)
    return {r["code"]: r["name"] for r in rows
            if r["active"] or not active_only}


def branch_rows():
    branches()          # fill cache
    return _cache["branches"]


def _build_promoters():
    conn = db.connect()
    rows = conn.execute("SELECT * FROM promoters ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def promoters(active_only=False):
    """code -> (name, branch) — the shape the rest of the code expects."""
    rows = _cached("promoters", _build_promoters)
    return {r["code"]: (r["name"], r["branch"]) for r in rows
            if r["active"] or not active_only}


def promoter_rows():
    # Read what the cache actually returned. Going back to _cache afterwards
    # can raise KeyError if another request invalidated it in between.
    return _cached("promoters", _build_promoters)


def promoter_codes():
    return [r["code"] for r in promoter_rows() if r["active"]]


def _build_agents():
    conn = db.connect()
    rows = conn.execute("SELECT * FROM agents ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def agents(active_only=False):
    rows = _cached("agents", _build_agents)
    return {r["code"]: r["name"] for r in rows if r["active"] or not active_only}


def agent_rows():
    # Read what the cache actually returned. Going back to _cache afterwards
    # can raise KeyError if another request invalidated it in between.
    return _cached("agents", _build_agents)


def agent_codes():
    return [r["code"] for r in agent_rows() if r["active"]]


def manager_pin():
    return get("manager_pin", config.MANAGER_PIN)


# ------------------------------------------------------------------ shifts

def shift_types():
    def build():
        conn = db.connect()
        rows = conn.execute(
            "SELECT * FROM shift_types ORDER BY sort, id").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    return _cached("shifts", build)


def shift_names():
    return [s["name"] for s in shift_types()]


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def shift_for(when):
    """Which configured shift contains this moment.

    Windows that run past midnight are handled, and a time that falls in no
    window is attributed to the nearest one that has already started — a
    promoter who opens early still lands on a real shift rather than a blank.
    """
    types = shift_types()
    if not types:
        return "Shift"
    if isinstance(when, datetime):
        mins = when.hour * 60 + when.minute
    else:
        mins = int(when)

    for s in types:
        start, end = _minutes(s["start_time"]), _minutes(s["end_time"])
        if start <= end:
            if start <= mins < end:
                return s["name"]
        else:                                   # crosses midnight
            if mins >= start or mins < end:
                return s["name"]

    started = [s for s in types if _minutes(s["start_time"]) <= mins]
    return (started[-1] if started else types[0])["name"]


# ------------------------------------------------------------------ roster

def roster(date_from=None, date_to=None):
    """Planned shifts. Read straight from the database — this changes often
    enough that caching it would only create staleness."""
    conn = db.connect()
    q = "SELECT * FROM roster WHERE 1=1"
    p = []
    if date_from:
        q += " AND date >= ?"
        p.append(date_from)
    if date_to:
        q += " AND date <= ?"
        p.append(date_to)
    q += " ORDER BY date DESC, shift_type, promoter_code"
    rows = [dict(r) for r in conn.execute(q, p).fetchall()]
    conn.close()
    return rows


def roster_set(date, promoter_code, branch, shift_type, note=""):
    conn = db.connect()
    conn.execute(
        "INSERT INTO roster (date, promoter_code, branch, shift_type, note) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(date, promoter_code) DO UPDATE SET branch=excluded.branch, "
        "shift_type=excluded.shift_type, note=excluded.note",
        (date, promoter_code, branch, shift_type, note))
    conn.commit()
    conn.close()


def roster_remove(entry_id):
    conn = db.connect()
    conn.execute("DELETE FROM roster WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


def shift_hours(name):
    for s in shift_types():
        if s["name"] == name:
            span = _minutes(s["end_time"]) - _minutes(s["start_time"])
            if span < 0:
                span += 24 * 60
            return round(span / 60.0, 2)
    return 0.0


# ------------------------------------------------------------------- phone

def phone_digits():
    """Total digits in a valid local number, leading zero included."""
    return get_int("phone_total_digits", config.PHONE_DIGITS)


def phone_prefix():
    return get("phone_prefix", config.PHONE_PREFIX)


def normalise_phone(raw):
    """Reduce any way of writing the number to one canonical local form.

    Accepts 07XX XXX XXXX, +9647XXXXXXXX, 009647XXXXXXXX and so on. It never
    pads or truncates to force a fit: a number that is the wrong length stays
    the wrong length so validation can reject it. Silently trimming a digit
    produces a number that looks valid and rings the wrong phone.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""

    # Strip an international prefix if one was typed.
    for cc in ("00964", "964"):
        if digits.startswith(cc) and len(digits) > len(cc):
            digits = digits[len(cc):]
            break

    # Local numbers are written with a leading zero; add it back if the
    # country code swallowed it.
    prefix = phone_prefix()
    if prefix.startswith("0") and not digits.startswith("0"):
        if digits.startswith(prefix[1:]):
            digits = "0" + digits

    return digits


def phone_is_valid(norm):
    """Exact length and exact opening. Near misses are not accepted."""
    n = norm or ""
    return len(n) == phone_digits() and n.startswith(phone_prefix())


def phone_error():
    return ("رقم الهاتف لازم %d خانة ويبدأ بـ %s — مثال: %s"
            % (phone_digits(), phone_prefix(),
               phone_prefix() + "7" + "0" * (phone_digits() - len(phone_prefix()) - 1)))


# ------------------------------------------------------- operating numbers

def break_hours():
    return get_float("break_hours", config.BREAK_HOURS)


def maturity_days():
    return get_int("maturity_days", config.MATURITY_DAYS)


def sla_hours():
    return get_int("sla_hours", config.SLA_HOURS)


def stale_days():
    return get_int("stale_days", config.STALE_DAYS)


def max_attempts():
    return get_int("max_contact_attempts", config.MAX_CONTACT_ATTEMPTS)


def gift_gap_tolerance():
    return get_float("gift_gap_tolerance", config.GIFT_GAP_TOLERANCE)


def min_shifts():
    return get_int("min_shifts_for_ranking", config.MIN_SHIFTS_FOR_RANKING)


def min_hours():
    return get_float("min_hours_for_ranking", config.MIN_HOURS_FOR_RANKING)


def min_branch_hours():
    return get_float("min_branch_hours_for_ranking",
                     config.MIN_BRANCH_HOURS_FOR_RANKING)


def min_mature_leads():
    return get_int("min_mature_leads", config.MIN_MATURE_LEADS)


def currency():
    return get("currency", config.CURRENCY)
