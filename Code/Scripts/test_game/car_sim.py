import math
import pygame

# ----------------------------
# Simple 2D Car Simulation
# ----------------------------

WIDTH, HEIGHT = 1000, 700
FPS = 60

# Colors
WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
GRAY = (120, 120, 120)
GREEN = (40, 140, 60)
RED = (200, 60, 60)
BLUE = (60, 100, 220)
YELLOW = (230, 210, 80)

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Simple 2D Car Simulation")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)


class Car:
    def __init__(self, x, y):
        self.start_x = x
        self.start_y = y
        self.reset()

    def reset(self):
        self.x = self.start_x
        self.y = self.start_y
        self.angle = 0  # degrees, 0 points right
        self.speed = 0.0

        self.max_speed = 8.0
        self.max_reverse = -3.0
        self.acceleration = 0.15
        self.brake_strength = 0.20
        self.friction = 0.04
        self.steer_strength = 2.8

        self.width = 50
        self.height = 26

    def update(self, keys):
        # Throttle / reverse
        if keys[pygame.K_UP]:
            self.speed += self.acceleration
        elif keys[pygame.K_DOWN]:
            self.speed -= self.acceleration
        else:
            # natural friction
            if self.speed > 0:
                self.speed -= self.friction
                if self.speed < 0:
                    self.speed = 0
            elif self.speed < 0:
                self.speed += self.friction
                if self.speed > 0:
                    self.speed = 0

        # Clamp speed
        self.speed = max(self.max_reverse, min(self.speed, self.max_speed))

        # Steering gets stronger when moving
        if abs(self.speed) > 0.05:
            steer_amount = self.steer_strength * (abs(self.speed) / self.max_speed)
            if keys[pygame.K_LEFT]:
                self.angle -= steer_amount if self.speed >= 0 else -steer_amount
            if keys[pygame.K_RIGHT]:
                self.angle += steer_amount if self.speed >= 0 else -steer_amount

        # Move car
        rad = math.radians(self.angle)
        self.x += math.cos(rad) * self.speed
        self.y += math.sin(rad) * self.speed

    def get_corners(self):
        """Return rotated corners for drawing/collision-ish checks."""
        rad = math.radians(self.angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        half_w = self.width / 2
        half_h = self.height / 2

        local_corners = [
            (-half_w, -half_h),
            (half_w, -half_h),
            (half_w, half_h),
            (-half_w, half_h),
        ]

        world_corners = []
        for lx, ly in local_corners:
            wx = self.x + lx * cos_a - ly * sin_a
            wy = self.y + lx * sin_a + ly * cos_a
            world_corners.append((wx, wy))
        return world_corners

    def draw(self, surface):
        corners = self.get_corners()
        pygame.draw.polygon(surface, BLUE, corners)
        pygame.draw.polygon(surface, BLACK, corners, 2)

        # front indicator
        rad = math.radians(self.angle)
        front_x = self.x + math.cos(rad) * (self.width / 2 - 6)
        front_y = self.y + math.sin(rad) * (self.width / 2 - 6)
        pygame.draw.circle(surface, YELLOW, (int(front_x), int(front_y)), 4)


def point_in_drive_area(x, y, drive_rect):
    return drive_rect.collidepoint(x, y)


def car_inside_drive_area(car, drive_rect):
    for x, y in car.get_corners():
        if not point_in_drive_area(x, y, drive_rect):
            return False
    return True


def draw_text(surface, text, x, y, color=WHITE):
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def main():
    car = Car(WIDTH // 2, HEIGHT // 2)

    # Simple rectangular road area
    drive_rect = pygame.Rect(120, 100, WIDTH - 240, HEIGHT - 200)

    running = True
    while running:
        dt = clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        keys = pygame.key.get_pressed()

        if keys[pygame.K_r]:
            car.reset()

        old_x, old_y, old_angle, old_speed = car.x, car.y, car.angle, car.speed
        car.update(keys)

        # crude collision / out-of-bounds rule:
        # if any corner leaves drive area, revert position and damp speed
        if not car_inside_drive_area(car, drive_rect):
            car.x, car.y, car.angle = old_x, old_y, old_angle
            car.speed = -old_speed * 0.25

        # Draw
        screen.fill(GREEN)

        # Road
        pygame.draw.rect(screen, GRAY, drive_rect)
        pygame.draw.rect(screen, WHITE, drive_rect, 4)

        # Inner guide lines
        pygame.draw.line(
            screen, WHITE,
            (drive_rect.left + 40, drive_rect.centery),
            (drive_rect.right - 40, drive_rect.centery),
            2
        )
        pygame.draw.line(
            screen, WHITE,
            (drive_rect.centerx, drive_rect.top + 40),
            (drive_rect.centerx, drive_rect.bottom - 40),
            2
        )

        car.draw(screen)

        draw_text(screen, "Arrow keys to drive, R to reset", 20, 20)
        draw_text(screen, f"Speed: {car.speed:.2f}", 20, 50)
        draw_text(screen, f"Angle: {car.angle:.1f}", 20, 80)
        draw_text(screen, f"FPS target: {FPS}", 20, 110)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()