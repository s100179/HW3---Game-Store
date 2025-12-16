import os
import socket
import json
import threading
import queue
import tkinter as tk
from tkinter import messagebox


def send_json(sock, obj):
    try:
        data = json.dumps(obj).encode("utf-8") + b"\n"
        sock.sendall(data)
    except OSError:
        pass


def recv_json_line(f):
    """從 makefile 讀一行 JSON，失敗或 EOF 回傳 None"""
    line = f.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _pick_server_endpoint():
    host = os.getenv("GAME_SERVER_HOST")
    room_id = os.getenv("GAME_ROOM_ID")

    # fallback：沿用 lobby 的 host
    if not host:
        host = os.getenv("SERVER_HOST")
    if not host:
        host = "127.0.0.1"

    # 取得 room_id
    try:
        room_id = int(room_id)
    except (TypeError, ValueError):
        room_id = 0

    BASE_PORT = 8000
    port = BASE_PORT + (room_id % 1000)

    return host, port


class NetworkThread(threading.Thread):

    def __init__(self, sock: socket.socket, msg_queue: queue.Queue):
        super().__init__(daemon=True)
        self.sock = sock
        self.msg_queue = msg_queue

    def run(self):
        try:
            f = self.sock.makefile("r", encoding="utf-8")
            while True:
                msg = recv_json_line(f)
                if msg is None:
                    # EOF 或錯誤
                    self.msg_queue.put({"type": "connection_lost"})
                    break
                self.msg_queue.put(msg)
        except Exception as e:
            self.msg_queue.put({"type": "connection_lost", "error": str(e)})


class TicTacToeClientGUI:
    def __init__(self, root: tk.Tk, sock: socket.socket, player_name: str,
                 game_name: str, version: str):
        self.root = root
        self.sock = sock
        self.player_name = player_name
        self.game_name = game_name
        self.version = version

        self.root.title(f"{game_name} (v{version}) - {player_name}")

        # 狀態
        self.msg_queue: queue.Queue = queue.Queue()
        self.net_thread = NetworkThread(sock, self.msg_queue)
        self.net_thread.start()

        self.my_symbol = "?"      # "X" or "O"
        self.board = [" "] * 9    # 0~8
        self.your_turn = False
        self.game_over = False

        # UI
        self._build_ui()

        # 開始輪詢訊息
        self.root.after(50, self._poll_messages)

    # ====== UI 建立 ======
    def _build_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=5)

        tk.Label(top_frame, text=f"Player: {self.player_name}").grid(row=0, column=0, padx=5)
        self.label_symbol = tk.Label(top_frame, text="Symbol: ?", width=13)
        self.label_symbol.grid(row=0, column=1, padx=5)
        self.label_status = tk.Label(top_frame, text="連線中...", width=25)
        self.label_status.grid(row=0, column=2, padx=5)

        board_frame = tk.Frame(self.root)
        board_frame.pack(pady=10)

        self.buttons: list[tk.Button] = []
        for r in range(3):
            for c in range(3):
                idx = r * 3 + c
                btn = tk.Button(
                    board_frame,
                    text=" ",
                    width=4,
                    height=2,
                    font=("Arial", 24),
                    command=lambda i=idx: self.on_cell_click(i),
                )
                btn.grid(row=r, column=c, padx=5, pady=5)
                self.buttons.append(btn)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(pady=5)

        self.btn_quit = tk.Button(bottom_frame, text="離開遊戲", command=self.on_quit)
        self.btn_quit.pack()

    # ====== 訊息輪詢 ======
    def _poll_messages(self):
        while not self.msg_queue.empty():
            msg = self.msg_queue.get()
            self.handle_message(msg)

        # 如果尚未 game_over，持續輪詢
        if not self.game_over:
            self.root.after(50, self._poll_messages)

    # ====== 處理 server 訊息 ======
    def handle_message(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "welcome":
            # {"type": "welcome", "symbol": sym, "message": "...", ...}
            self.my_symbol = msg.get("symbol", "?")
            self.label_symbol.config(text=f"Symbol: {self.my_symbol}")
            text = msg.get("message", "")
            if text:
                self.label_status.config(text=text)

        elif mtype == "state":
            # {"type": "state", "board": [...], "your_turn": bool, "message": "..."}
            self.board = msg.get("board", [" "] * 9)
            self.your_turn = msg.get("your_turn", False)
            message = msg.get("message", "")
            if self.your_turn:
                if self.my_symbol != "?":
                    self.label_status.config(text=f"輪到你 ({self.my_symbol})")
                else:
                    self.label_status.config(text="輪到你")
            else:
                self.label_status.config(text=message or "等待對手落子")

            self.update_board_ui()

        elif mtype == "error":
            # {"type": "error", "message": "..."}
            err = msg.get("message", "未知錯誤")
            messagebox.showwarning("錯誤", err)

        elif mtype == "game_over":
            # {"type": "game_over", "board": [...], "winner": "X"/"O"/None, "reason": "..."}
            self.board = msg.get("board", [" "] * 9)
            self.update_board_ui()
            winner = msg.get("winner")
            reason = msg.get("reason", "")

            self.game_over = True
            self.disable_board()

            if reason:
                # server 可能傳「平手」或「對手斷線，遊戲結束」之類
                msg_text = reason
            else:
                if winner is None:
                    msg_text = "平手！"
                elif winner == self.my_symbol:
                    msg_text = "你贏了！🎉"
                else:
                    msg_text = f"玩家 {winner} 獲勝，你輸了 QQ"

            self.label_status.config(text="遊戲結束")
            messagebox.showinfo("Game Over", msg_text)

            # 關閉 socket
            try:
                self.sock.close()
            except OSError:
                pass

        elif mtype == "connection_lost":
            if not self.game_over:
                self.game_over = True
                self.disable_board()
                self.label_status.config(text="連線中斷")
                messagebox.showinfo("連線中斷", "伺服器中斷連線，遊戲結束。")
                try:
                    self.sock.close()
                except OSError:
                    pass

    # ====== GUI 動作 ======
    def update_board_ui(self):
        for i, btn in enumerate(self.buttons):
            ch = self.board[i]
            btn.config(text=ch if ch != " " else " ")

    def disable_board(self):
        for btn in self.buttons:
            btn.config(state=tk.DISABLED)

    def on_cell_click(self, index: int):
        if self.game_over:
            return
        if not self.your_turn:
            return
        if index < 0 or index >= 9:
            return
        if self.board[index] != " ":
            return

        # 傳送 move 給 server
        send_json(self.sock, {"type": "move", "pos": index})

    def on_quit(self):
        if messagebox.askokcancel("離開遊戲", "確定要離開遊戲嗎？"):
            try:
                send_json(self.sock, {"type": "quit"})
            except Exception:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.game_over = True
            self.root.destroy()


def main():
    player_name = os.getenv("GAME_PLAYER_NAME", "Player")
    game_name = os.getenv("GAME_NAME", "OOXX")
    version = os.getenv("GAME_VERSION", "1")

    server_host, server_port = _pick_server_endpoint()

    # 先建立 socket 連線
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((server_host, server_port))
    except Exception as e:
        # 連不上就用簡單的訊息框告訴使用者
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "連線失敗",
            f"無法連線到遊戲伺服器 {server_host}:{server_port}\n{e}\n\n"
            f"提示：請確認 game_server.py 已啟動，且 port 一致。",
        )
        root.destroy()
        return

    # 建立 GUI
    root = tk.Tk()
    app = TicTacToeClientGUI(root, s, player_name, game_name, version)
    root.mainloop()


if __name__ == "__main__":
    main()
