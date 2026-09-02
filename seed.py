"""
Generate a realistic demo dataset so every dashboard panel can be checked
against data before the first real shift.

    python seed.py           # 14 days of activity
    python seed.py --wipe    # clear everything and start empty

The generator deliberately injects a handful of data errors — a missing
grade, a repeated phone number, an unclosed shift, an under-clicked tally —
so the Data Quality panel has something to catch. Nothing here is used at
runtime; delete the database before going live.
"""

import os
import random
import sys
from baghdad_time import datetime, timedelta

import config
import db
import settings

random.seed(7)

# Promoters differ from each other on purpose, so the scoring has something
# to separate: (conversations/hour, qualification rate, capture rate, close rate)
SKILL = {
    "P01": (26, 0.34, 0.78, 0.20),   # strong all round
    "P02": (31, 0.22, 0.61, 0.11),   # high volume, low quality
    "P03": (21, 0.41, 0.83, 0.24),   # low volume, excellent quality
    "P04": (24, 0.28, 0.70, 0.14),
    "P05": (19, 0.31, 0.74, 0.17),
    "P06": (23, 0.25, 0.66, 0.12),
}
# Branch footfall multipliers — some locations are simply busier.
FOOTFALL = {"B01": 1.25, "B02": 1.10, "B03": 0.85, "B04": 0.70}

INTEREST_WEIGHTS = [0.24, 0.21, 0.18, 0.12, 0.15, 0.10]
# Weighted towards the exam years, which is what a real booth sees.
GRADE_POOL = (["Grade 12"] * 16 + ["Grade 11"] * 13 + ["Grade 10"] * 12
              + ["Grade 9"] * 11 + ["Grade 8"] * 10 + ["Grade 7"] * 9
              + ["Grade 6"] * 8 + ["Grade 5"] * 7)
# Interest drives conversion — exam prep and full curriculum close far better.
CLOSE_BY_INTEREST = {
    "Exam Preparation": 1.9, "Full Curriculum": 1.7, "Weak Subject": 1.1,
    "Revision": 1.0, "Daily Study Help": 0.8, "Just Exploring": 0.25,
}
PRICE = {"Single Subject": (25, 45), "Revision Pack": (35, 60),
         "Exam Bundle": (60, 110), "Full Year Subscription": (120, 240)}
PRODUCT_BY_INTEREST = {
    "Exam Preparation": "Exam Bundle", "Full Curriculum": "Full Year Subscription",
    "Weak Subject": "Single Subject", "Revision": "Revision Pack",
    "Daily Study Help": "Single Subject", "Just Exploring": "Revision Pack",
}

FIRST = ["أحمد", "ليلى", "محمد", "نور", "خالد", "سارة", "حسين", "رنا",
         "علي", "مها", "يزن", "دينا", "عمر", "آية", "بشار", "سلمى",
         "فادي", "هالة", "زياد", "ريم", "سمير", "لينا", "طارق", "هدى"]


def phone():
    return "07" + random.choice("789") + "".join(random.choice("0123456789") for _ in range(7))


def wipe():
    conn = db.connect()
    for t in ("followups", "leads", "shifts", "costs"):
        conn.execute("DELETE FROM %s" % t)
    conn.commit()
    conn.close()
    print("Cleared all data.")


def run(days=14, small=False):
    """small=True keeps the dataset human-sized — a few promoters over a few
    days, so every table on the dashboard can be read and checked by eye."""
    conn = db.connect()
    scale = 0.07 if small else 1.0
    roster = ["P01", "P02", "P03"] if small else list(settings.promoters())
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used_phones = []
    leads_made = 0
    shifts_made = 0

    for back in range(days, -1, -1):
        day = today - timedelta(days=back)
        # Weekends are busier in this market.
        busy = 1.35 if day.weekday() in (4, 5) else 1.0

        for code in roster:
            name, home = settings.promoters()[code]
            if not small and random.random() < 0.18:      # days off
                continue
            branch = home
            if random.random() < 0.12:          # occasional cover at another branch
                branch = random.choice(list(settings.branches()))

            cph, qual_rate, cap_rate, close_rate = SKILL[code]
            evening = random.random() < 0.5
            start_hour = 16 if evening else 10
            start = day.replace(hour=start_hour, minute=random.choice([0, 5, 15]))
            length = random.choice([5, 6, 6, 7])
            end = start + timedelta(hours=length)

            hours = length - settings.break_hours()
            conversations = int(cph * hours * FOOTFALL[branch] * busy
                                * random.uniform(0.85, 1.15) * scale)

            key = "%s|%s" % (day.strftime("%Y-%m-%d"), code)
            # One promoter forgets to close a shift, once — so the Data
            # Quality panel has a real open shift to catch.
            leave_open = (back == 0 and code == roster[-1])

            qualified = int(conversations * qual_rate * random.uniform(0.85, 1.15))
            captured_target = int(qualified * cap_rate)

            # One shift has an under-clicked tally, to trip LEADS_GT_CONVOS.
            recorded_conversations = conversations
            if back == 1 and code == roster[1]:
                recorded_conversations = max(1, qualified - 2)

            gifts = captured_target + random.choice([-1, 0, 0, 0, 1, 2])
            if back == 2 and code == roster[0]:
                gifts = captured_target + max(4, int(captured_target * 0.5))

            conn.execute(
                """INSERT OR REPLACE INTO shifts
                   (shift_key, date, branch, promoter_code, shift, start_ts, end_ts,
                    conversations, gifts_issued, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (key, day.strftime("%Y-%m-%d"), branch, code,
                 settings.shift_for(start),
                 start.strftime("%Y-%m-%d %H:%M:%S"),
                 None if leave_open else end.strftime("%Y-%m-%d %H:%M:%S"),
                 None if leave_open else recorded_conversations,
                 None if leave_open else max(0, gifts),
                 "Aisle closed for restocking" if random.random() < 0.05 else ""))
            shifts_made += 1

            for i in range(qualified):
                ts = start + timedelta(minutes=random.randint(5, int(length * 60) - 5),
                                       seconds=random.randint(0, 59))
                grade = random.choice(GRADE_POOL)
                interest = random.choices(config.INTERESTS, weights=INTEREST_WEIGHTS)[0]
                ctype = "Parent" if random.random() < 0.72 else "Student"
                captured = i < captured_target

                name_v, raw, norm = "", "", ""
                if captured:
                    name_v = random.choice(FIRST)
                    raw = phone()
                    # A small share of repeat shoppers gives real duplicates.
                    if used_phones and random.random() < 0.012:
                        raw = random.choice(used_phones)
                    norm = db.normalise_phone(raw)
                    used_phones.append(raw)

                # Occasional real-world entry errors.
                if captured and random.random() < 0.008:
                    raw, norm = "0799", db.normalise_phone("0799")     # BAD_PHONE
                if random.random() < 0.006:
                    grade = ""                                          # MISSING_GRADE

                lead_id = db.make_lead_id(ts, code)
                bump = 0
                while conn.execute("SELECT 1 FROM leads WHERE lead_id=?",
                                   (lead_id,)).fetchone():
                    bump += 1
                    lead_id = db.make_lead_id(ts + timedelta(seconds=bump), code)

                conn.execute(
                    """INSERT INTO leads (lead_id, ts, date, branch, promoter_code, shift,
                                          grade, interest, customer_type, outcome,
                                          customer_name, phone_raw, phone_norm)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (lead_id, (ts + timedelta(seconds=bump)).strftime("%Y-%m-%d %H:%M:%S"),
                     day.strftime("%Y-%m-%d"), branch, code,
                     settings.shift_for(ts),
                     grade, interest, ctype,
                     "Captured" if captured else "Declined",
                     name_v, raw, norm))
                leads_made += 1

    conn.commit()

    # ---- sales follow-up -------------------------------------------------
    agents = list(settings.agents())
    rows = conn.execute(
        "SELECT * FROM leads WHERE outcome='Captured' ORDER BY ts").fetchall()
    contacted = converted = 0

    for r in rows:
        lead_ts = db.parse_ts(r["ts"])
        age = (datetime.now() - lead_ts).days
        if age < 1 and random.random() < 0.55:
            continue                                    # still legitimately pending
        if not db.phone_is_valid(r["phone_norm"] or ""):
            continue                                    # sales cannot call it
        if random.random() < 0.08:
            continue                                    # genuinely never called

        # ~78% inside the SLA, the rest late.
        if random.random() < 0.78:
            delay = random.uniform(1.5, 22)
        else:
            delay = random.uniform(26, 90)
        contact = lead_ts + timedelta(hours=delay)
        if contact > datetime.now():
            continue

        _, _, _, close_rate = SKILL[r["promoter_code"]]
        p_close = close_rate * CLOSE_BY_INTEREST.get(r["interest"], 1.0)
        roll = random.random()

        if roll < 0.05:
            status, attempts, purchase = "Wrong Number", 1, False
        elif roll < 0.09:
            status, attempts, purchase = "No Answer", 3, False
        elif roll < p_close + 0.09 and age >= 1:
            status, attempts, purchase = "Converted", random.choice([1, 1, 2]), True
        elif roll < 0.55:
            status, attempts, purchase = "Not Interested", random.choice([1, 2]), False
        else:
            status, attempts, purchase = "Interested", 1, False

        product = revenue = purchase_date = None
        if purchase:
            product = PRODUCT_BY_INTEREST[r["interest"]]
            lo, hi = PRICE[product]
            revenue = round(random.uniform(lo, hi), 2)
            pdate = contact + timedelta(days=random.randint(0, 4))
            if pdate > datetime.now():
                pdate = datetime.now()
            purchase_date = pdate.strftime("%Y-%m-%d")
            converted += 1

        conn.execute(
            """INSERT INTO followups (lead_id, contact_ts, sales_agent, attempts, status,
                                      purchase, purchase_date, revenue, product, notes,
                                      backdated, logged_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["lead_id"], contact.strftime("%Y-%m-%d %H:%M:%S"), random.choice(agents),
             attempts, status, 1 if purchase else 0, purchase_date, revenue or 0,
             product, "", 0, contact.strftime("%Y-%m-%d %H:%M:%S")))
        contacted += 1

    conn.commit()
    conn.close()
    print("Seeded %d shifts, %d leads, %d follow-ups, %d conversions."
          % (shifts_made, leads_made, contacted, converted))
    print("Costs are deliberately left empty — enter real figures on the Costs tab.")


if __name__ == "__main__":
    db.init()
    if "--wipe" in sys.argv:
        wipe()                      # completely empty system
    elif "--full" in sys.argv:
        wipe()
        run(14)                     # two weeks, thousands of leads
    else:
        wipe()
        run(10, small=True)         # small daily volume, but long enough
                                    # that leads mature and purchase rates appear
