# caelestia-ai-usage

Claude と OpenAI（Codex）のサブスクリプション利用枠を Caelestia Shell のバーに表示する個人用ウィジェット。

```text
Claude Code / Codex CLI
        ↓  (各CLIが自分のログインで取得)
bin/ai-usage  (Python, 標準ライブラリのみ)
        ↓  --json
~/.cache/ai-usage/usage.json  (キャッシュ)
        ↓
shell/aiusage/AiUsage.qml  (Quickshell singleton)
        ↓
バー: AiUsageBar.qml  /  ポップアウト: AiUsagePopout.qml
```

## 取得方法

| プロバイダー | 取得元 | 枠 | 共有範囲（公式情報） |
| --- | --- | --- | --- |
| Claude | `claude -p --input-format stream-json` に `get_usage` 制御リクエストを送信 | 5h / Weekly（＋モデル別週間枠があれば別行） | claude.ai（Web/Desktop/Mobile）と Claude Code で共有 |
| OpenAI | `codex app-server` の JSON-RPC `account/rateLimits/read` | 5h / Weekly（`limitId` ごとに別枠） | Codex と ChatGPT Work で共有（`codex` 枠のみ） |

- どちらも **プロンプトを送らない** ので利用枠は消費しません。
- 認証は各CLIが自分で行います。このツールは `~/.claude/.credentials.json` や `~/.codex/auth.json` を読まず、トークンを外部に送ることもありません。
- 通常の ChatGPT チャットのモデル別メッセージ制限は対象外です（APIからも取得されません）。
- 取得できない値を推測で補ったり、別々の枠を合算したりはしません。

### リスクと代替案

- **Claude の `get_usage` は実験的 API** です。Agent SDK では `usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET` という名前で公開されており、Claude Code の更新で名前や形が変わる可能性があります。その知識は `ai_usage/claude.py` に閉じ込めています。
  - 代替案: statusline の JSON に含まれる `rate_limits`（公式に文書化済み）。ただしこれは対話型 TUI でしか動かず、Zed（ACP）経由で使っているこの環境では更新されないため採用していません。
  - 不採用: `api.anthropic.com/api/oauth/usage` に OAuth トークンを自分で付けて叩く方法。サブスクリプションの OAuth トークンを Claude Code 以外で使うことになり、利用規約に抵触するため使いません。
- **Codex の `app-server`** は CLI のヘルプで `[experimental]` と表示されていますが、IDE拡張や `/status` と同じ公式プロトコルです。スキーマは `codex app-server generate-json-schema` で確認できます。
- CLI はどちらも Zed の external agents 配下にしか入っていないため、`ai_usage/locate.py` で `$PATH` と Zed のパスの両方を探します。見つからない場合は `AI_USAGE_CLAUDE_BIN` / `AI_USAGE_CODEX_BIN` で指定できます。

## CLI

```sh
ai-usage                 # 人間向けの表示（ローカル時刻）
ai-usage --json          # 正規化されたJSON
ai-usage --json --max-age 240   # 240秒以内のキャッシュがあれば再取得しない
ai-usage --cached --json # キャッシュだけを表示（取得しない）
ai-usage --provider claude
ai-usage --mock partial_failure # mock/<シナリオ>/ の生データを使う（キャッシュは使わない）
```

一時的な失敗（timeout / error）の場合は2秒後に1回だけリトライします。同時実行は `usage.lock` で直列化されます。

### JSON 形式

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-23T07:35:00+00:00",
  "mode": "live",            // live | cache | mock
  "providers": [{
    "id": "claude",          // claude | openai
    "name": "Claude",
    "status": "ok",          // 下表
    "error": null,           // {"code": status, "message": "..."}
    "plan": "pro",
    "source": "claude-code:get_usage",
    "shared_scope": "Claude apps + Claude Code",
    "fetched_at": "...",     // データを実際に取得した時刻（stale の場合は前回成功時）
    "attempted_at": "...",   // 今回試行した時刻
    "stale": false,          // true = 今回失敗し、前回成功時のデータを表示中
    "windows": [{
      "id": "five_hour", "kind": "short",  // short (<=1日) | weekly
      "label": "5h", "scope": null,         // scope: モデル別枠などの区別
      "used_percent": 20.0,
      "resets_at": "2026-09-23T10:20:00+00:00",
      "window_minutes": 300
    }]
  }]
}
```

時刻はすべて UTC の ISO 8601 です。表示時にローカル時刻（Asia/Tokyo）へ変換します。

| status | 意味 |
| --- | --- |
| `ok` | 取得成功 |
| `auth_error` | CLI がログインしていない |
| `unsupported` | ログイン済みだがプラン枠が適用されない（APIキー利用など） |
| `not_installed` | CLI が見つからない |
| `timeout` | 応答なし（リトライ対象） |
| `error` | その他（プロトコル・解析・ネットワーク） |
| `not_fetched` | まだ一度も取得していない（キャッシュなし） |

失敗時は前回成功したデータを `stale: true` として引き継ぎます。リセット時刻を過ぎた枠は引き継ぎません。

## Caelestia への組み込み

Caelestia 2.4.0 のバーは項目が `Bar.qml` にハードコードされていて、拡張の仕組みがありません。そこで `/etc/xdg` のファイルは変更せず、**`~/.config/quickshell/caelestia` にオーバーレイを作ります**（Quickshell はユーザー側の設定を優先します）。

- ほぼすべてを `/etc/xdg/quickshell/caelestia` へのシンボリックリンクにします。パッケージ更新の内容はそのまま反映されます。
- 次の2ファイルだけ、パッケージ版のコピーに小さなパッチを当てます（`shell/patches/`）。
  - `modules/bar/Bar.qml`: import 1行、エントリ一覧に `aiUsage` を追加（時計の直前）、`DelegateChoice` を1つ追加、`checkPopout()` にホバー時の分岐を追加
  - `modules/bar/popouts/Content.qml`: import 1行、`Popout { name: "aiusage" }` を追加
- `aiusage/` はこのリポジトリの `shell/aiusage` へのリンクです。

```sh
./install.sh --restart            # オーバーレイを作成し、~/.local/bin/ai-usage をリンクして再起動
./install.sh --uninstall --restart # 元のパッケージ版に戻す
```

この環境では Hyprland の autostart（dotfiles の `hypr/.config/hypr/lua/autostart.lua`）が、ログインのたびに `install.sh` を実行してから `caelestia shell -d` を起動します。そのため、パッケージを更新しても次のログインで自動的に追従します。ログインせずにシェルだけ再起動するときは、`caelestia shell -k` ではなく `./install.sh --restart` を使ってください。

**caelestia-shell を更新したら `./install.sh --restart` を再実行してください**（上の autostart を使っていない場合）。 パッチを当てた2ファイルはコピーなので、再実行しないと古い版のままになります。パッチが当たらなくなった場合はエラーで止まり、既存のオーバーレイは変更されません。

> `caelestia shell -k` は起動時と同じパスでインスタンスを探します。そのため、パッケージ版とオーバーレイ版を切り替えるときは旧インスタンスを止められません。`--restart` を付けると両方のパスで停止し、プロセスが終了するのを待ってから起動します（`caelestia shell -d` は重複起動を禁止しているため、待たずに起動すると何も起きません）。

## ウィジェット

- **バー**（時計の上）: プロバイダーごとに二重リングを表示します。外側が短期枠（5h）、内側が週間枠、中央の数字が短期枠の%です。上が Claude（primary 色）、下が OpenAI（tertiary 色）です。
  - どちらかの枠が90%以上 → error 色
  - stale → 半透明
  - 未ログイン → 🔑 に斜線のアイコン、その他の失敗 → ⚠
- **ホバーでポップアウト**: ネットワークやトレイと同じく、バーの項目にカーソルを乗せると左からポップアウトが出ます。ポップアウトの中へカーソルを移しても閉じないので、更新ボタンも押せます。内容は全ての枠のプログレスバー、リセットまでの残り時間とリセット時刻、共有範囲、プラン、エラー内容、最終更新時刻、更新ボタンを表示します。
- 5分ごとに `--max-age 240` で取得します。失敗時は60秒→120秒→…→5分の間隔でリトライします（未ログインの場合はリトライしません）。
- カウントダウンは Caelestia の `Time` サービス（1秒刻み）から計算し、CLI は呼びません。リセット時刻を過ぎた枠は「Reset at … — waiting for update」と表示します。

### モックでのプレビュー

実行中のシェルとは別に、フローティングウィンドウでプレビューできます。

```sh
./preview.sh                                   # 実データ
AI_USAGE_MOCK=partial_failure ./preview.sh     # normal / auth_error / partial_failure / unsupported
AI_USAGE_BIN=/nonexistent ./preview.sh         # フェッチャー起動失敗の表示
```

本体のシェルで `AI_USAGE_MOCK` を設定しても同じように動作します。

## 公開時の注意

- キャッシュ（`~/.cache/ai-usage/`）とオーバーレイ（`~/.config/quickshell/caelestia`）はリポジトリの外に作られます。取得した実データや認証情報はリポジトリに入りません。
- `mock/` のデータは架空の値です（アカウントIDなどは含みません）。
- `shell/patches/` は [caelestia-dots/shell](https://github.com/caelestia-dots/shell)（GPL-3.0）のコードの一部を含み、QML も同プロジェクトのコンポーネントを利用しています。

## テスト

```sh
python3 -m unittest discover -s tests
```

正規化、枠を統合しないこと、未知キーの無視、ステータスの区別、stale の引き継ぎ、期限切れ枠の破棄、キャッシュ再利用を検証します。

## ファイル構成

```text
bin/ai-usage              CLI ランチャー
ai_usage/
  cli.py                  引数・キャッシュ・リトライ・出力
  model.py                正規化形式とステータス定義
  jsonl.py                CLI と stdio JSONL でやり取りする共通処理
  claude.py               Claude Code get_usage（実験的API。変更時はここだけ直す）
  codex.py                Codex app-server account/rateLimits/read
  locate.py               CLI バイナリの探索
mock/<scenario>/          生レスポンスのモック（{"__error__": …} で失敗を再現）
tests/test_fetcher.py
shell/aiusage/            QML（AiUsage サービス / バー項目 / ポップアウト）
shell/patches/            Bar.qml・Content.qml へのパッチ
shell/preview/shell.qml   プレビュー用
install.sh / preview.sh
```
