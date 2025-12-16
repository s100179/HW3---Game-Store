import os
import socket
import json
import datetime

HOST = "0.0.0.0"
PORT = 8000

def send_json(sock, obj):
    data = json.dumps(obj).encode("utf-8") + b"\n"
    sock.sendall(data)

def recv_json(sock):
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf += chunk
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                return json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                return None


def print_board(board):
    """給 server log 用，不影響協定"""
    def cell(i):
        return board[i] if board[i] != " " else str(i + 1)
    print(f" {cell(0)} | {cell(1)} | {cell(2)} ")
    print("---+---+---")
    print(f" {cell(3)} | {cell(4)} | {cell(5)} ")
    print("---+---+---")
    print(f" {cell(6)} | {cell(7)} | {cell(8)} ")


def check_winner(board):
    lines = [
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    ]
    for a, b, c in lines:
        if board[a] != " " and board[a] == board[b] and board[b] == board[c]:
            return board[a]
    return None


def is_full(board):
    return all(cell != " " for cell in board)


def main():
    room_id = os.getenv("GAME_ROOM_ID", "?")
    players = os.getenv("GAME_ROOM_PLAYERS", "")
    game_name = os.getenv("GAME_NAME", "ooxx")
    version = os.getenv("GAME_VERSION", "1")

    print("=== OOXX Game Server ===")
    print(f"Room ID   : {room_id}")
    print(f"Game name : {game_name} (v{version})")
    print(f"Players   : {players}")

    # 寫 log，證明 server 有被啟動
    try:
        with open("server_log.txt", "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] "
                f"room={room_id}, game={game_name}, v={version}, players={players}\n"
            )
    except Exception as e:
        print("Failed to write log:", e)

    # 建 socket 開始聽
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(2)

    print(f"Server listening on {HOST}:{PORT}, waiting for 2 players...")

    conns = []
    addrs = []
    symbols = ["X", "O"]

    # 等兩個玩家連進來
    while len(conns) < 2:
        conn, addr = srv.accept()
        conns.append(conn)
        addrs.append(addr)
        player_idx = len(conns) - 1
        sym = symbols[player_idx]
        print(f"Player {player_idx} ({sym}) connected from {addr}")
        send_json(
            conn,
            {
                "type": "welcome",
                "symbol": sym,
                "message": f"你是 {sym}，等待另一位玩家加入...",
                "player_index": player_idx,
            },
        )

    # 兩個都連線後，開始遊戲
    board = [" "] * 9
    current_idx = 0  # 0: X, 1: O

    # 遊戲主迴圈
    while True:
        # 先同步棋盤給兩邊
        for i, conn in enumerate(conns):
            try:
                send_json(
                    conn,
                    {
                        "type": "state",
                        "board": board,
                        "your_turn": (i == current_idx),
                        "message": f"輪到 {'X' if current_idx == 0 else 'O'} 下子",
                    },
                )
            except Exception as e:
                print(f"Failed to send state to player {i}: {e}")
                return

        # 檢查是否已經有人贏 / 平手（理論上上面送 state 前就可以檢查）
        winner = check_winner(board)
        if winner or is_full(board):
            break

        # 等目前玩家送出落子
        conn = conns[current_idx]
        while True:
            msg = recv_json(conn)
            if msg is None:
                print(f"Player {current_idx} disconnected.")
                # 通知對方遊戲結束
                other = conns[1 - current_idx]
                try:
                    send_json(
                        other,
                        {
                            "type": "game_over",
                            "board": board,
                            "winner": None,
                            "reason": "對手斷線，遊戲結束",
                        },
                    )
                except Exception:
                    pass
                return

            if msg.get("type") == "move":
                pos = msg.get("pos")
                if not isinstance(pos, int) or not (0 <= pos < 9):
                    send_json(conn, {"type": "error", "message": "位置無效，請輸入 0~8。"})
                    continue
                if board[pos] != " ":
                    send_json(conn, {"type": "error", "message": "該位置已被佔用。"})
                    continue

                # 合法落子
                board[pos] = symbols[current_idx]
                print(f"Player {current_idx} ({symbols[current_idx]}) moves at {pos + 1}")
                print_board(board)
                break

            elif msg.get("type") == "quit":
                print(f"Player {current_idx} quits.")
                other = conns[1 - current_idx]
                try:
                    send_json(
                        other,
                        {
                            "type": "game_over",
                            "board": board,
                            "winner": None,
                            "reason": "對手離開遊戲",
                        },
                    )
                except Exception:
                    pass
                return

            else:
                send_json(conn, {"type": "error", "message": "未知指令。"})

        # 檢查勝負
        winner = check_winner(board)
        if winner or is_full(board):
            break

        # 換另一個玩家
        current_idx = 1 - current_idx

    # 遊戲結束，通知兩邊
    winner = check_winner(board)
    if winner:
        msg = {"type": "game_over", "board": board, "winner": winner, "reason": ""}
    else:
        msg = {"type": "game_over", "board": board, "winner": None, "reason": "平手"}

    for conn in conns:
        try:
            send_json(conn, msg)
        except Exception:
            pass

    for conn in conns:
        conn.close()
    srv.close()
    print("Game finished. Server exit.")


if __name__ == "__main__":
    main()
