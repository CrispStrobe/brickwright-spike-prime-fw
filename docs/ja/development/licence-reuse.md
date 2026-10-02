# ファームウェアのソース再利用

モーター制御、IMU 処理、デバイス通信には Pybricks 由来または参照した
コードを使用しています。MIT/BSD-3-Clause の再利用であり、クリーンルーム
実装とは主張しません。Pybricks、LEGO、David Lechner の原著作権表示を保持し、
`policy/pybricks-reuse.json` と `licenses/` に記録しています。

[追加の出所調査](../../project/source-origin-review.md) では、継承した Madgwick
実装の許諾根拠、過去の Git コミットに残る TI データ、修正済みの許諾文を
含まない旧公開ブランチが未解決と判明しました。現在の著作権表示とビルドの
入力検査に合格しても、これらの問題が解決したことにはなりません。

組み込み MicroPython と生成ヘッダーには別の固定インベントリがあります。
Stack Overflow を参照する整数幅計算は、記録済み BSD-3-Clause 実装に置換しました。
CI とビルドでハッシュ、ライセンス式、著作権表示とファイル構成を確認します。

Pybricks 自体は必須ではありませんが、削除には同等の制御、センサー検出、
IMU 処理の代替実装が必要です。MicroPython LEGO_HUB_NO6 は基盤として利用
できますが、標準構成には BTstack と TI 初期化データが含まれ、既存のロボット
API 全体は提供しません。移行には別途実装と実機検証が必要です。

TI サービスパックを取得して組み込む実機イメージには TI の制限が適用されます。
シミュレーション構成はこれを除外します。ソース一覧は全イメージの許諾確認ではありません。


構成済みのシミュレーションビルドの監査結果と再配布用の通知は
`policy/simulation-firmware-inputs.json` と
`licenses/Simulation-Firmware-NOTICES.txt` に記録されています。
対象の構成、ソースのハッシュ、コンパイラのランタイム、リンク時に選択された
アーカイブメンバーを検査します。入力を変更した場合は再確認が必要です。
GCC のランタイムは、明示された GCC Runtime Library Exception 付きの GPLv3
として記録されています。既定のビルドはシミュレーション用です。
