"""교육영상 데이터 검증 — 렌더 전, AI 추출 직후 모두 이 함수를 통과해야 한다.

오류(errors)는 렌더를 막고, 경고(warnings)는 검수자에게 보여준다.
사용: python renderer/validate.py data/*.json
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
IC = json.loads((HERE / "icons.json").read_text())
GHS, SIGNS = set(IC["ghs"]), set(IC["signs"])
KINDS = {"title": 1, "phys": 2, "health": 2, "handle": 3, "ppe": 4, "aid": 5, "accident": 5, "label": 6, "msds": 6}
REQUIRED_ITEMS = {1, 2, 3, 4, 5, 6}          # 산안법 시행규칙 별표5 MSDS 교육내용 6개 항목
MAX_WORDS_LINE = 26                          # 자막 박스에 4줄 이내로 들어가는 영어 단어 수
WORDS_PER_SEC = 2.6                          # Kokoro 속도 1.08 기준 실측치

def validate(m, warnings=None):
    e, w = [], warnings if warnings is not None else []
    for f in ("id", "name_en", "name_ko", "cas", "signal_word", "pictograms", "label", "source_line", "sections"):
        if not m.get(f): e.append(f"필수 필드 누락: {f}")
    if e: return e
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", m["id"]): e.append(f"id는 영문 소문자·숫자·하이픈만: {m['id']}")
    if m["signal_word"] not in ("Danger", "Warning"): e.append(f"신호어는 Danger/Warning: {m['signal_word']}")
    for p in m["pictograms"]:
        if p in IC["ghs_missing"]: e.append(f"그림문자 자산 없음: {IC['ghs_missing'][p]} — assets에 공식 도안 추가 필요")
        elif p not in GHS: e.append(f"알 수 없는 그림문자: {p}")
    if len(set(m["pictograms"])) != len(m["pictograms"]): e.append("같은 그림문자가 중복됨 (GHS: 라벨에 1회만)")
    for f in ("pictos", "h", "p", "sup"):
        if not m["label"].get(f): e.append(f"label.{f} 누락")
    if m.get("review", {}).get("status") not in ("pending", "approved", "rejected"):
        e.append("review.status는 pending/approved/rejected 중 하나")

    items, words = set(), 0
    for i, s in enumerate(m["sections"]):
        k = s.get("kind")
        if k not in KINDS: e.append(f"섹션 {i}: 알 수 없는 kind '{k}'"); continue
        if s.get("item") != KINDS[k]: e.append(f"섹션 {i} ({k}): item은 {KINDS[k]}이어야 함")
        items.add(s.get("item"))
        if k in ("phys", "health") and s.get("picto") not in GHS: e.append(f"섹션 {i} ({k}): picto 누락/오류")
        if k in ("phys", "health") and s.get("picto") not in m["pictograms"]:
            w.append(f"섹션 {i}: 화면 그림문자 '{s.get('picto')}'가 물질 그림문자 목록에 없음")
        if k == "ppe":
            bad = [p for p in s.get("ppe", []) if p not in SIGNS]
            if not s.get("ppe") or bad: e.append(f"섹션 {i} (ppe): 보호구 키 누락/오류 {bad}")
        for x in s.get("icons", []):
            if x not in SIGNS: e.append(f"섹션 {i}: 알 수 없는 표지 '{x}'")
        if not s.get("lines"): e.append(f"섹션 {i} ({k}): 문장 없음")
        for j, l in enumerate(s.get("lines", [])):
            if not l.get("en") or not l.get("ko"): e.append(f"섹션 {i} 문장 {j}: en/ko 누락")
            n = len(l.get("en", "").split()); words += n
            if n > MAX_WORDS_LINE: e.append(f"섹션 {i} 문장 {j}: {n}단어 — 자막 넘침, {MAX_WORDS_LINE}단어 이하로")
    if m["sections"] and m["sections"][0].get("kind") != "title": e.append("첫 섹션은 title이어야 함")
    missing = REQUIRED_ITEMS - items
    if missing: e.append(f"별표5 필수 교육항목 누락: {sorted(missing)}")
    est = words / WORDS_PER_SEC + 0.28 * sum(len(s.get("lines", [])) for s in m["sections"])
    if est > 80: w.append(f"예상 길이 {est:.0f}초 — 80초 초과, 문장 축약 검토")
    return e

if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        warn = []; errs = validate(json.loads(Path(p).read_text()), warn)
        print(("❌ " if errs else "✅ ") + p)
        for x in errs: print("   오류:", x)
        for x in warn: print("   경고:", x)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
