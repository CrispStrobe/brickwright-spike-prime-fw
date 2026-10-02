# SPIKE Prime Hub NuttX プロジェクト

SPIKE Prime Hub 上で NuttX RTOS を動作させる環境を構築するプロジェクト。

## Quick Start

### ビルド

```bash
make
```

### フラッシュ (DFU)

```bash
brew install dfu-util  # 初回のみ
```

1. Hub の USB を抜く
2. Bluetooth ボタンを押したまま USB 接続、5秒待って離す（DFU モード）
3. 書き込み (`usbnsh` 既定構成は BUILD_PROTECTED なので kernel + user の 2 段書き込み):

この派生版はシミュレーション専用のため、書き込みコマンドは意図的に掲載していません。
リポジトリ直下の `SAFETY.md` を参照してください。

### シリアル接続

```bash
picocom /dev/tty.usbmodem01
```

## ハードウェア仕様

| 項目 | スペック |
|------|---------|
| MCU | STM32F413VG (ARM Cortex-M4, 96MHz) |
| Flash | 1 MB (992KB available, 32KB bootloader) |
| RAM | 320 KB (SRAM1 256KB + SRAM2 64KB) |

## Benchmark

### CoreMark

| Board | MCU | CoreMark Score | CoreMark/MHz |
|-------|-----|---------------|-------------|
| SPIKE Prime Hub | STM32F413VG (96MHz) | 171.19 | 1.78 |
| B-L4S5I-IOT01A | STM32L4R5VI (80MHz) | 143.16 | 1.79 |
