# サブPC経由のPi Zero W自動配布（#25）

## 配布経路

GitHubの**公開済み正式Release**をサブPCが5分ごとに確認し、LAN内SSHでPiへ転送する。
develop/mainへのpush、draft Release、prerelease、任意HEADは配布しない。
サブPC停止中の更新も次回起動後に拾う。GitHubホストから宅内へポートを開けない。

`controller.py` はアーカイブSHA256、GitHub asset digest（ある場合）、内外manifest、
全ファイルdigest、版、タグのcommit、mainへの到達性を検証する。
同じ版の再公開変更や自動downgradeは拒否する。変更なしでは転送・再起動を省く。

Piのroot所有helperは固定コマンド・引数なしで起動し、JSONとtarをstdinで受ける。
ローカル/リモート双方で排他制御、SSH接続/生存確認、各処理のtimeoutを設ける。
配布キーはforced commandと`restrict`付き。汎用sudoやSSHポート転送は許可しない。
**既存SwitchBotサービスがrootで動くため、配布キーは本番コード実行の権限を持つ。**
サブPCのキーと正式Releaseの公開権限を信頼境界とし、外部PRに渡さない。
helperやsudoersの更新はroot管理者による初回/個別操作で、リリースtarから置き換えない。

## 旧版・実機設定の保持

初回bootstrapは既存 `/opt/myroom-pi` を `/var/lib/pi0w-deploy/baseline/myroom-api` に保持し、
元のパスをsymlinkにする。既存systemd定義・ユーザー・enabled状態は変更しない。
root設定で明示したアプリ以外は触らない。room-panelは既定の設定雛形に含めず、導入確認後に下記の手順で加える。

更新は別ディレクトリに準備し、`.env`、`sensors.json`、履歴、その他非ソースは既存の実体へリンクする。
依存が変わる場合だけ、新しいvenvへPiに適合するwheelを導入する。
`--only-binary=:all:`のためARMv6/Pythonに対応するwheelが無い場合は失敗し、稼働版を維持する。
本番requirementsの範囲は変更しない。pip更新・ソースビルドは行わない。
新しい依存環境を準備できてから変更対象のサービス/タイマーを止め、symlinkを切り替える。
BLEは`--require-all`で全設定センサーの取得とAPI送信を実際に確認し、その後既存serviceも起動する。
既存unitはpartial successでも0を返すため、完全取得・送信の追加検証を省かない。
この検証では通常のservice起動とは別に1回分の測定データが送信される。
エアコンは既存oneshotの正常終了、panelはservice状態とloopback `/healthz`を確認する。
新旧コード・依存環境・設定/履歴の整合性を保って切り戻す。

設定不足を成功扱いにしない。MYROOM_API_URL / MYROOM_AIRCON_API_URL等の既定値は
公開整理で除去するため、**実機の非公開.envに実値を明示してから初回配布**する。
AirCloud資格情報がサンプルのままの場合も拒否する。
単発のBLE/API確認成功は長時間の継続取得まで保証しない。別途確認する。

## 初回導入（未実施）

先にPR #28 → #27（#29/#25差分も統合）をレビューして取り込み、配布対象を正式Releaseとして確定する。
サブPCのcloneは `~/apps/pi0w` に置く。GitHub CLIのContents読み取り認証、
OpenSSHクライアント、Python 3.7以上が必要。Pi側はBlueZ、Python/venv、既存サービスが必要。

**Piのコンソール/既存の信頼済み管理接続**でホスト鍵指紋を読む。

```bash
cd / && ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

**サブPC**で専用キーと設定を作る。入力した指紋とssh-keyscanの鍵が一致した場合だけ保存する。
IP、ログイン名、ポート、指紋を対話入力する。既存設定は上書きしない。

```bash
cd ~/apps/pi0w && python3 deploy/setup_connection.py
```

**サブPC**から既存の管理用SSH認証で初期導入する。SSH/sudoのパスワードが必要なら端末で入力する。
キーが必要な場合は`--admin-identity ~/.ssh/実際の管理キー名`を付ける。
専用配布キーを管理キーに流用しない。転送は公開キーとhelperのみで、秘密鍵はサブPCに残る。

```bash
cd ~/apps/pi0w && python3 deploy/bootstrap_remote.py
```

必要なら**Pi**で `/etc/pi0w-deploy.json` を調整する。room-panelの既存配置とsystemdサービスを
事前確認できた場合のみ、`apps`へ`room-panel`、path `/opt/room-panel`、services
`["room-panel.service"]`を追加して再度bootstrapする。未導入のpanelを勝手にサービス化しない。
追加後の形は `deploy/pi-config.room-panel.example.json` を参照する（手動編集時の参照用。
bootstrap/install-agentはこのファイルを使わず、導入済みの `/etc/pi0w-deploy.json` も上書きしない）。
追加後は、panelの `.env`（`MYROOM_API_TOKEN`等）と `venv` が `/opt/room-panel` にあることが必要で、
以降はpanelの修正も正式Releaseのたびに配布される。panelのみの変更ではpanelだけが再起動される。

```bash
cd / && sudoedit /etc/pi0w-deploy.json
```

**Pi**で既存private設定の不足だけを補う。実値をGitHubのIssueやログへ貼らない。

```bash
cd /opt/myroom-pi && sudoedit .env
```

**サブPC**で初回配布を実行し、stateと実機側のデータ取得を確認してからタイマーを有効化する。

```bash
cd ~/apps/pi0w && python3 deploy/controller.py poll
```

```bash
cd ~/apps/pi0w && bash deploy/install-subpc.sh
```

subpc構成管理の連携PRを取り込む場合も、設定・bootstrap・初回配布の確認後に適用する。
serviceはprivate設定と初回poll成功のinitialized markerを両方確認する。
タイマーを先に配置しても、初回の明示した配布が成功するまでは自動実行しない。

## 状態・ログ・切り戻し（サブPC）

```bash
cd ~/apps/pi0w && python3 deploy/controller.py status
```

```bash
cd ~/apps/pi0w && python3 deploy/controller.py diagnostics
```

diagnosticsはjournalの時刻・優先度と状態を扱い、秘密が含まれ得るMESSAGEは返さない。
詳細journalは信頼済みの管理用SSHでPi上だけで調べる。debug/raw出力をCIへ流さない。
サブPCの状態は `~/.local/state/pi0w-deploy/state.json`（0600）、Piの実行版/成功時刻は
`/var/lib/pi0w-deploy/current.json`（0600）。失敗理由は構造化したコードで保存する。
外部コマンドのstderr/API応答/資格情報はログへ保存しない。

```bash
cd ~/apps/pi0w && python3 deploy/controller.py rollback
```

手動rollback後は自動配布をpauseする。同じ失敗版を次の5分で再投入しない。
修正版または再配布の承認後に再開する。

```bash
cd ~/apps/pi0w && python3 deploy/controller.py resume
```

クラッシュ時はtransaction journalを保持し、次回のstatus/pollで旧版へ復旧してから処理する。
rollback自体が失敗した場合はjournalを消さず失敗扱いにし、管理者がサービス状態を確認する。
保持したbaseline・旧releaseは自動削除しない。失敗した準備ディレクトリだけは除去する。
空き容量は管理者が確認し、live/previous/設定・履歴のリンク元は削除しない。

## 実機で残る確認

| 項目 | 状態 |
| --- | --- |
| SSHホスト鍵・公開鍵・root helper・sudoers | 未設定/未確認 |
| OS、armv6l、Python/venv、配置先、service名 | ソース基準のみ、未実測 |
| bootstrap/正式Releaseの初回配布 | 未実施 |
| リビング・屋外センサーのBLE/API継続取得 | 未確認 |
| AirCloud/panelの実機確認 | 未確認 |
| CPU/メモリ影響、Pi/サブPC再起動後の自動復帰 | 未確認 |
| 接続不可/依存失敗/起動失敗/クラッシュ復旧 | モックによる自動テスト、実機は未確認 |

#25はコードのマージだけでcloseしない。実機結果を記録してから完了とする。
このChatGPT環境にはLAN/Tailscale経路とSSH認証がなく、実機反映済みとは記録しない。

公式Release仕様: https://docs.github.com/en/rest/releases/releases#get-the-latest-release

