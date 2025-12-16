# server/db_server.py
import json
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============ accounts ============

_accounts_lock = Lock()
ACCOUNTS_PATH = DATA_DIR / "accounts.json"

ACCOUNTS_DEFAULT = {
    "players": {},
    "developers": {},
}


def load_accounts():
    data = _load_json(ACCOUNTS_PATH, ACCOUNTS_DEFAULT.copy())
    data.setdefault("players", {})
    data.setdefault("developers", {})
    return data


def save_accounts(data):
    with _accounts_lock:
        data.setdefault("players", {})
        data.setdefault("developers", {})
        _save_json(ACCOUNTS_PATH, data)


# ============ games ============

_games_lock = Lock()
GAMES_PATH = DATA_DIR / "games.json"

# 預設就給空 dict，不要放型別物件
GAMES_DEFAULT = {}


def load_games():
    data = _load_json(GAMES_PATH, GAMES_DEFAULT.copy())
    return data


def save_games(data):
    with _games_lock:
        _save_json(GAMES_PATH, data)


# ============ rooms ============

_rooms_lock = Lock()
ROOMS_PATH = DATA_DIR / "rooms.json"

ROOMS_DEFAULT = {}


def load_rooms():
    data = _load_json(ROOMS_PATH, ROOMS_DEFAULT.copy())
    return data


def save_rooms(data):
    with _rooms_lock:
        _save_json(ROOMS_PATH, data)

# ============ ratings ============

_ratings_lock = Lock()
RATINGS_PATH = DATA_DIR / "ratings.json"
RATINGS_DEFAULT = {}  # {game_name: [ {player, score, comment, timestamp}, ... ]}


def load_ratings():
    data = _load_json(RATINGS_PATH, RATINGS_DEFAULT.copy())
    # 確保一定是 dict
    if not isinstance(data, dict):
        data = {}
    return data


def save_ratings(data):
    with _ratings_lock:
        _save_json(RATINGS_PATH, data)


# ============ play history ============

_history_lock = Lock()
HISTORY_PATH = DATA_DIR / "history.json"
HISTORY_DEFAULT = {}  # {player: {game_name: play_count}}


def load_history():
    data = _load_json(HISTORY_PATH, HISTORY_DEFAULT.copy())
    if not isinstance(data, dict):
        data = {}
    return data


def save_history(data):
    with _history_lock:
        _save_json(HISTORY_PATH, data)


