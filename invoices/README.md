# Export Invoices — EXCELLENT AUTO SALES AND LEASING → CARSHOP WORLD IN MIND

`EX_INV_TO_CARSHOP81009.xlsx` をひな形として作成した 10 件のインボイスです。
書式（フォント・罫線・列幅・印刷範囲 `$A$1:$F$39`・`Total = SUM(F24:F38)`）は元ファイルと同一です。

| ファイル | Invoice # / P.O. | Date | 車両 | Total |
|---|---|---|---|---|
| EX_INV_TO_CARSHOP81010.xlsx | 81010 | 5/10/2021 | 2018 TOYOTA TACOMA TRD OFF ROAD | $27,850.00 |
| EX_INV_TO_CARSHOP81011.xlsx | 81011 | 5/14/2021 | 2020 FORD F-150 XLT SUPERCREW | $34,200.00 |
| EX_INV_TO_CARSHOP81012.xlsx | 81012 | 5/19/2021 | 2017 JEEP WRANGLER UNLIMITED SPORT / 2016 SUBARU OUTBACK 3.6R LIMITED | $40,550.00 |
| EX_INV_TO_CARSHOP81013.xlsx | 81013 | 5/24/2021 | 2019 RAM 1500 BIG HORN | $31,750.00 |
| EX_INV_TO_CARSHOP81014.xlsx | 81014 | 5/28/2021 | 2016 CHEVY CORVETTE STINGRAY | $42,900.00 |
| EX_INV_TO_CARSHOP81015.xlsx | 81015 | 6/2/2021 | 2018 NISSAN FRONTIER SV CREW CAB | $19,450.00 |
| EX_INV_TO_CARSHOP81016.xlsx | 81016 | 6/8/2021 | 2015 FORD MUSTANG GT PREMIUM | $23,300.00 |
| EX_INV_TO_CARSHOP81017.xlsx | 81017 | 6/15/2021 | 2019 GMC SIERRA 1500 SLT / 2018 HONDA CR-V EX-L AWD | $51,450.00 |
| EX_INV_TO_CARSHOP81018.xlsx | 81018 | 6/21/2021 | 2020 TOYOTA 4RUNNER SR5 4WD | $36,800.00 |
| EX_INV_TO_CARSHOP81019.xlsx | 81019 | 6/28/2021 | 2014 CHEVY CAMARO SS COUPE | $21,200.00 |

## 書き換える箇所

| セル | 内容 |
|---|---|
| `E7` | Date |
| `F7` | Invoice # |
| `D22` | P.O. NO. |
| `A24` / `B24` / `E24` / `F24` | 数量 / 車種 / 単価 / 金額（1台目） |
| `B25` / `B26` | VIN / 色（1台目） |
| `A28`–`F30`, `A32`–`F34` | 2台目・3台目（同じ並び） |
| `F39` | `=SUM(F24:F38)` ＝ 自動計算。触らないこと |

シート名は `INV-<請求番号>`、印刷範囲もそれに合わせてあります。

## 注意

- 車種・VIN・色・金額はすべて **サンプルデータ** です。実際の車両情報に差し替えてください。
- 元ファイルの非表示シート `Sheet2` / `Sheet3` に入っていた個人の入出金メモは、
  取引先に送るファイルなので削除してあります（シート自体は非表示のまま残しています）。
