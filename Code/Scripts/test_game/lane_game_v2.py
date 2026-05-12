"""
game1_lane_dodge.py — EEG Lane Dodge
======================================
2-class MI BCI game. Player moves between lanes to avoid obstacles.
Left MI = move left one lane | Right MI = move right one lane

EEG HOOK:
    Call eeg_queue.put('left') or eeg_queue.put('right') from your
    classifier thread. The game reads it each frame.

KEYBOARD (for testing):
    Left / Right arrow  — move lane
    R                   — restart
    ESC                 — quit
"""

import pygame
import sys
import queue
import random

import serial
import threading

# ─────────────────────────────────────────────
#  PARAMETERS — tweak these
# ─────────────────────────────────────────────

# Window
WIDTH, HEIGHT = 600, 700
FPS           = 60

# Lanes
NUM_LANES     = 5          # number of lanes on screen

# Obstacle scroll speed (px per frame)
OBSTACLE_SPEED_START = 1.0   # starting scroll speed
OBSTACLE_SPEED_MAX   = 4.0   # max scroll speed over time
OBSTACLE_SPEED_RAMP  = 0.002  # how fast speed increases per frame

# Spawning
SPAWN_INTERVAL_START = 150   # frames between obstacle waves at start
SPAWN_INTERVAL_MIN   = 60    # minimum spawn interval (harder cap)
SPAWN_INTERVAL_RAMP  = 0.05  # how fast interval shrinks per frame

# Max simultaneous obstacle columns (leave at least 2 lanes open)
MAX_BLOCKED_LANES    = 1     # never block more than this many at once

# Player movement
MOVE_COOLDOWN_MS     = 1000   # ms between allowed lane changes
                              # set higher (e.g. 1500) for EEG use

# EEG command hold time (ms) — how long after eeg_queue fires the
# input counts as "held". Increase if classifier fires short bursts.
EEG_HOLD_MS          = 800

RATIO_THRESHOLD = 0.30
LEFT_THRESHOLD  = 0.20   # easier to trigger LEFT (compensate for right bias)
RIGHT_THRESHOLD = 0.45   # harder to trigger RIGHT

# Colors (R, G, B)
COLOR_BG             = (18,  18,  30)
COLOR_LANE_HIGHLIGHT = (30,  40,  70)
COLOR_LANE_LINE      = (255, 255, 255)
COLOR_OBSTACLE       = (180,  40,  40)
COLOR_OBSTACLE_STRIPE= (240, 100, 100)
COLOR_CAR_BODY       = (30,  80, 160)
COLOR_CAR_WINDOW     = (80, 160, 230)
COLOR_CAR_WHEEL      = (15,  15,  15)
COLOR_COOLDOWN_READY = (40,  90,  40)
COLOR_COOLDOWN_WAIT  = (25,  25,  25)
COLOR_TEXT           = (200, 200, 200)
COLOR_TEXT_DIM       = (80,  80,  80)
COLOR_GAMEOVER_BG    = (0,   0,   0)   # overlay (uses alpha)

SERIAL_PORT = "COM5"       # change to your port
SERIAL_BAUD = 460800


# ─────────────────────────────────────────────
#  EEG QUEUE — import this and push into it
#  from your classifier thread
# ─────────────────────────────────────────────
eeg_queue: queue.Queue = queue.Queue()



#  Helpers
def draw_rounded_rect(surface, color, rect, radius=6):
    pygame.draw.rect(surface, color, rect, border_radius=radius)

def draw_text(surface, text, x, y, font, color=None):
    color = color or COLOR_TEXT
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def draw_text_centered(surface, text, cx, y, font, color=None):
    color = color or COLOR_TEXT
    img = font.render(text, True, color)
    surface.blit(img, (cx - img.get_width() // 2, y))



#  Game state

class LaneDodge:
    def __init__(self, screen, fonts):
        self.screen = screen
        self.fonts  = fonts
        self.lane_w = WIDTH // NUM_LANES
        # Initialize EEG state here so reset() can preserve it
        self.eeg_ready         = False
        self.baseline_progress = "waiting..."
        self.reset()

    def reset(self):
        self.player_lane  = NUM_LANES // 2
        self.obstacles    = []          # list of {lane, y, w, h}
        self.scroll_speed = OBSTACLE_SPEED_START
        self.spawn_interval = SPAWN_INTERVAL_START
        self.spawn_timer  = 0
        self.tick         = 0
        self.score        = 0
        self.best         = getattr(self, 'best', 0)
        self.game_over    = False
        self.last_move_ms = 0           # timestamp of last lane change
        self.eeg_last     = {'left': 0, 'right': 0}  # last EEG command time
        # self.eeg_ready = False
        # self.baseline_progress = "waiting..."
        
    def full_reset(self):
        self.reset()
        self.eeg_ready         = False
        self.baseline_progress = "waiting..."

    # ── Input ──────────────────────────────
    def _drain_eeg(self):
        now = pygame.time.get_ticks()
        while not eeg_queue.empty():
            cmd = eeg_queue.get_nowait()
            # if cmd == "baseline_done":
            #     self.eeg_ready = True
            #     continue
            # if cmd in self.eeg_last:
            #     self.eeg_last[cmd] = now
            if cmd == "baseline_done":
                self.eeg_ready = True
                continue
            if isinstance(cmd, tuple) and cmd[0] == "baseline_progress":
                self.baseline_progress = cmd[1]
                continue
            if cmd in self.eeg_last:
                self.eeg_last[cmd] = now


    def _input_left(self):
        now = pygame.time.get_ticks()
        keys = pygame.key.get_pressed()
        return (keys[pygame.K_LEFT] or
                now - self.eeg_last['left'] < EEG_HOLD_MS)

    def _input_right(self):
        now = pygame.time.get_ticks()
        keys = pygame.key.get_pressed()
        return (keys[pygame.K_RIGHT] or
                now - self.eeg_last['right'] < EEG_HOLD_MS)

    # ── Update ─────────────────────────────
    def update(self):
        self._drain_eeg()
        
        if not self.eeg_ready:
            return

        if self.game_over:
            return

        self.tick += 1
        self.score = self.tick // FPS   # score = seconds survived

        # Ramp difficulty
        self.scroll_speed   = min(OBSTACLE_SPEED_MAX,
                                  OBSTACLE_SPEED_START + self.tick * OBSTACLE_SPEED_RAMP)
        self.spawn_interval = max(SPAWN_INTERVAL_MIN,
                                  SPAWN_INTERVAL_START - self.tick * SPAWN_INTERVAL_RAMP)

        # Lane change with cooldown
        now = pygame.time.get_ticks()
        if now - self.last_move_ms >= MOVE_COOLDOWN_MS:
            moved = False
            if self._input_left() and self.player_lane > 0:
                self.player_lane -= 1
                moved = True
            elif self._input_right() and self.player_lane < NUM_LANES - 1:
                self.player_lane += 1
                moved = True
            if moved:
                self.last_move_ms = now

        # Spawn obstacles
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            n_block = random.randint(1, min(MAX_BLOCKED_LANES, NUM_LANES - 2))
            blocked = random.sample(range(NUM_LANES), n_block)
            for lane in blocked:
                self.obstacles.append({
                    'lane': lane,
                    'y':    -40,
                    'w':    self.lane_w - 10,
                    'h':    32,
                })

        # Scroll obstacles
        for o in self.obstacles:
            o['y'] += self.scroll_speed
        self.obstacles = [o for o in self.obstacles if o['y'] < HEIGHT + 50]

        # Collision check (AABB on center points)
        player_cx = self.player_lane * self.lane_w + self.lane_w // 2
        player_cy = HEIGHT - 90
        for o in self.obstacles:
            obs_cx = o['lane'] * self.lane_w + self.lane_w // 2
            obs_cy = o['y'] + o['h'] // 2
            if (abs(player_cx - obs_cx) < self.lane_w * 0.45 and
                    abs(player_cy - obs_cy) < 34):
                self.game_over = True
                self.best = max(self.best, self.score)

    # ── Draw ───────────────────────────────
    def draw(self):
        self.screen.fill(COLOR_BG)

        # Lane highlight for current lane
        highlight = pygame.Surface((self.lane_w, HEIGHT), pygame.SRCALPHA)
        highlight.fill((*COLOR_LANE_HIGHLIGHT, 60))
        self.screen.blit(highlight, (self.player_lane * self.lane_w, 0))

        # Lane dividers (dashed, scrolling)
        dash_len, gap_len = 28, 20
        offset = int(self.tick * self.scroll_speed) % (dash_len + gap_len)
        for i in range(1, NUM_LANES):
            x = i * self.lane_w
            y = -gap_len + offset
            while y < HEIGHT:
                pygame.draw.line(self.screen, (*COLOR_LANE_LINE, 25),
                                 (x, y), (x, y + dash_len), 1)
                y += dash_len + gap_len

        # Cooldown bar at bottom
        now = pygame.time.get_ticks()
        cd_ratio = min(1.0, (now - self.last_move_ms) / MOVE_COOLDOWN_MS)
        bar_color = COLOR_COOLDOWN_READY if cd_ratio >= 1.0 else COLOR_COOLDOWN_WAIT
        pygame.draw.rect(self.screen, (30, 30, 30), (0, HEIGHT - 5, WIDTH, 5))
        pygame.draw.rect(self.screen, bar_color,
                         (0, HEIGHT - 5, int(WIDTH * cd_ratio), 5))

        # Obstacles
        for o in self.obstacles:
            ox = o['lane'] * self.lane_w + 5
            draw_rounded_rect(self.screen, COLOR_OBSTACLE,
                               pygame.Rect(ox, int(o['y']), o['w'], o['h']), 5)
            # stripe detail
            pygame.draw.rect(self.screen, COLOR_OBSTACLE_STRIPE,
                             (ox + 5, int(o['y']) + 7, o['w'] - 10, 6))
            pygame.draw.rect(self.screen, COLOR_OBSTACLE_STRIPE,
                             (ox + 5, int(o['y']) + 17, o['w'] - 10, 4))

        # Player car
        if not self.game_over or (self.tick // 5) % 2 == 0:
            px = self.player_lane * self.lane_w + 5
            py = HEIGHT - 110
            cw, ch = self.lane_w - 10, 50
            # body
            draw_rounded_rect(self.screen, COLOR_CAR_BODY,
                               pygame.Rect(px, py, cw, ch), 6)
            # windows
            pygame.draw.rect(self.screen, COLOR_CAR_WINDOW,
                             (px + 6, py + 7, cw - 12, 14))
            # wheels
            for wx, wy in [(px, py + 2), (px + cw - 9, py + 2),
                           (px, py + ch - 12), (px + cw - 9, py + ch - 12)]:
                pygame.draw.rect(self.screen, COLOR_CAR_WHEEL,
                                 (wx, wy, 9, 10))

        # HUD
        draw_text(self.screen, f"Score: {self.score}",  10, 10,
                  self.fonts['md'])
        draw_text(self.screen, f"Best:  {self.best}",   10, 36,
                  self.fonts['md'], COLOR_TEXT_DIM)
        draw_text(self.screen, f"Speed: {self.scroll_speed:.2f}", 10, 62,
                  self.fonts['sm'], COLOR_TEXT_DIM)

        cd_ms = max(0, int(MOVE_COOLDOWN_MS - (now - self.last_move_ms)))
        if cd_ms > 0:
            draw_text_centered(self.screen, f"cooldown {cd_ms}ms",
                               WIDTH // 2, HEIGHT - 22,
                               self.fonts['sm'], COLOR_TEXT_DIM)

        # Game over overlay
        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            draw_text_centered(self.screen, "GAME OVER",
                               WIDTH // 2, HEIGHT // 2 - 36,
                               self.fonts['lg'], (220, 80, 80))
            draw_text_centered(self.screen, f"Score: {self.score}",
                               WIDTH // 2, HEIGHT // 2 + 4,
                               self.fonts['md'])
            draw_text_centered(self.screen, "R to restart  |  ESC to quit",
                               WIDTH // 2, HEIGHT // 2 + 38,
                               self.fonts['sm'], COLOR_TEXT_DIM)
            
        
        if not self.eeg_ready:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, 0))
            draw_text_centered(self.screen, "Calibrating...",
                            WIDTH // 2, HEIGHT // 2 - 50,
                            self.fonts['lg'], (200, 200, 100))
            draw_text_centered(self.screen, "Sit still. Hands in lap.",
                            WIDTH // 2, HEIGHT // 2,
                            self.fonts['md'], COLOR_TEXT)
            draw_text_centered(self.screen, "Eyes open. Think of nothing.",
                            WIDTH // 2, HEIGHT // 2 + 30,
                            self.fonts['md'], COLOR_TEXT)
            draw_text_centered(self.screen, "Do NOT imagine moving your hands yet.",
                            WIDTH // 2, HEIGHT // 2 + 65,
                            self.fonts['sm'], (180, 120, 120))
            draw_text_centered(self.screen, f"{self.baseline_progress}",
                WIDTH // 2, HEIGHT // 2 + 100,
                self.fonts['sm'], COLOR_TEXT_DIM)


# ─────────────────────────────────────────────
#  EEG SERIAL READER THREAD
#  Reads BP,<ratio>,<class> lines from STM32
#  and pushes 'left' / 'right' into eeg_queue
# ─────────────────────────────────────────────


_serial_stop = threading.Event()

def eeg_serial_thread():
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1.0)
        print(f"[EEG] Connected on {SERIAL_PORT}")
    except serial.SerialException as e:
        print(f"[EEG] Could not open serial port: {e}")
        print("[EEG] Running in keyboard-only mode")
        return

    print("[EEG] Waiting for STM32 READY...")
    for _ in range(30):
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        print(f"[STM boot] {line}")
        if "READY" in line:
            break

    ser.write(b"START\n")
    ser.flush()
    print("[EEG] START sent, streaming...")

    try:
        while not _serial_stop.is_set():
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("I,"):
                    msg = line[2:]
                    print(f"[STM] {msg}")
                    if "BASELINE_DONE" in msg:
                        eeg_queue.put("baseline_done")   # signal the game
                    elif "BASELINE" in msg:
                        eeg_queue.put(("baseline_progress", msg))   
                    continue
                if line.startswith("BP,"):
                    parts = line.split(",")
                    if len(parts) != 3:
                        continue
                    try:
                        cls = int(parts[2])
                    except ValueError:
                        continue
                    
                    
                    if cls == 1:
                        eeg_queue.put("left")
                        print(f"[EEG] LEFT  (ratio={parts[1]})")
                    elif cls == 2:
                        eeg_queue.put("right")
                        print(f"[EEG] RIGHT (ratio={parts[1]})")
                    
                    
                    # ratio = float(parts[1])
                    # if ratio > RATIO_THRESHOLD:
                    #     eeg_queue.put("left")
                    #     print(f"[EEG] LEFT  (ratio={ratio:+.4f})")
                    # elif ratio < -RATIO_THRESHOLD:
                    #     eeg_queue.put("right")
                    #     print(f"[EEG] RIGHT (ratio={ratio:+.4f})")
                        
                    
                    # if ratio > LEFT_THRESHOLD:
                    #     eeg_queue.put("left")
                    #     print(f"[EEG] LEFT  (ratio={ratio:+.4f})")
                    # elif ratio < -RIGHT_THRESHOLD:
                    #     eeg_queue.put("right")
                    #     print(f"[EEG] RIGHT (ratio={ratio:+.4f})")
                        
                        
                        
            except serial.SerialException as e:
                print(f"[EEG] Serial error: {e}")
                break
    finally:
        try:
            ser.write(b"STOP\n")
            ser.flush()
            print("[EEG] STOP sent")
        except Exception:
            pass
        ser.close()
        print("[EEG] Serial port closed")

# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("EEG — Lane Dodge")
    clock = pygame.time.Clock()

    fonts = {
        'lg': pygame.font.SysFont(None, 48),
        'md': pygame.font.SysFont(None, 30),
        'sm': pygame.font.SysFont(None, 22),
    }

    # START EEG THREAD — add these two lines
    t = threading.Thread(target=eeg_serial_thread, daemon=True)
    t.start()

    game = LaneDodge(screen, fonts)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _serial_stop.set()
                t.join(timeout=2.0)
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    _serial_stop.set()
                    t.join(timeout=2.0)
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_r:
                    game.reset()

        game.update()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == '__main__':
    main()