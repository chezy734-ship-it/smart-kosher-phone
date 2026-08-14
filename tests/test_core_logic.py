#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
בדיקות התנהגותיות ללוגיקת הליבה של פלאפון כשר חכם (Smart-Kosher-Phone).
מריצות את הקוד האמיתי: מודם DTMF, מפענח AT/HFP, זיהוי ספרות קולי,
מנוע בייביסיטר, תא קולי, יומן שיחות ורג'יסטרי מכשירים.

הרצה:
    cd Smart-Kosher-Phone
    PYTHONIOENCODING=utf-8 QT_QPA_PLATFORM=offscreen python tests/test_core_logic.py
"""
import os
import sys
import tempfile
import json
import math
import time
from pathlib import Path

# PyQt6 ללא תצוגה
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QCoreApplication, QTimer

_app = QCoreApplication.instance() or QCoreApplication([])

from app.core import text_modem as tm
from app.core import babysitter_engine as be
from app.core import voice_recognizer as vr
from app.core import voicemail_manager as vm
from app.core import call_log as cl
from app.core import device_registry as dr
from app.bluetooth_manager import BluetoothManager, CallInfo


PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ✗ {name}  [{detail}]")


# ══════════════════════════════════════════════════════════
#  1. מודם טקסט (DTMF encode/decode + control state machine)
# ══════════════════════════════════════════════════════════

def test_text_modem():
    print("\n== מודם טקסט (DTMF) ==")

    # קידוד עברית → ספרות
    digits = tm.encode_text("שלום")
    check("encode Hebrew 'שלום' produces 8 digits",
          len(digits) == 8, f"got {len(digits)}")
    # decode עיגול מלא
    text = tm.decode_digits("".join(digits))
    check("round-trip Hebrew", text == "שלום", f"got {text!r}")

    # סופיות (ך/ם/ן/ף/ץ) מקבלות קוד ייחודי — עיגול מלא ללא אובדן
    d_final = tm.encode_text("ם")
    d_base = tm.encode_text("מ")
    check("final form ם has unique code (≠ מ)", d_final != d_base, f"{d_final} vs {d_base}")
    check("final forms round-trip lossless",
          tm.decode_digits("" .join(tm.encode_text("שלום"))) == "שלום",
          f"{tm.decode_digits(''.join(tm.encode_text('שלום')))}")

    # ספרות ופיסוק
    check("digits round-trip", tm.decode_digits("".join(tm.encode_text("0491234567"))) == "0491234567")
    check("punct round-trip", tm.decode_digits("".join(tm.encode_text("שלום! מה שלומך?"))) == "שלום! מה שלומך?")

    # תווים לא ידועים מדולגים בלי לקרוס
    d_unknown = tm.encode_text("a🙂")
    check("unknown char skipped, 'a' still encoded", len(d_unknown) == 2, f"{d_unknown}")

    # אנגלית round-trip
    check("latin round-trip", tm.decode_digits("".join(tm.encode_text("Hello123"))) == "Hello123",
          f"{tm.decode_digits(''.join(tm.encode_text('Hello123')))}")

    # קידוד ל-2 ספרות לכל תו (0-9 בלבד)
    check("all encoded digits are 0-9", all(d in "0123456789" for d in tm.encode_text("אבג012")),
          f"{tm.encode_text('אבג012')}")

    # עיגול מלא על כל האלפבית — מגן מפני התנגשויות קידוד
    full = (tm.HEBREW_LETTERS + tm.HEBREW_FINALS + "0123456789 .!?:-\"'" +
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "abcdefghijklmnopqrstuvwxyz")
    rt = tm.decode_digits("".join(tm.encode_text(full)))
    check("full-alphabet round-trip is lossless", rt == full,
          f"len {len(rt)} vs {len(full)}")

    # ── Control state machine (_check_ctrl) ──
    modem = tm.TextModem()
    received = []
    typing_started = []
    typing_stopped = []
    read_receipts = []
    modem.message_received.connect(lambda n, t: received.append((n, t)))
    modem.typing_started.connect(lambda n: typing_started.append(n))
    modem.typing_stopped.connect(lambda n: typing_stopped.append(n))
    modem.read_receipt.connect(lambda n: read_receipts.append(n))

    # שליחת ספרות לפי הפרוטוקול המלא של השולח: ##99 + תוכן + ##00
    digits = "".join(tm.encode_text("אבא"))
    for d in list("##99") + list(digits) + list("##00"):
        modem.on_dtmf_received("050", d)
    check("full message received via DTMF stream (incl. content '00')",
          received == [("050", "אבא")], f"{received}")

    # הודעה שמכילה "00" בפתיחה (א) לא נקטעת — שלמות התוכן
    received.clear()
    for d in list("##99") + list("".join(tm.encode_text("אבא אבא"))) + list("##00"):
        modem.on_dtmf_received("050", d)
    check("message with א-content arrives whole",
          received == [("050", "אבא אבא")], f"{received}")

    # typing start / stop / read — עם קידומת ## מלאה
    for d in "##11":
        modem.on_dtmf_received("051", d)
    check("typing_started emitted", typing_started == ["051"], f"{typing_started}")

    for d in "##12":
        modem.on_dtmf_received("051", d)
    check("typing_stopped emitted", typing_stopped == ["051"], f"{typing_stopped}")

    for d in "##22":
        modem.on_dtmf_received("051", d)
    check("read_receipt emitted", read_receipts == ["051"], f"{read_receipts}")


# ══════════════════════════════════════════════════════════
#  2. מפענח AT/HFP — מצב השיחה
# ══════════════════════════════════════════════════════════

def test_hfp_parser():
    print("\n== מפענח AT/HFP ==")
    bt = BluetoothManager()

    incoming = []
    answered = []
    ended = []
    resolved = []
    bt.call_incoming.connect(lambda c: incoming.append(c))
    bt.call_answered.connect(lambda c: answered.append(c))
    bt.call_ended.connect(lambda c: ended.append(c))
    bt.device_number_resolved.connect(lambda a, n: resolved.append((a, n)))

    # הגדרת אינדיקטורים — call=2, callsetup=3
    bt._parse_at('+CIND: ("service",(0,1)),("call",(0,1)),("callsetup",(0,3))')
    check("CIND definition maps call→2, callsetup→3",
          bt._indicators.get("call") == 2 and bt._indicators.get("callsetup") == 3,
          f"{bt._indicators}")

    # ערכים נוכחיים — שום שיחה
    bt._parse_at("+CIND: 1,0,0")
    check("no call initially", bt._current_call is None)

    # שיחה נכנסת: callsetup=1
    bt._parse_at("+CIEV: 3,1")
    check("incoming call via CIEV callsetup",
          incoming and incoming[-1].direction == "incoming", f"{incoming}")
    check("unknown number placeholder", incoming[-1].number == "מספר לא ידוע",
          f"{incoming[-1].number}")

    # מענה: call=1
    bt._parse_at("+CIEV: 2,1")
    check("call answered via CIEV call",
          answered and answered[-1].status == "active", f"{answered}")

    # ניתוק: call=0
    bt._parse_at("+CIEV: 2,0")
    check("call ended via CIEV call", len(ended) == 1, f"{ended}")
    check("no current call after end", bt._current_call is None)

    # ── CLIP עם מספר ──
    bt._parse_at('+CLIP: "0501234567",129,1,0,"",128')
    check("CLIP creates incoming with number",
          incoming[-1].number == "0501234567", f"{incoming[-1].number}")

    # ── RING לבד (בלי CLIP) ──
    bt._current_call = None
    bt._parse_at("RING")
    check("RING alone creates incoming", bt._current_call is not None)
    check("RING number is unknown", bt._current_call.number == "מספר לא ידוע",
          f"{bt._current_call.number}")

    # ── NO CARRIER מסיים ──
    bt._parse_at("NO CARRIER")
    check("NO CARRIER ends call", bt._current_call is None)
    check("NO CARRIER emitted end", len(ended) == 2, f"{len(ended)}")

    # ── CNUM שולח device_number_resolved ──
    dev = be.BabysitterExtension  # unrelated; just need a fake device object
    from types import SimpleNamespace
    bt._current_device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF")
    bt._parse_at('+CNUM: "","0501112222",129,7,4,1')
    check("CNUM resolves device number",
          resolved == [("AA:BB:CC:DD:EE:FF", "0501112222")], f"{resolved}")


# ══════════════════════════════════════════════════════════
#  3. בקרת שיחה — פקודות AT שנשלחות
# ══════════════════════════════════════════════════════════

def test_call_control():
    print("\n== בקרת שיחה (פקודות AT) ==")
    bt = BluetoothManager()
    sent = []
    bt._send_at = lambda cmd: (sent.append(cmd), True)[1]
    bt._contacts = {}

    # חיוג — המספר מנוקה מתווים לא חוקיים
    bt.dial("0 5-0 (123) 4567")
    check("dial sanitizes number → ATD0501234567;", sent and sent[-1] == "ATD0501234567;",
          f"{sent[-1] if sent else None}")

    # חיוג ריק = כלום
    before = len(sent)
    bt.dial("   ###   ")
    check("dial with empty number does nothing", len(sent) == before)

    # מענה
    bt.answer_call()
    check("answer sends ATA", sent[-1] == "ATA", f"{sent[-1]}")

    # ניתוק
    bt.hangup()
    check("hangup sends AT+CHUP", "AT+CHUP" in sent, f"{sent}")

    # DTMF — טון חוקי נשלח, לא חוקי מסורב
    bt.send_dtmf("5")
    check("DTMF 5 → AT+VTS=5", sent[-1] == "AT+VTS=5", f"{sent[-1]}")
    before = len(sent)
    ok = bt.send_dtmf("X")
    check("invalid DTMF rejected", not ok and len(sent) == before)

    # עוצמת קול — הידוק 0..15
    bt._send_at = lambda cmd: (sent.append(cmd), True)[1]
    bt.set_volume(99)
    check("volume clamps to 15 → AT+VGS=15", sent[-1] == "AT+VGS=15", f"{sent[-1]}")
    bt.set_mic_volume(-5)
    check("mic volume clamps to 0 → AT+VGM=0", sent[-1] == "AT+VGM=0", f"{sent[-1]}")

    # ללא חיבור — _send_at מחזיר False ומודיע
    bt2 = BluetoothManager()
    status_msgs = []
    bt2.status_message.connect(lambda m: status_msgs.append(m))
    ok = bt2._send_at("ATD123;")
    check("send without connection returns False", ok is False)
    check("send without connection reports message",
          any("אין חיבור" in m or "No active" in m for m in status_msgs), f"{status_msgs}")


# ══════════════════════════════════════════════════════════
#  4. זיהוי ספרות קולי
# ══════════════════════════════════════════════════════════

def test_words_to_digit():
    print("\n== זיהוי ספרות קולי ==")
    check("אחת → 1", vr._words_to_digit("אחת") == "1")
    check("שתיים → 2", vr._words_to_digit("שתיים") == "2")
    check("חמש → 5", vr._words_to_digit("חמש") == "5")
    check("כוכבית → *", vr._words_to_digit("כוכבית") == "*")
    check("סולמית → #", vr._words_to_digit("סולמית") == "#")
    check("english two → 2", vr._words_to_digit("two") == "2")
    check("english star → *", vr._words_to_digit("star") == "*")
    check("single char 7 → 7", vr._words_to_digit("7") == "7")
    check("Hebrew digit-in-sentence finds digit",
          vr._words_to_digit("תספר לי שלוש פעמים") == "3")
    check("unknown word → None", vr._words_to_digit("טקסט אקראי") is None)
    check("empty → None", vr._words_to_digit("") is None)


# ══════════════════════════════════════════════════════════
#  5. מנוע בייביסיטר — RMS, תבנית בכי, מענה אוטומטי, הגדרות
# ══════════════════════════════════════════════════════════

def _sine_pcm(amp: float, freq: float = 440, sr: int = 8000, dur: float = 0.2) -> bytes:
    import struct
    n = int(sr * dur)
    out = []
    for i in range(n):
        v = int(32767 * amp * math.sin(2 * math.pi * freq * i / sr))
        out.append(struct.pack("<h", v))
    return b"".join(out)


def test_babysitter():
    print("\n== מנוע בייביסיטר ==")

    # RMS של שקט = 0, של סינוס באמפליטודה ידועה = קרוב ל-amp/sqrt(2)
    silence = b"\x00\x00" * 400
    rms_sil = be._rms(silence)
    check("RMS of silence is 0", rms_sil == 0.0, f"{rms_sil}")

    rms_sine = be._rms(_sine_pcm(0.5))
    expected = 0.5 / math.sqrt(2)
    check("RMS of 0.5 sine ≈ 0.354",
          abs(rms_sine - expected) < 0.02, f"{rms_sine} vs {expected}")

    # ריק / קצר מדי = 0
    check("RMS of empty is 0", be._rms(b"") == 0.0)
    check("RMS of 1 byte is 0", be._rms(b"\x01") == 0.0)

    # תבנית בכי: פריימים חזקים ורועשים (וריאציה) → True
    loud = [0.5, 0.1, 0.45, 0.15, 0.5, 0.08, 0.48, 0.2, 0.5, 0.1]
    check("cry pattern detected (sensitivity 0.35)",
          be._is_cry_pattern(loud, 0.35) is True)

    # שקט מתמשך → False
    quiet = [0.01] * 10
    check("quiet frames not a cry", be._is_cry_pattern(quiet, 0.35) is False)

    # מעט מדי פריימים → False
    check("short history not a cry", be._is_cry_pattern([0.5] * 3, 0.35) is False)

    # קולות חלשים: רגישות גבוהה מזהה, נמוכה לא
    # סף = 0.04 + (1-sensitivity)*0.20 → 0.9: סף 0.06, 0.1: סף 0.22
    weak = [0.07] * 10
    check("high sensitivity catches weak sound (0.07>0.06)",
          be._is_cry_pattern(weak, 0.9) is True)
    check("low sensitivity ignores weak sound (0.07<0.22)",
          be._is_cry_pattern(weak, 0.1) is False)

    # ── should_auto_answer ──
    engine = be.BabysitterEngine()
    engine.settings.enabled = False
    engine.settings.auto_answer = True
    check("auto-answer off when monitoring disabled",
          engine.should_auto_answer("0501234567") is False)

    engine.settings.enabled = True
    engine.settings.allowed_callers = []
    check("auto-answer on when no restriction",
          engine.should_auto_answer("0501234567") is True)

    engine.settings.allowed_callers = ["054"]
    check("allowed caller suffix matches",
          engine.should_auto_answer("0549999999") is True)
    check("other caller rejected",
          engine.should_auto_answer("0501111111") is False)

    # ── הגדרות: save/load round-trip עם תיקייה זמנית ──
    engine2 = be.BabysitterEngine()
    tmp = Path(tempfile.mkdtemp()) / "babysitter.json"
    engine2._settings_path = str(tmp)
    engine2.settings.sensitivity = 0.77
    engine2.settings.call_numbers = ["0501234567", "0547654321"]
    engine2.settings.allowed_callers = ["054"]
    ext = engine2.add_extension("חדר תינוק")
    engine2.save_settings()

    engine3 = be.BabysitterEngine()
    engine3._settings_path = str(tmp)
    engine3._load_settings()
    check("settings round-trip sensitivity",
          abs(engine3.settings.sensitivity - 0.77) < 1e-9)
    check("settings round-trip call numbers",
          engine3.settings.call_numbers == ["0501234567", "0547654321"])
    check("settings round-trip extension",
          len(engine3.settings.extensions) == 1 and
          engine3.settings.extensions[0].name == "חדר תינוק")


# ══════════════════════════════════════════════════════════
#  6. תא קולי — התאמת כללים, שמירה, ספירת צלצולים
# ══════════════════════════════════════════════════════════

def test_voicemail():
    print("\n== תא קולי ==")

    import app.core.voicemail_manager as vm_mod
    real_datetime = vm_mod.datetime

    def fresh_mgr():
        return vm.VoicemailManager(voicemail_dir=str(Path(tempfile.mkdtemp())))

    # ── כלל פעיל: תמיד עונה ──
    mgr = fresh_mgr()
    rule = vm.VoicemailRule(
        rule_id="r1", name="test", enabled=True, answer_always=True,
        rings_before_answer=2)
    mgr.add_rule(rule)
    check("default rule present + custom rule",
          len(mgr.get_rules()) == 2)
    match = mgr.find_matching_rule("0501234567")
    check("answer_always matches any number", match is not None and match.rule_id == "r1")

    # ── התאמה לפי מספר (כל כלל במנהל מבודד — הראשון ברשימה זוכה) ──
    mgr = fresh_mgr()
    rule2 = vm.VoicemailRule(
        rule_id="r2", name="only-054", enabled=True,
        answer_always=False, answer_numbers=["054"],
        answer_hour_from=0, answer_hour_to=23)
    mgr.add_rule(rule2)
    match2 = mgr.find_matching_rule("0547654321")
    check("number-specific rule matches 054", match2 is not None and match2.rule_id == "r2")
    match3 = mgr.find_matching_rule("0501234567")
    check("number-specific rule rejects 050", match3 is None, f"{match3}")

    # ── התאמה לפי יום/שעה (זמן מזויף) ──
    class FakeDateTime:
        class datetime:
            @staticmethod
            def now():
                return real_datetime.datetime(2026, 1, 1, 9, 0)  # Thursday 09:00

    vm_mod.datetime = FakeDateTime
    try:
        mgr = fresh_mgr()
        rule3 = vm.VoicemailRule(
            rule_id="r3", name="weekdays-9to17", enabled=True,
            answer_always=True, answer_days=[0, 1, 2, 3, 4],
            answer_hour_from=9, answer_hour_to=17)
        mgr.add_rule(rule3)
        match4 = mgr.find_matching_rule("0501234567")
        check("weekday rule matches Thursday 09:00",
              match4 is not None and match4.rule_id == "r3", f"{match4.rule_id if match4 else None}")

        class FakeSat:
            class datetime:
                @staticmethod
                def now():
                    return real_datetime.datetime(2026, 1, 3, 9, 0)  # Saturday

        vm_mod.datetime = FakeSat
        match5 = mgr.find_matching_rule("0501234567")
        check("weekday rule does not match Saturday", match5 is None,
              f"{match5.rule_id if match5 else None}")

        # שעה מחוץ לטווח
        class FakeNight:
            class datetime:
                @staticmethod
                def now():
                    return real_datetime.datetime(2026, 1, 1, 22, 0)  # 22:00 > 17

        vm_mod.datetime = FakeNight
        match6 = mgr.find_matching_rule("0501234567")
        check("rule inactive out of hour range", match6 is None,
              f"{match6.rule_id if match6 else None}")
    finally:
        vm_mod.datetime = real_datetime

    # ── ספירת צלצולים → מענה ──
    bt_calls = []
    fake_bt = SimpleNamespace(
        answer_call=lambda: bt_calls.append("answer"),
        set_mic_volume=lambda lv: bt_calls.append(f"mic{lv}"),
        hangup=lambda: bt_calls.append("hangup"),
    )
    mgr3 = vm.VoicemailManager(voicemail_dir=str(Path(tempfile.mkdtemp())), bt_manager=fake_bt)
    rule4 = vm.VoicemailRule(rule_id="r4", name="rings", enabled=True,
                             answer_always=True, rings_before_answer=3)
    mgr3.add_rule(rule4)
    got = mgr3.on_incoming_call("0501112222")
    check("incoming accepted by voicemail", got is True)
    check("state is waiting", mgr3.state == "waiting")
    mgr3._on_ring_tick()
    mgr3._on_ring_tick()
    check("still waiting after 2 rings", mgr3.state == "waiting")
    mgr3._on_ring_tick()
    check("answers after 3rd ring", mgr3.state == "greeting" or bt_calls,
          f"state={mgr3.state} calls={bt_calls}")
    check("answer_call invoked", "answer" in bt_calls, f"{bt_calls}")

    # ── delete_rule + שמירה לדיסק ──
    mgr = fresh_mgr()
    mgr.add_rule(vm.VoicemailRule(rule_id="d1", name="del-me", enabled=True, answer_always=True))
    mgr.delete_rule("d1")
    check("delete_rule removes rule",
          all(r.rule_id != "d1" for r in mgr.get_rules()))

    mgr3b = vm.VoicemailManager(
        voicemail_dir=str(mgr3.vm_dir), bt_manager=fake_bt)
    check("rules persisted across instances",
          any(r.rule_id == "r4" for r in mgr3b.get_rules()), f"{mgr3.vm_dir}")


# ══════════════════════════════════════════════════════════
#  7. יומן שיחות + רשימה שחורה
# ══════════════════════════════════════════════════════════

def test_call_log():
    print("\n== יומן שיחות ==")
    tmp = Path(tempfile.mkdtemp())
    log = cl.CallLog(base_dir=str(tmp))

    # רשימה שחורה מכריחה direction=blacklist
    log.add_to_blacklist("0509999999")
    log.add("0509999999", "ספאם", "incoming")
    entries = log.get_all()
    check("blacklisted number forced to blacklist direction",
          entries and entries[0].direction == "blacklist", f"{[e.direction for e in entries]}")

    # הוספת שיחות רגילות
    log.add("0501234567", "אבא", "incoming", duration=95)
    log.add("0501111111", "", "missed")
    check("entries count", len(log.get_all()) == 3, f"{len(log.get_all())}")

    # פילטור לפי כיוון
    inc = log.get_filtered("incoming")
    check("filter incoming", len(inc) == 1 and inc[0].number == "0501234567",
          f"{[(e.number, e.direction) for e in inc]}")

    # רשימה שחורה
    check("is_blacklisted", log.is_blacklisted("0509999999") is True)
    log.remove_from_blacklist("0509999999")
    check("removed from blacklist", log.is_blacklisted("0509999999") is False)

    # תצוגת משך — 95s → 01:35 (מאתר את הערך הנכנס)
    entry = next(e for e in log.get_all() if e.number == "0501234567")
    check("duration format 95s → 01:35", entry.display_duration == "01:35",
          f"{entry.display_duration}")

    # תצוגת תאריך: היום/אתמול/תאריך
    import datetime as dt
    now = dt.datetime.now()
    today_entry = cl.CallLogEntry("1", "", "incoming", now.timestamp())
    check("today label", today_entry.display_date.startswith("היום"),
          f"{today_entry.display_date}")
    yesterday_entry = cl.CallLogEntry("1", "", "incoming",
                                      (now - dt.timedelta(days=1)).timestamp())
    check("yesterday label", yesterday_entry.display_date.startswith("אתמול"),
          f"{yesterday_entry.display_date}")
    old_entry = cl.CallLogEntry("1", "", "incoming",
                                (now - dt.timedelta(days=5)).timestamp())
    check("old date formatted", "/" in old_entry.display_date,
          f"{old_entry.display_date}")

    # שמירה לדיסק: מופע חדש רואה את אותו תוכן
    log2 = cl.CallLog(base_dir=str(tmp))
    check("log persisted", len(log2.get_all()) == len(log.get_all()),
          f"{len(log2.get_all())} vs {len(log.get_all())}")

    # clear
    log.clear()
    check("clear empties log", log.get_all() == [])


# ══════════════════════════════════════════════════════════
#  8. רג'יסטרי מכשירים
# ══════════════════════════════════════════════════════════

def test_device_registry():
    print("\n== רג'יסטרי מכשירים ==")
    import app.core.device_registry as dr_mod

    real_path = dr_mod.SETTINGS_PATH
    tmp = Path(tempfile.mkdtemp()) / "settings.json"
    dr_mod.SETTINGS_PATH = str(tmp)
    try:
        reg = dr.DeviceRegistry()
        d1 = reg.register("AA:BB:CC:DD:EE:01", "פלאפון")
        check("first device becomes primary", reg.primary() is not None and
              reg.primary().address == "AA:BB:CC:DD:EE:01")
        reg.rename("AA:BB:CC:DD:EE:01", "הפלאפון שלי")
        check("rename works", reg.get("AA:BB:CC:DD:EE:01").custom_name == "הפלאפון שלי")
        reg.set_phone_number("AA:BB:CC:DD:EE:01", "0501112222")
        check("phone number set", reg.get("AA:BB:CC:DD:EE:01").phone_number == "0501112222")

        reg.register("AA:BB:CC:DD:EE:02", "מכשיר שני")
        check("second device not primary",
              reg.get("AA:BB:CC:DD:EE:02").is_primary is False)

        # שמירה → מופע חדש
        reg2 = dr.DeviceRegistry()
        check("registry persisted", reg2.get("AA:BB:CC:DD:EE:01") is not None)
        check("primary persisted",
              reg2.primary().address == "AA:BB:CC:DD:EE:01")

        # מחיקת primary מעלה את הבא
        reg2.remove("AA:BB:CC:DD:EE:01")
        check("primary removed", reg2.get("AA:BB:CC:DD:EE:01") is None)
        check("next device promoted to primary",
              reg2.primary().address == "AA:BB:CC:DD:EE:02")
    finally:
        dr_mod.SETTINGS_PATH = real_path


# ══════════════════════════════════════════════════════════
#  Runner
# ══════════════════════════════════════════════════════════

from types import SimpleNamespace


def main():
    test_text_modem()
    test_hfp_parser()
    test_call_control()
    test_words_to_digit()
    test_babysitter()
    test_voicemail()
    test_call_log()
    test_device_registry()

    print(f"\n===== סיכום: {PASS} עברו, {FAIL} נכשלו =====")
    if FAILURES:
        print("כשלונות:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
