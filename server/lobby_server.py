import socket
import threading
import json
from typing import Dict, Any
import os, sys
import subprocess 
import time
from datetime import datetime

from db_server import (
    load_accounts,
    save_accounts,
    load_games,
    load_rooms,
    save_rooms,
    load_ratings,
    save_ratings,
    load_history,
    save_history,
)
from developer_server import handle_developer_action
from pathlib import Path

UPLOAD_DIR = Path(__file__).parent / "uploaded_games"
sys.path.append(os.path.dirname(__file__))

HOST = "0.0.0.0"
PORT = 7070

accounts_lock = threading.Lock()  # 帳號資料鎖
accounts: Dict[str, Any] = load_accounts()  # 載入帳號資料

online_users_lock = threading.Lock()  # 在線使用者鎖
online_users = {
    "players": set(),
    "developers": set(),
}

rooms_lock = threading.Lock()  # 遊戲房間鎖

_rooms_raw = load_rooms()
rooms: Dict[int, Dict[str, Any]] = {}
next_room_id = 1

def record_play_history(players, game_name: str):
    """
    在 history.json 裡記錄：這些 players 玩過 game_name 一次。
    """
    #history.json -> 紀錄玩家玩遊戲次數
    if not players:
        return
    history = load_history()
    changed = False
    for p in players:
        games = history.setdefault(p, {})
        count = int(games.get(game_name, 0))
        games[game_name] = count + 1
        changed = True
    if changed:
        save_history(history)

def _save_rooms():
    save_rooms(rooms)

# 處理 JSON 傳輸
def send_json(conn: socket.socket, obj: Dict[str, Any]):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
    conn.sendall(data)


# 接收 JSON 訊息
def recv_json(conn: socket.socket):
    buf = b""
    while True:
        chunk = conn.recv(4096)  # 每次接收最多 4096 bytes
        if not chunk:
            return None
        buf += chunk
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                return json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                return None


# 回傳成功訊息
def resp_ok(message: str = "ok", **extra):
    data: Dict[str, Any] = {"status": "ok", "message": message}
    data.update(extra)
    return data


# 回傳錯誤訊息
def resp_err(message: str, **extra):
    data: Dict[str, Any] = {"status": "error", "message": message}
    data.update(extra)
    return data


### 註冊
def handle_register(payload: Dict[str, Any]):
    role = payload.get("role")
    username = payload.get("username")
    password = payload.get("password")

    if role not in ("player", "developer"):
        return resp_err("invalid role")

    if not username or not password:
        return resp_err("username/password required")

    group_key = "players" if role == "player" else "developers"

    # 檢查帳號是否已經存在
    with accounts_lock:
        group = accounts.setdefault(group_key, {})
        if username in group:
            return resp_err("username already exists")
        group[username] = {"password": password}
        save_accounts(accounts)

    return resp_ok("registered successfully")


### 登入
def handle_login(payload: Dict[str, Any]):
    role = payload.get("role")
    username = payload.get("username")
    password = payload.get("password")

    if role not in ("player", "developer"):
        return resp_err("invalid role")

    if not username or not password:
        return resp_err("username/password required")

    group_key = "players" if role == "player" else "developers"

    # 檢查帳號密碼
    with accounts_lock:
        group = accounts.setdefault(group_key, {})
        user = group.get(username)

        if not user:
            return resp_err("username does not exist")
        if user.get("password") != password:
            return resp_err("invalid username or password")

    # 檢查是否已經登入
    with online_users_lock:
        online_set = online_users[group_key]
        if username in online_set:
            return resp_err("user already logged in")
        online_set.add(username)

    return resp_ok("login success", role=role, username=username)


### 玩家功能及遊戲大廳

def create_room(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    game_name = payload.get("game_name")

    if not username or not game_name:
        return resp_err("missing username or game_name")

    games = load_games()
    if game_name not in games:
        return resp_err("game not found")

    game_info = games[game_name]

    # 讀取最少和最多玩家
    try:
        min_players = int(game_info.get("min_players", 1))
    except (TypeError, ValueError):
        min_players = 2
    try:
        max_players = int(game_info.get("max_players", 2))
    except (TypeError, ValueError):
        max_players = 2
    if min_players < 1:
        min_players = 1
    if max_players < min_players:
        max_players = min_players

    # 紀錄遊戲版本
    game_version = str(game_info.get("version", "0"))

    global next_room_id
    with rooms_lock:
        room_id = next_room_id
        next_room_id += 1
        rooms[room_id] = {
            "id": room_id,
            "host": username,
            "game_name": game_name,
            "players": [username],
            "status": "waiting",
            "min_players": min_players,
            "max_players": max_players,
            "version": game_version,
            "ready_players": [username],
        }

        _save_rooms()

    return resp_ok("room created", room_id=room_id, game_name=game_name)


def list_rooms(game_name=None) -> Dict[str, Any]:
    # 顯示該遊戲還未開始的房間
    with rooms_lock:
        result = []
        for r in rooms.values():
            if r.get("status") != "waiting":
                continue
            if game_name and r.get("game_name") != game_name:
                continue
            result.append(r)
    return resp_ok("room list", rooms=result)


def join_room(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    room_id = payload.get("room_id")

    if not username or room_id is None:
        return resp_err("missing username or room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        if username in room["players"]:
            return resp_err("already in room")

        if room["status"] != "waiting":
            return resp_err("room not joinable")

        max_players = room.get("max_players", 2)
        if len(room["players"]) >= max_players:
            return resp_err("room full")

        room["players"].append(username)
        _save_rooms()

    return resp_ok("join room success", room_id=room_id)

def launch_game_server(game_name: str, version: str, room_id: int, players: list[str]):
    #在server/uploaded_games/<game_name>_<version> 找 game_server
    #找到後subprocess開背景
    game_dir = UPLOAD_DIR / f"{game_name}_{version}"
    if not game_dir.exists():
        print(f"[GAME_SERVER] game dir not found: {game_dir}")
        return

    candidates = [
        game_dir / "game_server.bat",
        game_dir / "game_server.cmd",
        game_dir / "game_server.sh",
        game_dir / "game_server.exe",
        game_dir / "server.py",
        game_dir / "game_server.py",
    ]

    target = None
    for p in candidates:
        if p.exists():
            target = p
            break

    if target is None:
        print(f"[GAME_SERVER] no server executable found in {game_dir}")
        return

    try:
        env = os.environ.copy()
        # 你可以把 room_id / players 等資訊塞進環境變數，讓 game_server 去讀
        env["GAME_ROOM_ID"] = str(room_id)
        env["GAME_ROOM_PLAYERS"] = ",".join(players)
        env["GAME_NAME"] = game_name
        env["GAME_VERSION"] = version

        if os.name == "nt" and target.suffix.lower() in (".bat", ".cmd", ".exe"):
            subprocess.Popen([str(target)], cwd=str(game_dir), env=env)
        elif target.suffix.lower() == ".sh":
            subprocess.Popen(["bash", str(target)], cwd=str(game_dir), env=env)
        elif target.suffix.lower() == ".py":
            log_path = game_dir / "game_server_runtime.log"
            logf = open(log_path, "a", encoding="utf-8")

            subprocess.Popen(
                [sys.executable, str(target)],
                cwd=str(game_dir),
                env=env,
                stdout=logf,
                stderr=logf,
            )
            print(f"[GAME_SERVER] launched: {target} (room {room_id}), log={log_path}")

        else:
            subprocess.Popen([str(target)], cwd=str(game_dir), env=env)

        print(f"[GAME_SERVER] launched: {target} (room {room_id})")
    except Exception as e:
        print(f"[GAME_SERVER] failed to launch: {e}")


def start_room_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    room_id = payload.get("room_id")

    if not username or room_id is None:
        return resp_err("missing username or room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        if room["host"] != username:
            return resp_err("only host can start")

        if room["status"] != "waiting":
            return resp_err("room already started")

        players = list(room.get("players", []))
        min_players = room.get("min_players", 1)

        if len(players) < min_players:
            return resp_err("not enough players to start")
        
        ready = room.get("ready_players", [])
        not_ready = [p for p in players if p != username and p not in ready]
        if not_ready:
            return resp_err(f"players not ready: {', '.join(not_ready)}")

        game_name = room["game_name"]
        game_version = str(room.get("version", "0"))

        #開始遊戲後 -> 標記房間正在玩
        room["status"] = "playing"
        _save_rooms()

    #離開log再啟動遊戲
    try:
        launch_game_server(game_name, game_version, room_id, players)
    except Exception as e:
        print(f"[GAME_SERVER] exception while launching: {e}")

    record_play_history(players, game_name)

    #回應client端 -> 啟動各玩家的game_glient
    return resp_ok(
        "game started",
        room_id=room_id,
        game_name=game_name,
        version=game_version,
        players=players,
    )

def room_players(payload: Dict[str, Any]) -> Dict[str, Any]:
    room_id = payload.get("room_id")
    if room_id is None:
        return resp_err("missing room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")
        players = list(room.get("players", []))

    return resp_ok("room players", players=players)


def leave_room(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    room_id = payload.get("room_id")

    if not username or room_id is None:
        return resp_err("missing username or room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        if username not in room.get("players", []):
            return resp_err("not in room")

        room["players"].remove(username)
        ready = room.get("ready_players", [])
        if username in ready:
            ready.remove(username)

        # 房主離開：如果還有其他人，交給下一個；沒人就關房
        if room.get("host") == username:
            if room["players"]:
                room["host"] = room["players"][0]
            else:
                del rooms[room_id]
                _save_rooms()
                return resp_ok("left room and room closed", room_id=room_id)

        _save_rooms()

    return resp_ok("left room", room_id=room_id)

def wait_room_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    room_id = payload.get("room_id")

    if not username or room_id is None:
        return resp_err("missing username or room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    # 先把這個玩家標記成 ready
    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        if username not in room.get("players", []):
            return resp_err("not in room")

        ready = room.setdefault("ready_players", [])
        if username not in ready:
            ready.append(username)

        version = str(room.get("version", "0"))

    # 然後開始「長輪詢」：等到房間變成 playing 才回覆
    while True:
        with rooms_lock:
            room = rooms.get(room_id)
            if not room:
                return resp_err("room closed")
            status = room.get("status", "waiting")
            players = list(room.get("players", []))
            game_name = room.get("game_name", "")
            version = str(room.get("version", "0"))

        if status == "playing":
            return resp_ok(
                "game started",
                room_id=room_id,
                game_name=game_name,
                version=version,
                players=players,
            )

        time.sleep(0.3)  # 不要瘋狂佔 CPU


def room_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    room_id = payload.get("room_id")
    if room_id is None:
        return resp_err("missing room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        info = {
            "id": room["id"],
            "host": room["host"],
            "game_name": room["game_name"],
            "players": list(room.get("players", [])),
            "status": room.get("status", "waiting"),
            "min_players": room.get("min_players", 1),
            "max_players": room.get("max_players", 2),
            "version": room.get("version", "0"),
        }

    return resp_ok("room info", room=info)

def reset_room(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    room_id = payload.get("room_id")

    if not username or room_id is None:
        return resp_err("missing username or room_id")

    try:
        room_id = int(room_id)
    except ValueError:
        return resp_err("invalid room_id")

    with rooms_lock:
        room = rooms.get(room_id)
        if not room:
            return resp_err("room not found")

        if room.get("host") != username:
            return resp_err("only host can reset the room")

        room["status"] = "waiting"
        room["ready_players"] = [username]  # 房主維持 ready
        _save_rooms()

    return resp_ok("room reset", room_id=room_id)

def remove_user_from_all_rooms(username: str):
    """登出 / 斷線時，把使用者從所有房間移除。"""
    if not username:
        return

    with rooms_lock:
        to_delete = []
        for room_id, room in list(rooms.items()):
            players = room.get("players", [])
            if username in players:
                players.remove(username)
                # 房主離線：轉交房主 / 關房
                if room.get("host") == username:
                    if players:
                        room["host"] = players[0]
                    else:
                        to_delete.append(room_id)
        for rid in to_delete:
            rooms.pop(rid, None)
        _save_rooms()

def list_online_users() -> Dict[str, Any]:
    #線上玩家及開發者名單
    with online_users_lock:
        players = sorted(list(online_users.get("players", set())))
        developers = sorted(list(online_users.get("developers", set())))
    return resp_ok("online users", players=players, developers=developers)

def get_player_history(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    if not username:
        return resp_err("missing username")

    history = load_history()
    user_hist = history.get(username, {})
    # user_hist: {game_name: play_count}
    return resp_ok("history", history=user_hist)


def add_rating(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = payload.get("username")
    game_name = payload.get("game_name")
    score = payload.get("score")
    comment = payload.get("comment", "")

    if not username or not game_name:
        return resp_err("missing username or game_name")

    # 轉成 int 並檢查範圍 1~5
    try:
        score_int = int(score)
    except (TypeError, ValueError):
        return resp_err("score must be an integer 1-5")

    if not (1 <= score_int <= 5):
        return resp_err("score must be between 1 and 5")

    # 檢查是否玩過這款遊戲
    history = load_history()
    user_hist = history.get(username, {})
    if game_name not in user_hist or user_hist[game_name] <= 0:
        return resp_err("you must play this game before rating")

    # 簡單字數限制（例如 300 字元）
    if comment is None:
        comment = ""
    comment = str(comment)
    if len(comment) > 300:
        return resp_err("comment too long (max 300 characters)")

    ratings = load_ratings()
    game_ratings = ratings.setdefault(game_name, [])

    entry = {
        "player": username,
        "score": score_int,
        "comment": comment,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    game_ratings.append(entry)
    save_ratings(ratings)

    return resp_ok("rating added", game_name=game_name)


def get_game_ratings(payload: Dict[str, Any]) -> Dict[str, Any]:
    game_name = payload.get("game_name")
    if not game_name:
        return resp_err("missing game_name")

    ratings = load_ratings()
    game_ratings = ratings.get(game_name, [])

    if not game_ratings:
        return resp_ok(
            "no ratings yet",
            game_name=game_name,
            avg_score=None,
            count=0,
            ratings=[],
        )

    scores = [r.get("score", 0) for r in game_ratings]
    scores = [int(s) for s in scores if isinstance(s, (int, float, str))]
    if scores:
        avg_score = sum(scores) / len(scores)
    else:
        avg_score = None

    # 只回傳最近 5 則（避免一次太多）
    latest = game_ratings[-5:]

    return resp_ok(
        "game ratings",
        game_name=game_name,
        avg_score=avg_score,
        count=len(game_ratings),
        ratings=latest,
    )


def handle_player_action(action: str, payload: Dict[str, Any]):
    if action == "list_games":
        games = load_games()
        return resp_ok("game list", games=games)
    
    if action == "list_online_users":
        return list_online_users()

    if action == "game_info":
        game_name = payload.get("game_name")
        if not game_name:
            return resp_err("missing game_name")
        games = load_games()
        info = games.get(game_name)
        if not info:
            return resp_err("game not found")
        return resp_ok("game info", game_name=game_name, info=info)

    if action == "create_room":
        return create_room(payload)

    if action == "list_rooms":
        game_name = payload.get("game_name")
        return list_rooms(game_name)

    if action == "join_room":
        return join_room(payload)

    if action == "start_game":
        return start_room_game(payload)

    if action == "room_players":
        return room_players(payload)

    if action == "leave_room":
        return leave_room(payload)
    
    if action == "my_history":
        return get_player_history(payload)

    if action == "add_rating":
        return add_rating(payload)

    if action == "get_game_ratings":
        return get_game_ratings(payload)
    
    if action == "room_info":
        return room_info(payload)

    if action == "wait_start":
        return wait_room_start(payload)
    
    if action == "reset_room":
        return reset_room(payload)

    return resp_err(f"unknown player action: {action}")


def player_download_game(conn: socket.socket, payload: Dict[str, Any]):
    # 1. 取得遊戲名稱
    game_name = payload.get("game_name")
    if not game_name:
        send_json(conn, resp_err("missing game_name"))
        return

    # 2. 確認遊戲是否存在
    games = load_games()
    info = games.get(game_name)
    if not info:
        send_json(conn, resp_err("game not found"))
        return

    version = str(info.get("version", "0"))  # 取得遊戲版本號
    zip_path = UPLOAD_DIR / f"{game_name}_{version}.zip"  # zip 檔路徑

    if not zip_path.exists():
        send_json(conn, resp_err("game file not found on server"))
        return

    file_size = zip_path.stat().st_size

    # 3. 把檔案大小資訊傳送給 client
    header = resp_ok(
        "download_ready",
        game_name=game_name,
        version=version,
        archive_size=file_size,
    )
    send_json(conn, header)

    # 傳送檔案內容
    try:
        with zip_path.open("rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                conn.sendall(chunk)
        print(f"[DOWNLOAD] sent {zip_path} ({file_size} bytes)")
    except Exception as e:
        print(f"[DOWNLOAD] error sending file: {e}")


# ---------- CLIENT LOOP ----------
def client_loop(conn: socket.socket, addr):
    print(f"[+] New connection from {addr}")

    current_role = None
    current_user = None

    try:
        while True:
            msg = recv_json(conn)
            if msg is None:
                print(f"[-] Client {addr} disconnected")
                break

            if not isinstance(msg, dict):
                send_json(conn, resp_err("invalid message format"))
                continue

            role = msg.get("role")
            action = msg.get("action")
            payload = msg.get("payload", {}) or {}

            # --- system: register/login ---
            if role == "system":
                if action == "register":
                    resp = handle_register(payload)
                    send_json(conn, resp)
                    continue
                elif action == "login":
                    resp = handle_login(payload)
                    send_json(conn, resp)
                    if resp.get("status") == "ok":
                        current_role = resp.get("role")
                        current_user = resp.get("username")
                        print(f"[LOGIN] {current_role} {current_user}")
                    continue
                elif action == "logout":
                    if current_role and current_user:
                        # 先從所有房間移除
                        remove_user_from_all_rooms(current_user)
                        # 再從在線列表拿掉
                        with online_users_lock:
                            key = "players" if current_role == "player" else "developers"
                            online_users[key].discard(current_user)
                        print(f"[LOGOUT] {current_role} {current_user}")
                        current_role = None
                        current_user = None

                    send_json(conn, resp_ok("logout success"))
                    continue
                else:
                    send_json(conn, resp_err("unknown system action"))
                    continue

            # 之後的動作都需要已登入
            if current_role is None or current_user is None:
                send_json(conn, resp_err("please login first"))
                continue

            # --- player actions ---
            if role == "player" and current_role == "player":

                if action == "download_game":
                    player_download_game(conn, payload)
                    continue

                resp = handle_player_action(action, payload)
                send_json(conn, resp)
                continue

            # --- developer actions ---
            if role == "developer" and current_role == "developer":
                resp = handle_developer_action(action, payload, conn)
                send_json(conn, resp)
                continue

            # 其他情況
            send_json(conn, resp_err("role mismatch or unknown role"))

    except Exception as e:
        print(f"[!] Error with client {addr}: {e}")
    finally:
        if current_role and current_user:
            # 斷線時也要把人從房間跟在線列表拿掉
            remove_user_from_all_rooms(current_user)
            with online_users_lock:
                key = "players" if current_role == "player" else "developers"
                online_users[key].discard(current_user)
        conn.close()
        print(f"[+] Connection with {addr} closed")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen()

        srv.settimeout(1.0)
        print(f"[SERVER] Listening on {HOST}:{PORT}")

        threads = []

        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(target=client_loop, args=(conn, addr), daemon=True)
                t.start()
                threads.append(t)

            except socket.timeout:
                pass

            except KeyboardInterrupt:
                print("\n[SERVER] Shutting down...")
                break

            except Exception as e:
                print(f"[SERVER] Error in main loop: {e}")
                break

        print("server shutting down, waiting for threads to finish...")


if __name__ == "__main__":
    main()
