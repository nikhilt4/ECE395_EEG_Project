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

# ─────────────────────────────────────────────
#  PARAMETERS — tweak these
# ─────────────────────────────────────────────

# Window
WIDTH, HEIGHT = 600, 700
FPS           = 60

# Lanes
NUM_LANES     = 5          # number of lanes on screen

# Obstacle scroll speed (px per frame)
OBSTACLE_SPEED_START = 1.5   # starting scroll speed
OBSTACLE_SPEED_MAX   = 4.0   # max scroll speed over time
OBSTACLE_SPEED_RAMP  = 0.005  # how fast speed increases per frame

# Spawning
SPAWN_INTERVAL_START = 150   # frames between obstacle waves at start
SPAWN_INTERVAL_MIN   = 60    # minimum spawn interval (harder cap)
SPAWN_INTERVAL_RAMP  = 0.05  # how fast interval shrinks per frame

# Max simultaneous obstacle columns (leave at least 2 lanes open)
MAX_BLOCKED_LANES    = 3     # never block more than this many at once

# Player movement
MOVE_COOLDOWN_MS     = 700   # ms between allowed lane changes
                              # set higher (e.g. 1500) for EEG use

# EEG command hold time (ms) — how long after eeg_queue fires the
# input counts as "held". Increase if classifier fires short bursts.
EEG_HOLD_MS          = 400

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

# ─────────────────────────────────────────────
#  EEG QUEUE — import this and push into it
#  from your classifier thread
# ─────────────────────────────────────────────
eeg_queue: queue.Queue = queue.Queue()


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
#  Game state
# ─────────────────────────────────────────────
class LaneDodge:
    def __init__(self, screen, fonts):
        self.screen = screen
        self.fonts  = fonts
        self.lane_w = WIDTH // NUM_LANES
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

    # ── Input ──────────────────────────────
    def _drain_eeg(self):
        now = pygame.time.get_ticks()
        while not eeg_queue.empty():
            cmd = eeg_queue.get_nowait()
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

    game = LaneDodge(screen, fonts)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_r:
                    game.reset()

        game.update()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == '__main__':
    main()