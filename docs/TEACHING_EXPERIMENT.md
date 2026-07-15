# 教學比較實驗

## 研究問題

1. Local 與 Gemini 的繁體中文逐字稿何者較準確？
2. 兩者選擇正確工具的比例為何？
3. 網路正常、延遲、斷線時，兩種方案的回應時間與成功率如何？
4. Local 0.5B 在只負責工具選擇與摘要時，是否足以處理居家問題？

## 公平比較條件

- 使用同一支 USB 麥克風。
- VAD 只錄製一次，兩條 pipeline 使用完全相同的 WAV。
- 工具層相同，例如都使用 Open-Meteo。
- 固定測試問題、距離、音量及背景噪音。

## 建議語料

每位學員至少錄製：

- 天氣 5 句
- 時間日期 3 句
- 最新新聞 5 句
- 一般網路搜尋 5 句
- 本地服務狀態 3 句
- 穩定常識問題 4 句

並在安靜、風扇噪音及多人交談背景下重複。

## 評估指標

- CER：中文 Character Error Rate
- Tool Accuracy：工具選擇正確率
- Argument Accuracy：地點、query、entity 正確率
- End-to-end Success：最終回答包含正確即時資料
- ASR Latency
- Tool Latency
- Answer Generation Latency
- Total Latency
- API Failure Rate
- Local Offline Success Rate
- Jetson RAM、溫度與 Load

## 隱私比較

- Local：原始語音留在 Jetson；工具只收到必要文字參數。
- Gemini：完整語音會傳給 Gemini API。
- Hybrid：通常留在本地，只有 Local 失敗時才上傳完整音訊。
