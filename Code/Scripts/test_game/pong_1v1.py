"""
game6_pong_1v1.py — EEG Pong 1v1
===================================
Classic pong. Your paddle sits at the bottom and only moves
left/right. Ball bounces back and forth between you and the AI.

Left MI  = paddle left
Right MI = paddle right

First to WINNING_SCORE points wins the set.

EEG HOOK:
    eeg_queue.put('left')   — move paddle left
    eeg_queue.put('right')  — move paddle right

KEYBOARD (for testing):
    Left / Right arrow  — move paddle
    Space               — serve (when prompted)
    R                   — restart set
    ESC                 — quit
"""

import pygame
import sys
import queue
import random
import math

# ─────────────────────────────────────────────
#  PARAMETERS
# ─────────────────────────────────────────────

WIDTH, HEIGHT        = 620, 680
FPS                  = 60

# Ball
BALL_RADIUS          = 10
BALL_SPEED_INIT      = 2.2    # px per frame
BALL_SPEED_MAX       = 5.5    # max speed
BALL_SPEED_RALLY     = 0.08   # speed added per paddle hit

# Player paddle
PADDLE_WIDTH         = 100
PADDLE_HEIGHT        = 14
PADDLE_Y_OFFSET      = 30     # px from bottom
PADDLE_SPEED         = 5.0    # px per frame (continuous mode)
PADDLE_JUMP_PX       = 45     # px per command (discrete mode)

# Input
INPUT_MODE           = 'continuous'   # 'continuous' | 'discrete'
MOVE_COOLDOWN_MS     = 600
EEG_HOLD_MS          = 400

# AI paddle
AI_PADDLE_WIDTH      = 100
AI_PADDLE_HEIGHT     = 14
AI_PADDLE_Y_OFFSET   = 30     # px from top
AI_SPEED             = 2.8    # px per frame — tune to make it beatable
AI_ERROR             = 18     # px of random error in AI target tracking
                               # higher = easier AI

# Scoring
WINNING_SCORE        = 7      # first to this wins the set

# Serve
SERVE_DELAY_MS       = 800    # ms pause before ball launches after serve

# Colors
COLOR_BG             = (10,  10,  20)
COLOR_COURT          = (14,  14,  28)
COLOR_NET            = (35,  35,  60)
COLOR_PADDLE_PLAYER  = (40,  95, 195)
COLOR_PADDLE_AI      = (180, 40,  40)
COLOR_PADDLE_HL      = (100, 170, 255)
COLOR_PADDLE_AI_HL   = (240, 100, 100)
COLOR_BALL           = (230, 230, 235)
COLOR_BALL_SHADOW    = (40,  40,  70)
COLOR_TRAIL          = (60,  80, 150)
COLOR_SCORE_PLAYER   = (80, 140, 240)
COLOR_SCORE_AI       = (220, 70,  70)
COLOR_TEXT           = (200, 200, 210)
COLOR_TEXT_DIM       = (65,  65,  90)
COLOR_WIN            = (60, 220,  80)
COLOR_LOSE           = (220, 60,  60)
COLOR_FLASH_HIT      = (30,  80, 160)   # brief flash on hit

# ─────────────────────────────────────────────
#  EEG QUEUE
# ─────────────────────────────────────────────
eeg_queue: queue.Queue = queue.Queue()


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


# ─────────────────────────────────────────────
#  Ball trail
# ─────────────────────────────────────────────
class Trail:
    def __init__(self, maxlen=18):
        self.pts = []
        self.maxlen = maxlen

    def push(self, x, y):
        self.pts.append((x, y))
        if len(self.pts) > self.maxlen:
            self.pts.pop(0)

    def draw(self, surface):
        for i in range(1, len(self.pts)):
            alpha = int(160 * (i / len(self.pts)))
            r     = max(2, int(BALL_RADIUS * 0.55 * (i / len(self.pts))))
            s     = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*COLOR_TRAIL, alpha), (r, r), r)
            surface.blit(s, (self.pts[i][0]-r, self.pts[i][1]-r))

    def clear(self):
        self.pts.clear()


# ─────────────────────────────────────────────
#  Game state
# ─────────────────────────────────────────────
class Pong1v1:
    PLAYER_Y = HEIGHT - PADDLE_Y_OFFSET - PADDLE_HEIGHT
    AI_Y     = AI_PADDLE_Y_OFFSET

    def __init__(self, screen, fonts):
        self.screen = screen
        self.fonts  = fonts
        self.sets_won  = 0
        self.sets_lost = 0
        self.reset()

    def reset(self):
        self.player_x    = WIDTH//2 - PADDLE_WIDTH//2
        self.ai_x        = WIDTH//2 - AI_PADDLE_WIDTH//2
        self.score_player= 0
        self.score_ai    = 0
        self.rally       = 0           # consecutive hits this rally
        self.ball_speed  = BALL_SPEED_INIT
        self.trail       = Trail()
        self.set_over    = False
        self.winner      = None
        self.tick        = 0
        self.last_move_ms= 0
        self.eeg_last    = {'left': 0, 'right': 0}
        self.flash       = 0           # frames of paddle hit flash
        self.ai_error    = 0           # current AI tracking error
        self._reset_ball(server='player')

    def _reset_ball(self, server='player'):
        self.ball_x   = float(WIDTH // 2)
        self.ball_y   = float(HEIGHT // 2)
        self.ball_vx  = 0.0
        self.ball_vy  = 0.0
        self.served   = False
        self.server   = server
        self.rally    = 0
        self.trail.clear()
        self.serve_timer = 0

    # ── Input ──────────────────────────────
    def _drain_eeg(self):
        now = pygame.time.get_ticks()
        while not eeg_queue.empty():
            cmd = eeg_queue.get_nowait()
            if cmd in self.eeg_last:
                self.eeg_last[cmd] = now

    def _input_left(self):
        now = pygame.time.get_ticks()
        return (pygame.key.get_pressed()[pygame.K_LEFT] or
                now - self.eeg_last['left'] < EEG_HOLD_MS)

    def _input_right(self):
        now = pygame.time.get_ticks()
        return (pygame.key.get_pressed()[pygame.K_RIGHT] or
                now - self.eeg_last['right'] < EEG_HOLD_MS)

    # ── Update ─────────────────────────────
    def update(self):
        self._drain_eeg()
        if self.set_over:
            return

        self.tick += 1
        now = pygame.time.get_ticks()

        # ── Paddle movement ──
        if INPUT_MODE == 'continuous':
            if self._input_left():
                self.player_x = max(0, self.player_x - PADDLE_SPEED)
            if self._input_right():
                self.player_x = min(WIDTH - PADDLE_WIDTH, self.player_x + PADDLE_SPEED)
        else:
            if now - self.last_move_ms >= MOVE_COOLDOWN_MS:
                if self._input_left():
                    self.player_x = max(0, self.player_x - PADDLE_JUMP_PX)
                    self.last_move_ms = now
                elif self._input_right():
                    self.player_x = min(WIDTH - PADDLE_WIDTH,
                                        self.player_x + PADDLE_JUMP_PX)
                    self.last_move_ms = now

        # ── Serve ──
        if not self.served:
            if self.server == 'player':
                self.ball_x = self.player_x + PADDLE_WIDTH / 2
                self.ball_y = float(self.PLAYER_Y - BALL_RADIUS - 4)
            else:
                self.ball_x = self.ai_x + AI_PADDLE_WIDTH / 2
                self.ball_y = float(self.AI_Y + AI_PADDLE_HEIGHT + BALL_RADIUS + 4)

            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE] or self.server == 'ai':
                self.serve_timer += 1
                if self.serve_timer >= SERVE_DELAY_MS / (1000/FPS):
                    self.served = True
                    angle = (random.uniform(-50, 50) if self.server == 'player'
                             else random.uniform(130, 230))
                    rad   = math.radians(angle - 90)
                    self.ball_vx = math.cos(rad) * self.ball_speed
                    self.ball_vy = math.sin(rad) * self.ball_speed
                    # ensure ball moves toward correct side
                    if self.server == 'player':
                        self.ball_vy = -abs(self.ball_vy)
                    else:
                        self.ball_vy = abs(self.ball_vy)
            return

        # ── Ball physics ──
        self.trail.push(int(self.ball_x), int(self.ball_y))
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        # Wall bounces
        if self.ball_x - BALL_RADIUS < 0:
            self.ball_x  = BALL_RADIUS
            self.ball_vx = abs(self.ball_vx)
        if self.ball_x + BALL_RADIUS > WIDTH:
            self.ball_x  = WIDTH - BALL_RADIUS
            self.ball_vx = -abs(self.ball_vx)

        # Flash decay
        if self.flash > 0:
            self.flash -= 1

        # ── Player paddle bounce ──
        if (self.ball_vy > 0 and
                self.ball_y + BALL_RADIUS >= self.PLAYER_Y and
                self.ball_y < self.PLAYER_Y + PADDLE_HEIGHT and
                self.ball_x > self.player_x and
                self.ball_x < self.player_x + PADDLE_WIDTH):
            self.rally      += 1
            self.ball_speed  = min(BALL_SPEED_MAX,
                                   self.ball_speed + BALL_SPEED_RALLY)
            rel    = (self.ball_x - (self.player_x + PADDLE_WIDTH/2)) / (PADDLE_WIDTH/2)
            angle  = math.radians(-90 + rel * 55)
            spd    = self.ball_speed
            self.ball_vx = math.cos(angle) * spd
            self.ball_vy = -abs(math.sin(angle) * spd)
            self.ball_y  = self.PLAYER_Y - BALL_RADIUS - 1
            self.flash   = 12

        # ── AI paddle bounce ──
        if (self.ball_vy < 0 and
                self.ball_y - BALL_RADIUS <= self.AI_Y + AI_PADDLE_HEIGHT and
                self.ball_y > self.AI_Y and
                self.ball_x > self.ai_x and
                self.ball_x < self.ai_x + AI_PADDLE_WIDTH):
            self.rally     += 1
            self.ball_speed = min(BALL_SPEED_MAX,
                                  self.ball_speed + BALL_SPEED_RALLY * 0.5)
            rel    = (self.ball_x - (self.ai_x + AI_PADDLE_WIDTH/2)) / (AI_PADDLE_WIDTH/2)
            angle  = math.radians(90 + rel * 40)
            spd    = self.ball_speed
            self.ball_vx = math.cos(angle) * spd
            self.ball_vy = abs(math.sin(angle) * spd)
            self.ball_y  = self.AI_Y + AI_PADDLE_HEIGHT + BALL_RADIUS + 1

        # ── AI movement ──
        # Recalculate target with random error occasionally
        if self.tick % 20 == 0:
            self.ai_error = random.uniform(-AI_ERROR, AI_ERROR)
        ai_target = self.ball_x + self.ai_error - AI_PADDLE_WIDTH / 2
        if self.ai_x < ai_target - 3:
            self.ai_x = min(WIDTH - AI_PADDLE_WIDTH, self.ai_x + AI_SPEED)
        elif self.ai_x > ai_target + 3:
            self.ai_x = max(0, self.ai_x - AI_SPEED)

        # ── Scoring ──
        if self.ball_y - BALL_RADIUS > HEIGHT + 10:
            # AI scores
            self.score_ai += 1
            self._check_set_over()
            if not self.set_over:
                self.ball_speed = BALL_SPEED_INIT
                self._reset_ball(server='ai')

        elif self.ball_y + BALL_RADIUS < -10:
            # Player scores
            self.score_player += 1
            self._check_set_over()
            if not self.set_over:
                self.ball_speed = BALL_SPEED_INIT
                self._reset_ball(server='player')

    def _check_set_over(self):
        if self.score_player >= WINNING_SCORE:
            self.set_over = True
            self.winner   = 'player'
            self.sets_won += 1
        elif self.score_ai >= WINNING_SCORE:
            self.set_over = True
            self.winner   = 'ai'
            self.sets_lost += 1

    # ── Draw ───────────────────────────────
    def draw(self):
        self.screen.fill(COLOR_BG)
        W, H = WIDTH, HEIGHT

        # Court background
        rr(self.screen, COLOR_COURT,
           pygame.Rect(20, 40, W-40, H-80), 8)

        # Net (center line)
        net_y = H // 2
        for x in range(24, W-24, 18):
            pygame.draw.rect(self.screen, COLOR_NET,
                             pygame.Rect(x, net_y-1, 10, 3))

        # Score display
        txt_c(self.screen, str(self.score_ai),
              W//2 - 50, net_y - 38, self.fonts['score'], COLOR_SCORE_AI)
        txt_c(self.screen, str(self.score_player),
              W//2 + 50, net_y + 12, self.fonts['score'], COLOR_SCORE_PLAYER)

        # Set record
        txt(self.screen, f"Sets W/L: {self.sets_won}/{self.sets_lost}",
            28, 10, self.fonts['sm'], COLOR_TEXT_DIM)

        # Ball trail
        self.trail.draw(self.screen)

        # Ball shadow
        shadow_y = self.PLAYER_Y - 6
        pygame.draw.ellipse(self.screen, COLOR_BALL_SHADOW,
                            pygame.Rect(int(self.ball_x)-10, shadow_y-3, 20, 6))

        # Ball
        pygame.draw.circle(self.screen, COLOR_BALL,
                           (int(self.ball_x), int(self.ball_y)), BALL_RADIUS)
        pygame.draw.circle(self.screen, (255,255,255),
                           (int(self.ball_x)-3, int(self.ball_y)-3), 3)

        # AI paddle
        ai_rect = pygame.Rect(self.ai_x, self.AI_Y, AI_PADDLE_WIDTH, AI_PADDLE_HEIGHT)
        rr(self.screen, COLOR_PADDLE_AI, ai_rect, 5)
        rr(self.screen, COLOR_PADDLE_AI_HL,
           pygame.Rect(self.ai_x, self.AI_Y, AI_PADDLE_WIDTH, 4), 5)

        # Player paddle
        flash_col = None
        if self.flash > 0:
            alpha = int(200 * (self.flash / 12))
            s     = pygame.Surface((PADDLE_WIDTH, PADDLE_HEIGHT), pygame.SRCALPHA)
            s.fill((*COLOR_FLASH_HIT, alpha))
        pad_rect = pygame.Rect(self.player_x, self.PLAYER_Y, PADDLE_WIDTH, PADDLE_HEIGHT)
        rr(self.screen, COLOR_PADDLE_PLAYER, pad_rect, 5)
        rr(self.screen, COLOR_PADDLE_HL,
           pygame.Rect(self.player_x, self.PLAYER_Y, PADDLE_WIDTH, 4), 5)
        if self.flash > 0:
            self.screen.blit(s, (self.player_x, self.PLAYER_Y))

        # Serve prompt
        if not self.served and not self.set_over and self.server == 'player':
            txt_c(self.screen, "SPACE to serve",
                  W//2, H//2 + 30, self.fonts['md'], COLOR_TEXT_DIM)

        # Discrete cooldown bar
        if INPUT_MODE == 'discrete':
            now = pygame.time.get_ticks()
            cd  = min(1.0, (now - self.last_move_ms) / MOVE_COOLDOWN_MS)
            pygame.draw.rect(self.screen, (30,30,30), (0, H-4, W, 4))
            pygame.draw.rect(self.screen,
                             (40,90,40) if cd >= 1.0 else (25,25,25),
                             (0, H-4, int(W*cd), 4))

        # Rally counter
        if self.rally > 2:
            txt_c(self.screen, f"rally {self.rally}",
                  W//2, H//2 - 18, self.fonts['sm'],
                  (100, 200, 100) if self.rally > 5 else COLOR_TEXT_DIM)

        # Set over overlay
        if self.set_over:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((0, 0, 0, 170))
            self.screen.blit(s, (0, 0))

            if self.winner == 'player':
                txt_c(self.screen, "YOU WIN!",
                      W//2, H//2 - 50, self.fonts['lg'], COLOR_WIN)
            else:
                txt_c(self.screen, "AI WINS",
                      W//2, H//2 - 50, self.fonts['lg'], COLOR_LOSE)

            txt_c(self.screen,
                  f"{self.score_player} — {self.score_ai}",
                  W//2, H//2 + 4, self.fonts['score'], COLOR_TEXT)
            txt_c(self.screen,
                  f"Sets: {self.sets_won} W  /  {self.sets_lost} L",
                  W//2, H//2 + 52, self.fonts['md'], COLOR_TEXT_DIM)
            txt_c(self.screen, "R to play again  |  ESC to quit",
                  W//2, H//2 + 90, self.fonts['sm'], COLOR_TEXT_DIM)


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("EEG — Pong 1v1")
    clock  = pygame.time.Clock()

    fonts = {
        'lg':    pygame.font.SysFont(None, 56),
        'score': pygame.font.SysFont(None, 72),
        'md':    pygame.font.SysFont(None, 32),
        'sm':    pygame.font.SysFont(None, 22),
    }

    game = Pong1v1(screen, fonts)

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
