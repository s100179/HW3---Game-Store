# game_server.py
# Python Tetris PK server (2 players + spectators)
# - line-delimited JSON protocol (like your OOXX)
# - server authoritative tick loop
# - shared 7-bag sequence, each player has seq_pos (like your C++ server) :contentReference[oaicite:2]{index=2}

import os
import time
import json
import socket
import threading
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

W, H = 10, 20

# fall speeds (ms), similar spirit to your C++ SPEED_MS :contentReference[oaicite:3]{index=3}
SPEED_MS = [900, 800, 700, 600, 500, 450, 400, 350, 300, 250, 200, 150, 100, 50]

# Shapes 4x4: order I L J S O T Z (same as your C++ SH) :contentReference[oaicite:4]{index=4}
SHAPES = {
    "I": [[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,0,0,0]],
    "L": [[0,0,0,0],[1,0,0,0],[1,0,0,0],[1,1,0,0]],
    "J": [[0,0,0,0],[0,0,0,1],[0,0,0,1],[0,0,1,1]],
    "S": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[1,1,0,0]],
    "O": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[0,1,1,0]],
    "T": [[0,0,0,0],[0,0,0,0],[0,1,1,1],[0,0,1,0]],
    "Z": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[0,0,1,1]],
}
LETTERS = ["I","L","J","S","O","T","Z"]

def compute_port_from_room(room_id: int) -> int:
    return 6000 + (room_id % 1000)

def send_json(sock: socket.socket, obj: dict):
    try:
        sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError:
        pass

def rot_cw(m: List[List[int]]) -> List[List[int]]:
    # 4x4 rotate clockwise
    return [[m[3-c][r] for c in range(4)] for r in range(4)]

def mask(letter: str, rot: int) -> List[List[int]]:
    m = [row[:] for row in SHAPES[letter]]
    for _ in range(rot & 3):
        m = rot_cw(m)
    return m

def bbox(letter: str, rot: int) -> Tuple[int,int,int,int]:
    m = mask(letter, rot)
    minr, maxr, minc, maxc = 4, -1, 4, -1
    for r in range(4):
        for c in range(4):
            if m[r][c]:
                minr = min(minr, r); maxr = max(maxr, r)
                minc = min(minc, c); maxc = max(maxc, c)
    if maxr == -1:
        return (0,0,0,0)
    return (minr, maxr, minc, maxc)

@dataclass
class Piece:
    letter: str = "T"
    rot: int = 0
    x: int = 3
    y: int = 0

@dataclass
class PlayerState:
    fd: Optional[socket.socket] = None
    role: str = "SPEC"     # P1 / P2 / SPEC
    alive: bool = False
    is_spec: bool = False

    board: List[List[int]] = field(default_factory=lambda: [[0]*W for _ in range(H)])
    cur: Piece = field(default_factory=Piece)
    next_letter: Optional[str] = None
    hold_letter: Optional[str] = None
    can_hold: bool = True

    level: int = 1
    score: int = 0
    lines: int = 0
    fall_ms: int = SPEED_MS[0]
    next_fall_at: float = 0.0
    lost: bool = False

    seq_pos: int = 0  # per-player cursor into global sequence :contentReference[oaicite:5]{index=5}

class Match:
    def __init__(self):
        self.mu = threading.Lock()
        self.p1 = PlayerState(role="P1", is_spec=False)
        self.p2 = PlayerState(role="P2", is_spec=False)
        self.specs: List[PlayerState] = []
        self.started = False

        self.rng = random.Random()
        self.piece_seq: List[str] = []  # shared 7-bag sequence :contentReference[oaicite:6]{index=6}

    def ensure_seq_len(self, n: int):
        while len(self.piece_seq) < n:
            bag = LETTERS[:]
            self.rng.shuffle(bag)
            self.piece_seq.extend(bag)

    def get_piece(self, pl: PlayerState) -> str:
        if pl.seq_pos < 0:
            pl.seq_pos = 0
        self.ensure_seq_len(pl.seq_pos + 1)
        letter = self.piece_seq[pl.seq_pos]
        pl.seq_pos += 1
        return letter

    def bcast(self, obj: dict):
        with self.mu:
            targets = []
            if self.p1.fd: targets.append(self.p1.fd)
            if self.p2.fd: targets.append(self.p2.fd)
            for sp in self.specs:
                if sp.fd: targets.append(sp.fd)
        for fd in targets:
            send_json(fd, obj)

def collide(pl: PlayerState, pc: Piece) -> bool:
    m = mask(pc.letter, pc.rot)
    for i in range(4):
        for j in range(4):
            if not m[i][j]:
                continue
            yy = pc.y + i
            xx = pc.x + j
            if xx < 0 or xx >= W or yy >= H:
                return True
            if yy >= 0 and pl.board[yy][xx]:
                return True
    return False

def lock_piece(pl: PlayerState):
    m = mask(pl.cur.letter, pl.cur.rot)
    touch_top = False
    for i in range(4):
        for j in range(4):
            if not m[i][j]:
                continue
            yy = pl.cur.y + i
            xx = pl.cur.x + j
            if 0 <= yy < H and 0 <= xx < W:
                pl.board[yy][xx] = 1
                if yy == 0:
                    touch_top = True
    pl.can_hold = True
    if touch_top:
        pl.lost = True

def clear_lines(pl: PlayerState) -> int:
    cleared = 0
    r = H - 1
    while r >= 0:
        if all(pl.board[r][c] for c in range(W)):
            cleared += 1
            # drop
            for y in range(r, 0, -1):
                pl.board[y] = pl.board[y-1][:]
            pl.board[0] = [0]*W
        else:
            r -= 1

    if cleared:
        pl.lines += cleared
        pl.score += 10 * cleared
        if pl.score % 100 == 0 and pl.level < 7:
            pl.level += 1
        pl.fall_ms = SPEED_MS[min(pl.level - 1, len(SPEED_MS)-1)]
    return cleared

def spawn_new(pl: PlayerState, M: Match):
    if pl.next_letter is None:
        pl.next_letter = M.get_piece(pl)

    pl.cur.letter = pl.next_letter
    pl.cur.rot = 0
    pl.next_letter = M.get_piece(pl)

    minr, maxr, minc, maxc = bbox(pl.cur.letter, pl.cur.rot)
    width = maxc - minc + 1
    pl.cur.x = (W - width)//2 - minc
    pl.cur.y = -minr

def try_hold(pl: PlayerState, M: Match):
    if not pl.can_hold or pl.lost:
        return
    cur = pl.cur.letter
    if pl.hold_letter is None:
        pl.hold_letter = cur
        spawn_new(pl, M)
    else:
        pl.hold_letter, pl.cur.letter = pl.cur.letter, pl.hold_letter
        pl.cur.rot = 0
        minr, maxr, minc, maxc = bbox(pl.cur.letter, pl.cur.rot)
        width = maxc - minc + 1
        pl.cur.x = (W - width)//2 - minc
        pl.cur.y = -minr
        # small wallkick: x+1 then x-2 like your C++ logic :contentReference[oaicite:7]{index=7}
        if collide(pl, pl.cur):
            t = Piece(pl.cur.letter, pl.cur.rot, pl.cur.x + 1, pl.cur.y)
            if collide(pl, t):
                t = Piece(pl.cur.letter, pl.cur.rot, pl.cur.x - 1, pl.cur.y)
                t.x -= 1  # total -2
                if collide(pl, t):
                    t = pl.cur
            pl.cur = t
    pl.can_hold = False

def apply_input(pl: PlayerState, key: str, M: Match):
    if pl.lost:
        return
    k = key.lower()
    if k == "p":
        return
    if k == "c":
        try_hold(pl, M)
        return

    def move(np: Piece) -> bool:
        if not collide(pl, np):
            pl.cur = np
            return True
        return False

    if k == "a":  # left
        move(Piece(pl.cur.letter, pl.cur.rot, pl.cur.x - 1, pl.cur.y))
    elif k == "d":  # right
        move(Piece(pl.cur.letter, pl.cur.rot, pl.cur.x + 1, pl.cur.y))
    elif k == "s":  # soft drop
        move(Piece(pl.cur.letter, pl.cur.rot, pl.cur.x, pl.cur.y + 1))
    elif k == "w":  # rotate cw with simple wallkick (+1 then -2) :contentReference[oaicite:8]{index=8}
        np = Piece(pl.cur.letter, (pl.cur.rot + 1) & 3, pl.cur.x, pl.cur.y)
        if not move(np):
            np2 = Piece(np.letter, np.rot, np.x + 1, np.y)
            if not move(np2):
                np3 = Piece(np.letter, np.rot, np.x - 1, np.y)
                np3.x -= 1
                move(np3)
    elif k == "b":  # hard drop
        np = Piece(pl.cur.letter, pl.cur.rot, pl.cur.x, pl.cur.y)
        while True:
            t = Piece(np.letter, np.rot, np.x, np.y + 1)
            if collide(pl, t):
                break
            np = t
        pl.cur = np
        lock_piece(pl)
        if not pl.lost:
            clear_lines(pl)
            spawn_new(pl, M)

def build_player_view(pl: PlayerState) -> dict:
    return {
        "board": pl.board,
        "active": {"x": pl.cur.x, "y": pl.cur.y, "rot": pl.cur.rot, "shape": pl.cur.letter},
        "score": pl.score,
        "lines": pl.lines,
        "level": pl.level,
        "next": pl.next_letter,
        "hold": pl.hold_letter,
        "lost": pl.lost,
    }

def build_state(M: Match) -> dict:
    # send both boards each tick (like SNAPSHOT2 idea) :contentReference[oaicite:9]{index=9}
    return {"type": "state", "p1": build_player_view(M.p1), "p2": build_player_view(M.p2)}

def game_loop(M: Match, tick_hz: float = 60.0):
    # init
    with M.mu:
        spawn_new(M.p1, M)
        spawn_new(M.p2, M)
        now = time.time()
        M.p1.next_fall_at = now + M.p1.fall_ms / 1000.0
        M.p2.next_fall_at = now + M.p2.fall_ms / 1000.0

    M.bcast({"type": "info", "message": "Game start!"})
    M.bcast(build_state(M))

    dt = 1.0 / tick_hz
    while True:
        time.sleep(dt)

        with M.mu:
            now = time.time()

            # check end
            over = False
            winner = "DRAW"
            if M.p1.lost and M.p2.lost:
                if M.p1.score > M.p2.score: winner = "P1"
                elif M.p2.score > M.p1.score: winner = "P2"
                over = True
            elif M.p1.lost:
                winner = "P2"; over = True
            elif M.p2.lost:
                winner = "P1"; over = True

            if over:
                # OOXX-style: game_over
                M.bcast({"type": "game_over", "winner": winner})
                return

            changed = False

            def step(pl: PlayerState) -> bool:
                nonlocal now
                if pl.lost:
                    return False
                if now < pl.next_fall_at:
                    return False
                t = Piece(pl.cur.letter, pl.cur.rot, pl.cur.x, pl.cur.y + 1)
                if not collide(pl, t):
                    pl.cur = t
                else:
                    lock_piece(pl)
                    if not pl.lost:
                        clear_lines(pl)
                        spawn_new(pl, M)
                pl.next_fall_at = now + pl.fall_ms / 1000.0
                return True

            changed = step(M.p1) or step(M.p2)

        if changed:
            M.bcast(build_state(M))

def assign_role(M: Match, fd: socket.socket) -> str:
    with M.mu:
        if M.p1.fd is None:
            M.p1.fd = fd; M.p1.alive = True; M.p1.role = "P1"; M.p1.is_spec = False
            return "P1"
        if M.p2.fd is None:
            M.p2.fd = fd; M.p2.alive = True; M.p2.role = "P2"; M.p2.is_spec = False
            return "P2"
        sp = PlayerState(fd=fd, role="SPEC", alive=True, is_spec=True)
        M.specs.append(sp)
        return "SPEC"

def maybe_start(M: Match):
    go = False
    with M.mu:
        if (not M.started) and (M.p1.fd is not None) and (M.p2.fd is not None):
            M.started = True
            go = True
    if go:
        threading.Thread(target=game_loop, args=(M,), daemon=True).start()

def client_thread(M: Match, fd: socket.socket, addr):
    f = fd.makefile("r", encoding="utf-8")
    role = assign_role(M, fd)
    send_json(fd, {"type": "welcome", "role": role})

    # immediately push state so GUI can draw something
    send_json(fd, build_state(M))

    maybe_start(M)

    try:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "input":
                key = msg.get("key", "")
                if not key:
                    continue
                with M.mu:
                    pl = None
                    if role == "P1": pl = M.p1
                    elif role == "P2": pl = M.p2
                    else: pl = None
                    if pl is not None:
                        apply_input(pl, key[0], M)
                        # reset fall timer like your server does after input :contentReference[oaicite:10]{index=10}
                        pl.next_fall_at = time.time() + pl.fall_ms / 1000.0
                M.bcast(build_state(M))
            elif mtype == "ping":
                send_json(fd, {"type": "pong"})
    except Exception:
        pass
    finally:
        # disconnect handling: if P1/P2 leaves, end game awarding other (like your server) :contentReference[oaicite:11]{index=11}
        other_winner = None
        with M.mu:
            if role == "P1" and M.p1.fd == fd:
                M.p1.fd = None; M.p1.alive = False
                other_winner = "P2"
            elif role == "P2" and M.p2.fd == fd:
                M.p2.fd = None; M.p2.alive = False
                other_winner = "P1"
            else:
                # spectator remove
                M.specs = [sp for sp in M.specs if sp.fd != fd]

        try:
            fd.close()
        except OSError:
            pass

        if other_winner:
            M.bcast({"type": "game_over", "winner": other_winner})

def main():
    room_id = int(os.environ.get("GAME_ROOM_ID", "1"))
    host = "0.0.0.0"
    port = compute_port_from_room(room_id)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen()

    print(f"[TETRIS] game_server listening on {host}:{port} (room {room_id})")

    M = Match()

    while True:
        fd, addr = srv.accept()
        threading.Thread(target=client_thread, args=(M, fd, addr), daemon=True).start()

if __name__ == "__main__":
    main()
