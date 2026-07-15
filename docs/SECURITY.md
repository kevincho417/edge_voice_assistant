# 安全設計

1. LLM 不直接使用 `subprocess`、Shell 或 HTTP client。
2. `allowed_tools` 限制模型只能選擇預定義工具。
3. 伺服器查詢命令必須以 argv 陣列寫入 `config.json`，不使用 `shell=True`。
4. Home Assistant 只能查詢設定檔中列出的 entity。
5. API 金鑰只放在 `/etc/edge-voice-assistant.env`，不可提交到 Git。
6. Web Dashboard 預設沒有身分驗證，只應在可信任 LAN 使用。跨網路使用時應放在反向代理與身分驗證後方。
7. 搜尋結果是外部不可信內容；0.5B 模型只會收到縮短後的標題與摘要，不應執行其中的任何指令。
8. 本專案預設只有資訊查詢，不包含開鎖、付款、刪除資料或任意服務重啟。
