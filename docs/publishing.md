# 配布手順

## 管理者による初期設定

1. PyPI と TestPyPI で配布名 pptviper の利用可否と管理権限を確認する。
2. 各サービスの Trusted Publisher に次を登録する。新規プロジェクトは
   Pending Publisher を利用する。

| 設定 | 本番 PyPI | TestPyPI |
|---|---|---|
| 所有者 | stellar-aiz | stellar-aiz |
| リポジトリ | pptviper | pptviper |
| ワークフロー | publish.yml | publish.yml |
| 環境名 | pypi | testpypi |

3. GitHub の Environments に pypi と testpypi を作る。
   本番環境はリリースタグ、検証環境は main からの公開に使用する。
   API トークンは保存しない。

## TestPyPI での受け入れ検証

コードの main へのマージと公開先設定が済んだ後、GitHub Actions の「配布」を
main を選択して手動実行する。別ブランチを選択しても公開処理は動かない。

```sh
gh workflow run publish.yml --ref main
```

公開成功後、独立環境でその版を取得する。初期版は 0.1.0。

```sh
uv venv /tmp/pptviper-testpypi
uv pip install --python /tmp/pptviper-testpypi/bin/python --no-deps   --index-url https://test.pypi.org/simple/ pptviper==0.1.0
/tmp/pptviper-testpypi/bin/pptviper --version
```

Windows では仮想環境を任意の一時ディレクトリに作り、bin/python と bin/pptviper を
Scripts/python.exe と Scripts/pptviper.exe に読み替える。
実行時依存がないため、追加のパッケージ索引は必要ない。

公開したコミット・版・Actions の実行 URL・インストール結果を Issue #2 に記録する。
AC-3 が未検証の間は Issue を閉じない。管理者設定が不足している場合は、
不足内容を記録する。手順の存在だけでは AC-3 を合格にしない。
同じ版は再アップロードできないため、内容を変えて再公開する場合は版を更新する。

## 本番への公開

pyproject.toml の版を更新する PR をマージした後、一致する vX.Y.Z タグを push する。
タグの形式と版の一致を公開前に検証する。不一致・通常のブランチ更新・PR・手動実行では
本番へ公開しない。公開先での設定は本番と TestPyPI で別々に必要。
本番公開は Issue #2 の受け入れ検証には含めない。

- [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [uv による配布](https://docs.astral.sh/uv/guides/publish/)
