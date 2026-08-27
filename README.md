# Abwab Hypermarket Activation — Lead Tracking System

A working web application implementing the *Offline Activities – Activation:
Lead Generation & Tracking Plan*, adapted so that **promoters manually enter
every lead** rather than relying on QR scans or customer self-registration.

The interface is **Arabic, right-to-left**. The database is not: every stored
value stays an English key. See [Language](#language) for why.

```
ENGAGE  →  CAPTURE  →  QUALIFY  →  CONVERT  →  MEASURE
```

---

## Running it

Requires Python 3.8+.

```bash
pip install flask
```

```bash
python seed.py
```

```bash
python app.py
```

Then open <http://localhost:5000>.

`seed.py` gives you a small readable dataset — 10 days, 3 promoters, ~110 leads.
It spans long enough that some leads pass the maturity window, so the purchase-rate
columns actually show numbers rather than dashes. It includes
deliberate data errors so the Data Quality panel has something to catch. Options:

```bash
python seed.py --wipe    # completely empty system, ready for real use
```

```bash
python seed.py --full    # 14 days, thousands of leads, for load testing
```

To let promoters reach it from their phones, run the server on a machine on the
same network and give them `http://<server-ip>:5000`.

---

## Putting it online — Railway

**Railway** is the pick for this project: it gives a persistent disk (which
SQLite needs), it does **not** sleep on idle, and HTTPS is automatic. The
no-sleep part is what decides it — a free tier that cold-starts for 50 seconds
is unusable when a promoter has a customer standing in front of them.

Cost is about **$5/month**. Region: pick **EU West (Amsterdam)** — roughly
70–90 ms to Baghdad, the closest option Railway offers.

### Steps

**1. Put the code on GitHub**

```bash
git init && git add -A && git commit -m "Abwab activation tracker"
```

Then create an empty repo on GitHub and push to it.

**2. Create the Railway project**

At [railway.app](https://railway.app): *New Project* → *Deploy from GitHub repo*
→ pick the repo. It reads `railway.json` and `Procfile` on its own.

**3. Attach a disk — do not skip this**

In the service: *Settings* → *Volumes* → *New Volume*, mount path `/data`.

Without it the filesystem resets on every deploy and **every lead is lost
silently**. This is the single most common way a project like this loses a
week of fieldwork.

**4. Set the variables**

*Variables* tab:

| Name | Value |
|---|---|
| `ABWAB_SECRET_KEY` | output of `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ABWAB_ENV` | `production` |
| `ABWAB_DB` | `/data/abwab.db` |

**5. Get the URL**

*Settings* → *Networking* → *Generate Domain*. You get
`something.up.railway.app`. A custom domain can be added later.

**6. Check it**

```bash
python deploy_check.py https://your-app.up.railway.app
```

This confirms HTTPS, that the server answers, and that the dashboard and API
are actually closed to strangers.

**7. Sign in as manager and change every password**

الإعدادات → set a new password for yourself and each promoter, then hand each
person their own. Passwords are hashed, so this is the only moment they exist
in readable form.

**8. Give the promoters the link**

Send each one the URL and have them **Add to Home Screen** in front of you. It
then opens like an app, straight to the sign-in.

### What arrives on the live site

A fresh deploy seeds your real setup — the branches, promoters, agents and
shifts currently in `config.py` — and **zero leads**. The demo data on this
laptop does not travel. Run `python seed.py --wipe` here too when you are done
testing.

### The signal problem, again

Hosting fixes reach, not coverage. Hypermarket interiors often have no usable
mobile data. Before the first shift, stand **at the booth position** and load
the site on a promoter's phone. If it fails there, the fix is a branch WiFi
password or a cheap router — not a different host.

---

## Language

All three screens render in Arabic with `dir="rtl"`, but **only the display is
translated.** Grades, interests, statuses, outcomes and flag codes are stored in
the database as English keys and translated at render time through the label
maps at the bottom of `config.py`.

This split is deliberate:

- Historical rows never change meaning when someone rewords a translation.
- The CSV export stays importable by a CRM that does not speak Arabic — the
  Grade column reads `Grade 12`, not الثاني عشر, while customer names, branches
  and promoter names export in Arabic as entered.
- Adding a second language later means adding one more map, not a data migration.

To reword any label, edit the maps in `config.py` — nothing else needs to change.

Two Arabic typography rules are enforced in `app.css`: Arabic letters join, so
`letter-spacing` is stripped from every label style that used it for Latin
small-caps texture, and `text-transform: uppercase` is removed because Arabic
has no case. Latin runs inside Arabic text — Lead IDs, phone numbers, money —
are forced to `direction: ltr` so the bidi algorithm does not reorder them.

---

## Signing in

Everyone lands on `/login`, picks their name and enters their password.
They are then sent to their own screen and can reach nothing else.

| Who | Sees |
|---|---|
| Promoters | Only their own shift and their own leads |
| Sales agents | The SLA queue and follow-up logging |
| Project Manager | Everything, including الإعدادات |

**No password is written anywhere in this repository.**

- The **manager** password comes from `ABWAB_MANAGER_PASSWORD` on the host. Set
  it before the first boot.
- **Promoters and sales agents** get a random password the first time the
  database is created. It is printed to the server log **once** — on Railway,
  read it under *Deployments → View Logs* right after the first deploy. Look for:

  ```
  ==========================================================
  FIRST-RUN PASSWORDS — copy these now, they are not shown again
  ==========================================================
     P01    p01k4m2xq9t
  ```

- Change them all from الإعدادات once you are in. Passwords are hashed
  (scrypt), so that tab writes a new one and can never show you an old one.

**Policy:** at least 8 characters, containing both letters and digits, no
spaces.

### What the privacy actually enforces

- A promoter cannot open another promoter's screen. `?p=P02` in the URL is
  ignored — identity comes from the signed-in session only.
- A promoter asking the API for another promoter's leads gets **their own**
  leads back, not an error and not someone else's data.
- A lead posted with `"promoter": "P02"` in the body is saved against whoever is
  signed in. The request body cannot choose an identity.
- Promoters get 401 on the dashboard, the CSV exports and the sales queue.
- Sales agents get 401 on the dashboard.

This is a **door lock, not a safe.** It puts the right person on the right
screen, which is what this project needs. It is not hardened authentication —
do not expose it to the public internet without HTTPS and real accounts.

---

## Settings — editing the setup without touching code

The dashboard has an **الإعدادات** tab. Branches, promoters, sales agents,
shift times and the operating rules all live in the database and are edited
there. `config.py` now only holds the **defaults** used to seed those tables on
first run; changing a value there has no effect on an installation that already
has data.

What the manager can change, with no restart:

| Section | What it controls |
|---|---|
| الفروع | Branch codes and names, and whether each is still active |
| المروّجون | Names, default branch, sign-in PIN, active/inactive |
| موظفو المبيعات | Names, sign-in PIN, active/inactive |
| الشفتات وأوقاتها | Shift names and their start/end times |
| قواعد التشغيل | Currency, phone length, SLA hours, lead maturity, break hours, ranking thresholds, manager PIN |

### Two rules that protect the data

**Nothing with history is ever hard-deleted.** Deleting a branch or promoter
that already has leads or shifts against it *deactivates* it instead: it
disappears from every dropdown, existing records keep their name on the
dashboard, and the row count that caused it is reported back. Only an unused
entry is actually removed.

**Every setting is range-checked on the server.** `sla_hours` must be 1–168,
`phone_digits` 5–15, PINs 4–6 digits, and so on. A typo in the browser cannot
put the scoring rules into an impossible state.

Shift times apply to *new* shifts only. A shift already recorded keeps the name
it was opened under, so renaming or re-timing a shift never rewrites history.

---

## Shifts: no gate for the promoter, full visibility for the manager

A promoter is **never** blocked waiting to start. Signing in is enough: the
shift row is created automatically on first contact with the app, and they can
log a lead in the same second. There is no Start button, no allowed window, and
no approval step. If they end the day and business picks up again, **أكمل
التسجيل اليوم** reopens it and keeps the conversation count already reported.

The branch is picked automatically — from today's roster, else the promoter's
own branch — and a selector at the top of their screen lets them move it if
they are covering elsewhere. Changing it moves today's leads with it.

The plan lives separately, in **جدول المناوبات** on the settings tab: date,
promoter, branch, shift. It constrains nobody. It exists so the manager gets
**مناوبات اليوم** on the overview, comparing plan against floor:

| State | Meaning |
|---|---|
| في الموعد | Rostered, opened within the grace window |
| متأخر | Rostered, opened after the shift start plus grace (default 15 min, settable) |
| لم يحضر | Rostered, never opened |
| بدون جدولة | Worked without being rostered |

Each row shows the planned shift and branch beside the actual start time,
minutes late, actual branch, and the conversations and leads produced — so a
late start that still delivered is visibly different from one that did not.

---

## The three surfaces

| Route | Who | What it does |
|---|---|---|
| `/promoter` | Promoter | Shift open/close and lead capture. Phone-sized. |
| `/sales` | Sales agent | The live 24-hour SLA queue and follow-up logging. |
| `/manager` | Project manager | Four tabs: Overview, Promoters & Branches, Leads, Data & Costs. |

The promoter's code and branch come from their sign-in, so the two
most-mistyped fields are removed from their job entirely.

---

## What the promoter actually does

Three interactions, total effort under 30 seconds per day plus ~20 seconds per
lead:

1. **Start Shift** — one tap. Date, start time and shift band are derived from
   the timestamp.
2. **＋ Capture Lead** — grade → need → who am I talking to → did they give
   details → name and phone. The questions appear in the order the conversation
   happens, so there is no scrolling back.
3. **End Shift** — confirm the conversation count, gifts issued, optional note.

### The conversation counter

Every captured lead **automatically counts as a conversation**. The
`＋ Conversation — no lead` button is only for interactions that did *not*
produce a lead. This makes it structurally impossible to log more leads than
conversations, and it removes the end-of-shift guessing that ruins tally
numbers. The running count is held in `localStorage`, so a dropped connection
never loses it.

---

## The three counts

These are different numbers, and the whole funnel depends on promoters sharing
one definition:

| Count | Definition | The promoter's test |
|---|---|---|
| **Conversation** | Pitch delivered *and* at least one qualifying question asked | "Did I get as far as asking about their student?" |
| **Qualified Lead** | Student confirmed, grade known **and in range**, need stated | "Do I know the grade *and* the need?" |
| **Captured Lead** | Name and phone recorded | "Do I have a number I can call?" |

A qualified customer who refuses their number **still gets a row**, marked
`Declined`. Without those rows the Lead Capture Rate is permanently 100% and
tells you nothing.

---

## Grades in scope

The activation targets **الخامس ابتدائي → السادس إعدادي** (Grade 5 to Grade 12
in the stored keys). Anything younger, and university, is deliberately absent
from the promoter's picker — and the API rejects it too, so an out-of-target
lead cannot be recorded even by a crafted request.

| Stored key | Promoter sees | Short | Band |
|---|---|---|---|
| Grade 5 | الخامس ابتدائي | 5 ابت | ابتدائي |
| Grade 6 | السادس ابتدائي | 6 ابت | ابتدائي |
| Grade 7 | الأول متوسط | 1 مت | متوسط |
| Grade 8 | الثاني متوسط | 2 مت | متوسط |
| Grade 9 | الثالث متوسط | 3 مت | متوسط |
| Grade 10 | الرابع إعدادي | 4 إع | إعدادي |
| Grade 11 | الخامس إعدادي | 5 إع | إعدادي |
| Grade 12 | السادس إعدادي | 6 إع | السادس إعدادي |

Edit `GRADE_BANDS`, `GRADE_LABELS` and `GRADE_SHORT` in `config.py` to change
the range. Keep the list frozen once the activation starts — changing it
mid-campaign splits the data and makes week-on-week comparison impossible.

---

## Scoring

### Promoter score — 35% volume, 65% quality

| Metric | Weight | Benchmarked against |
|---|---|---|
| Captured leads / hour | 25% | the branch worked |
| Purchase conversion rate | 25% | project average |
| Qualification rate | 15% | project average |
| Revenue / captured lead | 15% | project average |
| Conversations / hour | 10% | the branch worked |
| Lead capture rate | 10% | project average |

Volume metrics are benchmarked against the **branch** because footfall is a
rostering outcome, not an achievement. Each index is capped at 2.0 so one freak
day cannot dominate a campaign. **Score 100 = exactly average.**

Two rules stop the score lying:

- **Eligibility** — 2+ shifts and 8+ hours, else "Insufficient data".
- **Maturity** — purchase-based components use only leads 7+ days old. Under 5
  mature leads, those weights are redistributed and the score is marked
  *Provisional*.

An **integrity multiplier** (`1 − promoter flag rate`, floored at 0.80) then
applies. It counts *only flags the promoter owns* — an SLA breach is a sales
failure and never moves a promoter's score.

### Branch — two rankings, not one

- **Execution Score** — everything per promoter-hour. *Is the team performing?*
- **Site Value** — revenue ÷ cost (or ÷ promoter-hour until costs exist).
  *Is this location worth continuing?*

A strong team at a dead location scores high on one and low on the other, and
the correct action is to move them — not to coach them. Footfall is displayed
but never scored.

---

## Denominators that differ from the obvious choice

| Rate | This system uses | Why |
|---|---|---|
| Sales Contact Rate | ÷ **CRM-ready** leads | Sales cannot call a number the promoter typed wrong |
| 24-Hour Follow-up Rate | ÷ leads **older than 24h** | A lead captured 2 hours ago cannot yet have breached |
| Purchase Conversion | ÷ **mature** captured leads | Purchases lag capture; otherwise the rate drops every good day |

Each rate is displayed with its raw numerator and denominator, so a rate built
on four leads is visibly a rate built on four leads.

---

## Data quality

Two layers. **Prevention**: invalid phone numbers, missing grades and missing
interests are rejected at the point of entry, while the customer is still
standing there. **Detection**: 16 flag codes with severities and owners.

A `Declined` lead with no phone number is deliberately **not** flagged — it is a
correctly recorded refusal, and flagging it would bury the real errors.

The headline Data Quality score covers whether the lead *record* is sound.
Follow-up failures are listed in the same panel but tracked separately, because
they belong to a different team.

---

## Costs

`Cost per Lead` and `Cost per Acquisition` read **"Cost data not entered"** until
real amounts are added on the Costs tab. Nothing is estimated or invented.

---

## Files

```
config.py    Defaults only — seeds the settings tables on first run,
             plus the Arabic label maps and the score weights.
settings.py  Runtime settings read from the database, with caching.
db.py        SQLite schema, phone normalisation, Lead ID generation.
metrics.py   The engine: funnel, rates, promoter and branch scores,
             lead quality, data quality, SLA queue.
app.py       Flask routes, PIN sign-in, role gates, and the JSON API.
seed.py      Demo data generator. Not used at runtime.
static/      app.css, promoter.js, sales.js, manager.js
templates/   login, promoter, sales, manager
data/        abwab.db (created on first run)
```

### Lead ID

`AB-260820-P07-144312` — prefix, date, promoter code, time to the second.
Unique by construction (one promoter cannot submit twice in the same second),
sorts chronologically, and survives sorting or deletion because it derives only
from the row's own timestamp.

### Phone normalisation

Strips every non-digit, keeps the last `PHONE_DIGITS` (default 9), re-adds a
leading zero — so `+962 79 123 4567`, `079-1234567` and `0791234567` all become
the same value. **Set `PHONE_DIGITS` in `config.py` to match your market
before launch.** Duplicate detection and CRM export both use this value, not the
raw entry.

---

## Before going live

- [ ] Set `CURRENCY` and `PHONE_DIGITS` in `config.py`
- [ ] Check the Arabic labels match how your team actually talks (`config.py`)
- [ ] Replace the demo branches, promoters and sales agents
- [ ] **Change every PIN and `SECRET_KEY` in `config.py`**
- [ ] `python seed.py --wipe` to clear all demo data
- [ ] Test mobile signal **at the actual booth position**, not at the entrance
- [ ] Brief promoters on the three counts — that is the whole training
- [ ] Confirm one live lead flows through to revenue against the right promoter

That last check is the one that matters: it proves the loop closes end to end.
