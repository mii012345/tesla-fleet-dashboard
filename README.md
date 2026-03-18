# Tesla Fleet Telemetry Dashboard

Tesla Fleet Telemetry のストリーミングデータをリアルタイム表示するセルフホスト型ダッシュボード。

ポーリング API の **1/1500 のコスト** で運用できる。

![Architecture](https://img.shields.io/badge/architecture-Fleet_Telemetry_%E2%86%92_VPS_%E2%86%92_SSH_%E2%86%92_SQLite_%E2%86%92_Dashboard-blue)

## スクリーンショット

| 地図 + リアルタイム | トリップ詳細 |
|---|---|
| 走行経路を速度で色分け表示 | タップで個別経路をハイライト |
| バッテリー・温度・速度 | 緑=スタート、赤=ゴール |

## なぜ作ったか

Tesla Fleet API の `vehicle_data` エンドポイントをポーリングしていたら、**無料枠（月$10）を一晩で使い切った。**

| カテゴリ | リクエスト数 | 費用 |
|---|---|---|
| ストリーミング信号 | 1,725 | **¥1** |
| データ（ポーリング） | 5,204 | **¥1,508** |

同じ車両データなのに、取得方法で **1,500倍のコスト差** がある。

## アーキテクチャ

```
テスラ車 ──WebSocket/mTLS──→ VPS (Fleet Telemetry)
                                    │
                                journald
                                    │
                           SSH stream (ブリッジ)
                                    │
                               SQLite (自宅PC)
                                    │
                           FastAPI (port 8100)
                                    │
                              Tailscale / LAN
```

### なぜ自宅サーバーだけでは動かないか

Fleet Telemetry は車からの WebSocket 接続を受けるため、**パブリック IPv4 アドレス** が必要。

自宅回線が IPv4 over IPv6（MAP-E / DS-Lite）の場合、IPv4 アドレスを他ユーザーと共有しているため、任意ポートの開放ができない。ルーターにポートフォワーディングの設定項目自体が存在しないケースもある（I-O DATA WN-7T94XR で確認）。

IPv6 なら直接到達可能だが、テスラ車のセルラー回線（docomo/au）が IPv6 で接続してくる保証がない。

**解決策: Oracle Cloud Always Free の VPS を中継サーバーにする。**

- VM.Standard.E2.1.Micro（1 OCPU, 1GB RAM）— **永久無料**
- VPS で Fleet Telemetry を動かし、自宅 PC から SSH でログをストリーム
- 自宅 PC 側で SQLite に蓄積 → ダッシュボードで表示

## 必要なもの

- Tesla 車両（ファームウェア 2023.20+）
- Tesla Developer アカウント + Fleet API アプリ登録
- ドメイン（サブドメイン可）
- VPS（Oracle Cloud Free Tier 推奨）
- 自宅 PC（ダッシュボード + SQLite）
- Python 3.10+

## セットアップ

### 1. VPS に Fleet Telemetry をインストール

```bash
# Fleet Telemetry ビルド
git clone https://github.com/teslamotors/fleet-telemetry.git
cd fleet-telemetry
go build -o fleet-telemetry ./cmd/

# TLS 証明書（Let's Encrypt）
sudo certbot certonly --manual --preferred-challenges dns \
  -d telemetry.yourdomain.com --agree-tos
```

config.json:

```json
{
  "host": "",
  "port": 4443,
  "status_port": 8085,
  "log_level": "info",
  "json_log_enable": true,
  "namespace": "tesla",
  "tls": {
    "server_cert": "/path/to/server.crt",
    "server_key": "/path/to/server.key"
  },
  "records": {
    "V": ["logger"],
    "alerts": ["logger"],
    "errors": ["logger"],
    "connectivity": ["logger"]
  }
}
```

### 2. Tesla Developer 設定

1. 公開鍵を配置: `https://yourdomain.com/.well-known/appspecific/com.tesla.3p.public-key.pem`
2. バーチャルキーペアリング: `https://tesla.com/_ak/yourdomain.com`
3. Vehicle Command HTTP Proxy 経由でテレメトリ設定を送信

### 3. ダッシュボード（自宅 PC）

```bash
# クローン
git clone https://github.com/mii012345/tesla-fleet-dashboard.git
cd tesla-fleet-dashboard

# venv セットアップ
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn requests python-dotenv

# DB 初期化 & 過去データインポート
python3 import_history.py

# ブリッジ起動（VPS → SQLite）
./run_bridge.sh &

# ダッシュボード起動
./run_server.sh &
```

`http://localhost:8100` でアクセス。

### 4. 設定変更

`telemetry_bridge.py` の以下を環境に合わせて変更:

```python
VPS_HOST = "your-vps-ip"
SSH_KEY = "/path/to/ssh/key"
SSH_USER = "ubuntu"
```

## ファイル構成

```
├── server.py              # FastAPI ダッシュボード API
├── db.py                  # SQLite スキーマ & クエリ
├── telemetry_bridge.py    # VPS → SQLite ブリッジ（SSH stream）
├── import_history.py      # 過去ログ一括インポート
├── static/
│   └── index.html         # ダッシュボード UI（Leaflet + Chart.js）
├── run_bridge.sh           # ブリッジ起動スクリプト
├── run_server.sh           # サーバー起動スクリプト
└── *.service              # systemd ユニットファイル
```

## ダッシュボード機能

- **リアルタイム車両ステータス**: バッテリー、速度、車内/車外温度、走行距離
- **地図**: OpenStreetMap 上に走行経路を表示
- **速度ヒートマップ**: 走行速度で経路の色と透明度が変化
  - 🔵 ~20km/h（徐行）→ 🟢 ~40（市街地）→ 🟡 ~60（郊外）→ 🔴 60+（高速）
- **バッテリーチャート**: 24時間のバッテリー残量推移
- **トリップ履歴**: 日付・距離・消費電力・電費を一覧表示
  - 行タップで個別経路をハイライト（スタート🟢・ゴール🔴マーカー付き）
- **充電セッション**: 充電データの表示

## API エンドポイント

| エンドポイント | 説明 |
|---|---|
| `GET /` | ダッシュボード UI |
| `GET /api/latest` | 最新の車両データ |
| `GET /api/logs?since=24h` | 指定期間のログ |
| `GET /api/trips?since=7d` | トリップ検出結果 |
| `GET /api/charging` | 充電セッション |

## コスト

| 項目 | 月額 |
|---|---|
| Fleet Telemetry ストリーミング | **~¥10**（ほぼ無料） |
| Oracle Cloud VPS | **¥0**（Always Free） |
| ドメイン | 既存のものを使用 |
| **合計** | **~¥10** |

※ ポーリング API だと同等のデータ取得に月 ¥15,000+ かかる

## 注意事項

- Fleet Telemetry は Tesla ファームウェア 2023.20 以降が必要
- Let's Encrypt 証明書は 90 日で期限切れ。自動更新を設定すること
- VPS の Fleet Telemetry サーバーが再起動すると、車からの再接続に Vehicle Command Proxy 経由でテレメトリ設定の再送が必要な場合がある
- `telemetry_bridge.py` の SSH 接続が切れた場合は自動再接続する

## ライセンス

MIT
