"""MSDS 교육영상 렌더러 — data/*.json → videos/<id>.mp4

흐름: 문장별 Kokoro TTS(wav) → 문장별 슬라이드 PNG → ffmpeg 합성
- 문장 단위로 쪼개는 이유: 음성 길이를 정확히 알아 자막 싱크가 자동으로 맞음
- 증분 렌더: (JSON + 렌더러 + 아이콘) 해시가 바뀐 물질만 다시 만든다 → 물질 100개여도 변경분만 처리

사용:
  python renderer/render.py              # 바뀐 물질만
  python renderer/render.py --all        # 전부
  python renderer/render.py acetone      # 특정 물질
환경변수 KOKORO_DIR: kokoro-v1.0.onnx, voices-v1.0.bin 위치 (기본: models/)
"""
import io, os, sys, json, hashlib, subprocess, tempfile
from pathlib import Path
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA, ASSETS, OUT = ROOT / "data", ROOT / "assets", ROOT / "videos"
ITEMS = {int(k): (v["en"], v["ko"]) for k, v in json.loads((Path(__file__).parent / "items.json").read_text()).items()}

W, H = 1080, 1920                     # 세로형: 현장 QR → 휴대폰 시청 기준
SR, GAP, SPEED, VOICE = 24000, 0.28, 1.08, "af_heart"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-{}.ttc"
KR = 1                                # Noto CJK .ttc 인덱스 1 = 한국어
def F(w, size): return ImageFont.truetype(FONT.format(w), size, index=KR)

THEME = {"title": "#C8102E", "phys": "#E4572E", "health": "#C2410C", "handle": "#B45309",
         "ppe": "#1F5FA8", "aid": "#1A7F4B", "accident": "#B91C1C", "label": "#6D28D9", "msds": "#6D28D9"}
SIGNAL = {"Danger": ("DANGER", "위험", "#C8102E"), "Warning": ("WARNING", "경고", "#D97706")}

# ---------- 아이콘: 공식 도안만 사용 ----------
# 아이콘 대응표는 icons.json 한 곳에서 관리 (공식 도안만: 별표6 우선, 없는 것만 ISO 7010)
_IC = json.loads((Path(__file__).parent / "icons.json").read_text())
GHS = {k: v["file"] for k, v in _IC["ghs"].items()}
SIGN = {k: (v["file"], v["en"], v["ko"]) for k, v in _IC["signs"].items()}
DEFAULT_ICONS = {"handle": ["nofire", "nosmoke", "ground"], "aid": ["firstaid", "eyewash", "shower"],
                 "accident": ["extinguisher"]}

_cache = {}
def icon(name, size):
    key = (name, size)
    if key not in _cache:
        _cache[key] = Image.open(ASSETS / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
    return _cache[key]

# ---------- 그리기 유틸 ----------
def wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur]

def center(d, y, text, font, fill):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)

def row(img, d, names, y, size, gap=40, labels=None):
    x = (W - (len(names) * size + (len(names) - 1) * gap)) // 2
    for i, n in enumerate(names):
        img.alpha_composite(icon(n, size), (x, y))
        if labels:
            en, ko = labels[i]; fe, fk = F("Bold", 34), F("Regular", 32); cx = x + size / 2
            d.text((cx - d.textlength(en, font=fe) / 2, y + size + 18), en, font=fe, fill="#111827")
            d.text((cx - d.textlength(ko, font=fk) / 2, y + size + 62), ko, font=fk, fill="#4B5563")
        x += size + gap

def sign_row(img, d, keys, y, size, gap):
    row(img, d, [SIGN[k][0] for k in keys], y, size, gap, labels=[SIGN[k][1:] for k in keys])

# ---------- 항목 6: 경고표지 견본 / MSDS 16개 항목 ----------
def label_mock(img, d, m, y0):
    L = m["label"]; x0, x1 = 70, W - 70
    s_en, s_ko, s_col = SIGNAL[m.get("signal_word", "Danger")]
    d.rounded_rectangle([x0, y0, x1, y0 + 760], 20, fill="#fff", outline="#111827", width=6)
    rows = [("제품명", "Product"), ("그림문자", "Pictogram"), ("신호어", "Signal word"),
            ("유해·위험문구", "Hazard stmt"), ("예방조치문구", "Precaution"), ("공급자", "Supplier")]
    y = y0 + 22
    for i, (ko, en) in enumerate(rows):
        h = 150 if i == 1 else 102
        d.rounded_rectangle([x0 + 20, y + 8, x0 + 250, y + 78], 14, fill="#6D28D9")
        d.text((x0 + 36, y + 12), ko, font=F("Bold", 30), fill="#fff")
        d.text((x0 + 36, y + 46), en, font=F("Regular", 22), fill="#E9D5FF")
        cx = x0 + 275
        if i == 0:
            t, sz = f'{m["name_en"].split(" (")[0].upper()}  {m["name_ko"]}', 40
            while d.textlength(t, font=F("Black", sz)) > x1 - cx - 20: sz -= 2   # 칸 폭에 맞춰 자동 축소
            d.text((cx, y + 14 + (40 - sz) / 2), t, font=F("Black", sz), fill="#111827")
        if i == 1:
            for j, p in enumerate(L["pictos"]): img.alpha_composite(icon(GHS[p], 136), (cx + j * 146, y))
        if i == 2: d.text((cx, y + 10), f"{s_en}  {s_ko}", font=F("Black", 48), fill=s_col)
        if i >= 3:
            t, sz = L[["h", "p", "sup"][i - 3]], 29
            while d.textlength(t, font=F("Medium", sz)) > x1 - cx - 20: sz -= 1
            d.text((cx, y + 22), t, font=F("Medium", sz), fill="#111827" if i < 5 else "#374151")
        y += h
        if i < 5: d.line([x0 + 20, y - 6, x1 - 20, y - 6], fill="#E5E7EB", width=2)

MSDS16 = ["제품정보", "유해성·위험성", "구성성분", "응급조치", "화재 대처", "누출 대처", "취급·저장", "노출방지·보호구",
          "물리화학 특성", "안정성·반응성", "독성", "환경 영향", "폐기", "운송", "법적 규제", "기타"]
KEY16 = {2, 4, 5, 6, 7, 8}   # 작업자가 꼭 볼 항목

def msds_grid(d, y0):
    bw, bh, gap = 225, 150, 14; x0 = (W - (4 * bw + 3 * gap)) // 2
    for i, name in enumerate(MSDS16):
        r, c = divmod(i, 4); x, y = x0 + c * (bw + gap), y0 + r * (bh + gap); key = (i + 1) in KEY16
        d.rounded_rectangle([x, y, x + bw, y + bh], 16, fill="#6D28D9" if key else "#E5E7EB")
        d.text((x + 16, y + 10), str(i + 1), font=F("Black", 44), fill="#fff" if key else "#9CA3AF")
        d.text((x + 16, y + 92), name, font=F("Bold", 28 if len(name) <= 6 else 24), fill="#fff" if key else "#4B5563")

# ---------- 프레임 1장 ----------
def frame(m, sec, line, progress):
    img = Image.new("RGBA", (W, H), "#F7F7F5"); d = ImageDraw.Draw(img)
    k, item = sec["kind"], sec["item"]; color = THEME[k]

    d.rectangle([0, 0, W, 150], fill="#111827")
    d.text((48, 26), "MSDS SAFETY BRIEFING · 물질안전보건자료 교육", font=F("Medium", 28), fill="#9CA3AF")
    d.text((48, 66), f'{m["name_en"]}  {m["name_ko"]}', font=F("Bold", 44), fill="#fff")
    d.rectangle([0, 144, W, 150], fill="#374151"); d.rectangle([0, 144, int(W * progress), 150], fill=color)

    for n in range(1, 7):   # 교육항목 1~6 표시줄 (별표5 대응, 감사 증빙용)
        x, on = 48 + (n - 1) * 164, n == item
        d.rounded_rectangle([x, 176, x + 150, 214], 19, fill=color if on else "#E5E7EB")
        t = f"항목 {n}"; d.text((x + (150 - d.textlength(t, font=F("Bold", 24))) / 2, 180), t, font=F("Bold", 24),
                               fill="#fff" if on else "#9CA3AF")

    en, ko = ITEMS[1] if k == "title" else ((sec["en"], sec["ko"]) if "en" in sec else ITEMS[item])
    d.rounded_rectangle([48, 236, W - 48, 396], 24, fill=color)
    d.ellipse([72, 262, 180, 370], fill="#fff")
    d.text((126 - d.textlength(str(item), font=F("Black", 70)) / 2, 262), str(item), font=F("Black", 70), fill=color)
    d.text((204, 250), en, font=F("Black", 60 if len(en) < 20 else 50), fill="#fff")
    d.text((206, 330), ko, font=F("Medium", 40), fill="#ffffffdd")

    if k == "title":
        nm = m["name_en"].split(" (")[0]
        center(d, 450, nm, F("Black", 92 if len(nm) < 12 else 76), "#111827")
        center(d, 570, m["name_ko"], F("Bold", 56), "#374151")
        center(d, 650, f'CAS No. {m["cas"]}', F("Medium", 40), "#6B7280")
        ps = m["pictograms"]; row(img, d, [GHS[p] for p in ps], 740, 230 if len(ps) < 3 else 210, gap=20)
        s_en, s_ko, s_col = SIGNAL[m.get("signal_word", "Danger")]
        d.rounded_rectangle([(W - 520) / 2, 1010, (W + 520) / 2, 1120], 18, fill=s_col)
        center(d, 1024, f"{s_en} · {s_ko}", F("Black", 64), "#fff")
    elif k in ("phys", "health"):
        row(img, d, [GHS[sec["picto"]]], 470, 420)
    elif k == "ppe":
        n = len(sec["ppe"]); sign_row(img, d, sec["ppe"], 560, 215 if n <= 4 else 178, 28 if n <= 4 else 18)
    elif k in DEFAULT_ICONS:
        keys = sec.get("icons", DEFAULT_ICONS[k])
        size = {1: 340, 2: 300, 3: 280}.get(len(keys), 230)
        sign_row(img, d, keys, 500, size, 55)
    elif k == "label":
        label_mock(img, d, m, 440)
    elif k == "msds":
        center(d, 430, "MSDS = 16 sections · 16개 항목", F("Black", 44), "#111827"); msds_grid(d, 510)

    if sec.get("fact"):
        fy = 1050 if k in DEFAULT_ICONS else 1010
        center(d, fy, sec["fact"]["en"], F("Black", 56), "#111827")
        center(d, fy + 80, sec["fact"]["ko"], F("Bold", 44), color)

    # 이중 자막 (영어 흰색 / 한국어 노랑)
    d.rounded_rectangle([40, 1250, W - 40, 1800], 32, fill="#111827")
    fe, fk = F("Bold", 50), F("Medium", 46)
    el, kl = wrap(d, line["en"], fe, W - 160), wrap(d, line["ko"], fk, W - 160)
    y = 1250 + (550 - (len(el) * 66 + 30 + len(kl) * 62)) / 2
    for l in el: center(d, y, l, fe, "#FFFFFF"); y += 66
    y += 30
    for l in kl: center(d, y, l, fk, "#FDE047"); y += 62
    center(d, 1846, m["source_line"], F("Regular", 26), "#6B7280")
    return img.convert("RGB")

# ---------- 증분 판단 ----------
def fingerprint(path):
    """물질 JSON + 렌더러 코드 + 아이콘이 하나라도 바뀌면 해시가 바뀐다."""
    h = hashlib.sha256(path.read_bytes())
    for f in sorted(Path(__file__).parent.glob("*")) + sorted(ASSETS.glob("*.png")):
        if f.is_file(): h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:16]

def vtt(cues, lang):
    ts = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"
    return "WEBVTT\n\n" + "\n".join(f"{ts(c['start'])} --> {ts(c['end'])}\n{c[lang]}\n" for c in cues)

# ---------- 물질 1개 렌더 ----------
def build(path, tts):
    m = json.loads(path.read_text())
    from validate import validate                       # 별표5 6개 항목 누락 등 → 렌더 차단
    errs = validate(m)
    if errs: raise SystemExit(f"{m['id']}: 검증 실패\n  - " + "\n  - ".join(errs))
    if m.get("review", {}).get("status") != "approved":
        print(f"skip {m['id']}: 검수 승인 전 (review.status != approved)"); return None
    lines = [(s, l) for s in m["sections"] for l in s["lines"]]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); audio, concat, cues, t = [], [], [], 0.0
        for i, (sec, line) in enumerate(lines):
            wav, _ = tts.create(line.get("tts", line["en"]), voice=VOICE, speed=SPEED, lang="en-us")
            wav = np.concatenate([wav, np.zeros(int(SR * GAP), dtype=wav.dtype)]); dur = len(wav) / SR
            audio.append(wav)
            png = tmp / f"f{i:02d}.png"; frame(m, sec, line, (i + 1) / len(lines)).save(png)
            if i == 0: frame(m, sec, line, 0).resize((540, 960)).save(OUT / f"{m['id']}.jpg", quality=85)  # 썸네일
            concat.append(f"file '{png}'\nduration {dur:.3f}")
            cues.append({"start": round(t, 2), "end": round(t + dur, 2), "en": line["en"], "ko": line["ko"]}); t += dur
        concat.append(f"file '{tmp / f'f{len(lines) - 1:02d}.png'}'")   # concat 데모먹서는 마지막 프레임을 한 번 더 적어야 함
        (tmp / "list.txt").write_text("\n".join(concat)); sf.write(tmp / "v.wav", np.concatenate(audio), SR)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", tmp / "list.txt",
                        "-i", tmp / "v.wav", "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "23", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-shortest",
                        OUT / f"{m['id']}.mp4"], check=True)   # faststart: 웹에서 다운로드 완료 전 재생 시작
    for lang in ("en", "ko"): (OUT / f"{m['id']}.{lang}.vtt").write_text(vtt(cues, lang))
    print(f"rendered {m['id']}: {t:.1f}s")
    return round(t, 1)

def main():
    args = sys.argv[1:]; OUT.mkdir(exist_ok=True)
    man_path = OUT / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {}
    targets = [DATA / f"{a}.json" for a in args if a != "--all"] or sorted(DATA.glob("*.json"))
    todo = [p for p in targets if "--all" in args or args and p.stem in args
            or man.get(p.stem, {}).get("hash") != fingerprint(p) or not (OUT / f"{p.stem}.mp4").exists()]
    for gone in set(man) - {p.stem for p in DATA.glob("*.json")}:   # 삭제된 물질 정리
        man.pop(gone); [f.unlink() for f in OUT.glob(f"{gone}.*")]
    if todo:
        from kokoro_onnx import Kokoro
        kd = Path(os.environ.get("KOKORO_DIR", ROOT / "models"))
        tts = Kokoro(str(kd / "kokoro-v1.0.onnx"), str(kd / "voices-v1.0.bin"))
        for p in todo:
            dur = build(p, tts)
            if dur: man[p.stem] = {"hash": fingerprint(p), "duration": dur}
    else:
        print("변경된 물질 없음")
    man_path.write_text(json.dumps(man, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
