"""
game5_neurofeedback.py — EEG Neurofeedback Monitor
=====================================================
Not a game — a real-time signal monitor for validating your EEG
pipeline before running the games. Shows:

  - Left / Right classifier probability bars (live)
  - Rolling waveform of both channels over time
  - Predicted class label + confidence
  - Trial log (last N classifications with timestamps)
  - Basic stats: mean, std, threshold crossings

Feed it from your classifier using either queue:

  Option A — discrete labels:
      eeg_queue.put('left')
      eeg_queue.put('right')

  Option B — continuous probabilities (recommended):
      eeg_prob_queue.put((left_prob, right_prob))
      e.g. eeg_prob_queue.put((0.82, 0.18))

KEYBOARD:
    C     — clear trial log
    S     — print stats to terminal
    ESC   — quit
"""

import pygame
import sys
import queue
import collections
import time

# ─────────────────────────────────────────────
#  PARAMETERS
# ─────────────────────────────────────────────

WIDTH, HEIGHT        = 720, 580
FPS                  = 60

# Waveform
WAVEFORM_HISTORY     = 300    # samples shown in rolling waveform
WAVEFORM_HEIGHT      = 110    # px height of waveform panel
SMOOTHING            = 0.12   # exponential smoothing on bars (0=instant, 1=frozen)

# Classification threshold
THRESHOLD            = 0.60   # probability must exceed this to count as a class event

# Trial log
MAX_LOG_ENTRIES      = 12     # number of trial rows shown on screen

# Colors
COLOR_BG             = (10,  10,  20)
COLOR_PANEL          = (16,  16,  30)
COLOR_PANEL_BORDER   = (40,  40,  65)
COLOR_LEFT           = (55, 138, 221)
COLOR_RIGHT          = (220, 65,  65)
COLOR_LEFT_DIM       = (25,  60, 110)
COLOR_RIGHT_DIM      = (110, 30,  30)
COLOR_THRESHOLD_LINE = (180, 180,  60)
COLOR_TEXT           = (200, 200, 200)
COLOR_TEXT_DIM       = (70,  70,  95)
COLOR_TEXT_GOOD      = (60, 210,  80)
COLOR_TEXT_BAD       = (210, 60,  60)
COLOR_GRID           = (28,  28,  45)
COLOR_LABEL_LEFT     = (30,  90, 180)
COLOR_LABEL_RIGHT    = (160, 30,  30)

# ─────────────────────────────────────────────
#  EEG QUEUES
# ─────────────────────────────────────────────
eeg_queue:      queue.Queue = queue.Queue()   # put('left') / put('right')
eeg_prob_queue: queue.Queue = queue.Queue()   # put((left_prob, right_prob))


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def rr(surface, color, rect, radius=5, width=0):
    if rect.width > 0 and rect.height > 0:
        pygame.draw.rect(surface, color, rect, width, border_radius=radius)

def txt(surface, text, x, y, font, color=None):
    surface.blit(font.render(text, True, color or COLOR_TEXT), (x, y))

def txt_c(surface, text, cx, y, font, color=None):
    img = font.render(text, True, color or COLOR_TEXT)
    surface.blit(img, (cx - img.get_width()//2, y))

def txt_r(surface, text, rx, y, font, color=None):
    img = font.render(text, True, color or COLOR_TEXT)
    surface.blit(img, (rx - img.get_width(), y))


# ─────────────────────────────────────────────
#  Monitor
# ─────────────────────────────────────────────
class NeurofeedbackMonitor:
    def __init__(self, screen, fonts):
        self.screen = screen
        self.fonts  = fonts
        self.reset()

    def reset(self):
        # Smoothed display values
        self.disp_l = 0.0
        self.disp_r = 0.0

        # Raw probability histories for waveform
        self.hist_l = collections.deque([0.0] * WAVEFORM_HISTORY,
                                        maxlen=WAVEFORM_HISTORY)
        self.hist_r = collections.deque([0.0] * WAVEFORM_HISTORY,
                                        maxlen=WAVEFORM_HISTORY)

        # Current raw probabilities
        self.raw_l = 0.0
        self.raw_r = 0.0

        # Last classified label
        self.last_label      = None
        self.last_confidence = 0.0
        self.label_flash     = 0       # countdown frames for label highlight

        # Trial log: list of (timestamp_str, label, confidence)
        self.trial_log = collections.deque(maxlen=MAX_LOG_ENTRIES)

        # Stats
        self.n_left  = 0
        self.n_right = 0
        self.all_l   = []   # all left probs received
        self.all_r   = []   # all right probs received

        self.eeg_last = {'left': 0, 'right': 0}

    # ── Drain queues ───────────────────────
    def _drain(self):
        now_ms = pygame.time.get_ticks()

        # Discrete label queue
        while not eeg_queue.empty():
            cmd = eeg_queue.get_nowait()
            if cmd == 'left':
                self.raw_l = 1.0
                self.raw_r = 0.0
                self.eeg_last['left'] = now_ms
                self._register_event('left', 1.0)
            elif cmd == 'right':
                self.raw_l = 0.0
                self.raw_r = 1.0
                self.eeg_last['right'] = now_ms
                self._register_event('right', 1.0)

        # Probability queue
        while not eeg_prob_queue.empty():
            lp, rp = eeg_prob_queue.get_nowait()
            self.raw_l = float(lp)
            self.raw_r = float(rp)
            self.all_l.append(lp)
            self.all_r.append(rp)
            if lp >= THRESHOLD and lp > rp:
                self._register_event('left', lp)
            elif rp >= THRESHOLD and rp > lp:
                self._register_event('right', rp)

    def _register_event(self, label, confidence):
        self.last_label      = label
        self.last_confidence = confidence
        self.label_flash     = 45
        ts = time.strftime('%H:%M:%S')
        self.trial_log.append((ts, label, confidence))
        if label == 'left':
            self.n_left  += 1
        else:
            self.n_right += 1

    # ── Update ─────────────────────────────
    def update(self):
        self._drain()

        # Smooth display bars
        self.disp_l += (self.raw_l - self.disp_l) * (1 - SMOOTHING)
        self.disp_r += (self.raw_r - self.disp_r) * (1 - SMOOTHING)

        # Push to waveform history every frame
        self.hist_l.append(self.raw_l)
        self.hist_r.append(self.raw_r)

        # Decay raw (simulate signal fading if no new data)
        self.raw_l = max(0.0, self.raw_l - 0.008)
        self.raw_r = max(0.0, self.raw_r - 0.008)

        if self.label_flash > 0:
            self.label_flash -= 1

    # ── Draw ───────────────────────────────
    def draw(self):
        self.screen.fill(COLOR_BG)
        W, H = WIDTH, HEIGHT
        pad  = 16

        # ── Title bar ──
        title_h = 36
        rr(self.screen, COLOR_PANEL, pygame.Rect(0, 0, W, title_h))
        txt_c(self.screen, "EEG NEUROFEEDBACK MONITOR",
              W//2, 10, self.fonts['sm'], COLOR_TEXT_DIM)

        y = title_h + pad

        # ── Big probability bars ──
        bar_section_h = 120
        bar_w         = int(W * 0.30)
        bar_h         = 70
        bar_y         = y + 28

        # Left bar
        lx = pad
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(lx, y, bar_w, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(lx, y, bar_w, bar_section_h), 8, 1)
        txt_c(self.screen, "LEFT MI", lx + bar_w//2, y + 8,
              self.fonts['sm'], COLOR_LEFT)
        # background track
        rr(self.screen, COLOR_LEFT_DIM,
           pygame.Rect(lx + 10, bar_y, bar_w - 20, bar_h), 5)
        # fill
        fill_w = int((bar_w - 20) * max(0, min(1, self.disp_l)))
        if fill_w > 0:
            rr(self.screen, COLOR_LEFT,
               pygame.Rect(lx + 10, bar_y, fill_w, bar_h), 5)
        # threshold line
        thr_x = lx + 10 + int((bar_w - 20) * THRESHOLD)
        pygame.draw.line(self.screen, COLOR_THRESHOLD_LINE,
                         (thr_x, bar_y - 4), (thr_x, bar_y + bar_h + 4), 2)
        txt_c(self.screen, f"{self.disp_l:.2f}",
              lx + bar_w//2, bar_y + bar_h + 6,
              self.fonts['md'], COLOR_LEFT if self.disp_l > THRESHOLD else COLOR_TEXT_DIM)

        # Right bar
        rx = W - pad - bar_w
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(rx, y, bar_w, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(rx, y, bar_w, bar_section_h), 8, 1)
        txt_c(self.screen, "RIGHT MI", rx + bar_w//2, y + 8,
              self.fonts['sm'], COLOR_RIGHT)
        rr(self.screen, COLOR_RIGHT_DIM,
           pygame.Rect(rx + 10, bar_y, bar_w - 20, bar_h), 5)
        fill_w = int((bar_w - 20) * max(0, min(1, self.disp_r)))
        if fill_w > 0:
            rr(self.screen, COLOR_RIGHT,
               pygame.Rect(rx + 10, bar_y, fill_w, bar_h), 5)
        thr_x = rx + 10 + int((bar_w - 20) * THRESHOLD)
        pygame.draw.line(self.screen, COLOR_THRESHOLD_LINE,
                         (thr_x, bar_y - 4), (thr_x, bar_y + bar_h + 4), 2)
        txt_c(self.screen, f"{self.disp_r:.2f}",
              rx + bar_w//2, bar_y + bar_h + 6,
              self.fonts['md'], COLOR_RIGHT if self.disp_r > THRESHOLD else COLOR_TEXT_DIM)

        # ── Center: current label ──
        cx = W // 2
        cw = W - (bar_w + pad) * 2 - pad * 2
        cl = bar_w + pad * 2
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(cl, y, cw, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(cl, y, cw, bar_section_h), 8, 1)
        txt_c(self.screen, "CURRENT CLASS",
              cx, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        if self.last_label:
            col   = COLOR_LEFT if self.last_label == 'left' else COLOR_RIGHT
            alpha = max(80, int(255 * (self.label_flash / 45))) if self.label_flash > 0 else 120
            label_str = '← LEFT' if self.last_label == 'left' else 'RIGHT →'
            img = self.fonts['lg'].render(label_str, True, col)
            s   = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            s.blit(img, (0,0))
            s.set_alpha(alpha)
            self.screen.blit(s, (cx - img.get_width()//2, y + 32))
            txt_c(self.screen, f"conf {self.last_confidence:.2f}",
                  cx, y + 86, self.fonts['sm'], COLOR_TEXT_DIM)
        else:
            txt_c(self.screen, "waiting...",
                  cx, y + 50, self.fonts['md'], COLOR_TEXT_DIM)

        y += bar_section_h + pad

        # ── Waveform ──
        wf_rect = pygame.Rect(pad, y, W - pad*2, WAVEFORM_HEIGHT)
        rr(self.screen, COLOR_PANEL, wf_rect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, wf_rect, 6, 1)
        txt(self.screen, "Probability waveform",
            pad + 8, y + 6, self.fonts['sm'], COLOR_TEXT_DIM)

        # Grid lines at 0.25, 0.5, 0.75
        for frac in (0.25, 0.50, 0.75):
            gy = y + WAVEFORM_HEIGHT - int(frac * (WAVEFORM_HEIGHT - 22)) - 8
            pygame.draw.line(self.screen, COLOR_GRID,
                             (pad + 4, gy), (W - pad - 4, gy), 1)
            txt(self.screen, f"{frac:.2f}", pad + 4, gy - 9,
                self.fonts['sm'], COLOR_GRID)

        # Threshold line
        thr_y = y + WAVEFORM_HEIGHT - int(THRESHOLD * (WAVEFORM_HEIGHT - 22)) - 8
        pygame.draw.line(self.screen, COLOR_THRESHOLD_LINE,
                         (pad + 4, thr_y), (W - pad - 4, thr_y), 1)
        txt_r(self.screen, f"thr {THRESHOLD:.2f}",
              W - pad - 6, thr_y - 10, self.fonts['sm'], COLOR_THRESHOLD_LINE)

        # Draw waveform lines
        wf_w    = W - pad*2 - 8
        wf_x0   = pad + 4
        wf_ybot = y + WAVEFORM_HEIGHT - 8
        wf_yh   = WAVEFORM_HEIGHT - 22

        def wf_pts(hist):
            pts = []
            for i, v in enumerate(hist):
                px = wf_x0 + int(i / WAVEFORM_HISTORY * wf_w)
                py = wf_ybot - int(v * wf_yh)
                pts.append((px, py))
            return pts

        pts_l = wf_pts(self.hist_l)
        pts_r = wf_pts(self.hist_r)
        if len(pts_l) > 1:
            pygame.draw.lines(self.screen, COLOR_LEFT_DIM, False, pts_l, 2)
        if len(pts_r) > 1:
            pygame.draw.lines(self.screen, COLOR_RIGHT_DIM, False, pts_r, 2)
        # Bright tip
        if pts_l: pygame.draw.circle(self.screen, COLOR_LEFT,   pts_l[-1], 4)
        if pts_r: pygame.draw.circle(self.screen, COLOR_RIGHT,  pts_r[-1], 4)

        y += WAVEFORM_HEIGHT + pad

        # ── Trial log + stats side by side ──
        log_w  = int((W - pad*3) * 0.60)
        stat_w = W - pad*3 - log_w
        log_h  = H - y - pad
        stat_h = log_h

        # Trial log
        log_rect = pygame.Rect(pad, y, log_w, log_h)
        rr(self.screen, COLOR_PANEL, log_rect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, log_rect, 6, 1)
        txt(self.screen, "Trial log",
            pad + 8, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        row_h = 20
        for i, (ts, label, conf) in enumerate(reversed(self.trial_log)):
            ry = y + 28 + i * row_h
            if ry + row_h > y + log_h - 6:
                break
            col = COLOR_LABEL_LEFT if label == 'left' else COLOR_LABEL_RIGHT
            arrow = '←' if label == 'left' else '→'
            txt(self.screen, ts,              pad + 8,  ry, self.fonts['sm'], COLOR_TEXT_DIM)
            txt(self.screen, f"{arrow} {label.upper()}", pad + 80, ry, self.fonts['sm'], col)
            txt_r(self.screen, f"{conf:.2f}",
                  pad + log_w - 8, ry, self.fonts['sm'], COLOR_TEXT_DIM)

        # Stats
        sx    = pad*2 + log_w
        srect = pygame.Rect(sx, y, stat_w, stat_h)
        rr(self.screen, COLOR_PANEL, srect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, srect, 6, 1)
        txt(self.screen, "Stats",
            sx + 8, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        total    = self.n_left + self.n_right
        bal_pct  = (self.n_left / total * 100) if total > 0 else 0
        avg_l    = (sum(self.all_l) / len(self.all_l)) if self.all_l else 0
        avg_r    = (sum(self.all_r) / len(self.all_r)) if self.all_r else 0
        import math
        std_l    = (math.sqrt(sum((x-avg_l)**2 for x in self.all_l)/len(self.all_l))
                    if len(self.all_l) > 1 else 0)
        std_r    = (math.sqrt(sum((x-avg_r)**2 for x in self.all_r)/len(self.all_r))
                    if len(self.all_r) > 1 else 0)

        stat_lines = [
            ("Events",   f"{total}"),
            ("Left",     f"{self.n_left}"),
            ("Right",    f"{self.n_right}"),
            ("Balance",  f"{bal_pct:.0f}% L"),
            ("Mean L",   f"{avg_l:.3f}"),
            ("Mean R",   f"{avg_r:.3f}"),
            ("Std L",    f"{std_l:.3f}"),
            ("Std R",    f"{std_r:.3f}"),
            ("Thresh",   f"{THRESHOLD:.2f}"),
        ]
        for i, (label, val) in enumerate(stat_lines):
            ry = y + 28 + i * 22
            txt(self.screen, label, sx + 8,           ry, self.fonts['sm'], COLOR_TEXT_DIM)
            txt_r(self.screen, val, sx + stat_w - 8,  ry, self.fonts['sm'], COLOR_TEXT)

        # ── Footer ──
        txt_c(self.screen, "C = clear log   S = print stats   ESC = quit",
              W//2, H - 16, self.fonts['sm'], COLOR_TEXT_DIM)

    def print_stats(self):
        total = self.n_left + self.n_right
        print("\n" + "="*40)
        print("NEUROFEEDBACK STATS")
        print("="*40)
        print(f"  Total events : {total}")
        print(f"  Left  events : {self.n_left}")
        print(f"  Right events : {self.n_right}")
        if self.all_l:
            import math
            avg_l = sum(self.all_l)/len(self.all_l)
            avg_r = sum(self.all_r)/len(self.all_r) if self.all_r else 0
            std_l = math.sqrt(sum((x-avg_l)**2 for x in self.all_l)/len(self.all_l))
            print(f"  Left  prob mean±std : {avg_l:.3f} ± {std_l:.3f}")
            print(f"  Right prob mean     : {avg_r:.3f}")
        print("="*40 + "\n")


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("EEG — Neurofeedback Monitor")
    clock  = pygame.time.Clock()

    fonts = {
        'lg': pygame.font.SysFont(None, 48),
        'md': pygame.font.SysFont(None, 30),
        'sm': pygame.font.SysFont(None, 20),
    }

    monitor = NeurofeedbackMonitor(screen, fonts)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_c:
                    monitor.trial_log.clear()
                    monitor.n_left = 0
                    monitor.n_right = 0
                if event.key == pygame.K_s:
                    monitor.print_stats()

        monitor.update()
        monitor.draw()
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == '__main__':
    main()
