#HELLO


import os
import socket
import json


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
    def cell(i):
        return board[i] if board[i] != " " else str(i + 1)

    print()
    print(f" {cell(0)} | {cell(1)} | {cell(2)} ")
    print("---+---+---")
    print(f" {cell(3)} | {cell(4)} | {cell(5)} ")
    print("---+---+---")
    print(f" {cell(6)} | {cell(7)} | {cell(8)} ")
    print()


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

    BASE_PORT = 7000
    port = BASE_PORT + (room_id % 1000)

    return host, port



def main():
    player_name = os.getenv("GAME_PLAYER_NAME", "Player")
    game_name = os.getenv("GAME_NAME", "OOXX")
    version = os.getenv("GAME_VERSION", "1")

    server_host, server_port = _pick_server_endpoint()

    print(f"=== {game_name} (v{version}) - Tic Tac Toe ===")
    print(f"Hello, {player_name}!")
    print(f"連線到遊戲伺服器 {server_host}:{server_port} ...")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((server_host, server_port))
    except Exception as e:
        print("無法連線到遊戲伺服器：", e)
        print("提示：請確認 game_server.py 有在該主機上啟動，且 port 一致。")
        try:
            input("按 Enter 結束")
        except EOFError:
            pass
        return

    symbol = "?"
    print("等待伺服器訊息...")

    while True:
        msg = recv_json(s)
        if msg is None:
            print("伺服器中斷連線。")
            break

        mtype = msg.get("type")

        if mtype == "welcome":
            symbol = msg.get("symbol", "?")
            print(msg.get("message", f"你是 {symbol}"))
            continue

        if mtype == "state":
            board = msg.get("board", [" "] * 9)
            your_turn = msg.get("your_turn", False)
            print_board(board)
            print(msg.get("message", ""))

            if your_turn:
                # 輪到自己：輸入落子位置
                while True:
                    s_input = input(f"輪到你 ({symbol}) 落子，輸入 1-9 (或 q 離開): ").strip()
                    if s_input.lower() == "q":
                        send_json(s, {"type": "quit"})
                        print("你已離開遊戲。")
                        s.close()
                        return

                    if not s_input.isdigit():
                        print("請輸入 1~9 或 q。")
                        continue

                    pos = int(s_input) - 1
                    if not (0 <= pos < 9):
                        print("超出範圍，請輸入 1~9。")
                        continue

                    send_json(s, {"type": "move", "pos": pos})
                    break

            continue

        if mtype == "error":
            print("錯誤：", msg.get("message"))
            continue

        if mtype == "game_over":
            board = msg.get("board", [" "] * 9)
            print_board(board)
            winner = msg.get("winner")
            reason = msg.get("reason", "")

            if reason:
                print(reason)

            if winner is None and not reason:
                print("平手！")
            elif winner == symbol:
                print("你贏了！🎉")
            elif winner in ("X", "O"):
                print(f"玩家 {winner} 獲勝，你輸了 QQ")
            else:
                print("遊戲結束。")

            break

    s.close()
    try:
        input("按 Enter 結束。")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
