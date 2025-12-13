import json
import os, sys
from pathlib import Path
import shutil
import subprocess

from network import send_json, recv_json, recv_exact

sys.path.append(os.path.dirname(__file__))

SERVER_HOST = "140.113.17.11"  
SERVER_PORT = 5000

###玩家

def create_room(sock, username: str, game_name: str):
    print("=== 創建房間 ===")
    send_json(
        sock,
        {
            "role": "player",
            "action": "create_room",
            "payload": {
                "username": username,
                "game_name": game_name,
            },
        },
    )
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return None

    print(">>", resp.get("message"))
    if resp.get("status") == "ok":
        room_id = int(resp.get("room_id"))
        # 創房成功 -> 直接進入房間
        room_menu(sock, username, game_name, room_id, is_host=True)
        return room_id
    return None


def list_rooms_client(sock, game_name: str | None = None):
    payload = {}
    if game_name is not None:
        payload["game_name"] = game_name

    send_json(
        sock,
        {
            "role": "player",
            "action": "list_rooms",
            "payload": payload,
        },
    )
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return

    if resp.get("status") != "ok":
        print(">>", resp.get("message"))
        return

    rooms = resp.get("rooms", [])
    print("=== 房間列表 ===")
    if not rooms:
        print("(目前沒有任何房間)")
        return

    for r in rooms:
        room_id = r.get("id")
        gname = r.get("game_name")
        host = r.get("host")
        players = r.get("players", [])
        status = r.get("status")
        min_p = r.get("min_players", "?")
        max_p = r.get("max_players", "?")
        print(
            f"- Room {room_id}: {gname} | host={host} | "
            f"players={len(players)}/{max_p} (min {min_p}) | status={status}"
        )


def join_room_client(sock, username: str, game_name: str):
    room_id = input("想加入的房間 ID: ").strip()

    send_json(
        sock,
        {
            "role": "player",
            "action": "join_room",
            "payload": {
                "username": username,
                "room_id": room_id,
            },
        },
    )
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return None

    print(">>", resp.get("message"))
    if resp.get("status") == "ok":
        room_id_int = int(resp.get("room_id"))
        # 加入成功 → 進入房間選單
        room_menu(sock, username, game_name, room_id_int, is_host=False)
        return room_id_int
    return None


def room_menu(sock, username: str, game_name: str, room_id: int, is_host: bool):
    """進入房間之後的選單：只處理房內操作"""
    while True:
        print(f"\n=== Room {room_id} ({game_name}) - Player: {username} ===")
        print("1. 查看房間玩家")
        if is_host:
            print("2. 開始遊戲（限房主）")
            print("3. 重置房間（限房主）")
        else:
            print("2. 準備開始遊戲（等待房主啟動）")
        print("0. 離開房間")
        choice = input("請選擇: ").strip()

        # 1. 查看房間玩家
        if choice == "":
            continue
        if choice == "1":
            send_json(
                sock,
                {
                    "role": "player",
                    "action": "room_players",
                    "payload": {
                        "room_id": room_id,
                    },
                },
            )
            resp = recv_json(sock)
            if resp is None:
                print("no response from server")
            elif resp.get("status") != "ok":
                print(">>", resp.get("message"))
            else:
                print("=== 玩家列表 ===")
                players = resp.get("players", [])
                if not players:
                    print("(房間目前沒有人)")
                else:
                    for p in players:
                        print(f"- {p}")

        # 2. 開始遊戲
        elif choice == "2":
            if is_host:
                #房主：等待game server開啟、自己立刻開洗game client
                start_game_client(sock, username, game_name, room_id)
            else:
                #非房主：進入等待狀態 -> 房主開啟遊戲後打開client
                print("你已準備完成，正在等待房主開始遊戲...")
                send_json(sock, {
                    "role": "player",
                    "action": "wait_start",
                    "payload": {
                        "username": username,
                        "room_id": room_id,
                    }
                })
                resp = recv_json(sock)
                if resp is None:
                    print("no response from server")
                elif resp.get("status") != "ok":
                    print(">>", resp.get("message"))
                else:
                    players = resp.get("players", [])
                    version = str(resp.get("version", "0"))
                    print(">> 遊戲已開始！房間玩家：", players)
                    print(f"遊戲版本：v{version}，啟動你的遊戲 client ...")
                    launch_game_client(username, game_name, version)

        if is_host and choice == "3":
            send_json(sock, {
                "role": "player",
                "action": "reset_room",
                "payload": {"room_id": room_id, "username": username},
            })
            resp = recv_json(sock)
            if resp is None:
                print("no response from server")
            else:
                print(">>", resp.get("message"))

        # 0. 離開房間
        elif choice == "0":
            send_json(
                sock,
                {
                    "role": "player",
                    "action": "leave_room",
                    "payload": {
                        "username": username,
                        "room_id": room_id,
                    },
                },
            )
            resp = recv_json(sock)
            if resp is not None:
                print(">>", resp.get("message"))
            else:
                print("no response from server")
            break

        else:
            print("輸入錯誤，請重新選擇。")


def launch_game_client(username: str, game_name: str, version: str | None = None):
    project_root = Path(__file__).resolve().parent.parent
    game_dir = project_root / "downloads" / username / game_name

    if not game_dir.exists():
        print(f"找不到遊戲資料夾: {game_dir}")
        return

    candidates = [
        game_dir / "run_client.bat",
        game_dir / "run_client.cmd",
        game_dir / "run_client.sh",
        game_dir / "game_client.exe",
        game_dir / "client.exe",
        game_dir / "client.py",
        game_dir / "game_client.py",
    ]
    target = None
    for p in candidates:
        if p.exists():
            target = p
            break

    if target is None:
        print("找不到可執行的 client（預期 run_client.* / game_client.* / client.py 等），請手動開啟遊戲。")
        return

    try:
        env = os.environ.copy()
        # 可以把玩家名字 / 遊戲資訊傳給 client 端
        env["GAME_PLAYER_NAME"] = username
        env["GAME_NAME"] = game_name
        env["GAME_SERVER_HOST"] = SERVER_HOST
        env["GAME_SERVER_PORT"] = "12001"
        if version is not None:
            env["GAME_VERSION"] = str(version)

        # 如果之後有 setting 過 GAME_SERVER_HOST / PORT，也一併帶給 client
        if "GAME_SERVER_HOST" not in env:
            # 如果你在檔案最上面有 SERVER_HOST 常數，也可以這樣：
            # from lobby import SERVER_HOST
            # env["GAME_SERVER_HOST"] = SERVER_HOST
            pass

        if os.name == "nt" and target.suffix.lower() in (".exe", ".bat", ".cmd"):
            # Windows 上 exe/bat/cmd 直接開（會跳新視窗），這個沒辦法阻塞等它結束
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif target.suffix.lower() == ".sh":
            # 阻塞：等 shell script 跑完再回來
            subprocess.run(["bash", str(target)], cwd=str(game_dir), env=env)
        elif target.suffix.lower() == ".py":
            # 阻塞：等 Python 遊戲結束，再回到房間選單
            subprocess.run([sys.executable, str(target)], cwd=str(game_dir), env=env)
        else:
            # 其他類型，直接 run（阻塞）
            subprocess.run([str(target)], cwd=str(game_dir), env=env)

        print(f"遊戲 client 結束，回到大廳（檔案：{target}）")
    except Exception as e:
        print(f"啟動遊戲 client 失敗：{e}")


def start_game_client(sock, username: str, game_name: str, current_room_id: int):
    if current_room_id is None:
        print("你目前沒有在任何房間中，請先創建或加入房間。")
        return

    send_json(
        sock,
        {
            "role": "player",
            "action": "start_game",
            "payload": {
                "username": username,
                "room_id": current_room_id,
            },
        },
    )
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return

    print(">>", resp.get("message"))
    if resp.get("status") == "ok":
        players = resp.get("players", [])
        version = str(resp.get("version", "0"))
        print("房間玩家：", players)
        print(f"伺服器已啟動 game_server（遊戲版本 v{version}），準備啟動本地 client ...")

        # 在本機啟動下載好的「遊戲 client」
        launch_game_client(username, game_name, version)



def _download_game_core(sock, username: str, game_name: str) -> bool:
    # 要求 server 準備這個遊戲
    send_json(
        sock,
        {
            "role": "player",
            "action": "download_game",
            "payload": {
                "game_name": game_name,
            },
        },
    )

    # 收 JSON header
    header = recv_json(sock)
    if header is None:
        print("no response from server")
        return False

    if header.get("status") != "ok":
        print(">>", header.get("message"))
        return False

    archive_size = header.get("archive_size")
    version = str(header.get("version", "0"))

    try:
        archive_size = int(archive_size)
    except Exception:
        print("invalid archive_size from server")
        return False

    # 準備 downloads/<username>/ 資料夾
    project_root = Path(__file__).resolve().parent.parent
    downloads_root = project_root / "downloads" / username
    downloads_root.mkdir(parents=True, exist_ok=True)

    zip_path = downloads_root / f"{game_name}_{version}.zip"
    extract_dir = downloads_root / game_name

    # 收 zip 檔
    remaining = archive_size
    try:
        with zip_path.open("wb") as f:
            while remaining > 0:
                to_read = min(4096, remaining) 
                chunk = recv_exact(sock, to_read) 
                if not chunk:
                    print("connection closed while downloading")
                    return False
                f.write(chunk)
                remaining -= len(chunk)
    except Exception as e:
        print("failed to receive file:", e)
        return False

    # 解壓縮
    try:
        import zipfile

        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)
    except Exception as e:
        print("failed to extract zip:", e)
        return False

    #metadata.json -> 記錄目前版本
    try:
        meta_path = extract_dir / "metadata.json"
        meta = {"version": version}
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("failed to write metadata:", e)

    print(f">> download complete: {extract_dir} (v{version})")
    return True


def download_game(sock, username: str):
    print("=== 下載遊戲 ===")
    game_name = input("game name to download: ").strip()
    _download_game_core(sock, username, game_name)


def ensure_game_ready(sock, username: str, game_name: str, server_info: dict) -> bool:
    """
    回傳 True 代表可以進入這款遊戲的 Lobby（已安裝且版本 ok）
    False 則代表玩家取消 / 下載失敗 / 拒絕更新。
    """
    project_root = Path(__file__).resolve().parent.parent
    downloads_root = project_root / "downloads" / username
    game_dir = downloads_root / game_name
    meta_path = game_dir / "metadata.json"

    server_version = str(server_info.get("version", "0"))

    # 3. 未下載：資料夾不存在
    if not game_dir.exists():
        print(f"你尚未下載 {game_name}（最新版本 v{server_version}）。")
        ans = input("要先下載嗎？(y/n): ").strip().lower()
        if ans == "y":
            ok = _download_game_core(sock, username, game_name)
            return ok
        else:
            print("已取消進入遊戲大廳。")
            return False

    # 有資料夾 → 試著讀 metadata 看本機版本
    local_version = None
    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
            local_version = str(meta.get("version"))
        except Exception:
            local_version = None

    # 1. 已下載且是最新版
    if local_version == server_version:
        print(f"{game_name} 已是最新版本 v{server_version}，直接進入遊戲大廳。")
        return True

    # 2. 已下載但為舊版 / 不明版本 → 一定要更新，不能帶舊版進線上大廳
    print(f"{game_name} 本機版本：{local_version or '未知'}，伺服器最新版本：v{server_version}")
    ans = input("要更新到最新版本嗎？(y/n): ").strip().lower()
    if ans == "y":
        ok = _download_game_core(sock, username, game_name)
        return ok
    else:
        print("已取消更新，將無法進入線上遊戲大廳。")
        return False

def show_game_ratings(sock, game_name: str):
    send_json(sock, {
        "role": "player",
        "action": "get_game_ratings",
        "payload": {
            "game_name": game_name,
        }
    })
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return

    if resp.get("status") != "ok":
        print(">>", resp.get("message"))
        return

    avg = resp.get("avg_score")
    count = resp.get("count", 0)
    ratings = resp.get("ratings", [])

    print(f"\n=== {game_name} 評價 ===")
    if count == 0 or avg is None:
        print("目前還沒有任何評價。")
        return

    print(f"平均評分：{avg:.2f} / 5（共 {count} 筆）")
    print("最近幾則評論：")
    for r in ratings:
        player = r.get("player", "?")
        score = r.get("score", "?")
        comment = r.get("comment", "")
        ts = r.get("timestamp", "")
        print(f"- [{score}/5] {player} @ {ts}")
        if comment:
            print(f"  {comment}")

def view_and_rate_from_history(sock, username: str):
    # 先向 server 要遊玩紀錄
    send_json(sock, {
        "role": "player",
        "action": "my_history",
        "payload": {
            "username": username,
        }
    })
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return

    if resp.get("status") != "ok":
        print(">>", resp.get("message"))
        return

    history = resp.get("history", {})
    if not history:
        print("你目前還沒有任何遊玩紀錄。")
        return

    print("\n=== 我的遊玩紀錄 ===")
    game_names = list(history.keys())
    for idx, name in enumerate(game_names, start=1):
        count = history[name]
        print(f"{idx}. {name}（玩過 {count} 次）")

    sel = input("想查看 / 評價哪一款？輸入編號（直接 Enter 取消）: ").strip()
    if sel == "":
        return

    try:
        idx = int(sel) - 1
        if idx < 0 or idx >= len(game_names):
            print("編號超出範圍")
            return
    except ValueError:
        print("請輸入數字")
        return

    game_name = game_names[idx]

    # 先顯示這款遊戲目前的評價
    show_game_ratings(sock, game_name)

    ans = input("要為這款遊戲留下你的評分與評論嗎？(y/n): ").strip().lower()
    if ans != "y":
        return

    # 讓玩家輸入 1~5 分
    while True:
        s = input("請輸入評分（1-5）: ").strip()
        try:
            score = int(s)
            if 1 <= score <= 5:
                break
            else:
                print("評分範圍必須介於 1 到 5。")
        except ValueError:
            print("請輸入數字 1~5。")

    comment = input("請輸入評論（可留空，最多 300 字）：").strip()

    send_json(sock, {
        "role": "player",
        "action": "add_rating",
        "payload": {
            "username": username,
            "game_name": game_name,
            "score": score,
            "comment": comment,
        }
    })

    resp = recv_json(sock)
    if resp is None:
        print("no response from server（評價可能沒有送成功）")
        return

    print(">>", resp.get("message"))

def show_online_users(sock):
    send_json(
        sock,
        {
            "role": "player",
            "action": "list_online_users",
            "payload": {},
        },
    )
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return

    if resp.get("status") != "ok":
        print(">>", resp.get("message"))
        return

    players = resp.get("players", [])
    developers = resp.get("developers", [])

    print("\n=== 線上使用者列表 ===")
    print("- 線上玩家 (players):")
    if players:
        for p in players:
            print(f"  * {p}")
    else:
        print("  (目前沒有線上玩家)")

    print("- 線上開發者 (developers):")
    if developers:
        for d in developers:
            print(f"  * {d}")
    else:
        print("  (目前沒有線上開發者)")


def player_menu(sock, username: str):
    while True:
        print(f"\n=== Player Menu ({username}) ===")
        print("1. 瀏覽商城遊戲")
        print("2. 查看線上玩家列表")
        print("3. 進入遊戲大廳")
        print("4. 查看遊玩紀錄 / 評價遊戲")
        print("0. 登出")
        choice = input("請選擇: ").strip()

        if choice == "0":
            send_json(
                sock,
                {
                    "role": "system",
                    "action": "logout",
                    "payload": {},
                },
            )
            resp = recv_json(sock)
            if resp is not None:
                print(">>", resp.get("message"))
            else:
                print("no response from server on logout")
            break

        elif choice == "1":
            # 瀏覽商城遊戲，選一款之後可以選擇下載 / 看評價
            send_json(
                sock,
                {
                    "role": "player",
                    "action": "list_games",
                    "payload": {},
                },
            )
            resp = recv_json(sock)
            print("=== 遊戲列表 ===")
            if resp is None:
                print("no response from server")
                continue

            games = (resp or {}).get("games", {})
            if not games:
                print("(目前沒有上架遊戲)")
                continue

            game_names = list(games.keys())
            for idx, name in enumerate(game_names, start=1):
                info = games.get(name, {}) or {}
                version = info.get("version", "?")
                developer = info.get("developer", "?")
                gtype = info.get("game_type", "?")
                min_p = info.get("min_players", "?")
                max_p = info.get("max_players", "?")
                desc = info.get("description") or "(無簡介)"

                print(f"{idx}. {name} (v{version})")
                print(f"   開發者: {developer}  類型: {gtype}  人數: {min_p}-{max_p}")
                print(f"   簡介: {desc}")
                print()

            sel = input("輸入編號可查看詳細資訊（直接 Enter 返回）: ").strip()
            if not sel:
                continue

            try:
                i = int(sel) - 1
                if i < 0 or i >= len(game_names):
                    print("編號超出範圍")
                    continue
            except ValueError:
                print("請輸入數字")
                continue

            selected_game = game_names[i]
            print(f">> 你選擇了遊戲: {selected_game}")

            # 顯示評價
            show_game_ratings(sock, selected_game)

            # 問要不要下載 / 更新到最新版本
            ans = input("要下載 / 更新這款遊戲嗎？(y/n): ").strip().lower()
            if ans == "y":
                ok = _download_game_core(sock, username, selected_game)
                if not ok:
                    print("下載失敗或中途出錯。")
                # 如果成功，你之後可以從「進入遊戲大廳」那邊進去玩

        elif choice == "2":
            # 顯示線上玩家列表
            show_online_users(sock)

        elif choice == "3":
            # 先拿遊戲列表，讓玩家選一款，再進入該遊戲的 Lobby
            send_json(
                sock,
                {
                    "role": "player",
                    "action": "list_games",
                    "payload": {},
                },
            )
            resp = recv_json(sock)
            if resp is None or resp.get("status") != "ok":
                print("無法取得遊戲列表")
                continue

            games = resp.get("games", {})
            if not games:
                print("目前沒有任何上架遊戲，請稍後再試。")
                continue

            game_names = list(games.keys())
            print("=== 選擇要玩的遊戲 ===")
            for idx, name in enumerate(game_names, start=1):
                info = games[name]
                print(
                    f"{idx}. {name} (v{info.get('version', '?')}), "
                    f"by {info.get('developer', '?')}"
                )

            sel = input("請輸入遊戲編號: ").strip()
            try:
                sel_idx = int(sel) - 1
                if sel_idx < 0 or sel_idx >= len(game_names):
                    print("編號超出範圍")
                    continue
            except ValueError:
                print("請輸入數字")
                continue

            selected_game = game_names[sel_idx]
            server_info = games[selected_game]
            print(f">> 你選擇了遊戲: {selected_game}")

            # 強制確認本地有最新版本（會在沒下載時順便問你要不要下載）
            if not ensure_game_ready(sock, username, selected_game, server_info):
                continue

            # 一切準備完畢，進入該遊戲的 Lobby
            game_lobby_menu(sock, username, selected_game)

        elif choice == "4":
            view_and_rate_from_history(sock, username)

        else:
            print("輸入錯誤，請重新選擇。")



def game_lobby_menu(sock, username: str, game_name: str):
    while True:
        print(f"\n=== Game Lobby ({game_name}) - Player: {username} ===")
        print("1. 創建房間")
        print("2. 查看房間列表")
        print("3. 加入房間")
        print("0. 返回上一層")
        choice = input("請選擇: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            create_room(sock, username, game_name)
        elif choice == "2":
            list_rooms_client(sock, game_name)
        elif choice == "3":
            join_room_client(sock, username, game_name)
        else:
            print("輸入錯誤，請重新選擇。")

def run_player_menu(sock, username: str):
    player_menu(sock, username)

if __name__ == "__main__":
    print("請從 lobby.py 啟動玩家介面")