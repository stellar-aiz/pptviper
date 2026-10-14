# pptviper

PPTX の見た目の問題を、描画せずに静的に検査する Python ライブラリと CLI です。
軽量・best effort を軸に、保存情報を優先し、不確実性を明示します。
仕様の正本は [Issue #1](https://github.com/stellar-aiz/pptviper/issues/1) です。

現在は開発基盤のみです。PPTX の検査機能は後続 Issue で実装します。

## 開発

Python 3.12 以上と uv が必要です。CI は Python 3.12・3.13・3.14 を
Linux・macOS・Windows の 9 組み合わせで検証します。

```sh
uv sync --locked
uv run pptviper --version
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
uv build
uv run python scripts/verify_dist.py
```

通常のテストは Python の socket 通信を遮断します。依存の取得・配布処理は別です。
実行時の依存はありません。開発時には python-pptx 等を使用します。

作業規約は [AGENTS.md](AGENTS.md)、公開手順は [配布手順](docs/publishing.md) を参照してください。
