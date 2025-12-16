from typing import Dict, Any
import zipfile
from pathlib import Path

from db_server import load_games, save_games

UPLOAD_DIR = Path(__file__).parent / "uploaded_games"
UPLOAD_DIR.mkdir(exist_ok=True)


def _recv_exact(conn, size: int):
    """
    從 socket 收滿 size bytes，yield 一塊一塊的 bytes。
    如果連線中途斷掉就丟例外。
    """
    remaining = size
    while remaining > 0:
        chunk = conn.recv(min(4096, remaining))
        if not chunk:
            raise ConnectionError("connection closed while receiving file")
        remaining -= len(chunk)
        yield chunk


def upload_game(payload: Dict[str, Any], conn) -> Dict[str, Any]:
    developer = payload.get("developer")
    game_name = payload.get("game_name")
    version = payload.get("version")
    description = payload.get("description")
    game_type = payload.get("type")  # "CLI" or "GUI"
    archive_size = payload.get("archive_size")
    min_players = payload.get("min_players")
    max_players = payload.get("max_players")

    # 基本欄位要有
    if not all([developer, game_name, version, archive_size]):
        return {"status": "error", "message": "missing fields in upload_game"}

    try:
        archive_size = int(archive_size)
    except ValueError:
        return {"status": "error", "message": "invalid archive_size"}

    # min/max players 檢查：min 預設 2、人數 >= 1
    try:
        if min_players is None or min_players == "":
            min_players_int = 2  # 預設兩個人
        else:
            min_players_int = int(min_players)
            if min_players_int < 1:
                raise ValueError

        if max_players is None or max_players == "":
            max_players_int = min_players_int
        else:
            max_players_int = int(max_players)
            if max_players_int < min_players_int:
                raise ValueError
    except ValueError:
        return {"status": "error", "message": "invalid min_players or max_players"}

    zip_name = f"{game_name}_{version}.zip"
    zip_path = UPLOAD_DIR / zip_name
    extract_dir = UPLOAD_DIR / f"{game_name}_{version}"

    # step 1: receive the zip file
    try:
        with open(zip_path, "wb") as f:
            for chunk in _recv_exact(conn, archive_size):
                f.write(chunk)
    except Exception as e:
        return {"status": "error", "message": f"failed to receive file: {e}"}

    # step 2: extract the zip file
    try:
        if not extract_dir.exists():
            extract_dir.mkdir()

        # 清空舊內容
        for item in extract_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                import shutil
                shutil.rmtree(item)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        return {"status": "error", "message": f"failed to extract zip: {e}"}

    # step 3: update games database
    games = load_games()
    info = {
        "developer": developer,
        "version": str(version),
        "description": description or "",
        "game_type": game_type,
        "min_players": min_players_int,
        "max_players": max_players_int,
    }
    games[game_name] = info
    save_games(games)

    return {
        "status": "ok",
        "message": "upload_game success",
        "game_name": game_name,
        "version": str(version),
    }



def update_game(payload: Dict[str, Any], conn) -> Dict[str, Any]:
    """只有原本的 developer 可以更新同一個 game_name。"""
    developer = payload.get("developer")
    game_name = payload.get("game_name")
    new_version = payload.get("version")
    description = payload.get("description")
    game_type = payload.get("type")
    archive_size = payload.get("archive_size")
    min_players = payload.get("min_players")
    max_players = payload.get("max_players")

    if not all([developer, game_name, new_version, archive_size]):
        return {"status": "error", "message": "missing fields in update_game"}

    try:
        archive_size = int(archive_size)
    except ValueError:
        return {"status": "error", "message": "invalid archive_size"}

    # 先載入遊戲資料，之後要用到舊的 min/max
    games = load_games()
    info = games.get(game_name)
    if not info:
        return {"status": "error", "message": "game not found"}

    # 權限檢查：必須是原本上架的 developer
    if info.get("developer") != developer:
        return {"status": "error", "message": "permission denied: not owner"}

    # 解析 min/max，如果有給就更新，沒給就沿用舊值
    try:
        old_min = int(info.get("min_players", 2))
    except (TypeError, ValueError):
        old_min = 2
    try:
        old_max = int(info.get("max_players", old_min))
    except (TypeError, ValueError):
        old_max = old_min

    try:
        if min_players is None or min_players == "":
            min_players_int = old_min
        else:
            min_players_int = int(min_players)
            if min_players_int < 1:
                raise ValueError

        if max_players is None or max_players == "":
            max_players_int = old_max
        else:
            max_players_int = int(max_players)
            if max_players_int < min_players_int:
                raise ValueError
    except ValueError:
        return {"status": "error", "message": "invalid min_players or max_players"}

    old_version = str(info.get("version", ""))
    # 刪舊檔案（忽略失敗）
    try:
        old_zip = UPLOAD_DIR / f"{game_name}_{old_version}.zip"
        old_dir = UPLOAD_DIR / f"{game_name}_{old_version}"
        if old_zip.exists():
            old_zip.unlink()
        if old_dir.exists():
            import shutil
            shutil.rmtree(old_dir)
    except Exception:
        pass

    # 跟 upload_game 一樣流程：收新的 zip、解壓
    zip_name = f"{game_name}_{new_version}.zip"
    zip_path = UPLOAD_DIR / zip_name
    extract_dir = UPLOAD_DIR / f"{game_name}_{new_version}"

    try:
        with open(zip_path, "wb") as f:
            for chunk in _recv_exact(conn, archive_size):
                f.write(chunk)
    except Exception as e:
        return {"status": "error", "message": f"failed to receive file: {e}"}

    try:
        if not extract_dir.exists():
            extract_dir.mkdir()

        for item in extract_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                import shutil
                shutil.rmtree(item)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        return {"status": "error", "message": f"failed to extract zip: {e}"}

    # 更新資料庫
    info["version"] = str(new_version)
    if description is not None:
        info["description"] = description
    if game_type is not None:
        info["game_type"] = game_type

    info["min_players"] = min_players_int
    info["max_players"] = max_players_int

    games[game_name] = info
    save_games(games)

    return {
        "status": "ok",
        "message": "update_game success",
        "game_name": game_name,
        "version": str(new_version),
    }

def delete_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    """只有原本的 developer 可以刪除遊戲。"""
    developer = payload.get("developer")
    game_name = payload.get("game_name")

    if not all([developer, game_name]):
        return {"status": "error", "message": "missing fields in delete_game"}

    games = load_games()
    info = games.get(game_name)
    if not info:
        return {"status": "error", "message": "game not found"}

    if info.get("developer") != developer:
        return {"status": "error", "message": "permission denied: not owner"}

    version = str(info.get("version", ""))

    # 先刪檔案
    try:
        zip_path = UPLOAD_DIR / f"{game_name}_{version}.zip"
        extract_dir = UPLOAD_DIR / f"{game_name}_{version}"
        if zip_path.exists():
            zip_path.unlink()
        if extract_dir.exists():
            import shutil
            shutil.rmtree(extract_dir)
    except Exception:
        pass

    # 再刪資料
    del games[game_name]
    save_games(games)

    return {
        "status": "ok",
        "message": "delete_game success",
        "game_name": game_name,
    }

def list_my_games(payload: Dict[str, Any]) -> Dict[str, Any]:
    developer = payload.get("developer")

    if not developer:
        return {"status": "error", "message": "missing developer field in list_my_games"}

    games = load_games()
    my_games = {name: info for name, info in games.items() if info.get("developer") == developer}

    for name, info in games.items():
        if info.get("developer") == developer:
            my_games[name] = info

    return {
        "status": "ok",
        "message": "list_my_games success",
        "games": my_games,
    }

def handle_developer_action(action: str, payload: Dict[str, Any], conn) -> Dict[str, Any]:
    if action == "upload_game":
        return upload_game(payload, conn)
    elif action == "update_game":
        return update_game(payload, conn)
    elif action == "delete_game":
        return delete_game(payload)
    elif action == "list_my_games":
        return list_my_games(payload)
    else:
        return {"status": "error", "message": f"unknown developer action: {action}"}
