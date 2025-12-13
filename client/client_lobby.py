import json
import os, sys
sys.path.append(os.path.dirname(__file__))

from network import connect_to_server, send_json, recv_json

from player_client import run_player_menu
from developer_client import run_developer_menu

SERVER_HOST = "140.113.17.11"
SERVER_PORT = 5000

### system處理註冊及登入
def system_register(sock):
    role = input("註冊身分 (player/developer): ").strip()
    username = input("帳號: ").strip()
    password = input("密碼: ").strip()

    send_json(
        sock,
        {
            "role": "system",
            "action": "register",
            "payload": {
                "role": role,
                "username": username,
                "password": password,
            },
        },
    )
    resp = recv_json(sock)
    print(">>", resp.get("message"))


def system_login(sock):
    role = input("登入身分 (player/developer): ").strip()
    username = input("帳號: ").strip()
    password = input("密碼: ").strip()

    send_json(
        sock,
        {
            "role": "system",
            "action": "login",
            "payload": {
                "role": role,
                "username": username,
                "password": password,
            },
        },
    )
    resp = recv_json(sock)

    if resp is None:
        print("no response from server")
        return None, None

    print(">>", resp.get("message"))
    if resp.get("status") == "ok":
        return role, username
    return None, None


def main():
    sock = connect_to_server(SERVER_HOST, SERVER_PORT)
    print(f"已連線到 {SERVER_HOST}:{SERVER_PORT}")

    try:
        while True:
            print("\n=== Game Store Lobby ===")
            print("1. 登入")
            print("2. 註冊")
            print("0. 離開")
            choice = input("請選擇: ").strip()

            if choice == "0":
                break
            elif choice == "2":
                system_register(sock)
            elif choice == "1":
                role, username = system_login(sock)
                if role == "player":
                    # 進入 player_client 的世界
                    run_player_menu(sock, username)
                    # run_player_menu 結束的時候，代表那邊選了「登出」，
                    # 你這裡就會回到 lobby 的 while 迴圈，顯示主選單
                elif role == "developer":
                    run_developer_menu(sock, username)
                else:
                    # 登入失敗或 role None，就回到 lobby 選單
                    pass
            else:
                print("輸入錯誤，請重新選擇。")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
