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

## 執行說明

請先啟動 Lobby Serve。

啟動lobby_server後，執行：
```bash
cd client
python client_lobby.py
```

執行後，即可進入遊戲商城大廳：

=== Game Store Lobby ===
1. 登入
2. 註冊
0. 離開
請選擇:

打上要執行的動作編號，依照指令即可註冊 / 登入

### 開發者說明

開發者大廳頁面如下：

=== Developer Menu (456) ===
1. 上傳新遊戲
2. 更新現有遊戲
3. 刪除遊戲
4. 列出我的遊戲
0. 登出
請選擇：

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

=== Player Menu (123) ===
1. 瀏覽商城遊戲
2. 查看線上玩家列表
3. 進入遊戲大廳
4. 查看遊玩紀錄 / 評價遊戲
0. 登出
請選擇:

可在瀏覽商城遊戲處下載遊戲，或是進入遊戲大廳下載
注意：若沒下載或未更新到最新版，則無法進入該遊戲的遊戲大廳

### 其他注意事項
1. 如果出現 **no response from server** 代表lobby_server斷線，請重啟lobby_server後再重啟client_lobby
2. 若未照指示輸入，會出現輸入錯誤的字樣，請重新輸入並按照指示操作
