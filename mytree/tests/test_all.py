"""回归测试：校验引擎的判定、错因、提示的 H3 规则、变式题验算、接口的安全边界。
运行：cd mytree && python3 -m pytest tests -q   （沙箱没有 pytest 时可用 python3 tests/test_all.py）"""
import json
import os
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("MYTREE_PROFILE", os.path.join(tempfile.mkdtemp(), "p.json"))

from app import profile  # noqa: E402
from app.mathcheck import analyze  # noqa: E402
from app.pipeline import diagnose, h3_leak  # noqa: E402
from app.practice import check_answer, for_cause  # noqa: E402
from app.server import Handler  # noqa: E402
from app.visual import build  # noqa: E402

# 逐步校验：(题目, 作答, 期望状态, 期望第几行出错, 期望错因)
CASES = [
    ("2x^2-8", ["2(x^2-4)", "2(x+2)(x-2)"], "correct", None, None),
    ("2x^2-8", ["2(x^2-4)"], "incomplete", 1, "F-NOT-FINISHED"),
    ("2x^2-8", ["(x+2)(x-2)"], "wrong_step", 1, "F-COEFF-LOST"),
    ("x^2-9", ["(x-3)^2"], "wrong_step", 1, "F-MIX-FORMULA"),
    ("x^2-4x+4", ["(x+2)^2"], "wrong_step", 1, "F-SIGN"),
    ("x^2-4x+4", ["(x-2)^2"], "correct", None, None),
    ("x(x-3)-2(3-x)", ["x(x-3)+2(x-3)", "(x-3)(x+2)"], "correct", None, None),
    ("x(x-3)-2(3-x)", ["x(x-3)-2(x-3)"], "wrong_step", 1, "F-SIGN"),
    ("x^2-9", ["(x+3)(x-3)"], "correct", None, None),
    ("(x^2-9)/(x^2+6x+9)", ["(x+3)(x-3)/(x+3)^2", "(x-3)/(x+3)"], "correct", None, None),
    ("(x^2-9)/(x^2+6x+9)", ["(x+3)(x-3)/(x+3)^2"], "incomplete", 1, "R-CANCEL-INCOMPLETE"),
    ("(x+2)/(x^2+2)", ["x/x^2"], "wrong_step", 1, "R-CANCEL-TERM"),
    ("x^4-1", ["(x^2+1)(x^2-1)"], "incomplete", 1, "F-NOT-FINISHED"),
    ("3x^2+6x", ["3x(x+2)"], "correct", None, None),
]


def test_analyze_cases():
    for problem, steps, status, where, cause in CASES:
        a = analyze(problem, steps)
        assert a["status"] == status, (problem, steps, a["status"])
        assert a["first_error"] == where, (problem, steps, a["first_error"])
        assert a["cause"] == cause, (problem, steps, a["cause"])


def test_unreadable_is_not_blamed_on_student():
    a = analyze("x^2-9", ["__import__('os')"])
    assert a["status"] == "unreadable"


def test_h3_hints_do_not_leak_answer():
    for problem, steps, status, _, _ in CASES:
        if status == "correct":
            continue
        r = diagnose(problem, steps)
        assert r["ok"], problem
        assert not r["analysis"]["h3_leaks"], (problem, r["analysis"]["hints"])


def test_h3_leak_detector():
    assert h3_leak("结果是 (x-3)(x+3)", "(x-3)(x+3)")
    assert not h3_leak("想想平方差", "(x-3)(x+3)")
    assert not h3_leak("x", "x")  # 太短的答案不判定，避免误伤


def test_practice_items_pass_sympy_check():
    for cause in ("F-SIGN", "F-MIX-FORMULA", "R-CANCEL-TERM"):
        d = for_cause(cause, 3, seed=5)
        assert len(d["items"]) == 3, cause
        for it in d["items"]:
            from app.pipeline import verify_equal
            assert verify_equal(it["q"], it["a"]), it


def test_answer_check():
    assert check_answer("x^2-9", "(x+3)(x-3)")[0] is True
    assert check_answer("x^2-9", "(x+3)(x+3)")[0] is False
    assert check_answer("x^2-9", "(x+3")[0] is False


def test_visual_diff_squares_and_bars():
    a = analyze("x^2-9", ["(x-3)^2"])
    svg = build("x^2-9", a)
    assert "data-rearranged" in svg and "x&gt;3" in svg  # 分步重组与正长度边界明确标注
    a = analyze("x(x-3)-2(3-x)", ["x(x-3)-2(x-3)"])
    svg = build("x(x-3)-2(3-x)", a)
    assert svg and svg.startswith("<svg")


def test_profile_lights_used_knowledge():
    profile.record("t_light", analyze("x^2-9", ["(x+3)(x-3)"]), "x^2-9")
    p = profile.get("t_light")
    lit = {k["id"] for k in p["tree"] if k["lit"]}
    assert "F2" in lit and "F4" in lit


def _serve():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_http_pages_and_api():
    httpd, base = _serve()
    try:
        for p in ("/", "/tree", "/parent"):
            assert _req(base, "GET", p)[0] == 200
        st, body = _req(base, "POST", "/api/diagnose",
                        {"student": "t_http", "problem": "2x^2-8", "steps": ["2(x^2-4)", "2(x+2)(x-2)"]})
        assert st == 200 and json.loads(body)["analysis"]["status"] == "correct"
        st, body = _req(base, "POST", "/api/diagnose",
                        {"student": "t_http", "problem": "x^2-9", "steps": ["(x-3)^2"]})
        assert json.loads(body)["analysis"]["cause"] == "F-MIX-FORMULA"
    finally:
        httpd.shutdown()


def test_http_rejects_bad_input():
    httpd, base = _serve()
    try:
        assert _req(base, "POST", "/api/diagnose", {"student": "../x", "problem": "x", "steps": ["x"]})[0] == 400
        assert _req(base, "POST", "/api/diagnose", {"student": "a", "problem": "x", "steps": []})[0] == 400
        assert _req(base, "POST", "/api/diagnose", {"student": "a", "problem": "x", "steps": ["x"] * 99})[0] == 400
        assert _req(base, "GET", "/api/practice?cause=../../etc")[0] == 400
        assert _req(base, "GET", "/api/profile?student=../x")[0] == 400
        # 超大指数不能让 SymPy 卡死
        st, body = _req(base, "POST", "/api/diagnose",
                        {"student": "a", "problem": "x^2-9", "steps": ["(x-3)^99999999"]})
        assert json.loads(body)["ok"] is False
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", fn.__name__, repr(e))
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
