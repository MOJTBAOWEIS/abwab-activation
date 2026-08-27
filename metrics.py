"""
Metrics engine for the Abwab activation tracker.

Implements the funnel, conversion rates, promoter and branch scores, lead
quality breakdowns and data-quality detection exactly as specified in the
tracking plan. Every number the dashboard shows is computed here; nothing
is stored pre-aggregated, so changing the date filter recomputes cleanly.
"""

from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

import config
import db
import settings


# ---------------------------------------------------------------- loading

def _followup_rollup(conn):
    """Collapse the follow-up log into one record per lead.

    First contact sets the SLA, the latest entry sets the status, and any
    entry recording a purchase carries the revenue.
    """
    rows = conn.execute(
        "SELECT * FROM followups ORDER BY lead_id, logged_ts, id"
    ).fetchall()
    out = {}
    for r in rows:
        lid = r["lead_id"]
        cur = out.setdefault(lid, {
            "first_contact_ts": None, "status": "New", "attempts": 0,
            "purchase": False, "purchase_date": None, "revenue": 0.0,
            "product": None, "notes": None, "backdated": False,
            "agent": None, "last_touch_ts": None,
        })
        cts = db.parse_ts(r["contact_ts"])
        if cts and (cur["first_contact_ts"] is None or cts < cur["first_contact_ts"]):
            cur["first_contact_ts"] = cts
        cur["status"] = r["status"]
        cur["attempts"] = max(cur["attempts"], r["attempts"] or 0)
        cur["agent"] = r["sales_agent"]
        cur["notes"] = r["notes"] or cur["notes"]
        cur["last_touch_ts"] = db.parse_ts(r["logged_ts"])
        if r["backdated"]:
            cur["backdated"] = True
        if r["purchase"]:
            cur["purchase"] = True
            cur["purchase_date"] = r["purchase_date"]
            cur["revenue"] = float(r["revenue"] or 0)
            cur["product"] = r["product"]
    return out


def load(conn, date_from=None, date_to=None, branch=None, promoter=None, now=None):
    """Build the enriched dataset the whole dashboard reads from.

    Duplicate detection and shift pairing run across *all* history before the
    date filter is applied — a duplicate is a duplicate regardless of the
    window the manager happens to be looking at.
    """
    now = now or datetime.now()
    fu = _followup_rollup(conn)

    shift_rows = conn.execute("SELECT * FROM shifts ORDER BY date, promoter_code").fetchall()
    lead_rows = conn.execute("SELECT * FROM leads ORDER BY ts, lead_id").fetchall()

    # --- shift index -----------------------------------------------------
    shifts_all = []
    shift_by_key = {}
    for r in shift_rows:
        start = db.parse_ts(r["start_ts"])
        end = db.parse_ts(r["end_ts"])
        hours = 0.0
        if start and end:
            hours = round((end - start).total_seconds() / 3600.0 - settings.break_hours(), 2)
            hours = max(hours, 0.0)
        s = {
            "shift_key": r["shift_key"], "date": r["date"], "branch": r["branch"],
            "promoter_code": r["promoter_code"],
            "promoter_name": _promoter_name(r["promoter_code"]),
            "branch_name": settings.branches().get(r["branch"], r["branch"]),
            "shift": r["shift"], "start_ts": r["start_ts"], "end_ts": r["end_ts"],
            "hours": hours, "closed": bool(r["end_ts"]),
            "conversations": r["conversations"] if r["conversations"] is not None else None,
            "gifts_issued": r["gifts_issued"],
            "note": r["note"], "flags": [],
        }
        shifts_all.append(s)
        shift_by_key[r["shift_key"]] = s

    # --- leads -----------------------------------------------------------
    seen_phone = {}
    id_counts = defaultdict(int)
    for r in lead_rows:
        id_counts[r["lead_id"]] += 1

    leads_all = []
    for r in lead_rows:
        ts = db.parse_ts(r["ts"])
        f = fu.get(r["lead_id"])
        captured = r["outcome"] == "Captured"
        norm = r["phone_norm"] or ""
        dup = False
        if norm:
            if norm in seen_phone:
                dup = True
            else:
                seen_phone[norm] = r["lead_id"]

        age_days = (now.date() - ts.date()).days if ts else 0
        contact_ts = f["first_contact_ts"] if f else None
        hours_to_contact = None
        if contact_ts and ts:
            hours_to_contact = round((contact_ts - ts).total_seconds() / 3600.0, 1)

        if hours_to_contact is not None:
            within = "Yes" if hours_to_contact <= settings.sla_hours() else "No"
        elif ts and (now - ts) <= timedelta(hours=settings.sla_hours()):
            within = "Pending"
        else:
            within = "No"

        lead = {
            "lead_id": r["lead_id"], "ts": ts, "date": r["date"],
            "time": ts.strftime("%H:%M") if ts else "",
            "hour": ts.hour if ts else 0,
            "dow": ts.strftime("%a") if ts else "",
            "branch": r["branch"],
            "branch_name": settings.branches().get(r["branch"], r["branch"]),
            "promoter_code": r["promoter_code"],
            "promoter_name": _promoter_name(r["promoter_code"]),
            "shift": r["shift"],
            "customer_name": r["customer_name"] or "",
            "phone_raw": r["phone_raw"] or "",
            "phone_norm": norm,
            "customer_type": r["customer_type"] or "",
            "grade": r["grade"] or "",
            "grade_band": config.GRADE_BAND_MAP.get(r["grade"] or "", ""),
            "interest": r["interest"] or "",
            "outcome": r["outcome"],
            "promoter_note": (r["note"] if "note" in r.keys() else "") or "",
            "is_qualified": 1,
            "is_captured": 1 if captured else 0,
            "age_days": age_days,
            "is_mature": 1 if age_days >= settings.maturity_days() else 0,
            "status": f["status"] if f else "New",
            "contacted": bool(contact_ts),
            "contact_ts": contact_ts.strftime("%Y-%m-%d %H:%M") if contact_ts else "",
            "hours_to_contact": hours_to_contact,
            "within_24h": within,
            "attempts": f["attempts"] if f else 0,
            "purchase": bool(f and f["purchase"]),
            "purchase_date": (f["purchase_date"] if f else None) or "",
            "revenue": float(f["revenue"]) if f else 0.0,
            "product": (f["product"] if f else None) or "",
            "agent": (f["agent"] if f else None) or "",
            "notes": (f["notes"] if f else None) or "",
            "backdated": bool(f and f["backdated"]),
            "dup_phone": dup,
            "dup_id": id_counts[r["lead_id"]] > 1,
            "last_touch": f["last_touch_ts"] if f else None,
        }
        lead["days_to_purchase"] = None
        if lead["purchase"] and lead["purchase_date"] and ts:
            pd = db.parse_ts(lead["purchase_date"])
            if pd:
                lead["days_to_purchase"] = (pd.date() - ts.date()).days

        shift_key = "%s|%s" % (r["date"], r["promoter_code"])
        lead["flags"] = _lead_flags(lead, shift_key in shift_by_key, now)
        lead["is_crm_ready"] = 1 if (
            captured and db.phone_is_valid(norm) and not dup and not lead["dup_id"]
        ) else 0
        leads_all.append(lead)

    # --- shift-level flags (need the leads) ------------------------------
    by_shift = defaultdict(list)
    for l in leads_all:
        by_shift["%s|%s" % (l["date"], l["promoter_code"])].append(l)

    for s in shifts_all:
        ls = by_shift.get(s["shift_key"], [])
        s["qualified"] = len(ls)
        s["captured"] = sum(l["is_captured"] for l in ls)
        if not s["closed"]:
            s["flags"].append("NO_CLOSE")
        if s["conversations"] is not None and s["qualified"] > s["conversations"]:
            s["flags"].append("LEADS_GT_CONVOS")
            for l in ls:
                if "LEADS_GT_CONVOS" not in l["flags"]:
                    l["flags"].append("LEADS_GT_CONVOS")
        g = s["gifts_issued"]
        if g:
            if abs(g - s["captured"]) / float(g) > settings.gift_gap_tolerance():
                s["flags"].append("GIFT_GAP")
        s["conversations_per_hour"] = _div(s["conversations"] or 0, s["hours"])
        s["captured_per_hour"] = _div(s["captured"], s["hours"])
        s["qualification_rate"] = _div(s["qualified"], s["conversations"] or 0)

    # --- apply the manager's filters -------------------------------------
    def keep(row):
        if date_from and row["date"] < date_from:
            return False
        if date_to and row["date"] > date_to:
            return False
        if branch and row["branch"] != branch:
            return False
        if promoter and row["promoter_code"] != promoter:
            return False
        return True

    return {
        "now": now,
        "leads": [l for l in leads_all if keep(l)],
        "shifts": [s for s in shifts_all if keep(s)],
        "leads_all": leads_all,
        "shifts_all": shifts_all,
        "phone_owner": seen_phone,
    }


def _promoter_name(code):
    p = settings.promoters().get(code)
    return p[0] if p else "UNKNOWN (%s)" % code


def _lead_flags(lead, has_shift, now):
    f = []
    captured = lead["outcome"] == "Captured"
    # A Declined lead is *supposed* to have no phone — flagging it would bury
    # the real errors under false positives.
    if captured and not lead["phone_raw"]:
        f.append("MISSING_PHONE")
    if lead["phone_raw"] and not db.phone_is_valid(lead["phone_norm"]):
        f.append("BAD_PHONE")
    if captured and not lead["customer_name"]:
        f.append("MISSING_NAME")
    if not lead["grade"]:
        f.append("MISSING_GRADE")
    if not lead["interest"]:
        f.append("MISSING_INTEREST")
    if lead["dup_phone"]:
        f.append("DUP_PHONE")
    if lead["dup_id"]:
        f.append("DUP_LEADID")
    if lead["promoter_code"] not in settings.promoters():
        f.append("NO_PROMOTER")
    if lead["branch"] not in settings.branches():
        f.append("NO_BRANCH")
    if not has_shift:
        f.append("NO_SHIFT_LOG")
    if captured and not lead["contacted"] and lead["age_days"] >= 2:
        f.append("NOT_CONTACTED")
    if lead["within_24h"] == "No":
        f.append("SLA_BREACH")
    if lead["status"] in ("Contacted", "Follow-up") and lead["last_touch"]:
        if (now - lead["last_touch"]).days >= settings.stale_days():
            f.append("STALE")
    if lead["backdated"]:
        f.append("BACKDATED")
    return f


# ------------------------------------------------------------- primitives

def _div(a, b):
    return (a / float(b)) if b else 0.0


def _agg(leads, shifts):
    """Shared aggregation block used at project, promoter and branch level."""
    mature = [l for l in leads if l["is_mature"] and l["is_captured"]]
    a = {
        "hours": round(sum(s["hours"] for s in shifts), 2),
        "shift_count": len(shifts),
        "conversations": sum((s["conversations"] or 0) for s in shifts),
        "gifts": sum((s["gifts_issued"] or 0) for s in shifts),
        "qualified": len(leads),
        "captured": sum(l["is_captured"] for l in leads),
        "crm_ready": sum(l["is_crm_ready"] for l in leads),
        "contacted": sum(1 for l in leads if l["contacted"]),
        "contacted_24h": sum(1 for l in leads if l["within_24h"] == "Yes"),
        "purchases": sum(1 for l in leads if l["purchase"]),
        "revenue": round(sum(l["revenue"] for l in leads), 2),
        "mature_captured": len(mature),
        "mature_purchases": sum(1 for l in mature if l["purchase"]),
        "mature_revenue": round(sum(l["revenue"] for l in mature), 2),
        "flagged": sum(1 for l in leads if l["flags"]),
        "flagged_data": sum(1 for l in leads
                            if any(f in config.DATA_FLAGS for f in l["flags"])),
        "flagged_promoter": sum(1 for l in leads
                                if any(f in config.PROMOTER_FLAGS for f in l["flags"])),
        "declined": sum(1 for l in leads if l["outcome"] == "Declined"),
    }
    a["captured_per_hour"] = _div(a["captured"], a["hours"])
    a["conversations_per_hour"] = _div(a["conversations"], a["hours"])
    a["revenue_per_hour"] = _div(a["revenue"], a["hours"])
    a["qualification_rate"] = _div(a["qualified"], a["conversations"])
    a["capture_rate"] = _div(a["captured"], a["qualified"])
    a["purchase_rate"] = _div(a["mature_purchases"], a["mature_captured"])
    a["revenue_per_lead"] = _div(a["mature_revenue"], a["mature_captured"])
    a["data_quality"] = (1.0 - _div(a["flagged_promoter"], a["qualified"])
                         if a["qualified"] else 1.0)
    return a


def _index(value, benchmark):
    if not benchmark:
        return 0.0
    return min(value / float(benchmark), config.INDEX_CAP)


def _band(score):
    for threshold, label, tone in config.SCORE_BANDS:
        if score >= threshold:
            return label, tone
    return config.SCORE_BANDS[-1][1], config.SCORE_BANDS[-1][2]


# ------------------------------------------------------------------ funnel

def funnel(data):
    leads, shifts = data["leads"], data["shifts"]
    a = _agg(leads, shifts)
    now = data["now"]

    # Only leads old enough to have breached the SLA belong in its denominator.
    sla_eligible = [
        l for l in leads
        if l["is_crm_ready"] and l["ts"] and (now - l["ts"]) > timedelta(hours=settings.sla_hours())
    ]
    sla_hit = sum(1 for l in sla_eligible if l["within_24h"] == "Yes")

    # Keys are stable identifiers; the interface resolves them to labels.
    stages = [
        ("conversations", a["conversations"]),
        ("qualified", a["qualified"]),
        ("captured", a["captured"]),
        ("crm", a["crm_ready"]),
        ("contacted", a["contacted"]),
        ("purchases", a["purchases"]),
    ]

    out, prev = [], None
    for key, value in stages:
        row = {
            "key": key, "value": value,
            "conversion": _div(value, prev) if prev is not None else None,
            "lost": (prev - value) if prev is not None else None,
        }
        out.append(row)
        prev = value

    biggest = None
    losses = [r for r in out if r["lost"] is not None and r["lost"] > 0]
    if losses:
        biggest = max(losses, key=lambda r: r["lost"])["key"]

    return {
        "stages": out,
        "revenue": a["revenue"],
        "biggest_leak": biggest,
        "sla_eligible": len(sla_eligible),
        "sla_hit": sla_hit,
        "totals": a,
    }


def rates(data, costs_total=0.0):
    leads, shifts = data["leads"], data["shifts"]
    a = _agg(leads, shifts)
    f = funnel(data)

    def r(key, num, den):
        return {"key": key, "num": num, "den": den, "value": _div(num, den)}

    live_purchase = _div(a["purchases"], a["captured"])

    out = [
        r("qualification", a["qualified"], a["conversations"]),
        r("capture", a["captured"], a["qualified"]),
        r("crm_ready", a["crm_ready"], a["captured"]),
        r("contact", a["contacted"], a["crm_ready"]),
        r("sla", f["sla_hit"], f["sla_eligible"]),
        r("purchase", a["mature_purchases"], a["mature_captured"]),
        r("overall", a["purchases"], a["conversations"]),
    ]

    value = {
        "revenue_per_conversation": _div(a["revenue"], a["conversations"]),
        "revenue_per_captured_lead": _div(a["mature_revenue"], a["mature_captured"]),
        "average_purchase_value": _div(a["revenue"], a["purchases"]),
        "live_purchase_rate": live_purchase,
        "cost_total": costs_total,
        "cost_per_lead": _div(costs_total, a["captured"]) if costs_total else None,
        "cost_per_acquisition": _div(costs_total, a["purchases"]) if costs_total else None,
    }
    return {"rates": out, "value": value, "totals": a}


# ------------------------------------------------------- promoter scoring

def promoter_scores(data):
    leads, shifts = data["leads"], data["shifts"]
    project = _agg(leads, shifts)

    # Branch-level benchmarks for the two volume metrics. Footfall is a
    # rostering outcome, so volume is measured against the branch worked.
    by_branch_leads = defaultdict(list)
    by_branch_shifts = defaultdict(list)
    for l in leads:
        by_branch_leads[l["branch"]].append(l)
    for s in shifts:
        by_branch_shifts[s["branch"]].append(s)
    branch_bm = {
        b: _agg(by_branch_leads.get(b, []), by_branch_shifts.get(b, []))
        for b in set(list(by_branch_leads) + list(by_branch_shifts))
    }

    by_prom_leads = defaultdict(list)
    by_prom_shifts = defaultdict(list)
    for l in leads:
        by_prom_leads[l["promoter_code"]].append(l)
    for s in shifts:
        by_prom_shifts[s["promoter_code"]].append(s)

    rows = []
    for code in sorted(set(list(by_prom_leads) + list(by_prom_shifts))):
        pl = by_prom_leads.get(code, [])
        ps = by_prom_shifts.get(code, [])
        a = _agg(pl, ps)

        # Blended branch benchmark, weighted by hours actually worked there.
        hours_by_branch = defaultdict(float)
        for s in ps:
            hours_by_branch[s["branch"]] += s["hours"]
        total_hours = sum(hours_by_branch.values())

        def blended(metric):
            if not total_hours:
                return project[metric]
            return sum(
                h * branch_bm.get(b, project).get(metric, 0.0)
                for b, h in hours_by_branch.items()
            ) / total_hours

        provisional = a["mature_captured"] < settings.min_mature_leads()
        weights = dict(config.PROMOTER_WEIGHTS)
        if provisional:
            dropped = sum(weights[k] for k in config.MATURITY_DEPENDENT)
            for k in config.MATURITY_DEPENDENT:
                weights.pop(k)
            remaining = sum(weights.values())
            if remaining:
                for k in weights:
                    weights[k] += weights[k] / remaining * dropped

        components = []
        base = 0.0
        for metric, w in config.PROMOTER_WEIGHTS.items():
            if metric not in weights:
                components.append({
                    "metric": metric, "weight": 0.0, "value": a[metric],
                    "benchmark": None, "index": None, "skipped": True,
                })
                continue
            bm = blended(metric) if metric in config.BRANCH_BENCHMARKED else project[metric]
            idx = _index(a[metric], bm)
            base += weights[metric] * idx
            components.append({
                "metric": metric, "weight": round(weights[metric], 4),
                "value": a[metric], "benchmark": bm, "index": idx, "skipped": False,
            })
        base *= 100.0

        # Only flags the promoter actually owns. An SLA breach is a sales
        # failure and must not move a promoter's score.
        integrity = 1.0
        if a["qualified"]:
            integrity = max(config.INTEGRITY_FLOOR,
                            1.0 - a["flagged_promoter"] / float(a["qualified"]))
        score = base * integrity

        eligible = (a["shift_count"] >= settings.min_shifts()
                    and a["hours"] >= settings.min_hours())

        active = [c for c in components if not c["skipped"] and c["index"] is not None]
        weakest = min(active, key=lambda c: c["index"])["metric"] if active else None
        band, tone = _band(score)

        primary_branch = max(hours_by_branch, key=hours_by_branch.get) if hours_by_branch else (
            pl[0]["branch"] if pl else "")

        rows.append({
            "promoter_code": code, "promoter_name": _promoter_name(code),
            "branch": primary_branch,
            "branch_name": settings.branches().get(primary_branch, primary_branch),
            "agg": a, "components": components,
            "base_score": round(base, 1), "integrity": round(integrity, 3),
            "score": round(score, 1), "band": band, "tone": tone,
            "eligible": eligible, "provisional": provisional,
            "weakest": weakest,
            "conversion_rate": _div(a["purchases"], a["captured"]),
        })

    rows.sort(key=lambda r: (r["eligible"], r["score"]), reverse=True)
    ranked = [r for r in rows if r["eligible"]]
    return {
        "rows": rows,
        "top": ranked[0] if ranked else None,
        "lowest": ranked[-1] if len(ranked) > 1 else None,
        "project": project,
    }


# --------------------------------------------------------- branch scoring

def branch_scores(data, costs_by_branch=None):
    costs_by_branch = costs_by_branch or {}
    leads, shifts = data["leads"], data["shifts"]
    project = _agg(leads, shifts)

    by_leads = defaultdict(list)
    by_shifts = defaultdict(list)
    for l in leads:
        by_leads[l["branch"]].append(l)
    for s in shifts:
        by_shifts[s["branch"]].append(s)

    rows = []
    for code in sorted(set(list(by_leads) + list(by_shifts))):
        a = _agg(by_leads.get(code, []), by_shifts.get(code, []))
        components, execution = [], 0.0
        for metric, w in config.BRANCH_WEIGHTS.items():
            idx = _index(a[metric], project[metric])
            execution += w * idx
            components.append({"metric": metric, "weight": w, "value": a[metric],
                               "benchmark": project[metric], "index": idx})
        execution *= 100.0

        cost = costs_by_branch.get(code, 0.0)
        if cost:
            site_value = _div(a["revenue"], cost)
            site_basis = "Revenue ÷ Cost (ROI)"
        else:
            site_value = a["revenue_per_hour"]
            site_basis = "Revenue ÷ Promoter-Hour"

        band, tone = _band(execution)
        rows.append({
            "branch": code, "branch_name": settings.branches().get(code, code),
            "agg": a, "components": components,
            "execution": round(execution, 1), "band": band, "tone": tone,
            "site_value": round(site_value, 2), "site_basis": site_basis,
            "footfall": a["conversations_per_hour"],
            "eligible": a["hours"] >= settings.min_branch_hours(),
            "conversion_rate": _div(a["purchases"], a["captured"]),
            "cost": cost,
        })

    rows.sort(key=lambda r: (r["eligible"], r["execution"]), reverse=True)
    ranked = [r for r in rows if r["eligible"]]
    by_value = sorted(ranked, key=lambda r: r["site_value"], reverse=True)
    return {
        "rows": rows,
        "top": ranked[0] if ranked else None,
        "lowest": ranked[-1] if len(ranked) > 1 else None,
        "best_value": by_value[0] if by_value else None,
        "worst_value": by_value[-1] if len(by_value) > 1 else None,
    }


# ------------------------------------------------------------ daily trend

def daily(data):
    by_l = defaultdict(list)
    by_s = defaultdict(list)
    for l in data["leads"]:
        by_l[l["date"]].append(l)
    for s in data["shifts"]:
        by_s[s["date"]].append(s)

    rows = []
    for d in sorted(set(list(by_l) + list(by_s)), reverse=True):
        a = _agg(by_l.get(d, []), by_s.get(d, []))
        dt = db.parse_ts(d)
        rows.append({
            "date": d, "dow": dt.strftime("%a") if dt else "",
            "shifts": a["shift_count"], "hours": a["hours"],
            "conversations": a["conversations"], "qualified": a["qualified"],
            "captured": a["captured"], "purchases": a["purchases"],
            "revenue": a["revenue"],
            "qualification_rate": a["qualification_rate"],
            "capture_rate": a["capture_rate"],
            "conversion_rate": _div(a["purchases"], a["captured"]),
        })
    return rows


# ----------------------------------------------------------- lead quality

def _breakdown(leads, key, order=None):
    groups = defaultdict(list)
    for l in leads:
        if l["is_captured"]:
            groups[l[key] or "(blank)"].append(l)
    total = sum(len(v) for v in groups.values())

    keys = order if order else sorted(groups, key=lambda k: -len(groups[k]))
    rows = []
    for k in keys:
        if k not in groups:
            continue
        g = groups[k]
        mature = [l for l in g if l["is_mature"]]
        rows.append({
            "key": k, "captured": len(g), "share": _div(len(g), total),
            "purchases": sum(1 for l in g if l["purchase"]),
            "purchase_rate": _div(sum(1 for l in mature if l["purchase"]), len(mature)),
            "mature": len(mature),
            "revenue": round(sum(l["revenue"] for l in g), 2),
        })
    return rows


def lead_quality(data):
    leads = data["leads"]
    return OrderedDict([
        ("Student Grade", _breakdown(leads, "grade", config.GRADES)),
        ("Grade Band", _breakdown(leads, "grade_band", config.BAND_ORDER)),
        ("Interest / Need", _breakdown(leads, "interest", config.INTERESTS)),
        ("Customer Type", _breakdown(leads, "customer_type", config.CUSTOMER_TYPES)),
        ("Branch", _breakdown(leads, "branch_name")),
        ("Promoter", _breakdown(leads, "promoter_name")),
    ])


# ----------------------------------------------------------- data quality

def data_quality(data):
    leads, shifts = data["leads"], data["shifts"]
    counts = defaultdict(int)
    for l in leads:
        for f in l["flags"]:
            counts[f] += 1
    for s in shifts:
        for f in s["flags"]:
            if f != "NO_CLOSE":
                continue
            counts[f] += 1

    # The score measures whether the lead *record* is sound. Follow-up
    # discipline is reported separately — it is a different team's failure.
    flagged = sum(1 for l in leads
                  if any(f in config.DATA_FLAGS for f in l["flags"]))
    ops_flagged = sum(1 for l in leads
                      if any(f in config.SALES_FLAGS for f in l["flags"]))
    score = 1.0 - _div(flagged, len(leads)) if leads else 1.0

    def sev(flag):
        if flag in config.CRITICAL_FLAGS:
            return "critical"
        if flag in config.HIGH_FLAGS:
            return "high"
        return "medium"

    def owner(flag):
        if flag in config.PROMOTER_FLAGS:
            return "Promoter"
        if flag in config.SALES_FLAGS:
            return "Sales"
        return "Manager"

    flag_rows = [{
        "flag": f, "count": c, "severity": sev(f), "owner": owner(f),
        "counts_in_score": f in config.DATA_FLAGS,
        "help": config.FLAG_HELP.get(f, ""),
    } for f, c in sorted(counts.items(), key=lambda kv: -kv[1])]

    critical = [l for l in leads if any(f in config.CRITICAL_FLAGS for f in l["flags"])]
    dupes = [l for l in leads if l["dup_phone"]]
    for d in dupes:
        d["dup_of"] = data["phone_owner"].get(d["phone_norm"], "")
    no_shift = [l for l in leads if "NO_SHIFT_LOG" in l["flags"]]
    sla = [l for l in leads if "SLA_BREACH" in l["flags"] or "NOT_CONTACTED" in l["flags"]]
    open_shifts = [s for s in shifts if "NO_CLOSE" in s["flags"]]
    shift_issues = [s for s in shifts if s["flags"]]

    by_prom = defaultdict(lambda: {"total": 0, "flagged": 0})
    for l in leads:
        p = by_prom[l["promoter_name"]]
        p["total"] += 1
        if any(f in config.PROMOTER_FLAGS for f in l["flags"]):
            p["flagged"] += 1
    promoter_quality = sorted(
        [{"promoter": k, "total": v["total"], "flagged": v["flagged"],
          "rate": _div(v["flagged"], v["total"])} for k, v in by_prom.items()],
        key=lambda r: -r["rate"])

    return {
        "score": score, "flagged": flagged, "total": len(leads),
        "ops_flagged": ops_flagged,
        "flags": flag_rows,
        "critical": critical, "duplicates": dupes, "no_shift_log": no_shift,
        "sla": sla, "open_shifts": open_shifts, "shift_issues": shift_issues,
        "promoter_quality": promoter_quality,
        "critical_count": len(critical),
    }


# -------------------------------------------------------------- SLA queue

def sla_queue(data):
    now = data["now"]
    rows = []
    for l in data["leads"]:
        if not l["is_crm_ready"] or l["contacted"]:
            continue
        remaining = settings.sla_hours() - (now - l["ts"]).total_seconds() / 3600.0
        rows.append({
            "lead_id": l["lead_id"], "ts": l["ts"].strftime("%Y-%m-%d %H:%M"),
            "customer_name": l["customer_name"], "phone": l["phone_norm"],
            "promoter_name": l["promoter_name"], "branch_name": l["branch_name"],
            "grade": l["grade"], "interest": l["interest"],
            "promoter_note": l["promoter_note"],
            "hours_remaining": round(remaining, 1),
            "state": "breached" if remaining < 0 else ("urgent" if remaining < 6 else "ok"),
        })
    rows.sort(key=lambda r: r["hours_remaining"])
    return rows


# ------------------------------------------------------------- attendance

def attendance(conn, data, date=None):
    """Planned roster against what actually happened.

    The promoter is never blocked by the roster — this is the manager's view
    of the gap between the plan and the floor. Four states:

      on_time   rostered, and opened within the grace window
      late      rostered, opened after the shift start plus grace
      absent    rostered, never opened
      unplanned worked without being rostered
    """
    import settings as _s

    date = date or datetime.now().strftime("%Y-%m-%d")
    grace = _s.get_int("late_grace_minutes", 15)

    planned = {r["promoter_code"]: r
               for r in _s.roster(date, date)}
    actual = {s["promoter_code"]: s
              for s in data["shifts_all"] if s["date"] == date}
    shift_start = {t["name"]: t["start_time"] for t in _s.shift_types()}

    rows = []
    for code in sorted(set(list(planned) + list(actual))):
        p, a = planned.get(code), actual.get(code)
        started = db.parse_ts(a["start_ts"]) if a else None

        minutes_late = None
        if p and started:
            due = shift_start.get(p["shift_type"])
            if due:
                h, m = (due.split(":") + ["0"])[:2]
                due_dt = started.replace(hour=int(h), minute=int(m),
                                         second=0, microsecond=0)
                minutes_late = int((started - due_dt).total_seconds() // 60)

        if p and not a:
            state = "absent"
        elif a and not p:
            state = "unplanned"
        elif minutes_late is not None and minutes_late > grace:
            state = "late"
        else:
            state = "on_time"

        rows.append({
            "promoter_code": code,
            "promoter_name": _promoter_name(code),
            "planned_shift": p["shift_type"] if p else "",
            "planned_branch": _s.branches().get(p["branch"], p["branch"]) if p else "",
            "planned_start": shift_start.get(p["shift_type"], "") if p else "",
            "actual_branch": a["branch_name"] if a else "",
            "actual_start": a["start_ts"][11:16] if a else "",
            "actual_end": (a["end_ts"] or "")[11:16] if a else "",
            "open_now": bool(a and not a["closed"]),
            "hours": a["hours"] if a else 0,
            "conversations": (a["conversations"] if a else None),
            "qualified": a.get("qualified", 0) if a else 0,
            "captured": a.get("captured", 0) if a else 0,
            "minutes_late": minutes_late,
            "state": state,
            "note": (p["note"] if p else "") or "",
        })

    order = {"absent": 0, "late": 1, "unplanned": 2, "on_time": 3}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["promoter_name"]))
    return {
        "date": date,
        "rows": rows,
        "planned": len(planned),
        "present": len(actual),
        "absent": sum(1 for r in rows if r["state"] == "absent"),
        "late": sum(1 for r in rows if r["state"] == "late"),
        "unplanned": sum(1 for r in rows if r["state"] == "unplanned"),
        "grace": grace,
    }
