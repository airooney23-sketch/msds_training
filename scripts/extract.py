"""MSDS PDF → 교육영상 데이터 초안(data/<id>.json, review.status = pending)

Claude API에 PDF를 그대로 보낸다(텍스트 추출기를 거치지 않으므로 한글 폰트가 깨진 PDF도 처리 가능).
결과는 검증(renderer/validate.py)을 거쳐 저장되고, 오류·경고는 review.notes 맨 앞에 붙는다.

사용: ANTHROPIC_API_KEY=... python scripts/extract.py msds/acetone.pdf [msds/....pdf ...]
환경변수 CLAUDE_MODEL (기본 claude-sonnet-5-5)
"""
import base64, json, os, re, sys
from pathlib import Path
import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "renderer"))
from validate import validate, IC  # noqa: E402

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

def build_prompt():
    example = json.loads((ROOT / "data/acetone.json").read_text())
    example["review"]["notes"] = example["review"]["notes"][:2]
    return ((ROOT / "prompts/extract.md").read_text()
            .replace("{GHS_KEYS}", ", ".join(f"`{k}` ({v['code']})" for k, v in IC["ghs"].items()) + ", `gas`, `environment`")
            .replace("{SIGN_KEYS}", ", ".join(f"`{k}`" for k in IC["signs"]))
            .replace("{EXAMPLE}", json.dumps(example, ensure_ascii=False, indent=1)))

def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)          # 혹시 코드펜스나 설명이 붙어도 JSON 본문만
    if not m: raise ValueError("응답에 JSON이 없습니다")
    return json.loads(m.group(0))

def extract(pdf: Path, client, prompt):
    data = base64.standard_b64encode(pdf.read_bytes()).decode()
    msg = client.messages.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": prompt}]}])          # PDF를 텍스트보다 앞에 두는 것이 권장 순서
    m = parse_json("".join(b.text for b in msg.content if b.type == "text"))
    m["msds"]["file"] = str(pdf.relative_to(ROOT))
    m["review"] = {**m.get("review", {}), "status": "pending", "reviewer": "", "approved_at": ""}
    warn = []; errs = validate(m, warn)
    m["review"]["notes"] = [f"[검증 오류] {x}" for x in errs] + [f"[검증 경고] {x}" for x in warn] + m["review"].get("notes", [])
    return m, errs

def main():
    pdfs = [Path(p).resolve() for p in sys.argv[1:]]
    if not pdfs: sys.exit("사용법: python scripts/extract.py <pdf> [...]")
    client, prompt = anthropic.Anthropic(), build_prompt()
    summary = []
    for pdf in pdfs:
        m, errs = extract(pdf, client, prompt)
        out = ROOT / "data" / f"{m['id']}.json"
        out.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
        summary.append(f"- `{out.name}` ← `{pdf.name}` " + ("❌ 검증 오류 " + str(len(errs)) + "건" if errs else "✅ 검증 통과"))
        print(summary[-1])
    Path(os.environ.get("SUMMARY_FILE", "/dev/null")).write_text("\n".join(summary))

if __name__ == "__main__":
    main()
