"""
Abwab Hypermarket Activation — project configuration.

Everything the manager may need to change without touching application logic
lives here. This is the code equivalent of the `Config` tab in the spec.
"""

import os

# --- Identity -----------------------------------------------------------
PROJECT_NAME = "Abwab Hypermarket Activation"
CURRENCY = "د.ع"          # change to SAR / AED / EGP as required
# Iraqi mobile numbers are 11 digits including the leading zero: 07XXXXXXXXX.
# These are TOTAL digits and the required opening, both checked exactly — a
# number that is one digit short is a number the sales team cannot call.
PHONE_DIGITS = 11
PHONE_PREFIX = "07"

# --- Branches -----------------------------------------------------------
# code -> display name
BRANCHES = {
    "B01": "التعاون - جميلة",
    "B05": "مسواك - نخيل بغداد",
    "B02": "التعاون - الحرية",
    "B03": "التعاون - الشعب",
    "B04": "التعاون - الصالحية",
}

# --- Promoters ----------------------------------------------------------
# code -> (full name, home branch)
PROMOTERS = {
    "P01": ("غسق", "B01"),
    "P02": ("سارة", "B01"),
    "P03": ("فاطمة", "B02"),
    "P04": ("زياد", "B02"),
    "P05": ("عبدالرحمن", "B03"),
    "P06": ("طارق عزيز", "B04"),
}

# --- Sales agents -------------------------------------------------------
SALES_AGENTS = {
    "S01": "مها عودة",
    "S02": "كريم فارس",
}

# --- Access -------------------------------------------------------------
# Each person signs in with their own password and can only reach their own
# screen. A promoter cannot open another promoter's page and cannot reach the
# dashboard at all. Passwords are stored hashed, never in this file.
#
# In production the secret key MUST come from the environment. The fallback exists only
# so the app still runs on a laptop; it is not a secret.
SECRET_KEY = os.environ.get("ABWAB_SECRET_KEY",
                            "abwab-activation-change-this-before-launch")
IS_PRODUCTION = os.environ.get("ABWAB_ENV", "").lower() == "production"

# Passwords must be at least 8 characters and mix letters with digits. Four
# digits was too easy to shoulder-surf on a shop floor and too easy to guess
# from a promoter code.
PASSWORD_MIN = 8
PASSWORD_MAX = 32

# No real password is written in this file — it goes to GitHub.
#
# The manager password comes from the environment. Set ABWAB_MANAGER_PASSWORD
# on the host before the first boot; the app hashes it and never stores the
# plain value. Change it later from the الإعدادات tab.
#
# Promoters and sales agents get a random password the first time the database
# is created. It is printed to the server log exactly once, and the manager
# replaces it from الإعدادات anyway.
MANAGER_PIN = os.environ.get("ABWAB_MANAGER_PASSWORD", "abwabmanager9090")

PROMOTER_PINS = {}      # filled with random values at first seed
SALES_PINS = {}

# --- Grades and bands ---------------------------------------------------
# The activation targets the fifth primary year up to the final preparatory
# year. Younger grades and university are deliberately out of scope: a
# promoter who cannot pick them cannot record an out-of-target lead.
# Keys stay English and stable; the Arabic labels below carry the Iraqi
# naming the promoters actually use.
GRADE_BANDS = [
    ("Grade 5", "Primary"), ("Grade 6", "Primary"),
    ("Grade 7", "Intermediate"), ("Grade 8", "Intermediate"),
    ("Grade 9", "Intermediate"),
    ("Grade 10", "Secondary"), ("Grade 11", "Secondary"),
    ("Grade 12", "Final"),
]
GRADES = [g for g, _ in GRADE_BANDS]
GRADE_BAND_MAP = dict(GRADE_BANDS)
BAND_ORDER = ["Primary", "Intermediate", "Secondary", "Final"]

# --- Interest / need ----------------------------------------------------
# Frozen for the whole activation. Adding a seventh option mid-campaign
# splits the data and makes week-on-week comparison impossible.
INTERESTS = [
    "Revision",
    "Exam Preparation",
    "Weak Subject",
    "Full Curriculum",
    "Daily Study Help",
    "Just Exploring",
]

CUSTOMER_TYPES = ["Parent", "Student"]
OUTCOMES = ["Captured", "Declined"]

LEAD_STATUSES = [
    "New",
    "Contacted",
    "Follow-up",
    "Converted",
    "Not Converted",
    "Invalid / Unreachable",
]
TERMINAL_STATUSES = {"Converted", "Not Converted", "Invalid / Unreachable"}

PRODUCTS = [
    "Single Subject",
    "Revision Pack",
    "Exam Bundle",
    "Full Year Subscription",
]

COST_TYPES = ["Promoter Wages", "Giveaway Stock", "Booth Fee", "Materials", "Other"]

# --- Shifts -------------------------------------------------------------
# Seeded into the shift_types table on first run; the manager edits the times
# from the dashboard afterwards. (name, start, end) — 24h clock.
DEFAULT_SHIFTS = [
    ("صباحي", "09:00", "15:00"),
    ("مسائي", "15:00", "23:00"),
]

# --- Defaults for the editable settings ---------------------------------
# These seed the settings table once. After that the database wins, so
# changing a number here has no effect on an existing installation — change
# it on the dashboard instead.
DEFAULT_SETTINGS = {
    "currency": CURRENCY,
    "phone_total_digits": PHONE_DIGITS,
    "phone_prefix": PHONE_PREFIX,
    "manager_pin": MANAGER_PIN,
    "break_hours": 0.5,
    "maturity_days": 7,
    "sla_hours": 24,
    "stale_days": 7,
    "max_contact_attempts": 3,
    "gift_gap_tolerance": 0.15,
    "min_shifts_for_ranking": 2,
    "min_hours_for_ranking": 8,
    "min_branch_hours_for_ranking": 20,
    "min_mature_leads": 5,
    "late_grace_minutes": 15,
}

# --- Operating rules ----------------------------------------------------
SHIFT_SPLIT_HOUR = 15      # before 15:00 = Morning, else Evening
BREAK_HOURS = 0.5          # unpaid break deducted from shift length
MATURITY_DAYS = 7          # a lead must be this old to count in purchase rates
SLA_HOURS = 24             # follow-up SLA from the source document
MIN_MATURE_LEADS = 5       # below this, purchase components are redistributed
MIN_SHIFTS_FOR_RANKING = 2
MIN_HOURS_FOR_RANKING = 8
MIN_BRANCH_HOURS_FOR_RANKING = 20
STALE_DAYS = 7             # Contacted/Follow-up unchanged this long = stale
MAX_CONTACT_ATTEMPTS = 3   # required before Invalid / Unreachable
GIFT_GAP_TOLERANCE = 0.15  # |gifts - captured| / gifts above this is flagged
INDEX_CAP = 2.0            # caps any single metric index in the scores

# --- Promoter score weights (must sum to 1.0) ---------------------------
PROMOTER_WEIGHTS = {
    "captured_per_hour":    0.25,   # branch-benchmarked
    "purchase_rate":        0.25,   # project-benchmarked, mature leads
    "qualification_rate":   0.15,   # project-benchmarked
    "revenue_per_lead":     0.15,   # project-benchmarked, mature leads
    "conversations_per_hour": 0.10,  # branch-benchmarked
    "capture_rate":         0.10,   # project-benchmarked
}
# Which promoter metrics are benchmarked against the branch, not the project
BRANCH_BENCHMARKED = {"captured_per_hour", "conversations_per_hour"}
# Which depend on mature leads existing
MATURITY_DEPENDENT = {"purchase_rate", "revenue_per_lead"}

INTEGRITY_FLOOR = 0.80     # worst the data-quality multiplier can get

SCORE_BANDS = [
    (125, "Outstanding", "good"),
    (105, "Above average", "good"),
    (90,  "On track", "neutral"),
    (75,  "Needs coaching", "warn"),
    (0,   "At risk", "bad"),
]

# --- Branch execution score weights (must sum to 1.0) -------------------
BRANCH_WEIGHTS = {
    "captured_per_hour":  0.30,
    "purchase_rate":      0.25,
    "revenue_per_hour":   0.20,
    "qualification_rate": 0.15,
    "data_quality":       0.10,
}

# --- Flag severities ----------------------------------------------------
CRITICAL_FLAGS = {
    "MISSING_PHONE", "BAD_PHONE", "MISSING_GRADE", "MISSING_INTEREST",
    "DUP_LEADID", "NO_PROMOTER", "NO_BRANCH", "LEADS_GT_CONVOS",
    "NOT_CONTACTED",
}
HIGH_FLAGS = {
    "MISSING_NAME", "DUP_PHONE", "NO_SHIFT_LOG", "GIFT_GAP", "SLA_BREACH",
}
MEDIUM_FLAGS = {"STALE", "BACKDATED"}

# Who a flag belongs to. This split matters: an SLA breach is a sales failure,
# so charging it to the promoter's integrity score would punish the wrong
# person for something they cannot influence.
PROMOTER_FLAGS = {
    "MISSING_PHONE", "BAD_PHONE", "MISSING_NAME", "MISSING_GRADE",
    "MISSING_INTEREST", "DUP_PHONE", "NO_SHIFT_LOG", "LEADS_GT_CONVOS",
}
SALES_FLAGS = {"NOT_CONTACTED", "SLA_BREACH", "STALE", "BACKDATED"}
SYSTEM_FLAGS = {"DUP_LEADID", "NO_PROMOTER", "NO_BRANCH", "GIFT_GAP"}

# The headline Data Quality score measures whether the *record* is sound.
# Follow-up discipline is real, but it is reported in the funnel and the
# follow-up panel, not folded into a data score.
DATA_FLAGS = PROMOTER_FLAGS | SYSTEM_FLAGS

FLAG_HELP = {
    "MISSING_PHONE":   "Captured lead with no phone number",
    "BAD_PHONE":       "Phone number is not a valid local mobile",
    "MISSING_NAME":    "Captured lead with no customer name",
    "MISSING_GRADE":   "No student grade — the lead was never qualified",
    "MISSING_INTEREST": "No interest recorded — the lead was never qualified",
    "DUP_PHONE":       "This number was already captured on an earlier lead",
    "DUP_LEADID":      "Duplicate Lead ID — should be structurally impossible",
    "NO_PROMOTER":     "Promoter code missing or unknown",
    "NO_BRANCH":       "Branch code missing or unknown",
    "NO_SHIFT_LOG":    "Leads exist for this promoter-date with no shift record",
    "LEADS_GT_CONVOS": "More qualified leads than conversations — tally under-clicked",
    "GIFT_GAP":        "Gifts issued and captured leads differ by more than 15%",
    "NOT_CONTACTED":   "CRM-ready, older than 48h, still New",
    "SLA_BREACH":      "Not contacted within 24 hours",
    "STALE":           "In play but untouched for 7+ days",
    "BACKDATED":       "Contact time was manually overridden",
}


# =======================================================================
# Arabic display labels
# =======================================================================
# The database keeps the English keys above — they are stable identifiers,
# they keep the CSV export readable by any CRM, and they mean historical rows
# never change meaning when a translation is reworded. Only the *display*
# is Arabic, resolved through the maps below.

GRADE_LABELS = {
    "Grade 5": "الخامس ابتدائي",
    "Grade 6": "السادس ابتدائي",
    "Grade 7": "الأول متوسط",
    "Grade 8": "الثاني متوسط",
    "Grade 9": "الثالث متوسط",
    "Grade 10": "الرابع إعدادي",
    "Grade 11": "الخامس إعدادي",
    "Grade 12": "السادس إعدادي",
}
# Short form for the capture screen, where the buttons must fit on a phone.
GRADE_SHORT = {
    "Grade 5": "5 ابت", "Grade 6": "6 ابت",
    "Grade 7": "1 مت", "Grade 8": "2 مت", "Grade 9": "3 مت",
    "Grade 10": "4 إع", "Grade 11": "5 إع", "Grade 12": "6 إع",
}
BAND_LABELS = {
    "Primary": "ابتدائي",
    "Intermediate": "متوسط",
    "Secondary": "إعدادي",
    "Final": "السادس إعدادي",
}

INTEREST_LABELS = {
    "Revision": "مراجعة",
    "Exam Preparation": "تحضير للامتحانات",
    "Weak Subject": "مادة ضعيفة",
    "Full Curriculum": "المنهج كامل",
    "Daily Study Help": "مساعدة يومية",
    "Just Exploring": "مهتم ويريد معلومات اكثر للشراء",
}
CUSTOMER_TYPE_LABELS = {"Parent": "ولي أمر", "Student": "طالب"}
OUTCOME_LABELS = {"Captured": "أخذت بياناته", "Declined": "رفض إعطاء رقمه"}
STATUS_LABELS = {
    "New": "جديد", "Contacted": "تم الاتصال", "Follow-up": "متابعة",
    "Converted": "اشترى", "Not Converted": "لم يشترِ",
    "Invalid / Unreachable": "رقم خاطئ / لا يرد",
}
PRODUCT_LABELS = {
    "Single Subject": "مادة واحدة", "Revision Pack": "باقة مراجعة",
    "Exam Bundle": "باقة امتحانات", "Full Year Subscription": "اشتراك سنة كاملة",
}
COST_TYPE_LABELS = {
    "Promoter Wages": "أجور المروّجين", "Giveaway Stock": "الهدايا",
    "Booth Fee": "إيجار البوث", "Materials": "مواد ومطبوعات", "Other": "أخرى",
}
SHIFT_LABELS = {"Morning": "صباحي", "Evening": "مسائي"}
BAND_SCORE_LABELS = {
    "Outstanding": "ممتاز", "Above average": "فوق المتوسط", "On track": "جيد",
    "Needs coaching": "يحتاج تدريب", "At risk": "ضعيف",
}
METRIC_LABELS = {
    "captured_per_hour": "ليدات في الساعة",
    "conversations_per_hour": "محادثات في الساعة",
    "purchase_rate": "نسبة الشراء",
    "qualification_rate": "نسبة التأهيل",
    "capture_rate": "نسبة أخذ البيانات",
    "revenue_per_lead": "إيراد لكل ليد",
    "revenue_per_hour": "إيراد لكل ساعة",
    "data_quality": "جودة البيانات",
}
STAGE_LABELS = {
    "conversations": "المحادثات",
    "qualified": "ليدات مؤهلة",
    "captured": "ليدات مسجّلة",
    "crm": "جاهزة للاتصال",
    "contacted": "تم الاتصال",
    "purchases": "مشتريات",
}
LEAK_LABELS = {
    "qualified": "لا يوجد طالب، أو لم يُعرف الصف والحاجة",
    "captured": "الزبون رفض إعطاء رقمه",
    "crm": "رقم غير صالح أو مكرر",
    "contacted": "لم يُتصل به، أو لا يرد، أو اتُّصل متأخراً",
    "purchases": "السعر، أو التوقيت، أو لم يكن مهتماً فعلاً",
}
RATE_LABELS = {
    "qualification": "نسبة التأهيل",
    "capture": "نسبة أخذ البيانات",
    "crm_ready": "نسبة الجاهزية للاتصال",
    "contact": "نسبة اتصال المبيعات",
    "sla": "الاتصال خلال 24 ساعة",
    "purchase": "نسبة التحويل للشراء",
    "overall": "التحويل الكلي",
}
OWNER_LABELS = {"Promoter": "المروّج", "Sales": "المبيعات", "Manager": "الإدارة"}
SEVERITY_LABELS = {"critical": "حرج", "high": "مهم", "medium": "متوسط"}

FLAG_LABELS = {
    "MISSING_PHONE":   "ليد مسجّل بدون رقم هاتف",
    "BAD_PHONE":       "رقم الهاتف غير صالح",
    "MISSING_NAME":    "ليد مسجّل بدون اسم",
    "MISSING_GRADE":   "بدون صف — الليد لم يكن مؤهلاً أصلاً",
    "MISSING_INTEREST": "بدون حاجة — الليد لم يكن مؤهلاً أصلاً",
    "DUP_PHONE":       "هذا الرقم مسجّل سابقاً على ليد آخر",
    "DUP_LEADID":      "رقم ليد مكرر — يفترض أن يكون مستحيلاً",
    "NO_PROMOTER":     "المروّج غير معروف أو مفقود",
    "NO_BRANCH":       "الفرع غير معروف أو مفقود",
    "NO_SHIFT_LOG":    "توجد ليدات بدون تسجيل شفت لهذا اليوم",
    "LEADS_GT_CONVOS": "الليدات أكثر من المحادثات — العدّاد ناقص",
    "GIFT_GAP":        "فرق كبير بين الهدايا الموزّعة والليدات المسجّلة",
    "NOT_CONTACTED":   "جاهز للاتصال منذ أكثر من 48 ساعة ولم يُتصل به",
    "SLA_BREACH":      "لم يُتصل به خلال 24 ساعة",
    "STALE":           "قيد المتابعة بدون أي تحديث منذ 7 أيام",
    "BACKDATED":       "وقت الاتصال أُدخل يدوياً",
}
