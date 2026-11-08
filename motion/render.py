# -*- coding: utf-8 -*-
"""30초 키네틱 타이포그래피 모션 그래픽 (흰 배경 + 도화지 + 포스트잇).
코드만으로 그림/애니메이션/효과음을 만들고, Windows 내장 TTS(Heami) 음성을 합쳐 MP4로 내보낸다.

사용: python render.py [--preview t1,t2,...]
"""
import os, sys, math, wave, subprocess
import numpy as np
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET = os.path.join(HERE, 'assets')
FRAMES = os.environ.get('MG_FRAMES', os.path.join(HERE, '_frames'))
OUTFILE = os.path.join(os.path.dirname(HERE), 'pizza-insights-30s.mp4')

W, H = 2880, 1620          # 월드(작업) 해상도: 출력의 1.5배 → 줌인해도 선명
OW, OH = 1920, 1080
FPS, DUR = 30, 30.0
BOLD = 'C:/Windows/Fonts/malgunbd.ttf'
REG = 'C:/Windows/Fonts/malgun.ttf'

INK = (30, 30, 30, 255)
GRAY = (95, 95, 95, 255)
RED = (214, 40, 40, 255)
ORANGE = (232, 93, 4, 255)
TEAL = (22, 128, 110, 255)
BLUE = (29, 78, 216, 255)

# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def eoc(x):  # ease-out cubic
    x = clamp(x); return 1 - (1 - x) ** 3

def eio(x):  # ease-in-out cubic
    x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2

def eob(x, s=1.9):  # ease-out back (overshoot)
    x = clamp(x) - 1; return 1 + (s + 1) * x ** 3 + s * x ** 2

def prog(t, t0, d):
    return clamp((t - t0) / d)

# ---------------------------------------------------------------- voice & timing
def read_wav(p):
    w = wave.open(p)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return x, sr

VO = []
for i in range(6):
    x, sr = read_wav(os.path.join(ASSET, f'v{i}.wav'))
    idx = np.where(np.abs(x) > 500 / 32768)[0]
    VO.append(dict(x=x, sr=sr, s=idx[0] / sr, e=idx[-1] / sr))

S = []
_t = 0.3
for v in VO:
    S.append(float(_t))
    _t += float(v['e'] - v['s']) + 0.42
for i, v in enumerate(VO):
    v['start'] = S[i]

# SAPI 단어 경계 이벤트(말하기 속도 보정 전 시간축)를 실제 음성 길이에 맞춰 선형 보정
WD = {}
_rows = [l.split('\t') for l in open(os.path.join(ASSET, 'words.tsv'), encoding='utf-8').read().splitlines() if l.strip()]
for li in range(6):
    lst = [(float(r[2]) / 1000, r[3]) for r in _rows if int(r[0]) == li]
    ev0 = lst[0][0]
    last_pos, last_txt = lst[-1]
    k = (VO[li]['e'] - VO[li]['s']) / (last_pos - ev0 + 0.26 * len(last_txt))
    for pos, txt in lst:
        WD[(li, txt)] = float(S[li] + (pos - ev0) * k)

def T(li, w):
    return WD[(li, w)]

# ---------------------------------------------------------------- drawing helpers
@lru_cache(None)
def F(path, size):
    return ImageFont.truetype(path, size)

@lru_cache(None)
def timg(text, path, size, color):
    f = F(path, size)
    asc, desc = f.getmetrics()
    w = int(math.ceil(f.getlength(text)))
    p = int(size * 0.25)
    im = Image.new('RGBA', (w + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((p, p), text, font=f, fill=color, anchor='la')
    return im, p, asc

def comp(dst, src, x, y, alpha=1.0):
    if alpha <= 0:
        return
    x, y = int(round(x)), int(round(y))
    if alpha < 1:
        src = src.copy()
        src.putalpha(src.getchannel('A').point(lambda v: int(v * alpha)))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (0, 0, src.width, src.height):
        src = src.crop((sx0, sy0, sx1, sy1))
    dst.alpha_composite(src, (x + sx0, y + sy0))


class Word:
    """한 단어(또는 글자)의 키네틱 등장. (x, y) = 왼쪽 기준선."""
    def __init__(self, t0, text, x, y, size, color=INK, font=BOLD, style='pop', dur=None, block=RED):
        self.t0, self.text, self.x, self.y = t0, text, x, y
        self.size, self.color, self.font, self.style = size, color, font, style
        self.dur = dur if dur is not None else {'block': 0.6, 'wipe': 0.4}.get(style, 0.45)
        self.block = block

    @property
    def width(self):
        return F(self.font, self.size).getlength(self.text)

    def cur_text(self, t):
        return self.text

    def draw(self, L, t):
        p = prog(t, self.t0, self.dur)
        if p <= 0:
            return
        im, pad, asc = timg(self.cur_text(t), self.font, self.size, self.color)
        ox, oy = self.x - pad, self.y - asc - pad
        if p >= 1:
            comp(L, im, ox, oy)
            return
        if self.style == 'wipe':          # 클리핑 마스크: 왼쪽부터 글자가 드러남
            cw = int(im.width * eoc(p))
            if cw > 0:
                comp(L, im.crop((0, 0, cw, im.height)), ox, oy - (1 - eoc(p)) * self.size * 0.12)
            return
        if self.style == 'block':         # 색 블록이 덮었다가 걷히며 글자가 드러남
            x0 = ox + pad * 0.6
            x1 = ox + im.width - pad * 0.6
            y0 = oy + pad + self.size * 0.12
            y1 = oy + pad + asc + self.size * 0.05
            bw = x1 - x0
            if p < 0.5:
                bx0, bx1 = x0, x0 + bw * eio(p / 0.5)
            else:
                q = eio((p - 0.5) / 0.5)
                bx0, bx1 = x0 + bw * q, x1
                cw = int(bx0 - ox)
                if cw > 0:
                    comp(L, im.crop((0, 0, min(cw, im.width), im.height)), ox, oy)
            if bx1 > bx0:
                ImageDraw.Draw(L).rectangle((bx0, y0, bx1, y1), fill=self.block)
            return
        sc, a, dx, dy, rot = 1.0, clamp(p * 3), 0.0, 0.0, 0.0
        if self.style == 'pop':
            sc = 0.3 + 0.7 * eob(p)
            dy = (1 - eoc(p)) * self.size * 0.35
            rot = (1 - eoc(p)) * 8
        elif self.style == 'drop':
            a = clamp(p * 5)
            dy = -(1 - eob(p, 2.6)) * self.size * 0.9
        elif self.style == 'slide':
            dx = -(1 - eoc(p)) * self.size * 1.2
            a = clamp(p * 2)
        elif self.style == 'stamp':
            sc = 1 + 1.4 * (1 - eoc(p))
            a = clamp(p * 4)
        im2 = im
        if sc != 1:
            im2 = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC)
        if rot:
            im2 = im2.rotate(rot, resample=Image.BICUBIC, expand=True)
        cx, cy = ox + im.width / 2 + dx, oy + im.height / 2 + dy
        comp(L, im2, cx - im2.width / 2, cy - im2.height / 2, a)


class Counter(Word):
    """숫자가 0에서 목표값까지 올라가는 단어."""
    def __init__(self, t0, x, y, size, target, fmt, cdur=0.7, **kw):
        super().__init__(t0, fmt(target), x, y, size, **kw)
        self.target, self.fmt, self.cdur = target, fmt, cdur

    def cur_text(self, t):
        return self.fmt(self.target * eoc(prog(t, self.t0, self.cdur)))


def line_words(specs, x, y, gap=0.3):
    """specs: (t0, text, size, color, font, style). 왼쪽→오른쪽 배치."""
    out = []
    for t0, text, size, color, font, style in specs:
        w = Word(t0, text, x, y, size, color, font, style)
        out.append(w)
        x += w.width + size * gap
    return out


def chars(t0, text, x, y, size, color=INK, font=BOLD, stagger=0.07, style='drop'):
    f = F(font, size)
    return [Word(t0 + i * stagger, ch, x + f.getlength(text[:i]), y, size, color, font, style)
            for i, ch in enumerate(text) if ch != ' ']


class Marker:
    """마커 펜으로 선을 그려 나가는 효과."""
    def __init__(self, t0, dur, pts, width, color):
        self.t0, self.dur, self.pts, self.w, self.color = t0, dur, pts, width, color
        seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        self.cum = np.concatenate([[0], np.cumsum(seg)])

    def draw(self, L, t):
        p = eio(prog(t, self.t0, self.dur))
        if p <= 0:
            return
        target = p * self.cum[-1]
        part = [self.pts[0]]
        for i in range(1, len(self.pts)):
            if self.cum[i] <= target:
                part.append(self.pts[i])
            else:
                a = (target - self.cum[i - 1]) / max(1e-6, self.cum[i] - self.cum[i - 1])
                p0, p1 = self.pts[i - 1], self.pts[i]
                part.append((p0[0] + (p1[0] - p0[0]) * a, p0[1] + (p1[1] - p0[1]) * a))
                break
        d = ImageDraw.Draw(L)
        if len(part) > 1:
            d.line(part, fill=self.color, width=self.w, joint='curve')
        r = self.w / 2
        for (px, py) in (part[0], part[-1]):
            d.ellipse((px - r, py - r, px + r, py + r), fill=self.color)


def ellipse_pts(cx, cy, rx, ry, tilt=-0.1, seed=0.0, n=120):
    pts = []
    start, sweep = -2.1, 2 * math.pi * 1.1
    for i in range(n + 1):
        u = i / n
        a = start + sweep * u
        r = 1 + 0.035 * math.sin(3 * a + seed) + 0.06 * u
        x, y = rx * r * math.cos(a), ry * r * math.sin(a)
        pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt)))
    return pts


def swoosh_pts(x0, x1, y, amp=10, n=40):
    return [(x0 + (x1 - x0) * u, y + amp * math.sin(math.pi * u) - 14 * u * u) for u in (i / n for i in range(n + 1))]


def arrow(t0, x0, x1, y, color, width=9):
    return [Marker(t0, 0.25, [(x0, y), (x1, y)], width, color),
            Marker(t0 + 0.22, 0.12, [(x1 - 26, y - 22), (x1, y)], width, color),
            Marker(t0 + 0.30, 0.12, [(x1 - 26, y + 22), (x1, y)], width, color)]


class Tri:
    def __init__(self, t0, cx, cy, size, up, color):
        self.t0, self.cx, self.cy, self.s, self.up, self.color = t0, cx, cy, size, up, color

    def draw(self, L, t):
        p = prog(t, self.t0, 0.35)
        if p <= 0:
            return
        s = self.s * eob(p) / 2
        d = 1 if self.up else -1
        pts = [(self.cx, self.cy - d * s), (self.cx - s, self.cy + d * s * 0.8), (self.cx + s, self.cy + d * s * 0.8)]
        ImageDraw.Draw(L).polygon(pts, fill=self.color)


# ---------------------------------------------------------------- surfaces
_rng = np.random.default_rng(7)

def note_surface(w, h, color):
    c = np.array(color, np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    shade = 1 - 0.07 * (yy / h) - 0.025 * (xx / w)
    shade[yy < h * 0.15] *= 0.972                      # 접착띠
    d = (xx / w + yy / h) - 1.80                         # 오른쪽 아래 말림
    shade *= 1 - 0.11 * np.clip(d / 0.2, 0, 1)
    noise = _rng.normal(0, 1.3, (h, w)).astype(np.float32)
    rgb = np.clip(c[None, None, :] * shade[..., None] + noise[..., None], 0, 255).astype(np.uint8)
    a = np.full((h, w, 1), 255, np.uint8)
    return Image.fromarray(np.concatenate([rgb, a], 2), 'RGBA')


def paper_surface(w, h):
    base = np.array([251, 249, 243], np.float32)
    n = Image.fromarray((_rng.normal(128, 40, (h // 2, w // 2))).clip(0, 255).astype(np.uint8))
    n = np.asarray(n.filter(ImageFilter.GaussianBlur(1.2)).resize((w, h)), np.float32) - 128
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum.reduce([xx, yy, w - xx, h - yy])
    vign = 1 - 0.025 * np.exp(-edge / 40)
    rgb = np.clip(base[None, None] * vign[..., None] + n[..., None] * 0.08, 0, 255).astype(np.uint8)
    return Image.fromarray(np.concatenate([rgb, np.full((h, w, 1), 255, np.uint8)], 2), 'RGBA')


def tape_img(w=310, h=80):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    zig = 8
    top = [(zig, 0), (w - zig, 0)]
    right = [(w - (zig if i % 2 else 0), h * i / 8) for i in range(9)]
    bottom = [(w - zig, h), (zig, h)]
    left = [((0 if i % 2 else zig), h - h * i / 8) for i in range(9)]
    ImageDraw.Draw(im).polygon(top + right + bottom + left, fill=(234, 224, 198, 205))
    return im


def soft_shadow(alpha_img, opacity, blur, pad):
    sh = Image.new('RGBA', (alpha_img.width + 2 * pad, alpha_img.height + 2 * pad), (40, 30, 10, 0))
    a = Image.new('L', sh.size, 0)
    a.paste(alpha_img.point(lambda v: int(v * opacity)), (pad, pad))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(blur)))
    return sh


class Note:
    """포스트잇: 붙는 순간 '탁' 하고 눌리는 애니메이션 + 내부 키네틱 텍스트."""
    def __init__(self, cx, cy, w, h, color, rot, t0, items):
        self.cx, self.cy, self.w, self.h, self.rot, self.t0 = cx, cy, w, h, rot, t0
        self.items = items
        self.base = note_surface(w, h, color)
        self._shadow = None

    def land_time(self):
        return self.t0 + 0.30

    def pose(self, t):
        """(dx, dy, 배율, 추가 회전, 들림 0~1). 기본은 제자리."""
        return 0.0, 0.0, 1.0, 0.0, 0.0

    def draw(self, world, t):
        p = prog(t, self.t0, 0.42)
        if p <= 0:
            return
        e = eoc(p)
        pdx, pdy, psc, prot, plift = self.pose(t)
        sc = (1 + 0.34 * (1 - e)) * psc
        if p > 0.6:
            sc *= 1 - 0.025 * math.sin(math.pi * (p - 0.6) / 0.4)
        rot = self.rot + 10 * (1 - e) + prot
        a = clamp(p * 5)
        im = self.base.copy()
        for it in self.items:
            it.draw(im, t)
        if sc != 1:
            im = im.resize((max(1, int(self.w * sc)), max(1, int(self.h * sc))), Image.BICUBIC)
        r = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        lift = max(1 - e, plift)
        pad = 70
        key = (round(sc, 4), round(rot, 3))
        if p >= 1 and plift == 0:
            if self._shadow is None or self._shadow[0] != key:
                self._shadow = (key, soft_shadow(r.getchannel('A'), 0.30, 11, pad))
            sh = self._shadow[1]
        else:
            sh = soft_shadow(r.getchannel('A'), 0.30 * a * (1 - 0.4 * lift), 11 + 26 * lift, pad)
        ox, oy = self.cx + pdx - r.width / 2, self.cy + pdy - r.height / 2
        comp(world, sh, ox - pad + 7 + 18 * lift, oy - pad + 15 + 50 * lift)
        comp(world, r, ox, oy, a)


def newsprint_surface(w, h):
    """신문 스크랩: 누런 신문지 + 찢긴 가장자리 + 제호와 본문 줄."""
    base = np.array([240, 236, 224], np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    shade = 1 - 0.035 * (yy / h) - 0.02 * (xx / w)
    noise = _rng.normal(0, 3.0, (h, w)).astype(np.float32)
    rgb = np.clip(base[None, None] * shade[..., None] + noise[..., None], 0, 255).astype(np.uint8)
    im = Image.fromarray(np.concatenate([rgb, np.full((h, w, 1), 255, np.uint8)], 2), 'RGBA')
    # 찢긴 가장자리 (가위로 오린 듯 불규칙)
    r = np.random.default_rng(11)
    pts = []
    for x in range(0, w, 14):
        pts.append((x, r.uniform(0, 9)))
    for y in range(0, h, 14):
        pts.append((w - r.uniform(0, 9), y))
    for x in range(w, 0, -14):
        pts.append((x, h - r.uniform(0, 9)))
    for y in range(h, 0, -14):
        pts.append((r.uniform(0, 9), y))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    f1, f2 = F(BOLD, 46), F(REG, 30)
    d.text((70, 95), '피자 데일리', font=f1, fill=INK, anchor='ls')
    sub = '2022 → 2025 연간 실적 결산'
    d.text((w - 70 - f2.getlength(sub), 92), sub, font=f2, fill=(110, 110, 110, 255), anchor='ls')
    d.rectangle((70, 118, w - 70, 122), fill=INK)
    d.rectangle((70, 128, w - 70, 129), fill=INK)
    rb = np.random.default_rng(5)
    for row, y in enumerate((598, 628, 658)):
        for c0, c1 in ((70, 560), (640, w - 70)):
            end = c1 if row < 2 else c0 + (c1 - c0) * rb.uniform(0.4, 0.8)
            d.rounded_rectangle((c0, y, end, y + 11), radius=5, fill=(170, 165, 152, 255))
    d.rectangle((600, 590, 601, 672), fill=(190, 185, 172, 255))
    return im


class Clip(Note):
    """후킹 장면의 신문 스크랩: 화면 가운데 '탁' 붙었다가 도화지 오른쪽 위로 옮겨 붙는다."""
    def __init__(self, cx, cy, w, h, rot, t0, items, fly_t, fly_dur, to_xy, to_scale, to_rot):
        super().__init__(cx, cy, w, h, (0, 0, 0), rot, t0, items)
        self.base = newsprint_surface(w, h)
        self.fly_t, self.fly_dur = fly_t, fly_dur
        self.to_xy, self.to_scale, self.to_rot = to_xy, to_scale, to_rot

    def pose(self, t):
        u = eio(prog(t, self.fly_t, self.fly_dur))
        if u <= 0:
            return 0.0, 0.0, 1.0, 0.0, 0.0
        arc = -120 * math.sin(math.pi * u)        # 살짝 들렸다가 내려앉는 궤적
        dx = (self.to_xy[0] - self.cx) * u
        dy = (self.to_xy[1] - self.cy) * u + arc
        sc = 1 + (self.to_scale - 1) * u
        lift = math.sin(math.pi * u) if u < 1 else 0.0
        return dx, dy, sc, (self.to_rot - self.rot) * u, lift


# ---------------------------------------------------------------- scene
PX0, PY0, PX1, PY1 = 190, 130, 2690, 1490
PAPER = paper_surface(PX1 - PX0, PY1 - PY0)
TAPE = tape_img()

class Paper:
    def __init__(self):
        self.settled = None

    def draw_base(self, t):
        p = prog(t, -1.0, 0.6)            # 후킹을 위해 첫 프레임부터 도화지가 놓여 있음
        if p >= 1 and self.settled is not None:
            return self.settled.copy()
        world = Image.new('RGBA', (W, H), (255, 255, 255, 255))
        if p > 0:
            e = eoc(p)
            sc = 1.06 - 0.06 * e
            pw, ph = int(PAPER.width * sc), int(PAPER.height * sc)
            img = PAPER if sc == 1 else PAPER.resize((pw, ph), Image.BICUBIC)
            cx, cy = (PX0 + PX1) / 2, (PY0 + PY1) / 2
            mask = Image.new('L', (pw // 4, ph // 4), 255)
            sh = soft_shadow(mask, 0.22 * clamp(p * 3), 8 + 10 * (1 - e), 40).resize((pw + 320, ph + 320))
            comp(world, sh, cx - pw / 2 - 160, cy - ph / 2 - 160 + 12 + 40 * (1 - e))
            comp(world, img, cx - pw / 2, cy - ph / 2, clamp(p * 3))
        if p >= 1:
            self.settled = world.copy()
        return world


class TapePiece:
    def __init__(self, t0, cx, cy, ang):
        self.t0, self.cx, self.cy = t0, cx, cy
        self.img = TAPE.rotate(ang, resample=Image.BICUBIC, expand=True)

    def draw(self, L, t):
        p = prog(t, self.t0, 0.3)
        if p <= 0:
            return
        sc = 1 + 0.25 * (1 - eoc(p))
        im = self.img if sc == 1 else self.img.resize((int(self.img.width * sc), int(self.img.height * sc)), Image.BICUBIC)
        comp(L, im, self.cx - im.width / 2, self.cy - im.height / 2, clamp(p * 3))


PAPER_OBJ = Paper()

# ---- 후킹: 신문 스크랩
FLY_T = S[1] - 0.12
FLY_D = 0.75
CW, CH = 1200, 700
CLIP_TO = (2235, 430)
CLIP_SCALE = 0.55
_hx = 70
_h1 = line_words([
    (T(0, '삼'), '3년 새', 100, INK, BOLD, 'block'),
    (T(0, '매출은'), '매출', 100, INK, BOLD, 'block')], _hx, 262, gap=0.25)
for _w in _h1:
    _w.block = INK
_cnt = Counter(T(0, '십칠'), _hx - 8, 482, 180, 17, lambda v: f'+{v:.0f}%', color=RED, cdur=0.6)
_cx_end = _hx - 8 + F(BOLD, 180).getlength('+17%')
_q1 = Word(T(0, '손님은요'), '손님은', 700, 545, 104, INK, BOLD, 'pop')
clip_items = _h1 + [
    _cnt,
    Tri(T(0, '늘었다'), _cx_end + 30, 410, 74, True, RED),
    Word(T(0, '그런데'), '그런데,', 705, 395, 72, GRAY, BOLD, 'wipe'),
    _q1,
    Word(T(0, '손님은요') + 0.28, '?', 700 + _q1.width + 18, 560, 190, RED, BOLD, 'stamp'),
]
CLIP = Clip(1440, 800, CW, CH, -1.5, 0.08, clip_items, FLY_T, FLY_D, CLIP_TO, CLIP_SCALE, 4.0)

_tt = FLY_T + FLY_D - 0.05
WORLD_ITEMS = [
    TapePiece(_tt + 0.10, PX0 + 35, PY0 + 25, 38), TapePiece(_tt + 0.18, PX1 - 35, PY0 + 25, -38),
    TapePiece(_tt + 0.26, PX0 + 35, PY1 - 25, -38), TapePiece(_tt + 0.34, PX1 - 35, PY1 - 25, 38),
]
OVERLAY_ITEMS = [TapePiece(_tt, CLIP_TO[0] + 10, CLIP_TO[1] - CH * CLIP_SCALE / 2 + 2, -3)]

# 제목 (도화지 위)
WORLD_ITEMS.append(Word(T(1, '피자') - 0.25, '9개 매장 · 2020–2026 실적 · 탐색적 데이터 분석', 338, 228, 40, (150, 150, 150, 255), REG, 'wipe', dur=0.6))
WORLD_ITEMS += line_words([
    (T(1, '피자'), '피자', 130, INK, BOLD, 'pop'),
    (T(1, '매장'), '매장', 130, INK, BOLD, 'pop'),
    (T(1, '아홉'), '9곳', 130, ORANGE, BOLD, 'stamp'),
    (T(1, '육') - 0.15, '·', 130, (180, 180, 180, 255), BOLD, 'pop'),
    (T(1, '육'), '6년', 130, ORANGE, BOLD, 'stamp'),
    (T(1, '데이터'), '데이터', 130, INK, BOLD, 'pop'),
], 330, 380, gap=0.22)
_l2 = line_words([
    (T(1, '핵심은'), '핵심은', 92, GRAY, REG, 'wipe'),
    (T(1, '핵심은') + 0.3, '딱', 92, GRAY, REG, 'pop'),
    (T(1, '세'), '3', 190, RED, BOLD, 'drop'),
    (T(1, '가지'), '가지', 92, GRAY, REG, 'pop'),
], 335, 590, gap=0.55)
WORLD_ITEMS += _l2
_three = _l2[2]
WORLD_ITEMS.append(Marker(T(1, '가지') + 0.15, 0.5,
                          ellipse_pts(_three.x + _three.width / 2, _three.y - 68, 88, 102, seed=1.3), 11, RED))

# 포스트잇 공통
NS = 680
NY = 1080
P = 58  # 포스트잇 안쪽 여백

def label(t0, num, color):
    return Word(t0, num, P, 112, 54, color, BOLD, 'pop')

# --- 01 노랑: 손님이 멈췄다
t1 = S[2] - 0.05
y_c = (255, 226, 92)
dark1 = (130, 100, 0, 255)
n1_items = [label(t1 + 0.25, '01', dark1)]
n1_items += [Word(T(2, '손님이'), '손님이', P, 250, 100, INK, BOLD, 'pop')]
n1_items += chars(T(2, '멈췄습니다'), '멈췄다', P, 370, 100, INK, stagger=0.08)
n1_items += [Word(T(2, '주문은'), '주문', P, 500, 60, GRAY, REG, 'wipe'),
             Tri(T(2, '줄었는데'), P + 190, 482, 46, False, RED),
             Counter(T(2, '줄었는데'), P + 230, 505, 76, 1.4, lambda v: f'{v:.1f}%', color=RED),
             Word(T(2, '단가만'), '단가', P, 615, 60, GRAY, REG, 'wipe'),
             Tri(T(2, '십구'), P + 190, 597, 46, True, TEAL),
             Counter(T(2, '십구'), P + 230, 620, 76, 19, lambda v: f'{v:.0f}%', color=TEAL)]
n1_items += [Marker(T(2, '올랐죠') - 0.1, 0.3, swoosh_pts(P + 225, P + 380, 645), 9, TEAL)]
N1 = Note(640, NY, NS, NS, y_c, -3.0, t1, n1_items)

# --- 02 분홍: 이익을 깎은 건 인건비
t2 = S[3] - 0.05
p_c = (255, 178, 196)
dark2 = (150, 40, 70, 255)
n2_items = [label(t2 + 0.25, '02', dark2)]
n2_items += line_words([
    (T(3, '이익을'), '이익을', 68, INK, BOLD, 'pop'),
    (T(3, '깎은'), '깎은', 68, INK, BOLD, 'pop'),
    (T(3, '건'), '건', 68, INK, BOLD, 'pop')], P, 225, gap=0.25)
n2_items += chars(T(3, '인건비입니다'), '인건비', P + 10, 415, 140, RED, stagger=0.09, style='drop')
n2_items += [Marker(T(3, '인건비입니다') + 0.6, 0.5, ellipse_pts(P + 10 + 210, 360, 245, 78, seed=0.4), 9, INK)]
n2_items += [Word(T(3, '인당'), '인당 인건비', P, 530, 58, GRAY, REG, 'wipe'),
             Tri(T(3, '이십팔'), P + 25, 610, 50, True, RED),
             Counter(T(3, '이십팔'), P + 70, 640, 96, 28, lambda v: f'+{v:.0f}%', color=RED),
             Marker(T(3, '뛰었습니다'), 0.35, swoosh_pts(P + 70, P + 310, 668), 10, RED)]
N2 = Note(1440, NY, NS, NS, p_c, 2.2, t2, n2_items)

# --- 03 하늘: 처방은 매장마다
t3 = S[4] - 0.05
b_c = (160, 214, 246)
dark3 = (20, 70, 120, 255)
n3_items = [label(t3 + 0.25, '03', dark3)]
n3_items += [Word(T(4, '처방은'), '처방은', P, 220, 84, INK, BOLD, 'pop')]
n3_items += line_words([
    (T(4, '매장마다'), '매장마다', 64, INK, BOLD, 'pop'),
    (T(4, '다릅니다'), '다르다', 64, INK, BOLD, 'stamp')], P, 315, gap=0.25)
n3_items += [Word(T(4, '강남과'), '강남·홍대', P, 420, 50, GRAY, REG, 'wipe')]
n3_items += arrow(T(4, '임차료') - 0.3, P + 4, P + 80, 482, BLUE)
n3_items += [Word(T(4, '임차료'), '임차료', P + 100, 505, 70, BLUE, BOLD, 'pop')]
n3_items += [Word(T(4, '충장로와'), '충장로·연동', P, 585, 50, GRAY, REG, 'wipe')]
n3_items += arrow(T(4, '원가') - 0.3, P + 4, P + 80, 647, BLUE)
n3_items += [Word(T(4, '원가'), '원가 관리', P + 100, 670, 70, BLUE, BOLD, 'pop')]
N3 = Note(2240, NY, NS, NS + 40, b_c, -1.6, t3, n3_items)

# --- 결론 띠지
t4 = S[5] + 0.02
o_c = (255, 168, 76)
SW, SH = 2050, 360
s_items = [Word(t4 + 0.15, '결론', 70, 105, 58, (110, 55, 0, 255), BOLD, 'pop')]
_s = line_words([
    (T(5, '단가'), '단가', 120, (70, 40, 0, 255), BOLD, 'pop'),
    (T(5, '말고'), '말고,', 120, (70, 40, 0, 255), BOLD, 'pop')], 70, 285, gap=0.2)
s_items += _s
_x = _s[-1].x + _s[-1].width + 50
_cust = Word(T(5, '손님을'), '손님을', _x, 285, 160, (190, 15, 30, 255), BOLD, 'stamp')
s_items += [Marker(T(5, '말고') + 0.15, 0.3, [(60, 245), (_s[0].x + _s[0].width + 12, 228)], 12, (190, 15, 30, 255)), _cust]
_x2 = _x + _cust.width + 40
s_items += line_words([
    (T(5, '늘려야'), '늘려야', 92, (70, 40, 0, 255), BOLD, 'pop'),
    (T(5, '합니다'), '합니다.', 92, (70, 40, 0, 255), BOLD, 'pop')], _x2, 285, gap=0.2)
s_items += [Marker(T(5, '늘려야') + 0.05, 0.4, swoosh_pts(_x - 5, _x + _cust.width + 5, 318, amp=8), 12, (190, 15, 30, 255))]
STRIP = Note(1440, 870, SW, SH, o_c, -3.0, t4, s_items)

NOTES = [CLIP, N1, N2, N3, STRIP]

# ---------------------------------------------------------------- camera
KEYS = [
    (0.0, 1440, 800, 1.50), (FLY_T, 1440, 800, 1.64),          # 후킹: 신문 스크랩 클로즈업
    (FLY_T + FLY_D + 0.1, 1440, 640, 1.15), (S[2] - 0.3, 1440, 660, 1.20),
    (S[2] + 0.3, 640, NY, 1.72), (S[3] - 0.5, 640, NY, 1.84),
    (S[3] + 0.15, 1440, NY, 1.72), (S[4] - 0.5, 1440, NY, 1.84),
    (S[4] + 0.15, 2240, NY, 1.68), (S[5] - 0.55, 2240, NY, 1.80),
    (S[5] + 0.12, 1440, 810, 1.00), (DUR, 1440, 810, 1.07),
]
SLAPS = [n.land_time() for n in NOTES]

def camera(t):
    for i in range(len(KEYS) - 1):
        if KEYS[i][0] <= t <= KEYS[i + 1][0]:
            a, b = KEYS[i], KEYS[i + 1]
            break
    else:
        a = b = KEYS[-1]
    u = eio((t - a[0]) / max(1e-6, b[0] - a[0])) if b is not a else 1
    cx = a[1] + (b[1] - a[1]) * u
    cy = a[2] + (b[2] - a[2]) * u
    z = math.exp(math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * u)
    dq = t - T(0, '손님은요') - 0.28      # '손님은?' 순간 카메라 펀치 줌
    if 0 <= dq < 0.9:
        z *= 1 + 0.07 * (dq / 0.07 if dq < 0.07 else math.exp(-(dq - 0.07) / 0.3))
    for ts in SLAPS:                      # 붙일 때 살짝 흔들림
        d = t - ts
        if 0 <= d < 0.25:
            amp = 9 * (1 - d / 0.25)
            cx += amp * math.sin(70 * d)
            cy += amp * math.cos(55 * d)
    vw, vh = W / z, H / z
    cx = clamp(cx, vw / 2, W - vw / 2)
    cy = clamp(cy, vh / 2, H - vh / 2)
    return (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)

# ---------------------------------------------------------------- render
def frame(t):
    world = PAPER_OBJ.draw_base(t)
    for it in WORLD_ITEMS:
        it.draw(world, t)
    for n in NOTES:
        n.draw(world, t)
    for it in OVERLAY_ITEMS:
        it.draw(world, t)
    return world.resize((OW, OH), Image.BICUBIC, box=camera(t)).convert('RGB')


def render_one(fi):
    frame(fi / FPS).save(os.path.join(FRAMES, f'f{fi:04d}.png'), compress_level=1)
    return fi

# ---------------------------------------------------------------- audio
def onepole(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def build_audio(path):
    SR = 48000
    mix = np.zeros(int(DUR * SR) + SR, np.float32)
    rng = np.random.default_rng(3)

    def add(t0, sig):
        o = int(t0 * SR)
        mix[o:o + len(sig)] += sig[:max(0, len(mix) - o)]

    for v in VO:
        x = v['x']
        up = np.interp(np.arange(len(x) * 2) / 2, np.arange(len(x)), x).astype(np.float32)
        add(v['start'] - v['s'], up * 0.95)

    def slap(g):
        n = int(0.22 * SR); tt = np.arange(n) / SR
        nz = onepole(rng.standard_normal(n).astype(np.float32), 0.22) * np.exp(-tt / 0.03)
        th = np.sin(2 * np.pi * 105 * tt) * np.exp(-tt / 0.05)
        return (nz * 1.6 + th * 0.7).astype(np.float32) * g

    def tape():
        n = int(0.22 * SR); tt = np.arange(n) / SR
        nz = np.diff(rng.standard_normal(n + 1)).astype(np.float32)
        env = np.minimum(tt / 0.02, 1) * np.exp(-tt / 0.09) * (0.6 + 0.4 * np.sin(2 * np.pi * 38 * tt))
        return nz * env * 0.05

    def scribble(dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        w = rng.standard_normal(n).astype(np.float32)
        band = onepole(w, 0.35) - onepole(w, 0.04)
        env = np.minimum(tt / 0.03, 1) * np.minimum((dur - tt) / 0.05, 1) * (0.55 + 0.45 * np.sin(2 * np.pi * 13 * tt))
        return band * env * 0.10

    def whoosh(dur, g):
        n = int(dur * SR); tt = np.arange(n) / SR
        w = rng.standard_normal(n).astype(np.float32)
        env = np.sin(np.pi * tt / dur) ** 2
        return (onepole(w, 0.08) * env * g).astype(np.float32)

    def boom(g):                          # '손님은?' 강조 저음
        n = int(0.5 * SR); tt = np.arange(n) / SR
        f = 70 + 40 * np.exp(-tt / 0.05)
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.18) * g).astype(np.float32)

    add(FLY_T, whoosh(FLY_D, 0.9))
    add(T(0, '손님은요') + 0.28, boom(0.35))
    for tp in WORLD_ITEMS + OVERLAY_ITEMS:
        if isinstance(tp, TapePiece):
            add(tp.t0, tape())
    for n in NOTES:
        add(n.land_time() - 0.02, slap(0.40))
        for it in n.items:
            if isinstance(it, Marker) and it.dur >= 0.25:
                add(it.t0, scribble(it.dur))
    for it in WORLD_ITEMS:
        if isinstance(it, Marker):
            add(it.t0, scribble(it.dur))

    mix = mix[:int(DUR * SR)]
    mix *= 0.89 / np.max(np.abs(mix))
    fade = int(0.4 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)
    w = wave.open(path, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())
    w.close()


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--preview':
        os.makedirs(FRAMES, exist_ok=True)
        for t in map(float, sys.argv[2].split(',')):
            frame(t).save(os.path.join(FRAMES, f'preview_{t:05.2f}.png'))
        print('schedule', [round(s, 2) for s in S])
        return
    from multiprocessing import Pool
    import imageio_ffmpeg
    os.makedirs(FRAMES, exist_ok=True)
    n = int(DUR * FPS)
    with Pool(max(1, os.cpu_count() - 2)) as pool:
        for k, _ in enumerate(pool.imap_unordered(render_one, range(n), chunksize=6)):
            if k % 90 == 0:
                print(f'frames {k}/{n}', flush=True)
    wav = os.path.join(FRAMES, 'mix.wav')
    build_audio(wav)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(FRAMES, 'f%04d.png'),
                    '-i', wav, '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', OUTFILE], check=True)
    print('done', OUTFILE)


if __name__ == '__main__':
    main()
