# -*- coding: utf-8 -*-
"""Pre-flight check. Run this before pushing, and again against the live URL.

    python deploy_check.py                 # check this copy is deployable
    python deploy_check.py https://…       # check the live site
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OK, BAD, WARN = "  ✓", "  ✗", "  !"
problems = []


def check(ok, good, bad, fatal=True):
    print((OK if ok else (BAD if fatal else WARN)) + " " + (good if ok else bad))
    if not ok and fatal:
        problems.append(bad)


def local():
    print("ملفات النشر")
    for f in ("wsgi.py", "Procfile", "requirements.txt", "railway.json"):
        check(os.path.exists(f), f, "%s ناقص" % f)

    print("\nالإعدادات")
    import config
    check(os.environ.get("ABWAB_SECRET_KEY") or not config.IS_PRODUCTION,
          "ABWAB_SECRET_KEY مضبوط (أو لسنا في الإنتاج)",
          "ABWAB_SECRET_KEY غير مضبوط بينما ABWAB_ENV=production")
    db_env = os.environ.get("ABWAB_DB")
    check(bool(db_env) or not config.IS_PRODUCTION,
          "ABWAB_DB = %s" % (db_env or "(محلي)"),
          "ABWAB_DB غير مضبوط — البيانات ستُمسح مع كل نشر")

    print("\nقاعدة البيانات")
    import db
    conn = db.connect()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    check(mode.lower() == "wal", "journal_mode = WAL",
          "journal_mode = %s — الكتابة المتزامنة قد تفشل" % mode)
    leads = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    conn.close()
    check(leads == 0, "لا توجد ليدات — نظيف للإطلاق",
          "فيه %d ليد تجريبي — شغّل: python seed.py --wipe" % leads, fatal=False)

    print("\nكلمات السر")
    import settings
    rows = settings.promoter_rows() + settings.agent_rows()
    unhashed = [r["code"] for r in rows if not settings.is_hashed(r["pin"])]
    check(not unhashed, "كل كلمات السر مشفّرة",
          "غير مشفّرة: %s" % unhashed)
    default = settings.verify(settings.get("manager_pin"), "abwabmanager9090")
    check(not default, "كلمة سر المدير مُغيّرة",
          "كلمة سر المدير لا تزال الافتراضية — غيّرها من الإعدادات", fatal=False)


def live(url):
    import json
    import urllib.request
    url = url.rstrip("/")
    print("فحص الموقع المباشر: %s" % url)

    check(url.startswith("https://"), "HTTPS", "الرابط ليس HTTPS")

    try:
        r = urllib.request.urlopen(url + "/healthz", timeout=20)
        body = json.loads(r.read().decode())
        check(r.status == 200 and body.get("ok"), "الخادم يستجيب",
              "healthz رجّع %s" % r.status)
    except Exception as e:
        check(False, "", "لا يمكن الوصول: %r" % e)
        return

    try:
        r = urllib.request.urlopen(url + "/manager", timeout=20)
        check("login" in r.url, "لوحة المدير محمية",
              "لوحة المدير مفتوحة بدون تسجيل دخول!")
    except Exception:
        check(True, "لوحة المدير محمية", "")

    try:
        urllib.request.urlopen(url + "/api/dashboard", timeout=20)
        check(False, "", "‏/api/dashboard مفتوح بدون تسجيل دخول!")
    except urllib.error.HTTPError as e:
        check(e.code == 401, "‏API محمي (401)", "‏API رجّع %d" % e.code)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        live(sys.argv[1])
    else:
        local()
    print()
    if problems:
        print("توقّف: %d مشكلة لازم تُحل قبل النشر." % len(problems))
        sys.exit(1)
    print("جاهز للنشر.")
