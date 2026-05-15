"""
Application desktop pour visualiser le protocole MAC avec backoff exponentiel.

Lancer :
    python mac_live_simulation_fr.py

Commandes dans la fenêtre :
    - glisser les curseurs pour changer N, K, lambda, tau et la vitesse ;
    - cliquer sur Pause/Reprendre ;
    - cliquer sur Redémarrer pour relancer avec les valeurs courantes.

Le notebook du projet reste inchangé. Cette application sert seulement de
support visuel et pédagogique.
"""

from __future__ import annotations

import argparse
import math
import os
import random
from dataclasses import dataclass


COLORS = {
    "bg": (244, 247, 250),
    "panel": (255, 255, 255),
    "line": (214, 224, 233),
    "ink": (23, 33, 43),
    "muted": (94, 110, 126),
    "channel": (38, 54, 69),
    "station": (41, 91, 143),
    "station_dark": (30, 63, 99),
    "packet": (242, 184, 75),
    "packet_edge": (150, 95, 0),
    "success": (46, 157, 99),
    "collision": (217, 75, 75),
    "loss": (123, 75, 179),
    "backoff": (46, 138, 184),
    "wait": (207, 126, 45),
    "slot": (237, 242, 246),
    "button": (238, 243, 247),
    "button_hover": (224, 234, 242),
}


@dataclass
class Params:
    n: int = 5
    k: int = 3
    lam: float = 0.14
    tau: float = 0.5
    speed: float = 1.0


@dataclass
class Metrics:
    arrived: int = 0
    success: int = 0
    collision: int = 0
    lost: int = 0

    def throughput(self, t: float) -> float:
        return self.success / max(t, 1e-6)

    def loss_rate(self) -> float:
        return self.lost / max(self.arrived, 1)


@dataclass
class Transmission:
    kind: str
    stations: list[int]
    start: float
    end: float


@dataclass
class Flash:
    kind: str
    station: int
    text: str
    born: float
    ttl: float = 1.4


class Simulation:
    def __init__(self, params: Params) -> None:
        self.params = params
        self.time = 0.0
        self.channel_busy_until = 0.0
        self.queues: list[int] = []
        self.backoff: list[int] = []
        self.pending: list[bool] = []
        self.next_attempt: list[float] = []
        self.arrival_clock: list[float] = []
        self.transmissions: list[Transmission] = []
        self.flashes: list[Flash] = []
        self.metrics = Metrics()
        self.event = "ARRIVÉE"
        self.message = "Les stations génèrent des paquets et partagent un seul canal."
        self.log: list[str] = []
        self.reset(params)

    def reset(self, params: Params | None = None, message: str | None = None) -> None:
        if params is not None:
            self.params = params
        self.time = 0.0
        self.channel_busy_until = 0.0
        self.queues = [0] * self.params.n
        self.backoff = [1] * self.params.n
        self.pending = [False] * self.params.n
        self.next_attempt = [math.inf] * self.params.n
        self.arrival_clock = [self.exp_delay(1.0 / max(self.params.lam, 0.001)) for _ in range(self.params.n)]
        self.transmissions = []
        self.flashes = []
        self.metrics = Metrics()
        self.event = "ARRIVÉE"
        self.message = message or "Simulation redémarrée avec les paramètres actuels."
        self.log = []
        self.add_log(self.message)

    @staticmethod
    def exp_delay(mean: float) -> float:
        return -math.log(max(random.random(), 1e-9)) * mean

    def add_log(self, text: str) -> None:
        self.log.insert(0, f"t={self.time:.1f} : {text}")
        del self.log[10:]

    def add_flash(self, kind: str, station: int, text: str) -> None:
        self.flashes.append(Flash(kind=kind, station=station, text=text, born=self.time))

    def schedule_attempt(self, station: int, at_time: float) -> None:
        if self.queues[station] <= 0:
            return
        self.pending[station] = True
        self.next_attempt[station] = at_time

    def set_params(self, params: Params) -> None:
        shape_changed = params.n != self.params.n or params.k != self.params.k
        self.params = params
        if shape_changed:
            self.reset(params, "N ou K a changé : la scène est reconstruite.")
        else:
            self.message = "Paramètres mis à jour en direct : lambda et tau agissent sur les prochains événements."

    def prepare_demo(self) -> None:
        self.reset(self.params, "Exemple simple : deux stations tentent ensemble, puis le backoff sépare les retry.")
        starters = min(2, self.params.n)
        for station in range(starters):
            self.queues[station] = 1
            self.schedule_attempt(station, 0.0)
        if self.params.n >= 3:
            self.queues[2] = 1
            self.schedule_attempt(2, 1.2)
        self.event = "TENTATIVE"

    def update(self, dt: float) -> None:
        dt = min(dt * self.params.speed, 0.18)
        self.time += dt
        self.process_arrivals(dt)
        self.process_attempts()
        self.transmissions = [tx for tx in self.transmissions if self.time <= tx.end + 0.25]
        self.flashes = [fl for fl in self.flashes if self.time - fl.born < fl.ttl]

    def process_arrivals(self, dt: float) -> None:
        mean = 1.0 / max(self.params.lam, 0.001)
        for station in range(self.params.n):
            self.arrival_clock[station] -= dt
            while self.arrival_clock[station] <= 0:
                self.metrics.arrived += 1
                if self.queues[station] < self.params.k:
                    self.queues[station] += 1
                    self.event = "ARRIVÉE"
                    self.message = "Arrivée : si queue[i] < K, le paquet rejoint la file."
                    self.add_flash("arrival", station, "+ paquet")
                    if not self.pending[station]:
                        self.schedule_attempt(station, self.time)
                else:
                    self.metrics.lost += 1
                    self.event = "PERTE"
                    self.message = "File pleine : le paquet est perdu et n_lost_full augmente."
                    self.add_flash("loss", station, "perdu")
                    self.add_log(f"Paquet perdu sur file pleine à S{station}.")
                self.arrival_clock[station] += self.exp_delay(mean)

    def process_attempts(self) -> None:
        for station in range(self.params.n):
            if (
                self.pending[station]
                and self.queues[station] > 0
                and self.next_attempt[station] <= self.time
                and self.time < self.channel_busy_until
            ):
                self.next_attempt[station] = self.channel_busy_until
                self.event = "TENTATIVE"
                self.message = "Canal occupé : Carrier Sense fait attendre la station."
                self.add_flash("wait", station, "attente")

        if self.time < self.channel_busy_until:
            return

        ready = [
            station
            for station in range(self.params.n)
            if self.pending[station] and self.queues[station] > 0 and self.next_attempt[station] <= self.time
        ]
        if not ready:
            return

        for station in ready:
            self.pending[station] = False
            self.next_attempt[station] = math.inf

        self.channel_busy_until = self.time + 1.0
        if len(ready) == 1:
            station = ready[0]
            self.queues[station] = max(0, self.queues[station] - 1)
            self.backoff[station] = 1
            self.metrics.success += 1
            self.event = "SUCCÈS"
            self.message = "Succès : un seul paquet occupe le canal, sort de la file et augmente le débit."
            self.transmissions.append(Transmission("success", ready, self.time, self.channel_busy_until))
            self.add_log(f"Succès de transmission pour S{station}.")
            if self.queues[station] > 0:
                self.schedule_attempt(station, self.channel_busy_until)
        else:
            self.metrics.collision += len(ready)
            self.event = "COLLISION"
            self.message = "Collision : plusieurs stations tentent au même instant. Les paquets restent en file."
            self.transmissions.append(Transmission("collision", ready, self.time, self.channel_busy_until))
            self.add_log("Collision entre " + ", ".join(f"S{s}" for s in ready) + ".")
            for station in ready:
                k = self.backoff[station]
                self.backoff[station] = k + 1
                delay = self.exp_delay(self.params.tau * (2**k))
                self.schedule_attempt(station, self.channel_busy_until + delay)


class Slider:
    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        width: int,
        min_value: float,
        max_value: float,
        step: float,
        value: float,
        fmt: str,
    ) -> None:
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.value = value
        self.fmt = fmt
        self.dragging = False

    def configure(self, x: int, y: int, width: int) -> None:
        self.x = x
        self.y = y
        self.width = max(80, width)

    def knob_x(self) -> int:
        ratio = (self.value - self.min_value) / (self.max_value - self.min_value)
        return int(self.x + ratio * self.width)

    def set_from_x(self, px: int) -> bool:
        ratio = min(1.0, max(0.0, (px - self.x) / self.width))
        raw = self.min_value + ratio * (self.max_value - self.min_value)
        stepped = round((raw - self.min_value) / self.step) * self.step + self.min_value
        if self.step >= 1:
            stepped = int(round(stepped))
        stepped = min(self.max_value, max(self.min_value, stepped))
        changed = stepped != self.value
        self.value = stepped
        return changed

    def handle_event(self, event, pygame) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.x - 8 <= mx <= self.x + self.width + 8 and self.y + 22 <= my <= self.y + 46:
                self.dragging = True
                return self.set_from_x(mx)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            return self.set_from_x(event.pos[0])
        return False

    def draw(self, screen, fonts, pygame) -> None:
        label = fonts["body_bold"].render(self.name, True, COLORS["ink"])
        value = fonts["body"].render(self.fmt.format(self.value), True, COLORS["muted"])
        screen.blit(label, (self.x, self.y))
        screen.blit(value, (self.x + self.width - value.get_width(), self.y))
        track_y = self.y + 35
        pygame.draw.line(screen, (193, 207, 220), (self.x, track_y), (self.x + self.width, track_y), 5)
        pygame.draw.line(screen, COLORS["station"], (self.x, track_y), (self.knob_x(), track_y), 5)
        pygame.draw.circle(screen, COLORS["station"], (self.knob_x(), track_y), 9)
        pygame.draw.circle(screen, COLORS["panel"], (self.knob_x(), track_y), 4)


class Button:
    def __init__(self, label: str, rect: tuple[int, int, int, int]) -> None:
        self.label = label
        self.rect = rect
        self.hover = False

    def configure(self, rect: tuple[int, int, int, int]) -> None:
        self.rect = rect

    def handle_event(self, event, pygame) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = pygame.Rect(self.rect).collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return pygame.Rect(self.rect).collidepoint(event.pos)
        return False

    def draw(self, screen, fonts, pygame) -> None:
        rect = pygame.Rect(self.rect)
        pygame.draw.rect(screen, COLORS["button_hover"] if self.hover else COLORS["button"], rect, border_radius=7)
        pygame.draw.rect(screen, (185, 200, 213), rect, 1, border_radius=7)
        text = fonts["body_bold"].render(self.label, True, COLORS["ink"])
        screen.blit(text, text.get_rect(center=rect.center))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lancer l'application desktop MAC en français.")
    parser.add_argument("--width", type=int, default=1120, help="Largeur de la fenêtre.")
    parser.add_argument("--height", type=int, default=650, help="Hauteur de la fenêtre.")
    parser.add_argument("--self-test", action="store_true", help="Vérifier l'initialisation sans ouvrir une vraie fenêtre.")
    parser.add_argument("--screenshot", help="Enregistrer une capture PNG de l'interface puis quitter.")
    parser.add_argument("--record-gif", help="Enregistrer un GIF court de la démonstration desktop puis quitter.")
    parser.add_argument("--record-seconds", type=float, default=12.0, help="Durée du GIF de démonstration.")
    parser.add_argument("--record-fps", type=int, default=8, help="Images par seconde du GIF de démonstration.")
    parser.add_argument("--seed", type=int, default=7, help="Graine aléatoire pour les captures et GIF.")
    return parser.parse_args()


def load_fonts(pygame) -> dict[str, object]:
    return {
        "title": pygame.font.SysFont("segoeui", 25, bold=True),
        "h2": pygame.font.SysFont("segoeui", 17, bold=True),
        "body": pygame.font.SysFont("segoeui", 13),
        "body_bold": pygame.font.SysFont("segoeui", 13, bold=True),
        "small": pygame.font.SysFont("segoeui", 11),
        "metric": pygame.font.SysFont("segoeui", 22, bold=True),
        "mono": pygame.font.SysFont("consolas", 12),
    }


def draw_text(screen, font, text: str, pos: tuple[int, int], color=COLORS["ink"]) -> None:
    screen.blit(font.render(text, True, color), pos)


def draw_wrapped(screen, font, text: str, rect, color=COLORS["muted"], line_height: int = 18) -> None:
    words = text.split()
    line = ""
    y = rect.y
    for word in words:
        test = f"{line} {word}".strip()
        if font.size(test)[0] <= rect.width:
            line = test
        else:
            screen.blit(font.render(line, True, color), (rect.x, y))
            y += line_height
            line = word
            if y > rect.bottom - line_height:
                break
    if line and y <= rect.bottom - line_height:
        screen.blit(font.render(line, True, color), (rect.x, y))


def panel(pygame, screen, rect, title: str | None = None) -> None:
    pygame.draw.rect(screen, COLORS["panel"], rect, border_radius=8)
    pygame.draw.rect(screen, COLORS["line"], rect, 1, border_radius=8)
    if title:
        draw_text(screen, pygame.font.SysFont("segoeui", 17, bold=True), title, (rect.x + 14, rect.y + 12))


def compute_layout(pygame, width: int, height: int) -> dict[str, object]:
    margin = 12
    gap = 12
    left_w = 270
    right_w = 254
    if width < 1060:
        left_w = 250
        right_w = 238

    usable_h = max(560, height)
    left = pygame.Rect(margin, margin, left_w, 430)
    legend = pygame.Rect(margin, left.bottom + gap, left_w, usable_h - left.bottom - margin - gap)
    right_x = width - margin - right_w
    right_top = pygame.Rect(right_x, margin, right_w, 276)
    right_bottom = pygame.Rect(right_x, right_top.bottom + gap, right_w, usable_h - right_top.bottom - margin - gap)
    stage_x = left.right + gap
    stage_w = max(360, right_x - gap - stage_x)
    timeline_h = 54
    stage = pygame.Rect(stage_x, margin, stage_w, usable_h - margin * 2 - gap - timeline_h)
    timeline = pygame.Rect(stage_x, stage.bottom + gap, stage_w, timeline_h)
    return {
        "left": left,
        "legend": legend,
        "stage": stage,
        "timeline": timeline,
        "right_top": right_top,
        "right_bottom": right_bottom,
    }


def configure_controls(sliders: dict[str, Slider], pause_button: Button, reset_button: Button, left_rect) -> None:
    x = left_rect.x + 14
    width = left_rect.width - 28
    y = left_rect.y + 92
    for key in ("n", "k", "lam", "tau", "speed"):
        sliders[key].configure(x, y, width)
        y += 52
    button_y = left_rect.bottom - 44
    button_gap = 8
    button_w = (width - button_gap) // 2
    pause_button.configure((x, button_y, button_w, 34))
    reset_button.configure((x + button_w + button_gap, button_y, button_w, 34))


def station_positions(params: Params, stage_rect) -> list[tuple[int, int]]:
    top = stage_rect.y + 112
    bottom = stage_rect.bottom - 76
    span = max(1, params.n - 1)
    return [(stage_rect.x + 74, int(top + (bottom - top) * i / span)) for i in range(params.n)]


def station_scale(params: Params, stage_rect) -> float:
    available = max(1, stage_rect.height - 188)
    spacing = available / max(1, params.n - 1)
    return max(0.58, min(0.94, spacing / 68))


def rounded_rect(pygame, screen, color, rect, radius=8, width=0) -> None:
    pygame.draw.rect(screen, color, rect, width=width, border_radius=radius)


def draw_laptop(pygame, screen, fonts, x: int, y: int, label: str, active: bool, scale: float = 1.0) -> None:
    edge = COLORS["collision"] if active else COLORS["station_dark"]
    sw = int(76 * scale)
    sh = int(48 * scale)
    base_w = int(96 * scale)
    base_h = max(8, int(12 * scale))
    rounded_rect(pygame, screen, COLORS["station"], pygame.Rect(x - sw // 2, y - sh // 2, sw, sh), max(5, int(7 * scale)))
    rounded_rect(pygame, screen, edge, pygame.Rect(x - sw // 2, y - sh // 2, sw, sh), max(5, int(7 * scale)), width=2)
    pygame.draw.rect(screen, (219, 230, 239), (x - base_w // 2, y + sh // 2 - 1, base_w, base_h))
    pygame.draw.rect(screen, edge, (x - base_w // 2, y + sh // 2 - 1, base_w, base_h), 2)
    text = fonts["body_bold"].render(label, True, (255, 255, 255))
    screen.blit(text, text.get_rect(center=(x, y - int(4 * scale))))


def draw_queue(pygame, screen, x: int, y: int, count: int, capacity: int, scale: float = 1.0) -> None:
    slot_w = min(int(26 * scale), int(145 * scale / max(capacity, 1)))
    slot_w = max(10, slot_w)
    slot_h = max(16, int(28 * scale))
    for idx in range(capacity):
        sx = x + idx * (slot_w + max(3, int(5 * scale)))
        rounded_rect(pygame, screen, COLORS["slot"], pygame.Rect(sx, y - slot_h // 2, slot_w, slot_h), 5)
        rounded_rect(pygame, screen, (196, 208, 219), pygame.Rect(sx, y - slot_h // 2, slot_w, slot_h), 5, width=1)
        if idx < count:
            rounded_rect(pygame, screen, COLORS["packet"], pygame.Rect(sx + 3, y - slot_h // 2 + 3, max(6, slot_w - 6), max(10, slot_h - 6)), 5)
            rounded_rect(pygame, screen, COLORS["packet_edge"], pygame.Rect(sx + 3, y - slot_h // 2 + 3, max(6, slot_w - 6), max(10, slot_h - 6)), 5, width=1)


def draw_packet(pygame, screen, fonts, x: int, y: int, color, label: str = "P", radius: int = 13) -> None:
    pygame.draw.circle(screen, color, (x, y), radius)
    pygame.draw.circle(screen, COLORS["packet_edge"], (x, y), radius, 2)
    text = fonts["small"].render(label, True, COLORS["ink"])
    screen.blit(text, text.get_rect(center=(x, y)))


def draw_router(pygame, screen, fonts, x: int, y: int) -> None:
    # Petit serveur/récepteur, dans le même esprit que la version web.
    rounded_rect(pygame, screen, (230, 237, 242), pygame.Rect(x - 43, y - 24, 86, 48), 9)
    rounded_rect(pygame, screen, (55, 80, 95), pygame.Rect(x - 43, y - 24, 86, 48), 9, width=2)
    pygame.draw.line(screen, (173, 190, 203), (x - 34, y - 6), (x + 34, y - 6), 1)
    pygame.draw.line(screen, (173, 190, 203), (x - 34, y + 9), (x + 34, y + 9), 1)
    for idx, color in enumerate((COLORS["success"], COLORS["packet"], COLORS["collision"])):
        pygame.draw.circle(screen, color, (x - 18 + idx * 18, y), 5)
    for w, h in ((78, 58), (58, 44), (38, 30)):
        pygame.draw.arc(screen, (85, 114, 132), pygame.Rect(x - w // 2, y - h - 10, w, h), math.pi * 0.15, math.pi * 0.85, 2)
    text = fonts["small"].render("serveur", True, COLORS["muted"])
    screen.blit(text, text.get_rect(center=(x, y + 44)))


def draw_transmissions(pygame, screen, fonts, sim: Simulation, positions, channel_y: int, receiver_x: int, stage_rect) -> None:
    center_x = stage_rect.x + int(stage_rect.width * 0.52)
    for tx in sim.transmissions:
        progress = max(0.0, min(1.0, (sim.time - tx.start) / max(0.001, tx.end - tx.start)))
        for station in tx.stations:
            sx, sy = positions[station]
            from_x, from_y = sx + 110, sy
            to_x = receiver_x - 58 if tx.kind == "success" else center_x
            x = int(from_x + (to_x - from_x) * progress)
            y = int(from_y + (channel_y - from_y) * progress)
            pygame.draw.line(screen, (204, 214, 223), (from_x, from_y), (x, y), 2)
            draw_packet(pygame, screen, fonts, x, y, COLORS["success"] if tx.kind == "success" else COLORS["packet"], f"S{station}", 12)

        if tx.kind == "collision" and progress > 0.45:
            pulse = int(28 + 38 * min(1.0, (progress - 0.45) / 0.55))
            pygame.draw.circle(screen, (245, 207, 207), (center_x, channel_y), pulse, 3)
            pygame.draw.circle(screen, (250, 226, 226), (center_x, channel_y), max(8, pulse // 2), 2)
            pygame.draw.line(screen, COLORS["collision"], (center_x - 36, channel_y - 36), (center_x + 36, channel_y + 36), 6)
            pygame.draw.line(screen, COLORS["collision"], (center_x - 36, channel_y + 36), (center_x + 36, channel_y - 36), 6)
            text = fonts["h2"].render("COLLISION", True, COLORS["collision"])
            screen.blit(text, text.get_rect(center=(center_x, channel_y - 62)))

        if tx.kind == "success" and progress > 0.5:
            pygame.draw.lines(
                screen,
                COLORS["success"],
                False,
                [(receiver_x - 112, channel_y + 8), (receiver_x - 92, channel_y + 32), (receiver_x - 50, channel_y - 28)],
                6,
            )


def draw_flashes(pygame, screen, fonts, sim: Simulation, positions) -> None:
    for flash in sim.flashes:
        age = sim.time - flash.born
        alpha = max(0, int(255 * (1 - age / flash.ttl)))
        color = {
            "loss": COLORS["loss"],
            "wait": COLORS["wait"],
            "arrival": COLORS["packet_edge"],
        }.get(flash.kind, COLORS["muted"])
        x, y = positions[flash.station]
        if flash.kind == "arrival":
            progress = min(1.0, age / 0.75)
            px = x + 120
            py = int(y - 62 + 54 * progress)
            draw_packet(pygame, screen, fonts, px, py, COLORS["packet"], "P", 10)
        elif flash.kind == "loss":
            draw_packet(pygame, screen, fonts, x + 128, y - 8, COLORS["loss"], "X", 10)
            pygame.draw.line(screen, COLORS["loss"], (x + 116, y - 20), (x + 140, y + 4), 3)
            pygame.draw.line(screen, COLORS["loss"], (x + 116, y + 4), (x + 140, y - 20), 3)
        else:
            text = fonts["body_bold"].render(flash.text, True, color)
            text.set_alpha(alpha)
            screen.blit(text, (x + 92, y - 29))


def draw_stage(pygame, screen, fonts, sim: Simulation, rect) -> None:
    panel(pygame, screen, rect)
    title = "Protocole MAC : accès à un canal partagé"
    title_font = fonts["title"]
    if title_font.size(title)[0] > rect.width - 40:
        title = "Protocole MAC : canal partagé"
        title_font = fonts["h2"]
    draw_text(screen, title_font, title, (rect.x + 20, rect.y + 18))
    draw_text(
        screen,
        fonts["body"],
        "Arrivées Poisson, files de capacité K, collisions et backoff exponentiel.",
        (rect.x + 20, rect.y + 52),
        COLORS["muted"],
    )

    positions = station_positions(sim.params, rect)
    scale = station_scale(sim.params, rect)
    channel_y = rect.y + int(rect.height * 0.52)
    receiver_x = rect.right - 76
    start_x = max(rect.x + int(rect.width * 0.40), rect.x + 225)
    end_x = receiver_x - 72
    if end_x <= start_x + 80:
        start_x = rect.x + int(rect.width * 0.38)
        end_x = rect.right - 142
    pygame.draw.line(screen, COLORS["channel"], (start_x, channel_y), (end_x, channel_y), 10)
    text = fonts["body_bold"].render("canal partagé", True, COLORS["channel"])
    screen.blit(text, text.get_rect(center=((start_x + end_x) // 2, channel_y - 30)))
    status = f"occupé jusqu'à t={sim.channel_busy_until:.1f}" if sim.time < sim.channel_busy_until else "libre"
    status_color = COLORS["wait"] if sim.time < sim.channel_busy_until else COLORS["success"]
    status_text = fonts["body_bold"].render(status, True, status_color)
    screen.blit(status_text, status_text.get_rect(center=((start_x + end_x) // 2, channel_y + 28)))

    active = {station for tx in sim.transmissions for station in tx.stations}
    for station, (x, y) in enumerate(positions):
        draw_laptop(pygame, screen, fonts, x, y, f"S{station}", station in active, scale)
        queue_x = x + int(68 * scale)
        draw_queue(pygame, screen, queue_x, y, sim.queues[station], sim.params.k, scale)
        color = COLORS["backoff"] if sim.backoff[station] > 1 else COLORS["muted"]
        draw_text(screen, fonts["small"], f"q={sim.queues[station]}  k={sim.backoff[station]}", (queue_x, y + int(28 * scale)), color)
        if sim.pending[station] and scale > 0.72:
            draw_text(screen, fonts["small"], f"t={sim.next_attempt[station]:.1f}", (queue_x + int(92 * scale), y + int(28 * scale)), COLORS["wait"])

    draw_router(pygame, screen, fonts, receiver_x, channel_y)
    draw_transmissions(pygame, screen, fonts, sim, positions, channel_y, receiver_x, rect)
    draw_flashes(pygame, screen, fonts, sim, positions)

    info_w = min(226, max(178, rect.width // 3))
    info = pygame.Rect(rect.right - info_w - 18, rect.y + 86, info_w, 104)
    rounded_rect(pygame, screen, (255, 255, 255), info, 8)
    rounded_rect(pygame, screen, COLORS["line"], info, 8, width=1)
    draw_text(screen, fonts["h2"], "Variables d'état", (info.x + 12, info.y + 10))
    draw_text(screen, fonts["small"], "queue[i] : paquets", (info.x + 12, info.y + 40), COLORS["muted"])
    draw_text(screen, fonts["small"], "k : backoff", (info.x + 12, info.y + 61), COLORS["muted"])
    draw_text(screen, fonts["small"], "pending : prévu", (info.x + 12, info.y + 82), COLORS["muted"])


def draw_metrics(pygame, screen, fonts, sim: Simulation, rect) -> None:
    panel(pygame, screen, rect, "Métriques live")
    items = [
        ("temps", f"{sim.time:.1f}"),
        ("débit", f"{sim.metrics.throughput(sim.time):.2f}"),
        ("arrivés", str(sim.metrics.arrived)),
        ("succès", str(sim.metrics.success)),
        ("collisions", str(sim.metrics.collision)),
        ("perdus", str(sim.metrics.lost)),
        ("taux perte", f"{sim.metrics.loss_rate():.2f}"),
        ("canal libre à", f"{sim.channel_busy_until:.1f}"),
    ]
    x0, y0 = rect.x + 12, rect.y + 42
    card_w, card_h = (rect.width - 36) // 2, 48
    for idx, (label, value) in enumerate(items):
        x = x0 + (idx % 2) * (card_w + 10)
        y = y0 + (idx // 2) * (card_h + 8)
        card = pygame.Rect(x, y, card_w, card_h)
        rounded_rect(pygame, screen, (250, 252, 254), card, 7)
        rounded_rect(pygame, screen, COLORS["line"], card, 7, width=1)
        draw_text(screen, fonts["small"], label, (x + 8, y + 6), COLORS["muted"])
        draw_text(screen, fonts["metric"], value, (x + 8, y + 21))


def draw_log(pygame, screen, fonts, sim: Simulation, rect) -> None:
    panel(pygame, screen, rect, "Événement courant")
    draw_wrapped(screen, fonts["body"], sim.message, pygame.Rect(rect.x + 14, rect.y + 44, rect.width - 28, 58))
    y = rect.y + 112
    for line in sim.log[:7]:
        pygame.draw.line(screen, COLORS["line"], (rect.x + 18, y + 7), (rect.x + 18, y + 27), 3)
        draw_wrapped(screen, fonts["small"], line, pygame.Rect(rect.x + 28, y, rect.width - 42, 34), COLORS["muted"], 14)
        y += 38


def draw_timeline(pygame, screen, fonts, sim: Simulation, rect) -> None:
    panel(pygame, screen, rect)
    steps = ["ARRIVÉE", "TENTATIVE", "SUCCÈS", "COLLISION", "BACKOFF", "PERTE"]
    gap = 9
    step_w = (rect.width - 28 - gap * (len(steps) - 1)) // len(steps)
    y = rect.y + 13
    for idx, step in enumerate(steps):
        x = rect.x + 14 + idx * (step_w + gap)
        active = step == sim.event or (step == "BACKOFF" and sim.event == "COLLISION")
        fill = COLORS["channel"] if active else COLORS["button"]
        text_color = (255, 255, 255) if active else COLORS["muted"]
        rounded_rect(pygame, screen, fill, pygame.Rect(x, y, step_w, 32), 7)
        rounded_rect(pygame, screen, (196, 208, 219), pygame.Rect(x, y, step_w, 32), 7, width=1)
        text = fonts["small"].render(step, True, text_color)
        screen.blit(text, text.get_rect(center=(x + step_w // 2, y + 16)))


def draw_left_panel(pygame, screen, fonts, rect, sliders, pause_button, reset_button) -> None:
    panel(pygame, screen, rect)
    draw_text(screen, fonts["title"], "Simulation MAC", (rect.x + 16, rect.y + 16))
    draw_wrapped(
        screen,
        fonts["body"],
        "Modifie les valeurs en direct pour voir comment le canal partagé réagit.",
        pygame.Rect(rect.x + 16, rect.y + 52, rect.width - 32, 52),
    )
    for slider in sliders:
        slider.draw(screen, fonts, pygame)
    pause_button.draw(screen, fonts, pygame)
    reset_button.draw(screen, fonts, pygame)


def draw_legend(pygame, screen, fonts, rect) -> None:
    panel(pygame, screen, rect, "Légende")
    rows = [
        (COLORS["packet"], "Paquet en file ou en transmission"),
        (COLORS["success"], "Succès : paquet livré"),
        (COLORS["collision"], "Collision : retry plus tard"),
        (COLORS["loss"], "Perte : file pleine"),
        (COLORS["backoff"], "k : niveau de backoff"),
    ]
    y = rect.y + 36
    for color, text in rows:
        pygame.draw.circle(screen, color, (rect.x + 23, y + 7), 6)
        draw_text(screen, fonts["small"], text, (rect.x + 39, y), COLORS["muted"])
        y += 18
    box_y = y + 6
    box_h = rect.bottom - box_y - 10
    if box_h >= 44:
        formula = "Backoff : délai moyen = tau * 2^k."
        box = pygame.Rect(rect.x + 14, box_y, rect.width - 28, min(58, box_h))
        rounded_rect(pygame, screen, (238, 246, 250), box, 7)
        rounded_rect(pygame, screen, (200, 223, 233), box, 7, width=1)
        draw_wrapped(screen, fonts["small"], formula, pygame.Rect(box.x + 10, box.y + 9, box.width - 20, box.height - 10), (36, 94, 124), 15)


def params_from_sliders(sliders: dict[str, Slider]) -> Params:
    return Params(
        n=int(sliders["n"].value),
        k=int(sliders["k"].value),
        lam=float(sliders["lam"].value),
        tau=float(sliders["tau"].value),
        speed=float(sliders["speed"].value),
    )


def configure_demo_values(sliders: dict[str, Slider]) -> None:
    sliders["n"].value = 4
    sliders["k"].value = 3
    sliders["lam"].value = 0.18
    sliders["tau"].value = 0.50
    sliders["speed"].value = 1.25


def run_app(args: argparse.Namespace) -> None:
    if args.self_test:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    if args.screenshot or args.record_gif:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    import pygame

    random.seed(args.seed)
    pygame.init()
    min_w, min_h = 980, 590
    start_w = max(min_w, args.width)
    start_h = max(min_h, args.height)
    screen = pygame.display.set_mode((start_w, start_h), pygame.RESIZABLE)
    pygame.display.set_caption("Simulation live MAC - desktop")
    clock = pygame.time.Clock()
    fonts = load_fonts(pygame)

    sliders = {
        "n": Slider("N stations", 0, 0, 240, 2, 10, 1, 5, "{:.0f}"),
        "k": Slider("K capacité file", 0, 0, 240, 1, 8, 1, 3, "{:.0f}"),
        "lam": Slider("lambda par station", 0, 0, 240, 0.01, 0.60, 0.01, 0.14, "{:.2f}"),
        "tau": Slider("tau backoff", 0, 0, 240, 0.10, 2.50, 0.05, 0.50, "{:.2f}"),
        "speed": Slider("vitesse", 0, 0, 240, 0.20, 5.00, 0.10, 1.00, "{:.1f}x"),
    }
    pause_button = Button("Pause", (0, 0, 100, 34))
    reset_button = Button("Redémarrer", (0, 0, 100, 34))
    if args.record_gif:
        configure_demo_values(sliders)
    sim = Simulation(params_from_sliders(sliders))
    if args.record_gif:
        sim.prepare_demo()
    running = True
    paused = False

    def draw_all() -> None:
        width, height = screen.get_size()
        layout = compute_layout(pygame, width, height)
        configure_controls(sliders, pause_button, reset_button, layout["left"])
        screen.fill(COLORS["bg"])
        draw_left_panel(pygame, screen, fonts, layout["left"], sliders.values(), pause_button, reset_button)
        draw_legend(pygame, screen, fonts, layout["legend"])
        draw_stage(pygame, screen, fonts, sim, layout["stage"])
        draw_timeline(pygame, screen, fonts, sim, layout["timeline"])
        draw_metrics(pygame, screen, fonts, sim, layout["right_top"])
        draw_log(pygame, screen, fonts, sim, layout["right_bottom"])

    if args.self_test:
        layout = compute_layout(pygame, start_w, start_h)
        configure_controls(sliders, pause_button, reset_button, layout["left"])
        sim.update(0.1)
        draw_all()
        pygame.display.flip()
        pygame.quit()
        print("desktop self-test ok")
        return

    if args.screenshot:
        layout = compute_layout(pygame, start_w, start_h)
        configure_controls(sliders, pause_button, reset_button, layout["left"])
        sim.update(0.2)
        draw_all()
        pygame.image.save(screen, args.screenshot)
        pygame.quit()
        print(f"capture enregistrée : {args.screenshot}")
        return

    if args.record_gif:
        from PIL import Image

        layout = compute_layout(pygame, start_w, start_h)
        configure_controls(sliders, pause_button, reset_button, layout["left"])
        frame_count = max(1, int(args.record_seconds * args.record_fps))
        frame_dt = 1.0 / max(1, args.record_fps)
        images: list[Image.Image] = []
        for _ in range(frame_count):
            sim.update(frame_dt)
            draw_all()
            raw = pygame.image.tostring(screen, "RGB")
            images.append(Image.frombytes("RGB", screen.get_size(), raw).resize((960, 557)))
        images[0].save(
            args.record_gif,
            save_all=True,
            append_images=images[1:],
            duration=int(1000 / max(1, args.record_fps)),
            loop=0,
            optimize=True,
        )
        pygame.quit()
        print(f"GIF desktop enregistré : {args.record_gif} ({len(images)} images)")
        return

    layout = compute_layout(pygame, start_w, start_h)
    configure_controls(sliders, pause_button, reset_button, layout["left"])

    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.VIDEORESIZE:
                new_w = max(min_w, event.w)
                new_h = max(min_h, event.h)
                screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
            changed = False
            for slider in sliders.values():
                if slider.handle_event(event, pygame):
                    changed = True
            if changed:
                sim.set_params(params_from_sliders(sliders))
            if pause_button.handle_event(event, pygame):
                paused = not paused
                pause_button.label = "Reprendre" if paused else "Pause"
                sim.add_log("Simulation en pause." if paused else "Simulation reprise.")
            if reset_button.handle_event(event, pygame):
                sim.reset(params_from_sliders(sliders))

        if not paused:
            sim.update(dt)

        draw_all()
        pygame.display.flip()

    pygame.quit()


def main() -> None:
    run_app(parse_args())


if __name__ == "__main__":
    main()
