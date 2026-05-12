"""
game1_lane_dodge.py — EEG Lane Dodge (BLE version)
====================================================
2-class MI BCI game. Player moves between lanes to avoid obstacles.
Left MI = move left one lane | Right MI = move right one lane

Connects to STM32WB55 over BLE via eeg_ble.py.

KEYBOARD (for testing):
    Left / Right arrow  — move lane
    R                   — restart game
    ESC                 — quit
"""

import pygame
import sys
import queue
import random

import eeg_ble

# ─────────────────────────────────────────────
#  PARAMETERS — unchanged from UART version
# ─────────────────────────────────────────────
WIDTH, HEIGHT = 600, 700
FPS           = 60

NUM_LANES     = 5

OBSTACLE_SPEED_START = 1.0
OBSTACLE_SPEED_MAX   = 4.0
OBSTACLE_SPEED_RAMP  = 0.002

SPAWN_INTERVAL_START = 150
SPAWN_INTERVAL_MIN   = 60
SPAWN_INTERVAL_RAMP  = 0.05

MAX_BLOCKED_LANES    = 1

MOVE_COOLDOWN_MS     = 1800
EEG_HOLD_MS          = 1200

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
COLOR_GAMEOVER_BG    = (0,   0,   0)


# ─────────────────────────────────────────────
#  Queues — populated by eeg_ble background thread
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
        self.eeg_ready         = False
        self.baseline_progress = "waiting..."
        self.reset()

    def reset(self):
        self.player_lane  = NUM_LANES // 2
        self.obstacles    = []
        self.scroll_speed = OBSTACLE_SPEED_START
        self.spawn_interval = SPAWN_INTERVAL_START
        self.spawn_timer  = 0
        self.tick         = 0
        self.score        = 0
        self.best         = getattr(self, 'best', 0)
        self.game_over    = False
        self.last_move_ms = 0
        self.eeg_last     = {'left': 0, 'right': 0}

    def full_reset(self):
        self.reset()
        self.eeg_ready         = False
        self.baseline_progress = "waiting..."

    def _drain_eeg(self):
        now = pygame.time.get_ticks()
        while not eeg_queue.empty():
            cmd = eeg_queue.get_nowait()
            if cmd == "baseline_done":
                self.eeg_ready = True
                continue
            if isinstance(cmd, tuple) and cmd[0] == "baseline_progress":
                self.baseline_progress = cmd[1]
                continue
            # Ignore "info" tuples and anything else neurofeedback-only
            if isinstance(cmd, tuple):
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

    def update(self):
        self._drain_eeg()

        if not self.eeg_ready:
            return

        if self.game_over:
            return

        self.tick += 1
        self.score = self.tick // FPS

        self.scroll_speed   = min(OBSTACLE_SPEED_MAX,
                                  OBSTACLE_SPEED_START + self.tick * OBSTACLE_SPEED_RAMP)
        self.spawn_interval = max(SPAWN_INTERVAL_MIN,
                                  SPAWN_INTERVAL_START - self.tick * SPAWN_INTERVAL_RAMP)

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

        for o in self.obstacles:
            o['y'] += self.scroll_speed
        self.obstacles = [o for o in self.obstacles if o['y'] < HEIGHT + 50]

        player_cx = self.player_lane * self.lane_w + self.lane_w // 2
        player_cy = HEIGHT - 90
        for o in self.obstacles:
            obs_cx = o['lane'] * self.lane_w + self.lane_w // 2
            obs_cy = o['y'] + o['h'] // 2
            if (abs(player_cx - obs_cx) < self.lane_w * 0.45 and
                    abs(player_cy - obs_cy) < 34):
                self.game_over = True
                self.best = max(self.best, self.score)

    def draw(self):
        self.screen.fill(COLOR_BG)

        highlight = pygame.Surface((self.lane_w, HEIGHT), pygame.SRCALPHA)
        highlight.fill((*COLOR_LANE_HIGHLIGHT, 60))
        self.screen.blit(highlight, (self.player_lane * self.lane_w, 0))

        dash_len, gap_len = 28, 20
        offset = int(self.tick * self.scroll_speed) % (dash_len + gap_len)
        for i in range(1, NUM_LANES):
            x = i * self.lane_w
            y = -gap_len + offset
            while y < HEIGHT:
                pygame.draw.line(self.screen, (*COLOR_LANE_LINE, 25),
                                 (x, y), (x, y + dash_len), 1)
                y += dash_len + gap_len

        now = pygame.time.get_ticks()
        cd_ratio = min(1.0, (now - self.last_move_ms) / MOVE_COOLDOWN_MS)
        bar_color = COLOR_COOLDOWN_READY if cd_ratio >= 1.0 else COLOR_COOLDOWN_WAIT
        pygame.draw.rect(self.screen, (30, 30, 30), (0, HEIGHT - 5, WIDTH, 5))
        pygame.draw.rect(self.screen, bar_color,
                         (0, HEIGHT - 5, int(WIDTH * cd_ratio), 5))

        for o in self.obstacles:
            ox = o['lane'] * self.lane_w + 5
            draw_rounded_rect(self.screen, COLOR_OBSTACLE,
                               pygame.Rect(ox, int(o['y']), o['w'], o['h']), 5)
            pygame.draw.rect(self.screen, COLOR_OBSTACLE_STRIPE,
                             (ox + 5, int(o['y']) + 7, o['w'] - 10, 6))
            pygame.draw.rect(self.screen, COLOR_OBSTACLE_STRIPE,
                             (ox + 5, int(o['y']) + 17, o['w'] - 10, 4))

        if not self.game_over or (self.tick // 5) % 2 == 0:
            px = self.player_lane * self.lane_w + 5
            py = HEIGHT - 110
            cw, ch = self.lane_w - 10, 50
            draw_rounded_rect(self.screen, COLOR_CAR_BODY,
                               pygame.Rect(px, py, cw, ch), 6)
            pygame.draw.rect(self.screen, COLOR_CAR_WINDOW,
                             (px + 6, py + 7, cw - 12, 14))
            for wx, wy in [(px, py + 2), (px + cw - 9, py + 2),
                           (px, py + ch - 12), (px + cw - 9, py + ch - 12)]:
                pygame.draw.rect(self.screen, COLOR_CAR_WHEEL,
                                 (wx, wy, 9, 10))

        draw_text(self.screen, f"Score: {self.score}",  10, 10, self.fonts['md'])
        draw_text(self.screen, f"Best:  {self.best}",   10, 36, self.fonts['md'], COLOR_TEXT_DIM)
        draw_text(self.screen, f"Speed: {self.scroll_speed:.2f}", 10, 62,
                  self.fonts['sm'], COLOR_TEXT_DIM)

        cd_ms = max(0, int(MOVE_COOLDOWN_MS - (now - self.last_move_ms)))
        if cd_ms > 0:
            draw_text_centered(self.screen, f"cooldown {cd_ms}ms",
                               WIDTH // 2, HEIGHT - 22,
                               self.fonts['sm'], COLOR_TEXT_DIM)

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

    # Start BLE bridge — pushes into eeg_queue (no prob_queue here)
    t = eeg_ble.start_ble_thread(eeg_queue)

    game = LaneDodge(screen, fonts)

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
                if event.key == pygame.K_r:
                    game.reset()

        game.update()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == '__main__':
    main()
