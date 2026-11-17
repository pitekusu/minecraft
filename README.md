# TerraFirmaGreg Modern サーバー

Minecraft 1.20.1、Forge 47.4.13、TFG Modern 0.13.18 を Java 21 で動かす。Java ヒープは初期 8 GiB、最大 16 GiB。BlueMap 5.29 CLI は Java 25 の別コンテナで地図を描画・配信し、Forge 版 5.12 はプレイヤーの現在地と顔画像を配信する。Caddy が両方の HTTP 応答を取りまとめる。Minecraft と Caddy はホストのループバックで待ち受け、外部からは playit.gg を経由する。

## 導入

`~/codex/minecraft` で実行する。Podman、Python 3.10 以降、libpng 1.6 が必要。Quadlet のパスと UID/GID はこのホストの `pitekusu` ユーザーに合わせている。

```sh
./scripts/prepare.sh
install -Dm644 -t ~/.config/containers/systemd quadlet/{minecraft.container,bluemap.container,bluemap.network,bluemap-proxy.container}
systemctl --user daemon-reload
systemctl --user start minecraft.service
journalctl --user-unit=minecraft.service -f
```

`prepare.sh` は配布元のアーカイブと JAR を取得してハッシュを照合し、Python 3 で BlueMap 用の補正パックを `downloads/` に生成する。初回起動には Forge の取得とワールド生成が含まれる。Minecraft のログで `Done` と BlueMap の `Loaded!` を確認したら、Forge 側の描画を止めてプロキシを起動する。BlueMap CLI もプロキシと一緒に起動する。設定済みの systemd linger により、ホスト起動時に暗号化ディスクを解除するとユーザーのログイン前に各サービスが起動する。

```sh
for map in overworld underground beneath; do
  podman exec tfg-minecraft mc-send-to-console "bluemap freeze $map"
done
podman exec tfg-minecraft mc-send-to-console 'bluemap stop'
systemctl --user start bluemap-proxy.service
```

Forge 側の描画停止状態は `data/bluemap/pluginState.json` に保存される。

## 参加者の管理

正規の Minecraft Java アカウントを認証し、ホワイトリストに登録されているプレイヤーを受け付ける。`PlayerName` は Java 版プロフィール名に置き換える。登録一覧は `data/whitelist.json` に永続化される。

```sh
podman exec tfg-minecraft mc-send-to-console 'whitelist add PlayerName'
podman exec tfg-minecraft mc-send-to-console 'whitelist list'
podman exec tfg-minecraft mc-send-to-console 'whitelist remove PlayerName'
```

コマンド結果は `journalctl --user-unit=minecraft.service` または `data/logs/latest.log` で確認できる。

## 公開設定

公開設定の再構築には、`playit-self-managed.service` のエージェント `popos` と次の DNS 値を使う。

| トンネル | 接続先 | Route 53 のレコード |
| --- | --- | --- |
| Minecraft Java | `127.0.0.1:25565` | `_minecraft._tcp.mc.pitekusu.dev` の SRV に `1 1 44931 molecule-moms.tun.ply.gg.` |
| HTTPS | `http://127.0.0.1:8100` | `bluemap.pitekusu.dev` の CNAME に `299db30ba712e705a74d.cname.playit-dns.com.` |

Minecraft の Java クライアントには `mc.pitekusu.dev` を入力する。サーバー一覧の照会は入力元のホスト名を送るため、この Minecraft トンネルの Playit ホスト名検証は `None` に設定している。

BlueMap はゲートウェイの外部ドメインに `bluemap.pitekusu.dev` を割り当て、HTTPS トンネルの TLS 終端を `letsencrypt` に設定する。発行された証明書は既存のエージェントボリュームに保存される。HTTPS トンネルには Playit Premium が必要。 [Playit HTTPS](https://playit.gg/support/https-tunnel/) · [エージェントの TLS 終端](https://github.com/playit-cloud/playit-agent/blob/v2.0.2/README.md#https-tunnels-with-tls-termination)

## BlueMap の運用

- `config/bluemap/` のマップ定義は Forge 版と CLI 版で共有する。CLI はワールド、MOD、Minecraft コンテナが同期した補正パックを読み取り専用で開く。描画は2スレッド、高精細3D、gzip 圧縮。出力は `data/bluemap-cli/web/maps/` に保存し、Minecraft がディスクに保存した変更を監視する。共通設定や補正パックを変更したら `systemctl --user restart minecraft.service bluemap.service` で反映する。 [BlueMap CLI](https://bluemap.bluecolored.de/wiki/getting-started/Installation.html#using-bluemap-on-the-cli--standalone)
- テクスチャやモデルを変更したら、CLI の `--force-render` で既存タイルも再描画する。 [リソースパックの更新](https://bluemap.bluecolored.de/wiki/customization/ResourcePacks.html)
- Caddy は `live/players.json` とプレイヤーの顔画像を Forge 版に中継する。観戦・透明化中および別ディメンションのプレイヤーを隠す。CLI は地形タイルの更新を SSE で通知し、5.29 用の `player-polling-5.29.js` が、SSE 接続中も現在地を約1秒間隔で取得する。BlueMap を更新するときは、追加スクリプトと地形の自動反映を確認する。
- `Overworld` は地表、`地下 (Y ≤ 60)` はオーバーワールドの洞窟、`深界 (The Beneath)` は岩盤天井を除いた深界を表示する。地下と深界は Free Flight で高度を下げて探索できる。高さの上限は各マップの `render-mask` で設定する。地上と深界は中心 X=-3760、Z=-3344 の半径416ブロックの正方形を事前生成した。BlueMap 専用パックは、TFG 0.13.18 同梱の深界ディメンションタイプとバイオーム定義も読み込む。 [深界への移動](https://wiki.terrafirmagreg.team/modern/field-guide/en_us/beneath/beneath.html)
- BlueMap は3Dタイルとテクスチャを最大24時間キャッシュする。描画補正を反映した後、既に開いている地図ではメニューの「地形情報を更新」でタイルを取り直す。
- `TFG_Map_Compatibility` は BlueMap 用の描画補正。TFG の地形・植生、GregTech の鉱石・鉱石目印、TFC の垂直ハーフブロックを補う。作物と噴煙源の素材は TerraFirmaGreg Modern 0.13.18（LGPL-3.0）の `kubejs/assets/tfg` 由来。ヒトデとサルノコシカケのモデルは同梱の TerraFirmaGreg Core 0.9.34（LGPL-3.0）から、外から見えない未定義テクスチャ面を除いた。鉱石の PNG は TFG と GregTech 7.5.3 の元テクスチャに素材色を適用して合成した。 [TFG 0.13.18](https://github.com/TerraFirmaGreg-Team/Modpack-Modern/tree/0.13.18) · [GregTech 7.5.3](https://github.com/GregTechCEu/GregTech-Modern/tree/v7.5.3)
- `scripts/prepare.sh` は Wan's Ancient Beasts 1.4.3 の植物モデル3点から面積ゼロの未定義テクスチャ面を取り除いた地図用パックも生成する。
- Minecraft 本体の凝灰岩・深層岩・ブラックストーンを下地にする GregTech の鉱石テクスチャは、`scripts/prepare.sh` 実行時に Minecraft 1.20.1 と GregTech の素材を使ってローカルで合成する。
- Create Resource Pack v1 を採用する。Create 6.0.8 と BlueMap 5.29 の隔離環境で、機械プレス、ファン、デプロイヤー、直線ベルトの補正を確認した。水車の羽根は補正対象外。 [Create Resource Pack v1](https://github.com/Uiniel/BlueMap-Create-Resource-Pack/releases/tag/v1)
- 月・火星は到達してチャンクが保存された後に有効化する。`maps/overworld.conf` を基に、`world` は `world`、`dimension` は `ad_astra:moon` または `ad_astra:mars` とする。必要な TFG の KubeJS バイオームとディメンションタイプは、名前空間を保持したまま BlueMap の `packs` で読み込ませて試験する。特に月のディメンションタイプは `tfg:moon`。 [TFG の惑星定義](https://github.com/TerraFirmaGreg-Team/Modpack-Modern/tree/0.13.18/kubejs/data/ad_astra/dimension)
- ローカルでは `http://127.0.0.1:8100/`、`/settings.json`、`/maps/overworld/live/players.json` を確認する。描画ログは `journalctl --user -u bluemap.service`、Minecraft の TPS は `podman exec tfg-minecraft mc-send-to-console 'forge tps'` で確認できる。描画スレッドの設定は `config/bluemap-cli/core.conf` にある。

## 補正素材の出典

- TerraFirmaGreg Modern 0.13.18 の KubeJS リソースから、作物・植生・地形モデル、テクスチャと深界のディメンション・バイオーム定義を収録した。BlueMap で描画できるよう、一部のモデルとブロックステートを調整した。 [ソースとライセンス](https://github.com/TerraFirmaGreg-Team/Modpack-Modern/tree/0.13.18)
- TerraFirmaGreg Core Modern 0.9.34 のヒトデ・サルノコシカケのモデルから未定義の面を除去した。GregTech CEu Modern 7.5.3 と TFG の素材を参照し、鉱石テクスチャの色合成と BlueMap 用モデルを作成した。 [TerraFirmaGreg Core Modern](https://github.com/TerraFirmaGreg-Team/Core-Modern/tree/0.9.34) · [GregTech CEu Modern](https://github.com/GregTechCEu/GregTech-Modern/tree/v7.5.3)
- 上記の LGPL 素材には [LGPL 3.0](LICENSES/LGPL-3.0.txt) と、同ライセンスが参照する [GPL 3.0](LICENSES/GPL-3.0.txt) を同梱する。Dries007 と AlcatrazEscapee の TerraFirmaCraft 3.2.28 に由来するサルノコシカケの `artists_conk_0.json`〜`artists_conk_4.json` は、2026年11月17日に BlueMap 用として未定義テクスチャ面を除去した。 [TerraFirmaCraft 3.2.28](https://github.com/TerraFirmaCraft/TerraFirmaCraft/tree/0acc975af53ec87cbe45b07e9076949e939fdb58) · [EUPL 1.2](LICENSES/TerraFirmaCraft.txt)
- BetterEnd の素材の出典と変更箇所は [BetterEnd クレジット](LICENSES/BetterEnd-CREDITS.md) を参照。垂直ハーフブロックの補正は FirEmerald の Additional Placements 3.0.1 のブロックステートに対応する。 [Additional Placements](https://github.com/FirEmerald/Additional-Placements/tree/84d5eb1d67f5f420e950ee759fde1366d35398ae) · [MIT](LICENSES/Additional-Placements.txt)

## バックアップ

TFG 同梱の FTB Backups 2 が `backups/` に保存する。手動バックアップは `podman exec tfg-minecraft mc-send-to-console 'backup create'` で実行する。復元時はまず ZIP を別ディレクトリに展開し、`level.dat` とリージョンファイルを確認する。本番復元はサービスを停止して現在のワールドを退避してから行う。 [FTB Backups 2](https://github.com/FTBTeam/FTB-Backups-2)
