"""WiZ Music Sync: Windows app (Qt UI over wiz_core.Engine)."""
import colorsys
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

import wiz_core as core

APP_NAME = "WiZ Music Sync"
APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
RES_DIR = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets")
SETTINGS = os.path.join(APP_DIR, "settings.json")

# ---- palette (unchanged from v1)
BG, CARD, CARD2, FG, MUTED = "#0f1115", "#181b22", "#21252e", "#eceef2", "#8b919c"
ACCENT, ACCENT_HI, GOOD, BAD, WARN = "#7c5cff", "#9479ff", "#3ecf8e", "#ff5c6c", "#f5b942"
FIELD, LINE, FAINT = "#12141a", "#272b36", "#5d6370"

QSS = f"""
* {{ color: {FG}; font-size: 13px; }}
QWidget#root {{ background: {BG}; }}
QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1d25, stop:1 #16191f);
    border: 1px solid {LINE}; border-radius: 16px;
}}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 21px; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="h"] {{ font-size: 15px; font-weight: 650; }}
QLabel[role="muted"] {{ color: {MUTED}; font-size: 12px; }}
QLabel[role="faint"] {{ color: {FAINT}; font-size: 11px; }}
QLabel[role="field"] {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
QLabel[role="badge"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b70ff, stop:1 #6a4cff);
    color: white; font-size: 11px; font-weight: 700; border-radius: 11px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
}}
QLabel[role="big"] {{ color: {ACCENT_HI}; font-size: 26px; font-weight: 700; }}
QLabel[role="value"] {{
    color: {FG}; background: {CARD2}; border-radius: 8px; padding: 2px 8px;
    font-size: 12px; font-weight: 600;
}}
QLabel[role="pill"] {{
    border-radius: 12px; padding: 4px 12px; font-size: 12px; font-weight: 600;
    background: {CARD2}; color: {MUTED}; border: 1px solid {LINE};
}}
QLabel[role="pill"][state="good"] {{ background: rgba(62,207,142,0.12); color: {GOOD}; border-color: rgba(62,207,142,0.35); }}
QLabel[role="pill"][state="warn"] {{ background: rgba(245,185,66,0.12); color: {WARN}; border-color: rgba(245,185,66,0.35); }}
QLabel[role="pill"][state="bad"]  {{ background: rgba(255,92,108,0.12); color: {BAD};  border-color: rgba(255,92,108,0.35); }}
QLabel[role="pill"][state="live"] {{ background: rgba(124,92,255,0.18); color: {ACCENT_HI}; border-color: rgba(124,92,255,0.5); }}
QLabel[role="msg"] {{ color: {MUTED}; font-size: 12px; }}
QLabel[role="msg"][state="good"] {{ color: {GOOD}; }}
QLabel[role="msg"][state="bad"]  {{ color: {BAD}; }}
QLabel[role="msg"][state="warn"] {{ color: {WARN}; }}

QPushButton {{
    background: #232733; border: 1px solid #2c3140; border-radius: 10px;
    padding: 7px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: #2a2f3c; border-color: #3a4052; }}
QPushButton:pressed {{ background: #1e2129; }}
QPushButton:disabled {{ color: {FAINT}; background: #1b1e25; border-color: #22262f; }}
QPushButton[kind="primary"] {{
    border: none; color: white;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8a6dff, stop:1 #6a4cff);
}}
QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9a82ff, stop:1 #7a5fff); }}
QPushButton[kind="primary"]:pressed {{ background: #6447f0; }}
QPushButton[kind="primary"]:disabled {{ background: #3a3360; color: #a99fd6; }}
QPushButton[kind="play"] {{
    border: none; color: white; font-size: 16px; font-weight: 700; padding: 13px; border-radius: 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8a6dff, stop:1 #5f40f5);
}}
QPushButton[kind="play"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9a82ff, stop:1 #6f52ff); }}
QPushButton[kind="stop"] {{
    border: none; color: white; font-size: 16px; font-weight: 700; padding: 13px; border-radius: 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff7684, stop:1 #e8475a);
}}
QPushButton[kind="stop"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff8b97, stop:1 #f2596b); }}
QPushButton[kind="seg"] {{ padding: 6px 0px; border-radius: 8px; font-size: 12px; min-width: 62px; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 5px 10px; }}
QPushButton[kind="ghost"]:hover {{ background: {CARD2}; color: {FG}; border-color: {LINE}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {ACCENT_HI}; padding: 2px 4px; }}
QPushButton[kind="link"]:hover {{ color: #b3a2ff; text-decoration: underline; }}

QLineEdit, QComboBox {{
    background: {FIELD}; border: 1px solid #2a2f3b; border-radius: 10px;
    padding: 7px 12px; selection-background-color: {ACCENT};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: #363c4b; }}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border-color: {ACCENT}; }}
QComboBox {{ padding-right: 30px; }}
QComboBox::drop-down {{ border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: right center; }}
QComboBox::down-arrow {{ image: url("{RES_DIR.replace(os.sep, '/')}/chevron.png"); width: 12px; height: 8px; }}
QComboBox QAbstractItemView {{
    background: #1b1e26; border: 1px solid #2f3442; border-radius: 10px; padding: 4px;
    selection-background-color: {ACCENT}; selection-color: white; outline: 0;
}}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 0 8px; border-radius: 6px; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 6px; background: #262a35; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6a4cff, stop:1 #9479ff); border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; border: 3px solid {ACCENT}; width: 12px; height: 12px;
    margin: -6px 0; border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT_HI}; background: #f1edff; }}
QSlider#delay::sub-page:horizontal {{ background: #262a35; }}
QSlider#delay::groove:horizontal {{ height: 8px; border-radius: 4px; }}
QSlider#delay::handle:horizontal {{ width: 16px; height: 16px; margin: -7px 0; border-radius: 11px; }}

QToolTip {{ background: #1b1e26; color: {FG}; border: 1px solid #2f3442; padding: 6px; border-radius: 6px; }}
QMessageBox {{ background: {CARD}; }}
QMessageBox QLabel {{ font-size: 13px; }}
QMessageBox QPushButton {{ min-width: 84px; }}
"""


def prop(w, **kw):
    for k, v in kw.items():
        w.setProperty(k, v)
    w.style().unpolish(w)
    w.style().polish(w)
    return w


def label(text="", role=None, wrap=False):
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def button(text, kind=None, slot=None, tip=None):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def hsv_q(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def eye_icon():
    from PySide6.QtGui import QPixmap
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(MUTED), 3))
    path = QPainterPath()
    path.moveTo(4, 20)
    path.quadTo(20, 4, 36, 20)
    path.quadTo(20, 36, 4, 20)
    p.drawPath(path)
    p.setBrush(QColor(MUTED))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(20, 20), 5.5, 5.5)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


class Card(QFrame):
    def __init__(self, title, step=None, right=None):
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 13)
        self.body.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        if step:
            b = label(str(step), "badge")
            b.setAlignment(Qt.AlignCenter)
            head.addWidget(b)
        head.addWidget(label(title, "h"))
        head.addStretch(1)
        if right is not None:
            head.addWidget(right)
        self.body.addLayout(head)


# ============================================================================ live view
class BulbView(QWidget):
    """Animated preview: glowing bulb, beat rings, strength meter, beat history."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 214)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.color = QColor("#2a2e38")
        self.target = QColor("#2a2e38")
        self.bright = 0.0
        self.target_bright = 0.0
        self.meter = 0.0
        self.rings = []                       # (t0, QColor, strength)
        self.history = deque(maxlen=44)       # (score, QColor)
        self.mode = None
        self.caption = "Ready when you are"
        self.stat = ""

    def beat(self, color, score):
        self.rings.append((time.time(), QColor(color), score))
        self.history.append((score, QColor(color)))
        self.meter = max(self.meter, score)

    def step(self):
        a = 0.35
        c, t = self.color, self.target
        self.color = QColor(int(c.red() + (t.red() - c.red()) * a), int(c.green() + (t.green() - c.green()) * a),
                            int(c.blue() + (t.blue() - c.blue()) * a))
        self.bright += (self.target_bright - self.bright) * 0.4
        self.meter *= 0.93
        now = time.time()
        self.rings = [r for r in self.rings if now - r[0] < 0.9]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, 80
        b = self.bright
        col = QColor(self.color)
        lit = QColor(int(col.red() * (0.3 + 0.7 * b)), int(col.green() * (0.3 + 0.7 * b)),
                     int(col.blue() * (0.3 + 0.7 * b)))

        # stage background
        stage = QRectF(0, 0, w, 168)
        path = QPainterPath()
        path.addRoundedRect(stage, 14, 14)
        p.fillPath(path, QColor("#121419"))
        p.save()
        p.setClipPath(path)
        # glow
        if b > 0.02:
            g = QRadialGradient(QPointF(cx, cy), 60 + 90 * b)
            c0 = QColor(col)
            c0.setAlphaF(0.55 * b)
            c1 = QColor(col)
            c1.setAlphaF(0.16 * b)
            c2 = QColor(col)
            c2.setAlphaF(0.0)
            g.setColorAt(0.0, c0)
            g.setColorAt(0.45, c1)
            g.setColorAt(1.0, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), 60 + 90 * b, 60 + 90 * b)
        # rings
        now = time.time()
        for t0, rc, s in self.rings:
            age = (now - t0) / 0.9
            r = 48 + (26 + 40 * s) * age
            rc = QColor(rc)
            rc.setAlphaF(max(0.0, (1 - age) * (0.35 + 0.5 * s)))
            p.setPen(QPen(rc, 2 + 3 * s * (1 - age)))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.restore()

        # bulb body
        bg = QRadialGradient(QPointF(cx - 14, cy - 16), 62)
        hi = QColor(min(255, lit.red() + 90), min(255, lit.green() + 90), min(255, lit.blue() + 90))
        bg.setColorAt(0.0, hi if b > 0.05 else QColor("#3a3f4c"))
        bg.setColorAt(0.55, lit if b > 0.05 else QColor("#2a2e38"))
        bg.setColorAt(1.0, lit.darker(160) if b > 0.05 else QColor("#20232b"))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(bg)
        p.drawEllipse(QPointF(cx, cy), 46, 46)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 46 if b > 0.05 else 16))
        p.drawEllipse(QPointF(cx - 16, cy - 18), 12, 8)

        # stage captions
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        p.setFont(f)
        mode_txt, mode_col = {"live": ("● LIVE", GOOD), "calibrate": ("● SYNC TEST", WARN)}.get(
            self.mode, ("IDLE", FAINT))
        p.setPen(QColor(mode_col))
        p.drawText(QRectF(14, 10, 160, 18), Qt.AlignLeft | Qt.AlignVCenter, mode_txt)
        p.setPen(QColor(MUTED))
        f2 = QFont(self.font())
        f2.setPointSizeF(8.5)
        p.setFont(f2)
        p.drawText(QRectF(w - 214, 10, 200, 18), Qt.AlignRight | Qt.AlignVCenter, self.stat)
        f3 = QFont(self.font())
        f3.setPointSizeF(9.5)
        p.setFont(f3)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(0, 138, w, 22), Qt.AlignCenter, self.caption)

        # beat-strength meter
        y = 182
        p.setFont(f2)
        p.setPen(QColor(FAINT))
        p.drawText(QRectF(0, y - 4, 92, 14), Qt.AlignLeft | Qt.AlignVCenter, "BEAT STRENGTH")
        track = QRectF(96, y, w - 96, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#262a35"))
        p.drawRoundedRect(track, 3, 3)
        if self.meter > 0.01:
            fill = QRectF(track.x(), track.y(), track.width() * min(1.0, self.meter), 6)
            lg = QLinearGradient(fill.topLeft(), fill.topRight())
            lg.setColorAt(0, QColor(ACCENT))
            lg.setColorAt(1, col if b > 0.05 else QColor(ACCENT_HI))
            p.setBrush(lg)
            p.drawRoundedRect(fill, 3, 3)

        # beat history
        base = h - 2
        bw, gap = 5, 3
        n = len(self.history)
        x0 = w - n * (bw + gap)
        for i, (s, hc) in enumerate(self.history):
            hh = 3 + 14 * s
            hc = QColor(hc)
            hc.setAlphaF(0.35 + 0.65 * (i + 1) / max(1, n))
            p.setBrush(hc)
            p.drawRoundedRect(QRectF(x0 + i * (bw + gap), base - hh, bw, hh), 2, 2)
        if n == 0:
            p.setPen(QColor(FAINT))
            p.drawText(QRectF(0, base - 18, w, 18), Qt.AlignCenter, "beats will appear here")
        p.end()


class PaletteChip(QAbstractButton):
    def __init__(self, name, hues):
        super().__init__()
        self.name, self.hues = name, hues
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{name} colours")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hover = False

    def sizeHint(self):
        return QSize(64, 54)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        p.setPen(QPen(QColor(ACCENT if on else ("#3a4052" if self._hover else LINE)), 2 if on else 1))
        p.setBrush(QColor("#1f1b33" if on else ("#20242d" if self._hover else "#1a1d24")))
        p.drawRoundedRect(r, 12, 12)
        hues = self.hues[:5]
        d, gap = 9, 3
        total = len(hues) * d + (len(hues) - 1) * gap
        x = r.center().x() - total / 2
        p.setPen(Qt.NoPen)
        for hval in hues:
            p.setBrush(hsv_q(hval))
            p.drawEllipse(QRectF(x, 11, d, d))
            x += d + gap
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setWeight(QFont.DemiBold if on else QFont.Medium)
        p.setFont(f)
        p.setPen(QColor(FG if on else MUTED))
        p.drawText(QRectF(r.x(), 26, r.width(), 20), Qt.AlignCenter, self.name)
        p.end()


class StatusRow(QWidget):
    """● text  [action]"""

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(22, 22)
        self.icon.setAlignment(Qt.AlignCenter)
        self.text = label("", "msg")
        self.text.setWordWrap(True)
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        self.action = button("", "ghost")
        self.action.hide()
        lay.addWidget(self.action)
        self._slot = None

    def set(self, state, text, action=None, slot=None, primary=False):
        sym, col, bg = {"good": ("✓", GOOD, "rgba(62,207,142,0.14)"),
                        "warn": ("!", WARN, "rgba(245,185,66,0.14)"),
                        "bad": ("✕", BAD, "rgba(255,92,108,0.14)")}[state]
        self.icon.setText(sym)
        self.icon.setStyleSheet(f"background:{bg}; color:{col}; border-radius:11px; font-weight:800; font-size:11px;")
        self.text.setText(text)
        prop(self.text, state=state)
        if self._slot:
            self.action.clicked.disconnect(self._slot)
            self._slot = None
        if action:
            self.action.setText(action)
            prop(self.action, kind="primary" if primary else "ghost")
            self.action.clicked.connect(slot)
            self._slot = slot
            self.action.show()
        else:
            self.action.hide()


class Bridge(QObject):
    found = Signal(object)
    tested = Signal(object)
    progress = Signal(str)


# ============================================================================ main window
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        icon = os.path.join(RES_DIR, "app.ico")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.cfg = self._load()
        self.engine = core.Engine()
        self.engine.delay_ms = float(self.cfg.get("delay_ms", 120))
        self.engine.style.update(self.cfg.get("style", {}))
        self.sort_keys = bool(self.cfg.get("sort_keys", False))
        self.bulb_state = None
        self.cable_ok = self.cable_default = False
        self._last_beats = 0
        self._last_flash = 0.0
        self._shown_err = None

        self.bridge = Bridge()
        self.bridge.found.connect(self._on_found)
        self.bridge.tested.connect(self._on_tested)
        self.bridge.progress.connect(lambda m: self._bulb_msg(m, None))

        self._save_timer = QTimer(self, singleShot=True, interval=400, timeout=self._write_settings)
        self._build()
        self.refresh_audio()
        self._apply_bulb(save=False)
        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self.timer.start()
        self.setFocusPolicy(Qt.ClickFocus)
        QTimer.singleShot(0, self.setFocus)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        # header
        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        icon_path = os.path.join(RES_DIR, "app.ico")
        if os.path.exists(icon_path):
            logo.setPixmap(QIcon(icon_path).pixmap(36, 36))
        head.addWidget(logo)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addWidget(label(APP_NAME, "title"))
        tcol.addWidget(label("Your WiZ light, in time with your music", "subtitle"))
        head.addLayout(tcol)
        head.addStretch(1)
        self.pill_bulb = label("Bulb · not tested", "pill")
        self.pill_audio = label("Audio", "pill")
        self.pill_live = label("Idle", "pill")
        for pl in (self.pill_bulb, self.pill_audio, self.pill_live):
            head.addWidget(pl)
        root.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)
        left.addWidget(self._bulb_card())
        left.addWidget(self._sound_card())
        left.addWidget(self._sync_card())
        left.addStretch(1)
        right.addWidget(self._live_card())
        right.addWidget(self._style_card())
        right.addStretch(1)
        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        left.setContentsMargins(0, 0, 0, 0)
        right.setContentsMargins(0, 0, 0, 0)
        rw.setFixedWidth(400)
        cols.addWidget(lw, 1)
        cols.addWidget(rw)
        root.addLayout(cols, 1)

        foot = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color:{FAINT}; font-size:10px;")
        self.status = label("Ready.", "msg")
        foot.addWidget(self.status_dot)
        foot.addWidget(self.status, 1)
        foot.addWidget(label("Settings save automatically", "faint"))
        root.addLayout(foot)

    def _field(self, text):
        lb = label(text, "field")
        lb.setFixedWidth(96)
        return lb

    def _bulb_card(self):
        c = Card("Bulb", 1)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        self.ip_box = QComboBox()
        self.ip_box.setEditable(True)
        self.ip_box.lineEdit().setPlaceholderText("e.g. 192.168.1.50")
        self.ip_box.setCurrentText(self.cfg.get("ip", ""))
        self.ip_box.lineEdit().editingFinished.connect(self._apply_bulb)
        self.ip_box.activated.connect(lambda _: self._apply_bulb())
        self.find_btn = button("Find bulbs", None, self.find_bulbs, "Search your Wi-Fi for WiZ bulbs")
        g.addWidget(self._field("Bulb IP"), 0, 0)
        g.addWidget(self.ip_box, 0, 1)
        g.addWidget(self.find_btn, 0, 2)

        self.key_edit = QLineEdit(self.cfg.get("key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Optional: only for newer firmware")
        self.key_edit.editingFinished.connect(self._apply_bulb)
        show = self.key_edit.addAction(eye_icon(), QLineEdit.TrailingPosition)
        show.setToolTip("Show / hide key")
        show.triggered.connect(lambda: self.key_edit.setEchoMode(
            QLineEdit.Normal if self.key_edit.echoMode() == QLineEdit.Password else QLineEdit.Password))
        g.addWidget(self._field("Signing key"), 1, 0)
        g.addWidget(self.key_edit, 1, 1)
        g.addWidget(button("Load file…", None, self.load_key_file, "Load the home export JSON from the WiZ app"),
                    1, 2)
        g.setColumnStretch(1, 1)
        c.body.addLayout(g)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.test_btn = button("Test bulb", "primary", self.test_bulb)
        self.test_btn.setFixedWidth(118)
        self.bulb_msg = label("Flashes red, green and blue so you know it's listening.", "msg", wrap=True)
        row.addWidget(self.test_btn)
        row.addWidget(self.bulb_msg, 1)
        c.body.addLayout(row)
        return c

    def _sound_card(self):
        refresh = button("↻  Refresh", "ghost", self.refresh_audio, "Re-scan audio devices")
        c = Card("Sound", 2, refresh)
        self.row_cable = StatusRow()
        self.row_default = StatusRow()
        c.body.addWidget(self.row_cable)
        c.body.addWidget(self.row_default)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._field("Play through"))
        self.out_box = QComboBox()
        self.out_box.activated.connect(lambda _: self._output_changed())
        row.addWidget(self.out_box, 1)
        self.out_box.setToolTip("Your headphones or speakers. For Bluetooth pick “Headphones”, not “Headset”.")
        c.body.addLayout(row)
        return c

    def _sync_card(self):
        self.delay_val = label("", "big")
        c = Card("Sync test", 3, self.delay_val)
        c.body.addWidget(label("The bulb flashes and you hear a tick once a second. "
                               "Slide until they land at the same moment.", "muted", wrap=True))
        self.delay = QSlider(Qt.Horizontal)
        self.delay.setObjectName("delay")
        self.delay.setRange(-300, 600)
        self.delay.setValue(int(self.engine.delay_ms))
        self.delay.setCursor(Qt.PointingHandCursor)
        self.delay.valueChanged.connect(self._delay_changed)
        c.body.addWidget(self.delay)
        ends = QHBoxLayout()
        ends.addWidget(label("◀  flash comes first", "faint"))
        ends.addStretch(1)
        ends.addWidget(label("tick comes first  ▶", "faint"))
        c.body.addLayout(ends)

        row = QHBoxLayout()
        row.setSpacing(6)
        for d in (-10, -1, +1, +10):
            b = button(f"{d:+d} ms".replace("-", "−"), "seg", lambda _=False, d=d: self._nudge(d))
            row.addWidget(b)
        row.addStretch(1)
        self.cal_btn = button("Start sync test", "primary", self.toggle_cal)
        self.cal_btn.setFixedWidth(150)
        row.addWidget(self.cal_btn)
        c.body.addLayout(row)
        self.sync_hint = label("", "faint", wrap=True)
        c.body.addWidget(self.sync_hint)
        self._delay_changed(self.delay.value(), save=False)
        return c

    def _live_card(self):
        c = Card("Music sync")
        self.view = BulbView()
        c.body.addWidget(self.view)
        self.play_btn = button("▶   Start music sync", "play", self.toggle_live)
        c.body.addWidget(self.play_btn)
        hint = label("Then play songs in any app: Spotify, YouTube, anything.", "faint")
        hint.setAlignment(Qt.AlignCenter)
        c.body.addWidget(hint)
        return c

    def _style_card(self):
        c = Card("Look & feel")
        st = self.engine.style
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        for name, hues in core.PALETTES.items():
            ch = PaletteChip(name, hues)
            ch.setChecked(name == st.get("palette", "Party"))
            ch.clicked.connect(self._style_changed)
            self.chip_group.addButton(ch)
            chips.addWidget(ch)
        c.body.addLayout(chips)

        self.sliders = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        specs = (("color_speed", "Colour changes", 3, 30, 10, "{:.1f}×", "How often softer beats change colour"),
                 ("contrast", "Big-hit contrast", 10, 25, 10, "{:.1f}", "Higher = only the biggest hits go full power"),
                 ("sensitivity", "Beat threshold", 8, 30, 10, "{:.1f}", "Lower = more flashes"),
                 ("min_bright", "Min brightness", 10, 60, 1, "{:.0f}%", "Brightness between beats"),
                 ("max_bright", "Max brightness", 40, 100, 1, "{:.0f}%", "Brightness on the biggest hits"))
        for r, (key, text, lo, hi, scale, fmt, tip) in enumerate(specs):
            name = label(text, "muted")
            name.setToolTip(tip)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(int(round(float(st[key]) * scale)))
            sl.setCursor(Qt.PointingHandCursor)
            sl.setToolTip(tip)
            val = label(fmt.format(sl.value() / scale), "value")
            val.setAlignment(Qt.AlignCenter)
            val.setFixedWidth(52)
            sl.valueChanged.connect(lambda v, k=key, lb=val, f=fmt, s=scale: self._slider(k, v, lb, f, s))
            grid.addWidget(name, r, 0)
            grid.addWidget(sl, r, 1)
            grid.addWidget(val, r, 2)
            self.sliders[key] = (sl, scale)
        grid.setColumnStretch(1, 1)
        c.body.addLayout(grid)
        return c

    # ------------------------------------------------------------------ helpers
    def _load(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        self._save_timer.start()

    def _write_settings(self):
        style = dict(self.engine.style)
        data = {"ip": self.ip_box.currentText().strip(), "key": self.key_edit.text().strip(),
                "sort_keys": self.sort_keys, "output": self.out_box.currentText(),
                "delay_ms": self.delay.value(), "style": style}
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def set_status(self, text, state=None):
        self.status.setText(text)
        prop(self.status, state=state or "")
        self.status_dot.setStyleSheet(
            f"color:{ {'good': GOOD, 'bad': BAD, 'warn': WARN}.get(state, FAINT) }; font-size:10px;")

    def _bulb_msg(self, text, state):
        self.bulb_msg.setText(text)
        prop(self.bulb_msg, state=state or "")

    def _set_pill(self, pill, text, state):
        pill.setText(text)
        prop(pill, state=state or "")

    def ask(self, title, text, yes_no=False, icon=QMessageBox.Information):
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(icon)
        box.setText(f"<b>{title}</b>")
        box.setInformativeText(text)
        if yes_no:
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    # ------------------------------------------------------------------ bulb
    def _apply_bulb(self, save=True):
        ip = self.ip_box.currentText().strip()
        try:
            key = core.parse_key(self.key_edit.text())
        except (ValueError, OSError) as e:
            self._bulb_msg(str(e), "bad")
            key = None
        self.engine.set_bulb(ip, key, self.sort_keys)
        if self.bulb_state is None:
            self._set_pill(self.pill_bulb, "Bulb · not tested" if ip else "Bulb · not set", None)
        if save:
            self._save()

    def find_bulbs(self):
        self.find_btn.setEnabled(False)
        self.find_btn.setText("Searching…")
        self.set_status("Searching for WiZ bulbs on your network…")
        threading.Thread(target=lambda: self.bridge.found.emit(core.discover()), daemon=True).start()

    def _on_found(self, found):
        self.find_btn.setEnabled(True)
        self.find_btn.setText("Find bulbs")
        ips = list(found)
        cur = self.ip_box.currentText()
        self.ip_box.clear()
        self.ip_box.addItems(ips)
        if ips:
            self.ip_box.setCurrentText(cur if cur in ips else ips[0])
            self._apply_bulb()
            self.set_status(f"Found {len(ips)} bulb{'s' if len(ips) > 1 else ''}: {', '.join(ips)}", "good")
        else:
            self.ip_box.setCurrentText(cur)
            self.set_status("No bulbs found. Same Wi-Fi? Allow the app through Windows Firewall if asked.", "bad")

    def load_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "WiZ home export", "", "JSON (*.json);;All files (*.*)")
        if path:
            try:
                self.key_edit.setText(core.parse_key(path).hex())
                self._apply_bulb()
                self._bulb_msg("Key loaded. Now click Test bulb.", "good")
            except (ValueError, OSError) as e:
                self.ask("Couldn't read that file", str(e), icon=QMessageBox.Warning)

    def test_bulb(self):
        ip = self.ip_box.currentText().strip()
        if not ip:
            self.ask("No bulb yet", "Type the bulb's IP or click <b>Find bulbs</b> first.")
            return
        try:
            key = core.parse_key(self.key_edit.text())
        except (ValueError, OSError) as e:
            self.ask("Signing key problem", str(e), icon=QMessageBox.Warning)
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")
        self._bulb_msg("Talking to the bulb…", None)
        threading.Thread(target=lambda: self.bridge.tested.emit(
            core.test_bulb(ip, key, progress=self.bridge.progress.emit)), daemon=True).start()

    def _on_tested(self, res):
        ok, sort_keys, msg = res
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test bulb")
        self.bulb_state = ok
        if ok:
            self.sort_keys = sort_keys
            self._apply_bulb()
        self._bulb_msg(msg, "good" if ok else "bad")
        self._set_pill(self.pill_bulb, "Bulb · ready" if ok else "Bulb · problem", "good" if ok else "bad")

    # ------------------------------------------------------------------ sound
    def refresh_audio(self):
        if self.engine.mode:
            self.stop_all()
        core.refresh_devices()
        try:
            outs = core.list_outputs()
            self.cable_ok, self.cable_default = core.cable_status()
        except Exception as e:  # noqa: BLE001
            outs, self.cable_ok, self.cable_default = [], False, False
            self.set_status(f"Audio error: {e}", "bad")
        want = self.out_box.currentText() or self.cfg.get("output", "")
        self.out_box.clear()
        self.out_box.addItems(outs)
        if want in outs:
            self.out_box.setCurrentText(want)
        elif outs:
            self.out_box.setCurrentText(next((o for o in outs if "headphone" in o.lower()), outs[0]))

        if not self.cable_ok:
            self.row_cable.set("bad", "VB-Cable isn't installed. Install it, then restart Windows.",
                               "Get VB-Cable", lambda: webbrowser.open("https://vb-audio.com/Cable/"), primary=True)
            self.row_default.hide()
            self._set_pill(self.pill_audio, "Audio · VB-Cable missing", "bad")
        else:
            self.row_cable.set("good", "VB-Cable installed")
            self.row_default.show()
            if self.cable_default:
                self.row_default.set("good", "Windows sound goes into CABLE Input")
                self._set_pill(self.pill_audio, "Audio · ready", "good")
            else:
                self.row_default.set("warn", "Set “CABLE Input” as the default playback device",
                                     "Open Sound settings", self.open_sound_panel, primary=True)
                self._set_pill(self.pill_audio, "Audio · needs setup", "warn")
        self._save()

    def open_sound_panel(self):
        try:
            subprocess.Popen(["control", "mmsys.cpl,,0"])
        except OSError:
            pass
        self.set_status("Playback tab → CABLE Input → Set Default → OK. Then click Refresh.", "warn")

    def _output_changed(self):
        self._save()
        if self.engine.mode:
            self._start(self.engine.mode)

    # ------------------------------------------------------------------ sync / play
    def _delay_changed(self, v, save=True):
        self.engine.delay_ms = v
        self.delay_val.setText(f"−{abs(v)} ms" if v < 0 else f"{v} ms")
        self.sync_hint.setText(
            "Negative: the light is held back instead. Use it if Bluetooth headphones lag more than the bulb."
            if v < 0 else "Positive: the sound waits for the bulb. Typical: 80–200 ms, more for Bluetooth.")
        if save:
            self._save()

    def _nudge(self, d):
        self.delay.setValue(self.delay.value() + d)

    def _ready(self, need_cable):
        if not self.ip_box.currentText().strip():
            self.ask("Step 1 first", "Enter the bulb's IP or click <b>Find bulbs</b>.")
            return False
        if not self.out_box.currentText():
            self.ask("Step 2 first", "Choose where to play the sound under <b>Play through</b>.")
            return False
        self._apply_bulb()
        if need_cable:
            core.refresh_devices()
            self.cable_ok, self.cable_default = core.cable_status()
            if not self.cable_ok:
                self.ask("VB-Cable isn't installed", "Click <b>Get VB-Cable</b>, install it, restart Windows, "
                                                     "then try again.", icon=QMessageBox.Warning)
                return False
            if not self.cable_default and not self.ask(
                    "Windows sound isn't going to CABLE Input",
                    "Songs won't reach the app until you set <b>CABLE Input</b> as the default playback "
                    "device (Sound settings → Playback).<br><br>Start anyway?", yes_no=True,
                    icon=QMessageBox.Question):
                return False
        return True

    def _start(self, mode):
        try:
            self.engine.start(mode, self.out_box.currentText())
        except Exception as e:  # noqa: BLE001
            self.set_status(str(e).splitlines()[0], "bad")
            self.ask("Couldn't start audio", str(e).replace("\n", "<br>"), icon=QMessageBox.Critical)
            self._update_mode()
            return
        st = self.engine.status
        self._last_beats = 0
        self._shown_err = None
        self.set_status(f"{st['api']} · {st['sr']} Hz · device latency {st['latency_ms']} ms", "good")
        self._update_mode()

    def toggle_cal(self):
        if self.engine.mode == "calibrate":
            self.stop_all()
        elif self._ready(need_cable=False):
            self._start("calibrate")

    def toggle_live(self):
        if self.engine.mode == "live":
            self.stop_all()
        elif self._ready(need_cable=True):
            self._start("live")

    def stop_all(self):
        self.engine.stop()
        self._update_mode()
        self.set_status("Stopped. The bulb is back to warm white.")

    def _update_mode(self):
        m = self.engine.mode
        self.cal_btn.setText("Stop sync test" if m == "calibrate" else "Start sync test")
        prop(self.cal_btn, kind="stop" if m == "calibrate" else "primary")
        if m == "calibrate":
            self.cal_btn.setStyleSheet("padding: 8px 16px; font-size: 13px; border-radius: 10px;")
        else:
            self.cal_btn.setStyleSheet("")
        self.play_btn.setText("■   Stop music sync" if m == "live" else "▶   Start music sync")
        prop(self.play_btn, kind="stop" if m == "live" else "play")
        self._set_pill(self.pill_live, {"live": "● Live", "calibrate": "● Sync test"}.get(m, "Idle"),
                       {"live": "live", "calibrate": "warn"}.get(m))
        self.view.mode = m
        self.view.caption = {"live": "Listening…", "calibrate": "Watch the bulb, listen for the tick"}.get(
            m, "Ready when you are")
        if not m:
            self.view.target, self.view.target_bright, self.view.stat = QColor("#2a2e38"), 0.0, ""

    # ------------------------------------------------------------------ style
    def _slider(self, key, v, lbl, fmt, scale):
        lbl.setText(fmt.format(v / scale))
        lo, hi = self.sliders["min_bright"][0], self.sliders["max_bright"][0]
        if key == "min_bright" and v > hi.value():
            hi.setValue(v)
        if key == "max_bright" and v < lo.value():
            lo.setValue(v)
        self._style_changed()

    def _style_changed(self):
        kw = {k: round(sl.value() / s, 2) for k, (sl, s) in self.sliders.items()}
        chk = self.chip_group.checkedButton()
        kw["palette"] = chk.name if chk else "Party"
        self.engine.set_style(**kw)
        self._save()

    # ------------------------------------------------------------------ frame loop
    def _tick(self):
        m, v = self.engine.mode, self.view
        if m == "live":
            lv = self.engine.live_view()
            if lv:
                col = QColor(*lv["rgb"])
                v.target, v.target_bright = col, lv["dim"] / 100
                if lv["beats"] != self._last_beats:
                    self._last_beats = lv["beats"]
                    v.beat(col, lv["score"])
                v.stat = f"{lv['beats']} beats · {lv['dim']}%"
                if lv["level"] < 0.002 and lv["beats"] == 0:
                    v.caption = "Waiting for sound… play a song"
                else:
                    v.caption = "Listening…"
        elif m == "calibrate":
            fl = self.engine.status.get("flash", 0.0)
            if fl != self._last_flash:
                self._last_flash = fl
                col = QColor(*self.engine.status.get("flash_rgb", (255, 255, 255)))
                v.target, v.target_bright = col, 1.0
                v.beat(col, 0.8)
            elif time.time() - fl > 0.4:
                v.target_bright = 0.12
            v.stat = f"delay {self.delay.value()} ms"
        v.step()
        if m:
            err = self.engine.bulb_error()
            if err and err != self._shown_err:
                self._shown_err = err
                self.set_status(err, "bad")
                self._set_pill(self.pill_bulb, "Bulb · problem", "bad")

    def closeEvent(self, e):
        self.engine.stop()
        self._write_settings()
        time.sleep(0.15)
        e.accept()


def dark_title_bar(win):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(win.winId())
        on = ctypes.c_int(1)
        for attr in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
        caption = ctypes.c_int(0x0015110F)                       # BG colour as COLORREF (Win11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WizMusicSync.App")  # taskbar icon
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans"])
    f.setPointSizeF(9.5)
    f.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(f)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    w = MainWindow()
    w.resize(1060, 700)
    w.setMinimumSize(980, 660)
    dark_title_bar(w)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
