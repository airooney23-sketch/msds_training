"""정적 사이트 빌드: data/*.json + videos/ → _site/ (GitHub Pages가 그대로 배포)
- 승인(review.status == approved)되고 영상이 있는 물질만 공개
- 내부 검수 메모(review.notes), MSDS 원본 PDF는 공개 사이트에 넣지 않음
"""
import json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"

def cues_from_vtt(en_path, ko_path):
    def parse(p):
        blocks = p.read_text().split("\n\n")[1:]
        out = []
        for b in blocks:
            m = re.match(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.*)", b.strip(), re.S)
            if m:
                g = m.groups(); s = int(g[0]) * 3600 + int(g[1]) * 60 + float(g[2])
                e = int(g[3]) * 3600 + int(g[4]) * 60 + float(g[5]); out.append((s, e, g[6].strip()))
        return out
    return [{"start": s, "end": e, "en": t1, "ko": t2} for (s, e, t1), (_, _, t2) in zip(parse(en_path), parse(ko_path))]

def main():
    man = json.loads((ROOT / "videos/manifest.json").read_text())
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "videos").mkdir(parents=True); (OUT / "assets").mkdir()
    rows = []
    for p in sorted((ROOT / "data").glob("*.json")):
        m = json.loads(p.read_text()); vid = ROOT / "videos" / f"{m['id']}.mp4"
        if m.get("review", {}).get("status") != "approved" or not vid.exists() or m["id"] not in man:
            print("skip", m["id"]); continue
        for ext in (".mp4", ".jpg", ".en.vtt", ".ko.vtt"):
            shutil.copy(ROOT / "videos" / f"{m['id']}{ext}", OUT / "videos")
        rows.append({"id": m["id"], "name_en": m["name_en"], "name_ko": m["name_ko"], "cas": m["cas"],
                     "signal_word": m.get("signal_word", "Danger"), "pictograms": m["pictograms"],
                     "msds": {k: m["msds"].get(k, "") for k in ("supplier", "revision_date")},
                     "approved_at": m["review"].get("approved_at", ""), "duration": man[m["id"]]["duration"],
                     "cues": cues_from_vtt(ROOT / "videos" / f"{m['id']}.en.vtt", ROOT / "videos" / f"{m['id']}.ko.vtt")})
    shutil.copy(ROOT / "site/qrcode.js", OUT)
    ghs = {k: v["file"] for k, v in json.loads((ROOT / "renderer/icons.json").read_text())["ghs"].items()}
    for f in ghs.values(): shutil.copy(ROOT / "assets" / f"{f}.png", OUT / "assets")
    html = (ROOT / "site/template.html").read_text()
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")   # </script> 조기 종료 방지
    html = html.replace("/*__ICONS__*/{}", json.dumps(ghs))
    (OUT / "index.html").write_text(html.replace("/*__DATA__*/[]", data))
    (OUT / ".nojekyll").write_text("")   # GitHub Pages의 Jekyll 처리 끄기
    print(f"built {len(rows)} materials → {OUT}")

if __name__ == "__main__":
    main()
