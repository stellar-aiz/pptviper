# PowerPoint 実機検証

この手順は #7 / #1 AC-15・AC-16 のためのものです。生成・比較ツールの
テスト合格は、PowerPoint 実機での受け入れ合格を意味しません。
Windows と macOS の実施者・OS・PowerPoint の版をそれぞれ記録してください。

## 準備と生成

リポジトリのルートから実行します。実行時ライブラリに追加依存はありません。
生成・レビュー補助は開発用 python-pptx / Pillow を使います。

```sh
uv sync --locked
uv run python -m scripts.acceptance generate /tmp/pptviper-uat
```

`calibration.pptx` は 36 スライド・216 テキスト図形です。
日本語・欧文・混在、6 フォント、太字・斜体・大文字・小型大文字・字間・
長い語・句読点・箇条書き・折り返し・AutoFit を含みます。
Arial / Calibri / Yu Gothic / Meiryo / Helvetica / Hiragino Sans のうち、
実際に存在するフォントと代替されたフォントを実施環境ごとに記録します。
全 OS で全フォントが存在するとは仮定しません。

`calibration.json` は固定の図形名・スライド番号・図形 ID と SHA-256 を持ちます。
ZIP の順序・日時、文書の日時を固定しており、同じ lockfile の環境で
2 回生成したバイト列が一致することをテストします。

`seeded.pptx` は 10 スライドです。各スライドのはみ出しと、5 スライドの
画像背景の文字を `seeded.json` に正解として記録します。
これは全 44 規則の網羅デッキではありません。規則単位の検証は既存の
自動テストが担当し、このデッキは実機レビュー経路と正解照合を確認します。

## 試験 1：行数と文字範囲

1. 対象 OS で `calibration.pptx` を PowerPoint で開きます。
2. VBA エディターで `scripts/acceptance/ExportCalibration.bas` を
   信頼するローカルのマクロ用プレゼンテーションにインポートします。
   実行時の `ActivePresentation` が較正デッキであることを確認します。
   較正デッキを再保存・編集せず、測定対象の SHA-256 を維持します。
3. `ExportCalibration` を実行し、新規 CSV の絶対パスを指定します。
   Windows / macOS の権限要求は実施者が確認します。
4. 最初に 1 行・複数行・折り返し・AutoFit の各図形を目視し、マクロの
   行数と範囲が実際の表示に対応することを確かめます。このマクロは
   両 OS で未検証です。エラー時の部分 CSV は破棄してください。
5. CSV を比較します。

```sh
uv run python -m scripts.acceptance compare \
  /tmp/pptviper-uat/calibration.pptx /tmp/pptviper-uat/calibration.json \
  /tmp/pptviper-uat/windows.csv /tmp/pptviper-uat/windows-comparison.json
```

macOS でも別の CSV / 比較 JSON を保存してください。検査側も同じ OS の
フォント環境で実行します。結果には図形ごとの行数・幅・高さの差を残します。
幅と高さは **文字の範囲**（余白を含まない）を pt で比較します。
見積もりから実測を引いた値が負なら失敗です。

マクロは Microsoft の
[Lines](https://learn.microsoft.com/en-us/office/vba/api/office.textrange2.lines)、
[Count](https://learn.microsoft.com/en-us/office/vba/api/office.textrange2.count)、
[BoundWidth](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.textrange2.boundwidth)、
[BoundHeight](https://learn.microsoft.com/en-us/office/vba/api/office.textrange2.boundheight)
を使用します。API の存在だけで実機互換性や計測精度を保証しません。

### マクロが動かない場合

各スライドを PNG へ書き出し、50 図形以上について行数を数えます。
文字範囲の幅・高さも画像上で測り、スライドの既知の pt 寸法で換算します。
アンチエイリアスや読み取り誤差を内側へ丸めず、測定方法と誤差を記録します。
図形名・ID は `calibration.json` を使います。
CSV の列は次のとおりです。小数点は `.`、単位は pt です。

```csv
name,slide,shape_id,lines,width_pt,height_pt
```

`compare` に `--mode manual` を加えます。50 件未満、重複、未知の ID、
欠落した寸法は拒否します。省略図形は結果の `omitted` に残り、
全 216 件を測定したとは扱いません。フォント・言語・AutoFit の偏りを
避けて対象を選び、選定理由も記録してください。

## 試験 2：見逃しと誤検出

生成デッキ 1 本と、**人が PowerPoint で通常どおり作成したデッキ 2 本**を
用意します。各 10 スライド以上とし、機密を含まない内容を使います。
生成デッキの複製は、人が作成したデッキの代替になりません。

1. PowerPoint で各デッキを開き、全スライドを PNG として書き出します。
   それぞれ専用ディレクトリに `1.png`、`2.png` … の名前で配置します。
2. 各デッキのレビュー HTML を作ります。

```sh
uv run python -m scripts.acceptance review \
  /tmp/pptviper-uat/seeded.pptx /tmp/pptviper-uat/seeded-images \
  /tmp/pptviper-uat/seeded-review.html --provenance generated
```

人が作ったデッキは `--provenance human` を使います。
HTML と隣接する `.report.json` を保存してください。HTML は画像を内包し、
ネットワーク不要で開けます。画像内容の機密性も HTML に引き継がれます。

3. HTML をブラウザーで開き、実施者・OS・PowerPoint の版を入力します。
   赤枠は指摘図形の推定範囲です。デッキ全体の指摘で図形を特定できない
   ものは、リストだけに表示されます。
4. 画像上の見逃した場所をクリックし、規則名と説明を記入します。
   規則にない問題は `other` と説明を記入します。
   誤検出は指摘のチェックボックスで記録します。
5. 画像背景の文字は `low-contrast` の判定不能に出ることが正解です。
   指摘にも判定不能にも無ければ、見逃しとして記録してください。
6. 全スライドを確認済みにし、全規則の確認観点をチェックします。
   機密確認を終えて JSON を保存します。途中保存と JSON 再読込も可能です。
   閉じる前に必ず保存してください。ブラウザーへの自動保存はありません。

次の manifest を実際のファイル名で作ります。全パスは manifest からの相対です。

```json
{
  "decks": [
    {"deck": "seeded.pptx", "report": "seeded-review.report.json",
     "review": "seeded-review.json", "images": "seeded-images",
     "provenance": "generated", "truth": "seeded.json"},
    {"deck": "human-a.pptx", "report": "human-a.report.json",
     "review": "human-a-review.json", "images": "human-a-images",
     "provenance": "human"},
    {"deck": "human-b.pptx", "report": "human-b.report.json",
     "review": "human-b-review.json", "images": "human-b-images",
     "provenance": "human"}
  ]
}
```

```sh
uv run python -m scripts.acceptance aggregate \
  /tmp/pptviper-uat/corpus.json /tmp/pptviper-uat/summary.json
```

見逃し 0、正解データの全件検出、必要な証跡が揃っている場合だけ合格です。
画像背景の正解は判定不能の有無で照合します。誤検出は規則別件数を残します。
人の判断の正しさや作成元の真偽までは自動検証できません。

## 証跡と未完了項目

- 試験 1：生成コマンド、lockfile / commit、デッキ SHA-256、実施者、
  OS・PowerPoint の版、フォント代替、マクロの事前確認、CSV、比較 JSON。
- 試験 2：デッキの作成者・作成手順、実施者、OS・PowerPoint の版、
  レビュー JSON、集計 JSON、画像、検査結果、デッキ SHA-256。
- 添付前に内容を確認します。生成デッキの画像だけを既定の添付対象とし、
  人が作成した資料は別途内容確認後に扱います。
- 失敗した図形や見逃しは Issue に記録し、修正後に再測定します。
- Windows/macOS 実機測定・人のレビュー・機密確認が終わるまで、
  #7 AC-4〜6 と #5/#6 の手動条件は未チェックのままです。

終了コードは 0 が合格、1 が比較・集計不合格、2 が証跡不備です。
`review` / `generate` の 0 は生成処理の成功だけを表します。
