"""
game5_neurofeedback.py — EEG Neurofeedback Monitor (BLE version)
==================================================================
Run before games to validate your EEG pipeline. Connects to STM32WB55
over BLE, waits for baseline_done, then displays live ERD ratio and
LEFT/RIGHT classifications in real time.

KEYBOARD:
    C     — clear trial log
    S     — print stats to terminal
    R     — send RECALIBRATE to MCU (redo baseline)
    LEFT  — fake LEFT event (for offline testing)
    RIGHT — fake RIGHT event
    SPACE — fake REST event
    B     — force baseline_done (offline testing)
    ESC   — quit
"""

import pygame
import sys
import queue
import collections
import time

import eeg_ble

# ─────────────────────────────────────────────
#  PARAMETERS
# ─────────────────────────────────────────────
WIDTH, HEIGHT        = 720, 600
FPS                  = 60

WAVEFORM_HISTORY     = 300
WAVEFORM_HEIGHT      = 110
SMOOTHING            = 0.12
THRESHOLD            = 0.60
MAX_LOG_ENTRIES      = 12

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
#  Queues — populated by eeg_ble background thread
# ─────────────────────────────────────────────
eeg_queue:      queue.Queue = queue.Queue()
eeg_prob_queue: queue.Queue = queue.Queue()


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
        self.disp_l      = 0.0
        self.disp_r      = 0.0
        self.raw_l       = 0.0
        self.raw_r       = 0.0
        self.last_ratio  = 0.0

        self.hist_l = collections.deque([0.0]*WAVEFORM_HISTORY,
                                        maxlen=WAVEFORM_HISTORY)
        self.hist_r = collections.deque([0.0]*WAVEFORM_HISTORY,
                                        maxlen=WAVEFORM_HISTORY)
        self.hist_ratio = collections.deque([0.0]*WAVEFORM_HISTORY,
                                            maxlen=WAVEFORM_HISTORY)

        self.last_label      = None
        self.last_confidence = 0.0
        self.label_flash     = 0

        self.trial_log = collections.deque(maxlen=MAX_LOG_ENTRIES)

        self.n_left   = 0
        self.n_right  = 0
        self.n_rest   = 0
        self.all_ratios = []

        self.eeg_ready         = False
        self.baseline_progress = "waiting..."
        self.last_info         = ""

    def _drain(self):
        # Drain status / event items
        while not eeg_queue.empty():
            item = eeg_queue.get_nowait()
            if not isinstance(item, tuple):
                # plain strings ("left"/"right"/"baseline_done") — ignore here,
                # we use the prob_queue path for classification events
                if item == "baseline_done":
                    self.eeg_ready = True
                    self.baseline_progress = "DONE"
                continue

            kind = item[0]
            if kind == "baseline_done":
                self.eeg_ready = True
                self.baseline_progress = "DONE"
            elif kind == "baseline_progress":
                self.baseline_progress = item[1]
            elif kind == "info":
                self.last_info = item[1]

        # Drain probability/ratio data
        while not eeg_prob_queue.empty():
            left_prob, right_prob, ratio, cls = eeg_prob_queue.get_nowait()

            self.raw_l      = left_prob
            self.raw_r      = right_prob
            self.last_ratio = ratio
            self.all_ratios.append(ratio)
            self.hist_ratio.append(ratio)

            if cls == 1:
                self._register_event('left',  abs(ratio))
            elif cls == 2:
                self._register_event('right', abs(ratio))
            else:
                self.n_rest += 1

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

    def update(self):
        self._drain()

        self.disp_l += (self.raw_l - self.disp_l) * (1 - SMOOTHING)
        self.disp_r += (self.raw_r - self.disp_r) * (1 - SMOOTHING)

        self.hist_l.append(self.raw_l)
        self.hist_r.append(self.raw_r)

        self.raw_l = max(0.0, self.raw_l - 0.008)
        self.raw_r = max(0.0, self.raw_r - 0.008)

        if self.label_flash > 0:
            self.label_flash -= 1

    def draw(self):
        self.screen.fill(COLOR_BG)
        W, H = WIDTH, HEIGHT
        pad  = 16

        title_h = 36
        rr(self.screen, COLOR_PANEL, pygame.Rect(0, 0, W, title_h))
        txt_c(self.screen, "EEG NEUROFEEDBACK MONITOR  —  Motor Imagery Validator",
              W//2, 10, self.fonts['sm'], COLOR_TEXT_DIM)

        y = title_h + pad

        if not self.eeg_ready:
            overlay = pygame.Surface((W, H - title_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, title_h))

            txt_c(self.screen, "Calibrating EEG...",
                  W//2, H//2 - 80, self.fonts['lg'], (200, 200, 100))
            txt_c(self.screen, "Sit still.  Hands in lap.",
                  W//2, H//2 - 20, self.fonts['md'], COLOR_TEXT)
            txt_c(self.screen, "Eyes open.  Think of nothing.",
                  W//2, H//2 + 14, self.fonts['md'], COLOR_TEXT)
            txt_c(self.screen, "Do NOT imagine moving your hands yet.",
                  W//2, H//2 + 52, self.fonts['sm'], (180, 120, 120))
            txt_c(self.screen, f"Progress: {self.baseline_progress}",
                  W//2, H//2 + 90, self.fonts['sm'], COLOR_TEXT_DIM)
            txt_c(self.screen, f"STM: {self.last_info}",
                  W//2, H//2 + 114, self.fonts['sm'], COLOR_TEXT_DIM)
            return

        bar_section_h = 120
        bar_w         = int(W * 0.30)
        bar_h         = 70
        bar_y         = y + 28

        lx = pad
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(lx, y, bar_w, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(lx, y, bar_w, bar_section_h), 8, 1)
        txt_c(self.screen, "LEFT MI", lx + bar_w//2, y + 8,
              self.fonts['sm'], COLOR_LEFT)
        rr(self.screen, COLOR_LEFT_DIM,
           pygame.Rect(lx + 10, bar_y, bar_w - 20, bar_h), 5)
        fill_w = int((bar_w - 20) * max(0, min(1, self.disp_l)))
        if fill_w > 0:
            rr(self.screen, COLOR_LEFT,
               pygame.Rect(lx + 10, bar_y, fill_w, bar_h), 5)
        thr_x = lx + 10 + int((bar_w - 20) * THRESHOLD)
        pygame.draw.line(self.screen, COLOR_THRESHOLD_LINE,
                         (thr_x, bar_y - 4), (thr_x, bar_y + bar_h + 4), 2)
        txt_c(self.screen, f"{self.disp_l:.2f}",
              lx + bar_w//2, bar_y + bar_h + 6,
              self.fonts['md'],
              COLOR_LEFT if self.disp_l > THRESHOLD else COLOR_TEXT_DIM)

        rx_bar = W - pad - bar_w
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(rx_bar, y, bar_w, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(rx_bar, y, bar_w, bar_section_h), 8, 1)
        txt_c(self.screen, "RIGHT MI", rx_bar + bar_w//2, y + 8,
              self.fonts['sm'], COLOR_RIGHT)
        rr(self.screen, COLOR_RIGHT_DIM,
           pygame.Rect(rx_bar + 10, bar_y, bar_w - 20, bar_h), 5)
        fill_w = int((bar_w - 20) * max(0, min(1, self.disp_r)))
        if fill_w > 0:
            rr(self.screen, COLOR_RIGHT,
               pygame.Rect(rx_bar + 10, bar_y, fill_w, bar_h), 5)
        thr_x = rx_bar + 10 + int((bar_w - 20) * THRESHOLD)
        pygame.draw.line(self.screen, COLOR_THRESHOLD_LINE,
                         (thr_x, bar_y - 4), (thr_x, bar_y + bar_h + 4), 2)
        txt_c(self.screen, f"{self.disp_r:.2f}",
              rx_bar + bar_w//2, bar_y + bar_h + 6,
              self.fonts['md'],
              COLOR_RIGHT if self.disp_r > THRESHOLD else COLOR_TEXT_DIM)

        cx  = W // 2
        cw  = W - (bar_w + pad) * 2 - pad * 2
        cl  = bar_w + pad * 2
        rr(self.screen, COLOR_PANEL,
           pygame.Rect(cl, y, cw, bar_section_h), 8)
        rr(self.screen, COLOR_PANEL_BORDER,
           pygame.Rect(cl, y, cw, bar_section_h), 8, 1)
        txt_c(self.screen, "CURRENT CLASS",
              cx, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        if self.last_label:
            col = COLOR_LEFT if self.last_label == 'left' else COLOR_RIGHT
            alpha = max(80, int(255 * (self.label_flash / 45))) \
                    if self.label_flash > 0 else 120
            label_str = '← LEFT' if self.last_label == 'left' else 'RIGHT →'
            img = self.fonts['lg'].render(label_str, True, col)
            s   = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            s.blit(img, (0, 0))
            s.set_alpha(alpha)
            self.screen.blit(s, (cx - img.get_width()//2, y + 28))
        else:
            txt_c(self.screen, "REST", cx, y + 38,
                  self.fonts['md'], COLOR_TEXT_DIM)

        ratio_col = COLOR_LEFT if self.last_ratio > 0 else COLOR_RIGHT
        txt_c(self.screen, f"ERD ratio: {self.last_ratio:+.4f}",
              cx, y + 82, self.fonts['sm'], ratio_col)

        y += bar_section_h + pad

        wf_rect = pygame.Rect(pad, y, W - pad*2, WAVEFORM_HEIGHT)
        rr(self.screen, COLOR_PANEL, wf_rect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, wf_rect, 6, 1)
        txt(self.screen, "ERD ratio waveform  (+ = LEFT  /  - = RIGHT)",
            pad + 8, y + 6, self.fonts['sm'], COLOR_TEXT_DIM)

        mid_y = y + WAVEFORM_HEIGHT // 2
        pygame.draw.line(self.screen, COLOR_GRID,
                         (pad + 4, mid_y), (W - pad - 4, mid_y), 1)

        thr_offset = int(THRESHOLD * 0.5 * (WAVEFORM_HEIGHT - 22))
        for sign, color in [(1, COLOR_LEFT_DIM), (-1, COLOR_RIGHT_DIM)]:
            ty = mid_y - sign * thr_offset
            pygame.draw.line(self.screen, color,
                             (pad + 4, ty), (W - pad - 4, ty), 1)

        wf_w  = W - pad*2 - 8
        wf_x0 = pad + 4
        pts   = []
        for i, r in enumerate(self.hist_ratio):
            px = wf_x0 + int(i / WAVEFORM_HISTORY * wf_w)
            py = mid_y - int(r * (WAVEFORM_HEIGHT - 22) * 0.5)
            py = max(y + 4, min(y + WAVEFORM_HEIGHT - 4, py))
            pts.append((px, py))
        if len(pts) > 1:
            pygame.draw.lines(self.screen, COLOR_TEXT_DIM, False, pts, 2)
        if pts:
            dot_col = COLOR_LEFT if self.last_ratio > 0 else COLOR_RIGHT
            pygame.draw.circle(self.screen, dot_col, pts[-1], 4)

        y += WAVEFORM_HEIGHT + pad

        log_w  = int((W - pad*3) * 0.60)
        stat_w = W - pad*3 - log_w
        log_h  = H - y - pad - 20

        log_rect = pygame.Rect(pad, y, log_w, log_h)
        rr(self.screen, COLOR_PANEL, log_rect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, log_rect, 6, 1)
        txt(self.screen, "Classification log",
            pad + 8, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        row_h = 20
        for i, (ts, label, conf) in enumerate(reversed(self.trial_log)):
            ry = y + 28 + i * row_h
            if ry + row_h > y + log_h - 6:
                break
            col   = COLOR_LABEL_LEFT if label == 'left' else COLOR_LABEL_RIGHT
            arrow = '←' if label == 'left' else '→'
            txt(self.screen, ts,
                pad + 8, ry, self.fonts['sm'], COLOR_TEXT_DIM)
            txt(self.screen, f"{arrow} {label.upper()}",
                pad + 80, ry, self.fonts['sm'], col)
            txt_r(self.screen, f"{conf:.3f}",
                  pad + log_w - 8, ry, self.fonts['sm'], COLOR_TEXT_DIM)

        sx    = pad*2 + log_w
        srect = pygame.Rect(sx, y, stat_w, log_h)
        rr(self.screen, COLOR_PANEL, srect, 6)
        rr(self.screen, COLOR_PANEL_BORDER, srect, 6, 1)
        txt(self.screen, "Stats",
            sx + 8, y + 8, self.fonts['sm'], COLOR_TEXT_DIM)

        total   = self.n_left + self.n_right + self.n_rest
        avg_r   = (sum(self.all_ratios)/len(self.all_ratios)) if self.all_ratios else 0
        import math
        std_r   = (math.sqrt(sum((x-avg_r)**2 for x in self.all_ratios)
                             / len(self.all_ratios))
                   if len(self.all_ratios) > 1 else 0)

        stat_lines = [
            ("Windows",  f"{total}"),
            ("LEFT",     f"{self.n_left}"),
            ("RIGHT",    f"{self.n_right}"),
            ("REST",     f"{self.n_rest}"),
            ("Mean ratio", f"{avg_r:+.3f}"),
            ("Std ratio",  f"{std_r:.3f}"),
            ("Last STM",   ""),
        ]
        for i, (label, val) in enumerate(stat_lines):
            ry = y + 28 + i * 22
            txt(self.screen, label,
                sx + 8, ry, self.fonts['sm'], COLOR_TEXT_DIM)
            if val:
                txt_r(self.screen, val,
                      sx + stat_w - 8, ry, self.fonts['sm'], COLOR_TEXT)

        info_y = y + 28 + len(stat_lines) * 22 - 22
        if self.last_info:
            short = self.last_info[:20]
            txt(self.screen, short,
                sx + 8, info_y, self.fonts['sm'], COLOR_TEXT_DIM)

        txt_c(self.screen,
              "C=clear  S=stats  R=recalibrate  ESC=quit",
              W//2, H - 16, self.fonts['sm'], COLOR_TEXT_DIM)

    def print_stats(self):
        total = self.n_left + self.n_right + self.n_rest
        import math
        print("\n" + "="*40)
        print("NEUROFEEDBACK STATS")
        print("="*40)
        print(f"  Total windows : {total}")
        print(f"  LEFT          : {self.n_left}")
        print(f"  RIGHT         : {self.n_right}")
        print(f"  REST          : {self.n_rest}")
        if self.all_ratios:
            avg = sum(self.all_ratios)/len(self.all_ratios)
            std = math.sqrt(sum((x-avg)**2 for x in self.all_ratios)
                            /len(self.all_ratios))
            print(f"  ERD mean±std  : {avg:+.4f} ± {std:.4f}")
            print(f"  Positive (L)  : {sum(1 for r in self.all_ratios if r>0)}")
            print(f"  Negative (R)  : {sum(1 for r in self.all_ratios if r<0)}")
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

    # Start BLE bridge — both queues used
    t = eeg_ble.start_ble_thread(eeg_queue, eeg_prob_queue)

    def shutdown():
        eeg_ble.stop()
        t.join(timeout=3.0)
        pygame.quit()
        sys.exit()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shutdown()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shutdown()

                if event.key == pygame.K_c:
                    monitor.trial_log.clear()
                    monitor.n_left  = 0
                    monitor.n_right = 0
                    monitor.n_rest  = 0

                if event.key == pygame.K_s:
                    monitor.print_stats()

                if event.key == pygame.K_r:
                    eeg_ble.send_recalibrate()
                    monitor.eeg_ready         = False
                    monitor.baseline_progress = "restarting..."
                    monitor.all_ratios.clear()
                    monitor.trial_log.clear()
                    monitor.n_left = monitor.n_right = monitor.n_rest = 0

                if event.key == pygame.K_LEFT:
                    eeg_prob_queue.put((0.8, 0.2, 0.6, 1))

                if event.key == pygame.K_RIGHT:
                    eeg_prob_queue.put((0.2, 0.8, -0.6, 2))

                if event.key == pygame.K_SPACE:
                    eeg_prob_queue.put((0.5, 0.5, 0.0, 0))

                if event.key == pygame.K_b:
                    monitor.eeg_ready = True

        monitor.update()
        monitor.draw()
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == '__main__':
    main()
