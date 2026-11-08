# 피자 매장 인사이트 — 30초 모션 그래픽

피자 프랜차이즈 9개 매장의 2020–2026 월별 실적(가상 데이터)을 분석해 뽑은 시사점 3가지를
흰 배경 · 도화지 · 포스트잇 스타일의 키네틱 타이포그래피 영상(30초, 한국어 내레이션)으로 만들었습니다.

- 영상: [`pizza-insights-30s.mp4`](pizza-insights-30s.mp4)
- 보기 페이지: [`index.html`](index.html)

## 시사점
1. **손님이 멈췄다** — 2022→2025 주문 -1.4%, 주문당 매출 +19%
2. **이익을 깎은 건 인건비** — 이익률 -1.2%p ≈ 인건비율 +1.7%p, 인당 인건비 +28%
3. **처방은 매장마다 다르다** — 강남·홍대는 임차료, 충장로·연동은 원가 관리

## 다시 만들기 (Windows)
```bash
pip install pillow numpy imageio-ffmpeg
python motion/render.py
```
- 그림·애니메이션·효과음은 모두 코드(Pillow, NumPy)로 생성합니다.
- 음성은 Windows 내장 TTS(Microsoft Heami)로 만든 `motion/assets/v*.wav`를 씁니다.
  `words.tsv`는 음성 엔진의 단어 경계 정보로, 글자가 말과 같은 시점에 나타나도록 맞추는 데 씁니다.
- 글꼴: 맑은 고딕(`C:/Windows/Fonts/malgun*.ttf`)
