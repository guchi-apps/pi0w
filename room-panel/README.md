# room-panel

I2C接続の16x2キャラクターLCDと単色LED（複数個）をラズパイに取り付け、MyRoomの最新センサー値や uptime-kuma の監視状況、ラズパイ本体・VPS本体のCPU/メモリ/ディスク使用状況を表示する常駐アプリ。表示モード・LED割当は同一LAN内のブラウザから即時切り替えできる。

```
                         ┌─ LCD表示モード切替
スマホ/PCブラウザ ──HTTP──► room-panel(Flask, :8080) ─┤
                         └─ LED割当切替（LEDごとに何を表示するか）
                                   │
                        (バックグラウンドスレッド poll_loop / heartbeat_loop)
                                   │
                    ┌──────────────┼──────────────┬──────────────┐
                    ▼              ▼              ▼              ▼
              MyRoom API    uptime-kuma      VPS状態API      I2C LCD / GPIO LED
           (要Bearerトークン) (ステータスページAPI) (要Bearerトークン)
```

## 前提

| 項目 | 内容 |
|------|------|
| ハードウェア | Raspberry Pi Zero W、PCF8574 I2Cバックパック搭載の16x2キャラクターLCD、単色LED×4（緑・黄・赤・白、+抵抗） |
| Python | 3.7（Pi Zero W実機）。ライブラリのバージョン上限に注意（下記） |
| ネットワーク | Pi から MyRoom API・uptime-kuma へHTTPS/HTTPで到達できること |

## LCD（PCF8574 I2Cバックパック）について

基板裏面に青いトリマー（可変抵抗）がはんだ付けされているタイプの、一般的なI2C 1602 LCD。コントラスト調整は基板上のトリマーで完結するため、外付け配線は不要。

- I2Cアドレスは基板により **`0x27` または `0x3F`** が多い（`i2cdetect -y 1` で確認）
- ピンは **GND / VCC / SDA / SCL の4本のみ**

### 配線

| LCDピン | 接続先 |
|---|---|
| GND | GND |
| VCC | **3.3V**（ラズパイのI2Cは3.3Vロジックのため。5Vで動かす場合はレベルシフタが必要。3.3V駆動でもバックライトがやや暗くなる程度で動作に支障はない） |
| SDA | GPIO2 (Pin3, I2C1 SDA) |
| SCL | GPIO3 (Pin5, I2C1 SCL) |

LED1〜4: 各GPIO（`.env` の `LED1_PIN`〜`LED4_PIN`）→ 抵抗（330Ω程度）→ LED → GND

| LED | GPIO(BCM) | 物理ピン番号 | 色（実配線） | 初期割当ソース |
|---|---|---|---|---|
| LED1 | GPIO17 | 11番 | 赤 | `myroom_freshness`（正常＝点灯） |
| LED2 | GPIO27 | 13番 | 黄 | `uptime_kuma_overall`（全UP＝点灯） |
| LED3 | GPIO22 | 15番 | 緑 | `heartbeat`（生存確認＝点滅） |
| LED4 | GPIO23 | 16番 | 白 | `always_off`（予備枠、Web UIから自由に割当変更可） |

色は初期表示上の目安で、割当自体はWeb UIからいつでも変更できる。

配線後、`sudo raspi-config` の Interface Options から I2C を有効化（`install.sh` でも試行するが、確実なのは手動確認）。有効化後 `i2cdetect -y 1` で `0x27` または `0x3F` が見えることを確認する。表示が薄い/濃すぎる場合は基板上のトリマーをマイナスドライバーで調整する。

## セットアップ

### 1. ファイル配置

このディレクトリ一式をラズパイ上の作業ディレクトリ（例 `~/room-panel`）へ配置する。

#### `deploy.sh`（同一LAN内から自動アップロード）

開発用PCがラズパイと同じ自宅LAN内にある場合、`deploy.sh` でファイル転送を自動化できます。

```bash
cd room-panel
./deploy.sh              # ローカル/リモートの差分確認 → 確認プロンプト → 転送
./deploy.sh --diff        # 差分確認のみ（転送しない）
./deploy.sh --install     # 転送後、Pi上で sudo ./install.sh とサービス再起動まで実行
./deploy.sh --yes         # 確認プロンプトをスキップ（フラグは組み合わせ可能）
```

接続先は環境変数で上書き可能です:

```bash
PI_HOST=raspberrypi.local PI_USER=pi-user PI_SSH_KEY=~/.ssh/pi0w REMOTE_DIR=room-panel ./deploy.sh
```

> **WSL2 からは実行できません**（`raspberrypi.local` / `192.168.1.x` に到達不可）。Windows PowerShell / Git Bash など、LANに直接出られる環境で実行してください。OpenSSH 形式の秘密鍵が必要です。

#### GitHubの正式Releaseから自動反映

サブPCの配布機構（[docs/deployment.md](../docs/deployment.md)）の対象に `room-panel` を加えると、
パネルの修正も正式ReleaseのたびにサブPC経由でPiへ反映されます（`deploy.sh` の手動転送は不要）。
対象に加える前の初回導入（`install.sh`・`.env`・`venv`）は従来どおり手動で行います。
`.env` と `venv` は配布で上書きされず、反映後は `/healthz` で起動を確認し、失敗時は旧版へ戻ります。

WinSCP 等でGUIから手動アップロードしたい場合は、`venv` / `__pycache__` / `.env` / `dev.sh` を除く一式（`web/` 配下も含む）を転送する。

### 2. `.env` の作成

作業ディレクトリに `.env.example` を参考に `.env` を作成。特に以下は必須で確認が必要:

| 変数 | 内容 |
|---|---|
| `MYROOM_API_TOKEN` | MyRoom `/api/latest` はBearer認証必須。myroomの`JWT_SECRET_KEY`で署名した長期トークンを発行して設定する（Googleログイン経由のトークンは`JWT_EXPIRE_HOURS`＝既定7日で失効するため非推奨） |
| `UPTIME_KUMA_BASE_URL` / `UPTIME_KUMA_SLUG` | uptime-kumaのステータスページURL（`https://kuma.example.com/status/<slug>` の `<slug>` 部分） |
| `VPS_STATUS_TOKEN` | VPS状態API（`https://vps.example.invalid/internal/vps-status`）はBearer認証必須。VPS側の管理リポジトリ の `vps-status-api.conf`（`VPS_STATUS_API_TOKEN`）と同じ値を設定する |
| `LED1_PIN`〜`LED3_PIN` | 実配線に合わせて変更 |
| `LCD_I2C_ADDRESS` | `i2cdetect -y 1` の結果に合わせて変更 |

### 3. インストール

```bash
cd ~/room-panel
chmod +x install.sh
sudo ./install.sh

sudo nano /opt/room-panel/.env   # 上記の必須項目を設定
```

### 4. 疎通確認（サービス起動前）

```bash
sudo /opt/room-panel/venv/bin/python3 /opt/room-panel/app.py --check-myroom
sudo /opt/room-panel/venv/bin/python3 /opt/room-panel/app.py --check-uptime-kuma
sudo /opt/room-panel/venv/bin/python3 /opt/room-panel/app.py --check-vps-status
# uptime-kumaのレスポンス形状を確認したい場合（バージョン差異の調査用）
sudo /opt/room-panel/venv/bin/python3 /opt/room-panel/app.py --dump-raw-uptime-kuma
```

### 5. 起動

```bash
sudo systemctl start room-panel.service
sudo systemctl enable room-panel.service   # install.shで既にenable済み
journalctl -u room-panel.service -f
```

同一LAN内のブラウザから `http://<ラズパイのIP>:8080/` へアクセスすると、LCD表示モード・LED割当を切り替えられる。

## Web UI / API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/` | 状況確認・モード切替・LED割当変更 |
| POST | `/mode/<mode_id>` | LCD表示モード切替（`myroom` / `uptime_kuma` / `system` / `vps` / `clock`） |
| POST | `/led/<led_key>/<source_id>` | 指定LED（`led1`/`led2`/`led3`）の割当を切替 |
| GET | `/api/status` | 現在の状態JSON |
| GET | `/healthz` | 200固定応答。**このアプリ自体をuptime-kumaの監視対象に追加できる** |

### LEDシグナルソース一覧（`led_sources.py`）

| ID | 内容 |
|---|---|
| `myroom_freshness` | 直近 `MYROOM_STALE_THRESHOLD_SEC` 秒以内にMyRoom取得成功していればON |
| `uptime_kuma_overall` | uptime-kuma監視対象が全てUPならON、1つでもDOWNならOFF、未取得ならBLINK |
| `heartbeat` | アプリの生存確認（一定間隔でトグル。ポーリングループがハングすると消灯） |
| `co2_alert` | MyRoomのCO2濃度が `CO2_ALERT_THRESHOLD`（既定1000ppm）以上ならON |
| `cpu_high_load` | ラズパイ本体のCPU使用率が `CPU_ALERT_THRESHOLD_PERCENT`（既定80%）以上ならON |
| `always_on` / `always_off` | 固定点灯/消灯（予備・動作確認用） |

LED割当はメモリ上の状態のみで、**サービス再起動時は `.env` の `DEFAULT_LED1_SOURCE` 等に戻る**（永続化はスコープ外）。

## 開発（非Pi環境でのオフライン確認・Web UIのデザイン調整）

```bash
./dev.sh
```

初回は`venv`作成・依存インストールも自動で行う。起動したら `http://localhost:8080/` にアクセスしてUI一式を確認できる。

- `MOCK_HARDWARE=1`: LCD/LEDへの実アクセスを行わず、LCD内容はログ出力、LEDは `gpiozero.pins.mock.MockFactory` で仮想化
- `FAKE_SOURCES=1`: MyRoom/uptime-kumaへの実通信を行わず、OK/NG/UNKNOWNの全パターンを巡回するダミーデータを使用
- `web/templates/index.html` / `web/static/style.css` はテンプレート自動リロードが有効なため、編集後はブラウザの再読み込みだけで反映される（`app.py`の再起動不要）

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `--check-myroom` が401 | `MYROOM_API_TOKEN` 未設定/誤り | トークンを再確認 |
| `--check-vps-status` が401 | `VPS_STATUS_TOKEN` が VPS側の管理リポジトリ の `vps-status-api.conf` と不一致 | 両者のトークンを再確認 |
| LCDに何も表示されない | I2C未有効化 / アドレス不一致 / コントラスト未調整 | `sudo raspi-config` でI2C有効化＋再起動、`i2cdetect -y 1` でアドレス確認、基板上のトリマーを回してコントラスト調整（真っ白/真っ黒になっていないか） |
| LEDが点かない | GPIO番号不一致 / 配線ミス（極性等） | `.env` の `LED*_PIN` と実配線を確認 |
| `heartbeat`を割り当てたLEDが消灯したまま | `poll_loop`がハングしている可能性 | `journalctl -u room-panel.service -f` でエラーログ確認、`sudo systemctl restart room-panel.service` |
| uptime-kumaのUP/DOWNが常にBLINK扱い | `UPTIME_KUMA_BASE_URL`/`SLUG`未設定、またはAPI形状がバージョン差異で想定と異なる | `--dump-raw-uptime-kuma` で生レスポンスを確認し `uptime_kuma_client.py` のパース処理を調整 |

## 関連ドキュメント

- プロジェクト全体: [../README.md](../README.md)
- MyRoom側センサー連携: [../myroom-api/README.md](../myroom-api/README.md)
- VPS状態API側: VPS側の管理リポジトリ（`vps-status-api.service` および README「運用方針」）


