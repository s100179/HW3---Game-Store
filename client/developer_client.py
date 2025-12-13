import json
import os, sys
from pathlib import Path
import shutil
import tempfile

from network import send_json, recv_json

SERVER_HOST = "140.113.17.11"  
SERVER_PORT = 5000

sys.path.append(os.path.dirname(__file__))

###開發者
def upload_game(sock, developer: str):
    print("上傳新遊戲")
    folder = input("遊戲資料夾: ").strip()
    game_name = input("遊戲名稱: ").strip()
    version = input("版本: ").strip()
    description = input("描述: ").strip()
    game_type = input("遊戲類型 (CLI/GUI): ").strip().upper()
    min_players = input("最少玩家數 (預設 2): ").strip()
    max_players = input("最多玩家數: ").strip()

    raw_path = Path(folder)
    if raw_path.is_absolute():
        folder_path = raw_path
    else:
        project_root = Path(__file__).resolve().parent.parent
        folder_path = (project_root / raw_path).resolve()

    if not folder_path.exists() or not folder_path.is_dir():
        print("folder not found")
        return

    # 轉成整數，min 預設 2，並檢查 max >= min
    try:
        if min_players == "":
            min_players_int = 2
        else:
            min_players_int = int(min_players)
            if min_players_int < 1:
                raise ValueError

        if max_players == "":
            max_players_int = min_players_int
        else:
            max_players_int = int(max_players)
            if max_players_int < min_players_int:
                raise ValueError
    except ValueError:
        print("invalid min/max players")
        return

    # step 1: zip the folder
    try:
        tmp_dir = Path(tempfile.mkdtemp())
        archive_base = tmp_dir / f"{game_name}_{version}"
        archive_path = shutil.make_archive(
            str(archive_base), "zip", root_dir=str(folder_path)
        )
        archive_path = Path(archive_path)
        archive_size = archive_path.stat().st_size
    except Exception as e:
        print(f"failed to create zip:", e)
        return

    # step 2: send upload_game request
    send_json(
        sock,
        {
            "role": "developer",
            "action": "upload_game",
            "payload": {
                "developer": developer,
                "game_name": game_name,
                "version": version,
                "description": description,
                "type": game_type,
                "archive_size": archive_size,
                "min_players": min_players_int,
                "max_players": max_players_int,
            },
        },
    )

    # step 3: send the zip file
    try:
        with archive_path.open("rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                sock.sendall(chunk)
    except Exception as e:
        print(f"failed to send file:", e)
        return
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    # step 4: receive response
    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return
    else:
        print(">>", resp.get("message"))


def update_game(sock, developer: str):
    print("更新現有遊戲")
    folder = input("遊戲資料夾 (新版本): ").strip()
    game_name = input("要更新的遊戲名稱: ").strip()
    version = input("新版本: ").strip()
    description = input("新描述 (留空則保留原描述): ").strip()
    game_type = input(
        "遊戲類型 (CLI/GUI, 留空則保留原設定): "
    ).strip().upper()
    min_players = input("新最少玩家數 (留空則保留原設定): ").strip()
    max_players = input("新最多玩家數 (留空則保留原設定): ").strip()

    raw_path = Path(folder)
    if raw_path.is_absolute():
        folder_path = raw_path
    else:
        project_root = Path(__file__).resolve().parent.parent
        folder_path = (project_root / raw_path).resolve()

    if not folder_path.exists() or not folder_path.is_dir():
        print("資料夾不存在")
        return

    # zip the folder
    try:
        tmp_dir = Path(tempfile.mkdtemp())
        archive_base = tmp_dir / f"{game_name}_{version}"
        archive_path = shutil.make_archive(
            str(archive_base), "zip", root_dir=str(folder_path)
        )
        archive_path = Path(archive_path)
        archive_size = archive_path.stat().st_size
    except Exception as e:
        print("failed to create zip:", e)
        return

    min_players_int = None
    max_players_int = None
    try:
        if min_players != "":
            min_players_int = int(min_players)
            if min_players_int < 1:
                raise ValueError
        if max_players != "":
            max_players_int = int(max_players)
            if max_players_int < 1:
                raise ValueError
        if (min_players_int is not None) and (max_players_int is not None):
            if max_players_int < min_players_int:
                raise ValueError
    except ValueError:
        print("invalid min/max players")
        return

    # send update_game request
    payload = {
        "developer": developer,
        "game_name": game_name,
        "version": version,
        "archive_size": archive_size,
    }
    if description:
        payload["description"] = description
    if game_type:
        payload["type"] = game_type
    if min_players_int is not None:
        payload["min_players"] = min_players_int
    if max_players_int is not None:
        payload["max_players"] = max_players_int

    send_json(
        sock,
        {
            "role": "developer",
            "action": "update_game",
            "payload": payload,
        },
    )

    # send file
    try:
        with archive_path.open("rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                sock.sendall(chunk)
    except Exception as e:
        print("failed to send file:", e)
        return
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return
    else:
        print(">>", resp.get("message"))


def delete_game(sock, developer: str):
    print("delete game")
    game_name = input("game name to delete: ").strip()

    send_json(
        sock,
        {
            "role": "developer",
            "action": "delete_game",
            "payload": {
                "developer": developer,
                "game_name": game_name,
            },
        },
    )

    resp = recv_json(sock)
    if resp is None:
        print("no response from server")
        return
    print(">>", resp.get("message"))


def list_my_games(sock, developer: str):
    send_json(
        sock,
        {
            "role": "developer",
            "action": "list_my_games",
            "payload": {
                "developer": developer,
            },
        },
    )

    resp = recv_json(sock)

    if resp is None:
        print("no response from server")
        return

    if resp.get("status") != "ok":
        print(">>", resp.get("message"))
        return

    games = resp.get("games", {})
    if not games:
        print("=== 目前沒有上架任何遊戲 ===")
        return

    print("=== 我的遊戲列表 ===")
    for name, info in games.items():
        print(
            f"- {name} (v{info.get('version', '?')}), "
            f"type={info.get('game_type', '?')}, desc={info.get('description', '')}"
        )


def developer_menu(sock, username: str):
    while True:
        print(f"\n=== Developer Menu ({username}) ===")
        print("1. 上傳新遊戲")
        print("2. 更新現有遊戲")
        print("3. 刪除遊戲")
        print("4. 列出我的遊戲")
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
            upload_game(sock, username)
        elif choice == "2":
            update_game(sock, username)
        elif choice == "3":
            delete_game(sock, username)
        elif choice == "4":
            list_my_games(sock, username)
        else:
            print("輸入錯誤，請重新選擇")

def run_developer_menu(sock, username: str):
    developer_menu(sock, username)


if __name__ == "__main__":
    print("請從 lobby.py 進入開發者介面")
