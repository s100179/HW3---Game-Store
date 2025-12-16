# HW3 — Game Store 

本專案為「網路程式設計概論 HW3」的 **Game Store 系統**。  
系統提供玩家與開發者登入、遊戲商城管理、房間建立與加入，以及遊戲檔案上傳 / 下載等功能。

> 本 README **只說明 Game Store / Lobby 系統本身**，不包含任何遊戲（game server / game client）的實作與說明。

---

## 系統簡介

本系統採用 **Client–Server 架構**，以 **TCP 長連線** 作為通訊方式：

- **Lobby Server**
  - 管理帳號登入狀態
  - 管理遊戲商城（遊戲列表、版本、下載）
  - 管理房間（建立 / 加入 / 等待開始）
  - 處理開發者上傳與更新遊戲

- **Client**
  - `client_lobby.py`：系統入口
  - `player_client.py`：玩家功能
  - `developer_client.py`：開發者功能

---

## 環境需求
- Python 3.9+（建議 3.10/3.11）
- 作業系統：Windows / Linux / macOS
- 僅使用 Python standard library（不需額外安裝套件）

---

## 系統架構

### server
- `server/lobby_server.py`：主伺服器（登入、商城、房間、下載）
- `server/developer_server.py`：開發者上傳/更新/刪除遊戲
- `server/db_server.py`：資料讀寫（帳號、遊玩紀錄、評價等）

### client
- `client/client_lobby.py`：入口選單（登入後分流到 player/developer）
- `client/player_client.py`：玩家功能（瀏覽/下載/房間/評價）
- `client/developer_client.py`：開發者功能（上傳/更新/刪除）
- `client/network.py`：通用網路層（send_json/recv_json/recv_exact）

### 通訊協定
- 使用 TCP 長連線
- 控制訊息採用「一行一個 JSON」：每則訊息以 `\n` 結尾（newline-delimited JSON）
- 檔案傳輸（遊戲 zip）採用：
  1) 先送 JSON header（包含 `archive_size`）
  2) 再送固定長度的 raw bytes（避免 binary 內含 `\n` 導致切包錯誤）

### 資料存放位置
- `data/accounts.json`：帳號資料（player / developer）
- `data/rooms.json`：房間資訊（房間狀態、人數、房主等）
- `data/games.json`：遊戲商城資訊（遊戲名稱、版本、描述、人數限制等）
- `data/ratings.json`：遊戲評價（分數、留言、時間）
- `data/history.json`：玩家遊玩紀錄（遊玩次數）
- `uploaded_games/`：server 端保存上傳遊戲與解壓後內容
- `downloads/`：client 端下載遊戲與解壓後內容

---

## 執行說明

請先啟動 Lobby Server。

```bash
cd server
python lobby_server.py
```

啟動 Lobby Server 後再啟動 Client，執行：
```bash
cd client
python client_lobby.py
```

注意：使用前請先到client_lobby.py修改HOST

執行後，即可進入遊戲商城大廳：

=== Game Store Lobby ===
1. 登入
2. 註冊
0. 離開
請選擇:

打上要執行的動作編號，依照指令即可註冊 / 登入

### 開發者說明

開發者大廳頁面如下：

```bash
=== Developer Menu (456) ===
1. 上傳新遊戲
2. 更新現有遊戲
3. 刪除遊戲
4. 列出我的遊戲
0. 登出
請選擇：
```

上傳 / 更新　遊戲的格式如下
```bash
遊戲資料夾:
遊戲名稱:
版本:
描述:
遊戲類型 (CLI/GUI):
最少玩家數 (預設 2):
最多玩家數:
```
請依照指示輸入遊戲資訊

注意：
1. 請將要上傳的遊戲資料夾放入 `HW3 — Game Store/` ，並在遊戲資料夾處輸入該遊戲的資料夾名稱
2. 遊戲內執行檔檔名為 `game_server` + `game_client`

### 玩家說明

玩家大廳頁面如下：

```bash
=== Player Menu (123) ===
1. 瀏覽商城遊戲
2. 查看線上玩家列表
3. 進入遊戲大廳
4. 查看遊玩紀錄 / 評價遊戲
0. 登出
請選擇:
```

可在瀏覽商城遊戲處下載遊戲，或是進入遊戲大廳下載

## 常見問題（FAQ）
1. 出現 `no response from server`
   - 代表 Lobby Server 連線中斷或未啟動
   - 請先重啟 `lobby_server.py`，再重啟 `client_lobby.py`

2. Port 被占用 / 無法 bind
   - 請確認沒有另一個 server 還在背景執行
   - Windows 可用工作管理員或重新開啟終端機後再試
   - Linux/macOS 可用 `lsof -i :<port>` 檢查占用

3. 無法加入遊戲大廳
   - 請確認已下載該遊戲且版本為最新

4. 停止 Server：在終端機按 Ctrl + C

5. 若未照指示輸入，會出現輸入錯誤的字樣，請重新輸入並按照指示操作