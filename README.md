# Raspberry Pi センサー・表示パネル

Raspberry Pi Zero W向けのBLEセンサー取得とLCD/LED表示アプリです。
Python 3.7 / ARMv6を互換性の基準にしています。

- `myroom-api`: SwitchBotのBLEデータとAirCloud Homeのエアコン状態を、設定したAPIへ送信。
- `room-panel`: センサー値、監視状況、システム状態をLCD/LEDとWeb画面で表示。

接続先、SSHログイン、センサーMAC、トークンは実機の `.env` / `sensors.json` で管理してください。
リポジトリ内のURL・MAC・ユーザー名は説明用です。実機設定をコピーしてコミットしないでください。
Web画面は認証なしのため、信頼できるLAN内で使用してください。

詳細: [センサー](myroom-api/README.md)、[表示パネル](room-panel/README.md)。
公開版はハードウェアなしCIのみを有効にしています。IssueDeck連携は公開入力の権限確認後に導入します。

```bash
python3 -m pip install -r requirements-ci.txt
bash scripts/verify.sh
```

CI成功はBLE/GPIO/I2Cの実機確認やデプロイ完了を意味しません。

