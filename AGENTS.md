# 作業規約

## 仕様と言語

- 仕様の正本は https://github.com/stellar-aiz/pptviper/issues/1。
  規則 ID・挙動・受け入れ条件を変える前に Epic を更新する。
- 軽量・best effort、保存情報の優先、不確実性の明示を判断の軸とする。
- 文書・コメント・コミット・Issue・PR・エージェントのやり取りは日本語にする。
  API 識別子とライセンス原文はそのまま扱う。
- コミットは日本語の Conventional Commits。PR はスカッシュでマージする。

## ブランチと依存

- 実装はブランチから PR にする。main に直接コミットしない。
- 空 repo でリモートにブランチが無い初回だけ、ファイルを含まない初期コミットを
  main に作って push してよい。実装はすべてその上の PR で追加する。
- 実行時依存は MIT・BSD・Apache-2.0 等の許容的ライセンスに限る。
  copyleft のものは追加しない。追加する依存の名前・ライセンス・理由を PR に書く。
- uv.lock をコミットする。実行時依存と開発時依存を分ける。
- push 前に .gitignore が認証情報・環境変数ファイル・仮想環境を除外するか確認する。
- PR テンプレートの概要・手動検証・言語チェック・リスク・関連リンクを埋める。

## テスト

```sh
uv sync --locked
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
uv build
uv run python scripts/verify_dist.py
```

- 通常の pytest でテスト対象 Python プロセスの socket 通信を既定遮断する。
  通信遮断テストは遮断例外を期待して成功する。実ネットワークには接続しない。
- 依存取得・配布・CI 自身の通信は対象外。
  子プロセスやネイティブコードまでの OS 全体の通信遮断は保証しない。
- PPTX はテスト内で生成し、バイナリをコミットしない。
  実行時に生成できない場合だけ例外とし、作り方を添える。
- tests/pptx_factory.py の single_shape_pptx は位置・大きさを EMU 整数で受け取る。
  python-pptx は開発用に限る。
- replace_part で XML 等の既存 ZIP 部品を差し替え、None で削除する。
  truncate_zip で ZIP を切断する。特殊な構造の専用素材は必要な Issue で追加する。
- 公開は docs/publishing.md に従う。TestPyPI の実公開確認が残る Issue は、
  PR のマージだけで自動的に閉じない。
