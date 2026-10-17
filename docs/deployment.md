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

既存の導入済みサブPCの更新は「既存サブPCのcontroller更新」節を参照する。

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

## 既存サブPCのcontroller更新（導入済みcloneの更新手順）

`deploy/controller.py`・`deploy/systemd/`・`deploy/install-subpc.sh`はリリースarchiveに含まれない
（`scripts/package_release.py`はアプリソースと`version.json`だけを含める）。正式Releaseを公開しても、導入済みサブPCの
`~/apps/pi0w`は自動では更新されない。**deploy配下を変更したReleaseは、各サブPCで次の手順により
cloneを正式Releaseの固定タグへ更新して初めて有効になる。** `last_poll_*`の記録と過去失敗表示の解除も
この更新後のcontrollerが行う。

- 更新対象は `~/apps/pi0w`（このリポジトリのclone）だけ。IssueDeckのgeneric pollerや
  `~/apps/issue-deck`の更新・再起動は不要で、混同しない。
- Pi側の収集service・timerは止めない。Piへの転送・再起動も起こさない（変更なしのpollは何もしない）。
- 追従するのは**公開済みの正式Releaseのタグ**だけ。develop・main HEAD・任意のブランチへは更新しない。
- 設定（`~/.config/pi0w-deploy/`）と状態（`~/.local/state/pi0w-deploy/`）はcloneの外にあり、更新で変わらない。
  以降のコマンド出力・貼り付けにconfig/stateの全文、IP・ユーザー名・指紋は含めない（下記のとおりキーを絞って表示する）。

### 手順（サブPC）

1. 対象タグを決め、公開済みの正式Releaseで、mainに含まれることを確認する。

```bash
cd ~/apps/pi0w && export TAG=vX.Y.Z && gh release view "$TAG" --json tagName,isDraft,isPrerelease --jq '[.tagName,.isDraft,.isPrerelease]' && git fetch --tags origin main && git merge-base --is-ancestor "refs/tags/$TAG" origin/main && echo ok
```

`false,false`かつ`ok`でなければ中止する。続けて、現在の版より新しい（downgradeでない）ことも確認する。

```bash
cd ~/apps/pi0w && git merge-base --is-ancestor HEAD "refs/tags/$TAG" && echo ok
```

2. 実行中のpollとの競合を防ぐ。タイマーだけ止め、実行中の`pi0w-deploy.service`の終了を待つ。
   pollは最大50分かかり得る。`inactive`になるまで繰り返す。

```bash
systemctl --user stop pi0w-deploy.timer && systemctl --user is-active pi0w-deploy.service
```

手動で`controller.py`を実行中の端末が無いことも確認する（controllerは`state-dir/lock`で排他制御する）。

3. 現在のコミットとローカル変更を保全する（失敗時の復旧に使う）。

```bash
cd ~/apps/pi0w && echo "旧コミット: $(git rev-parse HEAD)" && git branch "backup/pre-$TAG-$(date +%Y%m%d%H%M)" && git status --short
```

出力が空でなければローカル変更がある。破棄せず、一意なメッセージでstashして控える。

```bash
cd ~/apps/pi0w && git stash push -u -m "pi0w-pre-$TAG" && git stash list
```

4. cloneを固定タグへ更新する。`reset --hard`は使わない。detached HEADで固定する。

```bash
cd ~/apps/pi0w && git switch --detach "refs/tags/$TAG" && git rev-parse HEAD && python3 -m py_compile deploy/controller.py
```

stashしたローカル変更は、内容を確認してから必要な分だけ`git stash apply`で戻す（deploy配下を
手元で変えていた場合は、Release側の内容を正としてマージ要否を判断する）。

5. タイマー・unitを戻す。`install-subpc.sh`はunitを再配置して`daemon-reload`し、タイマーを有効化する
   （Piへは読み取り専用の`status`問い合わせをSSHで1回行うだけで、収集service・timerは止めず、転送・再起動もしない）。
   冪等なので、unitが変わっていなくても実行してよい。`status`が失敗するとstate.jsonに`failed`が記録され、
   タイマーを再開する前に止まる（下記「失敗時の復旧」）。`jq`が無い環境では`python3 -m json.tool`で代用する。

```bash
cd ~/apps/pi0w && bash deploy/install-subpc.sh
```

### 更新後の確認（サブPC）

更新直後に1回pollを実行する（変更なしなら転送・再起動はしない）。次回のタイマーpollを待ってもよい。

```bash
cd ~/apps/pi0w && python3 deploy/controller.py poll
```

```bash
jq '{status,last_poll_at,last_poll_result,last_poll_version,last_success_at,failure_reason}' ~/.local/state/pi0w-deploy/state.json
```

更新後のcontrollerが動いていれば、`last_poll_at`が更新後の時刻になり、`last_poll_result`が
`unchanged`または`deployed`になる。成功したpollでは過去の`failure_reason`が消える。
`last_poll_*`が出ない場合は旧controllerのままなので、`git rev-parse HEAD`がタグのコミットか、
`systemctl --user cat pi0w-deploy.service`のExecStartが`~/apps/pi0w/deploy/controller.py`かを確認する。
`unchanged`なら`last_success_at`は変わらず、Piの収集serviceの`ActiveEnterTimestamp`も変わらない。

### 失敗時の復旧

- `git switch --detach`が失敗した（ローカル変更との競合など）: cloneは変わっていない。手順3のstashを
  やり直してから再実行する。
- 更新後の`poll`/`status`/`py_compile`が失敗した: `install-subpc.sh`でタイマーが再開済みの場合があるため、
  先にタイマーを止めてserviceの終了を待ち（`inactive`が出ればよい。終了コード3は正常）、旧コミットへ戻す。
  タイマーと手動pollが重なると、lock取得に失敗してトレースバックで終了する（stateは書かれない）。

```bash
systemctl --user stop pi0w-deploy.timer; systemctl --user is-active pi0w-deploy.service
```

```bash
cd ~/apps/pi0w && git switch --detach <手順3で控えた旧コミット> && bash deploy/install-subpc.sh
```

  失敗したpollは`last_poll_result`が`failed:<コード>`になる。rollback後の`automatic_poll_paused`中は
  `automatic_poll_paused_after_rollback`で失敗するので、`controller.py resume`が必要かを確認する。
  failure_reasonのコードを確認し、原因が分かるまで更新を繰り返さない。
- 戻した後は、stashがあれば`git stash list`で確認して`git stash apply`する。成功を確認してからだけ
  `git stash drop`・`backup/*`ブランチの削除を行う。
- Pi側の配布版の切り戻しは別操作（`controller.py rollback`）。cloneの更新失敗では実行しない。
- `install-subpc.sh`が`initialized`不在などで止まった場合はタイマーが停止したままなので、
  原因を直すか`systemctl --user start pi0w-deploy.timer`で必ず再開する。

## 継続運用・再起動・障害の実機確認手順（#9）

実機確認はオフラインCI（`scripts/verify.sh`）とは別に、サブPC/Piの管理者が手動で行う。
結果は下の表へ日付つきで追記し、実機固有値（IP・ユーザー名・指紋・API URL・資格情報）は書かない。

### 稼働サービスを無関係に止めない原則

- 検証のために収集service・timer・他アプリを `stop` / `disable` しない。障害の再現は配布側の入力で行う。
- 接続不可: サブPCで `~/.config/pi0w-deploy/config.json` の複製を使い、ポート等を無効値にして `--config` で `poll` する（実設定は変更しない）。Pi側は一切触らない。
- 依存失敗/起動失敗: 稼働中のPiでは起こさない。モックによる自動テストと、公開前の別環境（予備Pi等）がある場合のみ行う。無い場合は「未確認」のまま残す。
- いずれも事前に `controller.py status` で現行版を控え、後に同じ版・`last_success_at`が維持されたことを確認する。

### 1. 定期pollの追跡・不要再起動の無さ（サブPC）

```bash
cd ~/apps/pi0w && python3 deploy/controller.py status
```

```bash
cat ~/.local/state/pi0w-deploy/state.json
```

`last_poll_at`（最後のpoll時刻）・`last_poll_result`（`deployed`/`unchanged`/`failed:<コード>`）・
`last_poll_version`で追跡する。`unchanged`のpollは過去の失敗表示を消すが、`last_success_at`
（最後に実際に配布した時刻）は動かさない。変更なしの間は、Piの `/var/lib/pi0w-deploy/current.json` の
成功時刻と、収集serviceの `systemctl show -p ActiveEnterTimestamp,NRestarts` が変わらないことを確認する。

### 2. 全BLEターゲットの継続取得・履歴保持（Pi）

設定済みの全センサーについて、一定時間（例: 1時間以上）収集timerが回り続け、API側に各センサーの
データが途切れず届くことを確認する。更新前後で `.env`・`sensors.json`・履歴DBのIDと件数が減っていないこと。
`--require-all`の検証送信は通常の1回分とは別に測定値を1件送るため、件数の増減は1件分を差し引いて見る。

### 3. CPU・メモリ・ディスク（Pi）

配布のpoll時（`status`のみ）と`apply`中、および平常時で次を記録する。

```bash
cd / && uptime && free -m && df -h /opt /var/lib && systemctl show -p MemoryCurrent,CPUUsageNSec myroom-collectors.service
```

（unit名は実機の定義に合わせる。）Pi Zero Wでは`apply`中の一時的な上昇は許容し、平常時のpoll・収集に
支障（収集間隔の遅延、OOM、空き容量不足）が出ないことを基準にする。旧release・baselineは自動削除しないので、
空き容量は更新のたびに確認する。

### 4. 再起動後の自動復帰

サブPC再起動後は `systemctl list-timers pi0w-deploy.timer` で次回予定があり（`Persistent=true`、起動2分後に初回）、
`state.json`の`last_poll_at`が再起動後の時刻に更新されること。Pi再起動後は収集timerがactiveで、データが再開すること。

### 5. 障害時の旧版保持・復旧後の再試行

「稼働サービスを止めない原則」の方法で`failed:ssh_or_helper_failed`等になっても、`version`と`last_success_at`が
変わらず、接続復旧後の次回pollで自動的に再試行されることを確認する。依存失敗/起動失敗の切り戻しは自動テスト
（`tests/test_deploy.py`）で保証している範囲を実機の結論としない。

## 実機で残る確認

| 項目 | 状態 |
| --- | --- |
| 正式Release配布（ARMv6/Python 3.7.3、BLE `--require-all`成功） | 2026-10-12 v0.1.1で確認（ユーザー実行結果） |
| 以降の版の配布 | サブPCの`state.json`上、v0.1.3の配布成功（2026-10-12 13:48 UTC、変更アプリなし）を確認。Pi側の`hardware_verification`は`not_run`で、実機のBLE/API確認は未実施 |
| 定期pollの追跡 | 2026-10-13時点のサブPCでtimerは5分周期で動作。06:43 UTCに`ssh_or_helper_failed`が1回記録され、その後のpollは成功したが失敗表示が残っていた→`last_poll_*`の記録と失敗表示の解除をコードへ追加（未デプロイ） |
| 既存サブPCのcontroller更新（正式Release公開後） | **未確認**。上記「既存サブPCのcontroller更新」の手順で`~/apps/pi0w`を新タグへ更新し、次回pollで`last_poll_*`が記録されることを#9で確認する。公開前のレビューはコードと手順のみで、実機での確認とは分ける |
| 全BLEターゲットの継続取得・履歴保持 | 未確認 |
| CPU/メモリ/ディスク影響 | 未測定 |
| Pi/サブPC再起動後の自動復帰 | 未確認 |
| 接続不可/依存失敗/起動失敗の実機確認 | モックによる自動テストのみ。実機は未確認 |
| AirCloud/room-panel | room-panelは配布対象外（追加は別の仕様判断）。AirCloudは未確認 |

#9は手順の整備と記録だけでcloseしない。上表の未確認項目を実機で確認し、結果を追記してから完了とする。

公式Release仕様: https://docs.github.com/en/rest/releases/releases#get-the-latest-release

