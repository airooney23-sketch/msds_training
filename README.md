# MSDS 교육영상 플랫폼 (1단계)

MSDS를 넣으면 약 1분짜리 교육영상(영어 음성 + 영·한 이중 자막)이 만들어지고,
누구나 휴대폰으로 볼 수 있는 사이트(GitHub Pages)에 자동 게시됩니다. 서버는 필요 없습니다.

```
현재 방식 (API 키 불필요)
MSDS PDF ──▶ [Claude 대화: 추출·원문 점검·검수·렌더] ──▶ data/ + videos/ 커밋 ──▶ build.yml ──▶ 공개 사이트 / QR
 claude.ai 프로젝트 "MSDS 교육영상"                                                 (자동)

나중 방식 (API 키 등록 시)
msds/ PDF ──▶ extract.yml(AI 추출) ──▶ 검수 PR ──▶ 승인·Merge ──▶ build.yml ──▶ 공개 사이트 / QR
```

원본 MSDS PDF와 검수 메모는 **공개 저장소에 올리지 않고** claude.ai 프로젝트에 보관합니다.

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `msds/` | (API 방식에서만) MSDS 원본 PDF — 현재는 사용 안 함 |
| `data/<id>.json` | 물질별 교육 데이터 (스크립트·그림문자·보호구). **승인본만 영상으로 만들어짐** |
| `assets/` | 공식 도안 아이콘 (GHS 그림문자, 별표6 안전보건표지, 일부 ISO 7010) |
| `renderer/` | 영상 렌더러 · 검증기 · 아이콘 대응표(`icons.json`) |
| `videos/` | 렌더된 영상·썸네일·자막(VTT). Actions가 자동 커밋 |
| `site/` | 공개 사이트 템플릿 (목록 · 영상 · QR 인쇄) |
| `prompts/extract.md` | AI 추출 지침 (별표5 6개 항목 구조, 원문 오류 점검 규칙) |
| `.github/workflows/` | `build.yml` 렌더·배포 / `extract.yml` AI 추출·검수요청 |

## 처음 설정 (한 번만)

1. GitHub에서 새 저장소를 만들고 이 폴더 전체를 올립니다. `.github` 폴더도 꼭 포함해야 합니다.
2. **Settings → Pages → Build and deployment → Source: `GitHub Actions`**
3. **Settings → Actions → General → Workflow permissions**
   - `Read and write permissions` 선택
   - `Allow GitHub Actions to create and approve pull requests` 체크 (AI 추출 검수요청용)
4. **Actions 탭 → `Build videos & site` → Run workflow**
   첫 실행은 음성 모델(약 350MB)을 받느라 몇 분 더 걸립니다.
5. 완료되면 사이트 주소: `https://<계정>.github.io/<저장소>/`

## 평소 사용

### 새 MSDS 추가 / 개정본 교체 — 현재 방식
1. claude.ai 프로젝트 "MSDS 교육영상"에서 새 대화를 열고 MSDS PDF를 첨부
2. Claude가 저장소를 불러와 추출·원문 점검 → 검수할 내용을 대화로 보여줌
3. 확인·수정 후 승인하면 Claude가 렌더해 `data/`·`videos/`에 커밋
4. 몇 분 뒤 사이트 자동 반영

### 새 MSDS 추가 / 개정본 교체 — API 방식 (키 등록 후)
1. `msds/` 폴더에 PDF 업로드 (개정본은 **같은 파일명**으로 덮어쓰기)
2. 몇 분 뒤 **Pull requests** 탭에 "MSDS 교육 데이터 초안"이 생깁니다
3. **Files changed**에서 원문과 대조 → 각 문장의 `src`가 출처 항목
4. `review.notes`의 지적사항(원문 오류, 검증 오류) 확인
5. `"status": "pending"` → `"approved"`, `reviewer`·`approved_at` 기입 후 커밋
6. **Merge** → 영상 자동 렌더 → 사이트 반영

개정본이면 3번 화면에서 이전 버전 대비 바뀐 문장이 줄 단위로 보입니다. Git 기록이 곧 개정·승인 이력입니다.

### API 키 등록
**Settings → Secrets and variables → Actions → New repository secret**
이름 `ANTHROPIC_API_KEY`, 값은 Anthropic Console에서 발급한 키. (claude.ai 구독과 별개, 사용량 과금)
모델을 바꾸려면 같은 화면 **Variables** 탭에 `CLAUDE_MODEL` 추가.

### QR
사이트 상단 **QR 인쇄** → 전체 물질 QR 라벨 시트. 물질 페이지의 **QR 인쇄**는 그 물질만.

## 로컬에서 실행 (선택)

```bash
pip install -r renderer/requirements.txt          # + ffmpeg, Noto CJK 폰트 필요
mkdir -p models && cd models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cd ..
python3 renderer/validate.py data/*.json           # 검증
python3 renderer/render.py                         # 바뀐 물질만 렌더 (--all: 전부)
python3 scripts/build_site.py                      # _site/ 생성
python3 -m http.server -d _site 8000               # http://localhost:8000
```

## 검증 규칙 (`renderer/validate.py`)
- 산안법 시행규칙 별표5 교육내용 6개 항목이 모두 있어야 렌더됨
- 그림문자·표지 키는 `renderer/icons.json`에 있는 것만 (공식 도안이 없는 GHS04 가스·GHS09 환경은 오류로 표시)
- 같은 그림문자 중복 금지, 자막 한 문장 26단어 이하, 예상 길이 80초 초과 시 경고

## 알아둘 점
- **공개 범위**: 무료 계정의 Pages 사이트는 인터넷에 공개됩니다. 공개 저장소에 올린 파일은 모두 공개되므로, 원본 PDF와 검수 메모는 저장소에 두지 않습니다.
  사이트에는 승인된 영상·요약만 올라가고 PDF와 검수 메모는 올라가지 않습니다.
  원본·메모를 숨기려면 비공개 저장소가 필요합니다(유료 플랜에서 비공개 저장소의 Pages 사용 가능 — 사이트 자체는 공개).
- **아이콘 출처**: 별표6 도안(법령 별표), ISO 7010 3종(M005·E012·F001 — ISO 저작물, 배포 전 라이선스 확인), GHS07은 트레이싱본(OSHA 원본 확보 시 `assets/ghs_GHS07.png` 교체).
- **음성**: Kokoro(오픈소스, 오프라인) 영어 음성 `af_heart`.
- **법적 기준**: 현재 템플릿은 한국 별표5 기준. 멕시코 NOM-018-STPS-2015는 HDS 16개 항목 전체와 표지 요소 교육을 요구하므로, 별도의 공통 모듈(16개 항목·표지 읽는 법)과 함께 운영해야 합니다.
