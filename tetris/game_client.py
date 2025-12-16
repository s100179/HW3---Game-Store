# game_client.py
# Python Tkinter GUI client for 2P Tetris
# - newline JSON protocol (like your OOXX)
# - server sends: welcome, state, info, game_over
# - client sends: input {key:"a"/"d"/"s"/"w"/"b"/"c"}

import os
import json
import socket
import threading
import queue
import tkinter as tk
from tkinter import messagebox

W, H = 10, 20

def compute_port_from_room(room_id: int) -> int:
    return 6000 + (room_id % 1000)

def send_json(sock: socket.socket, obj: dict):
    try:
        sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError:
        pass

class RxThread(threading.Thread):
    def __init__(self, sock: socket.socket, q: queue.Queue):
        super().__init__(daemon=True)
        self.sock = sock
        self.q = q

    def run(self):
        try:
            f = self.sock.makefile("r", encoding="utf-8")
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.q.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            self.q.put({"type": "connection_lost", "error": str(e)})
        finally:
            self.q.put({"type": "connection_lost"})

class TetrisGUI:
    def __init__(self, root: tk.Tk, sock: socket.socket):
        self.root = root
        self.sock = sock
        self.q = queue.Queue()
        self.rx = RxThread(sock, self.q)
        self.rx.start()

        self.role = "SPEC"   # P1/P2/SPEC
        self.p1 = None
        self.p2 = None
        self.game_over = False

        self.root.title("Online Tetris (2P)")
        self._build_ui()
        self._bind_keys()

        self.root.after(30, self._poll)

    def _build_ui(self):
        top = tk.Frame(self.root)
        top.pack(pady=6)

        self.lbl_role = tk.Label(top, text="Role: ?", width=12)
        self.lbl_role.pack(side=tk.LEFT, padx=6)

        self.lbl_status = tk.Label(top, text="Connecting...", width=40, anchor="w")
        self.lbl_status.pack(side=tk.LEFT, padx=6)

        mid = tk.Frame(self.root)
        mid.pack(padx=10, pady=10)

        # canvas sizes: me big, opp small (like your dual-board client concept) :contentReference[oaicite:13]{index=13}
        self.cell_me = 24
        self.cell_opp = 12

        self.canvas_me = tk.Canvas(mid, width=W*self.cell_me, height=H*self.cell_me, bg="#15151a", highlightthickness=0)
        self.canvas_me.grid(row=0, column=0, padx=10)

        side = tk.Frame(mid)
        side.grid(row=0, column=1, padx=10, sticky="n")

        self.canvas_opp = tk.Canvas(side, width=W*self.cell_opp, height=H*self.cell_opp, bg="#242434", highlightthickness=0)
        self.canvas_opp.pack(pady=6)

        self.lbl_score = tk.Label(side, text="Score: 0\nLines: 0\nLevel: 1\nNext: ?\nHold: ?", justify="left")
        self.lbl_score.pack(pady=6)

        self.btn_quit = tk.Button(side, text="離開", command=self.on_quit)
        self.btn_quit.pack(pady=10)

    def _bind_keys(self):
        # focus
        self.root.bind("<Button-1>", lambda e: self.root.focus_set())

        # WASD-ish + extras
        self.root.bind("<KeyPress-a>", lambda e: self.send_key("a"))
        self.root.bind("<KeyPress-d>", lambda e: self.send_key("d"))
        self.root.bind("<KeyPress-s>", lambda e: self.send_key("s"))
        self.root.bind("<KeyPress-w>", lambda e: self.send_key("w"))
        self.root.bind("<KeyPress-b>", lambda e: self.send_key("b"))
        self.root.bind("<KeyPress-c>", lambda e: self.send_key("c"))

        # arrow keys mapping
        self.root.bind("<Left>",  lambda e: self.send_key("a"))
        self.root.bind("<Right>", lambda e: self.send_key("d"))
        self.root.bind("<Down>",  lambda e: self.send_key("s"))
        self.root.bind("<Up>",    lambda e: self.send_key("w"))
        self.root.bind("<space>", lambda e: self.send_key("b"))

    def send_key(self, k: str):
        if self.game_over:
            return
        # only P1/P2 can control
        if self.role not in ("P1", "P2"):
            return
        send_json(self.sock, {"type": "input", "key": k})

    def _poll(self):
        while not self.q.empty():
            msg = self.q.get()
            self._handle(msg)
        if not self.game_over:
            self.root.after(30, self._poll)

    def _handle(self, msg: dict):
        t = msg.get("type")
        if t == "welcome":
            self.role = msg.get("role", "SPEC")
            self.lbl_role.config(text=f"Role: {self.role}")
            self.lbl_status.config(text="Connected")
        elif t == "info":
            self.lbl_status.config(text=msg.get("message", ""))
        elif t == "state":
            self.p1 = msg.get("p1")
            self.p2 = msg.get("p2")
            self._redraw()
        elif t == "game_over":
            self.game_over = True
            winner = msg.get("winner", "DRAW")
            self.lbl_status.config(text=f"Game Over - Winner: {winner}")
            messagebox.showinfo("Game Over", f"Winner: {winner}")
            try:
                self.sock.close()
            except OSError:
                pass
        elif t == "connection_lost":
            if not self.game_over:
                self.game_over = True
                self.lbl_status.config(text="Connection lost")
                messagebox.showinfo("Disconnected", "Server disconnected.")
                try:
                    self.sock.close()
                except OSError:
                    pass

    def _draw_board(self, canvas: tk.Canvas, cell: int, view: dict):
        canvas.delete("all")
        if not view:
            return

        board = view.get("board", [[0]*W for _ in range(H)])
        active = view.get("active", {})
        ax, ay = active.get("x", 0), active.get("y", 0)
        # draw grid + locked blocks
        for y in range(H):
            for x in range(W):
                if board[y][x]:
                    canvas.create_rectangle(
                        x*cell, y*cell, (x+1)*cell, (y+1)*cell,
                        fill="#7f7f7f", outline="#303040"
                    )
                else:
                    # faint grid (cheap)
                    canvas.create_rectangle(
                        x*cell, y*cell, (x+1)*cell, (y+1)*cell,
                        outline="#232334"
                    )

        # draw active piece as white squares
        shape = active.get("shape", "T")
        rot = active.get("rot", 0)

        # local mask rotation (same as server)
        from copy import deepcopy
        SHAPES = {
            "I": [[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,0,0,0]],
            "L": [[0,0,0,0],[1,0,0,0],[1,0,0,0],[1,1,0,0]],
            "J": [[0,0,0,0],[0,0,0,1],[0,0,0,1],[0,0,1,1]],
            "S": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[1,1,0,0]],
            "O": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[0,1,1,0]],
            "T": [[0,0,0,0],[0,0,0,0],[0,1,1,1],[0,0,1,0]],
            "Z": [[0,0,0,0],[0,0,0,0],[0,1,1,0],[0,0,1,1]],
        }
        def rot_cw(m):
            return [[m[3-c][r] for c in range(4)] for r in range(4)]
        m = deepcopy(SHAPES.get(shape, SHAPES["T"]))
        for _ in range(rot & 3):
            m = rot_cw(m)

        for i in range(4):
            for j in range(4):
                if not m[i][j]:
                    continue
                xx = ax + j
                yy = ay + i
                if 0 <= xx < W and 0 <= yy < H:
                    canvas.create_rectangle(
                        xx*cell, yy*cell, (xx+1)*cell, (yy+1)*cell,
                        fill="#f0f0f0", outline="#303040"
                    )

    def _redraw(self):
        if not (self.p1 and self.p2):
            return

        # decide which is "me" depending on role
        if self.role == "P2":
            me, opp = self.p2, self.p1
        else:
            me, opp = self.p1, self.p2

        self._draw_board(self.canvas_me, self.cell_me, me)
        self._draw_board(self.canvas_opp, self.cell_opp, opp)

        # stats (show my stats)
        self.lbl_score.config(text=
            f"Score: {me.get('score',0)}\n"
            f"Lines: {me.get('lines',0)}\n"
            f"Level: {me.get('level',1)}\n"
            f"Next: {me.get('next','?')}\n"
            f"Hold: {me.get('hold','-')}"
        )

    def on_quit(self):
        if messagebox.askokcancel("Quit", "要離開遊戲嗎？"):
            try:
                self.sock.close()
            except OSError:
                pass
            self.game_over = True
            self.root.destroy()

def main():
    host = os.environ.get("GAME_SERVER_HOST", "127.0.0.1")
    room_id = int(os.environ.get("GAME_ROOM_ID", "1"))

    env_port = os.environ.get("GAME_SERVER_PORT", "")
    port = None
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            port = None

    if port in (None, 5000, 12001):
        port = compute_port_from_room(room_id)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Connect failed", f"Cannot connect {host}:{port}\n{e}")
        root.destroy()
        return

    root = tk.Tk()
    app = TetrisGUI(root, s)
    root.mainloop()


if __name__ == "__main__":
    main()
