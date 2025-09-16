# 支払い/おさいふ 機能 仕様メモ（現状とA案の方針）

本ドキュメントは、エンドユーザーの閲覧から収益の確定、出金申請、着金までの一連の流れと、関連テーブル/API/表示仕様を簡潔にまとめたものです。まず現状の仕様を整理し、その上で「昨日までを申請可能」にするA案の設計方針を示します。

## 1. 主要テーブルの役割（要点）

- `event_log`
  - 生イベント（view/click 等）を記録。日次集計のソース。

- `creator_daily`
  - JST基準で「昨日」のデータを毎日集計し確定保存。
  - 主な列: `pv`, `clicks`, `ctr`, `price_median`, `cpc_dynamic`, `ppv`, `ecmp`, `payout_day`（日次収益）。

- `creator_monthly`
  - 前月の `creator_daily` を集約した月次サマリ。

- `payout_ledger`
  - 「未払いの公式台帳」。現状は月単位の締めでレコード管理。
  - 列: `confirmed_amount`（確定額）, `paid_amount`（支払済み）, `unpaid_balance`（未払い残）, `status`。

- `withdrawals`
  - ユーザーの出金申請。金額と状態遷移（`requested`→`transferring`→`payout_pending`→`paid` 等）。

- `transfers`
  - Stripe Transfer（当社→クリエイターStripe口座）記録。`stripe_transfer_id`。

- `payouts`
  - Stripe Payout（Stripe口座→銀行口座）記録。`stripe_payout_id` と状態。

- `payout_transactions`
  - 着金済みの履歴（UI/履歴用ブリッジ）。Webhookで `paid` 確定時に記録。

- `ledger_entries`
  - 仕訳ログ（監査/証跡用途）。現状は `withdrawal_hold` などを記録。金額計算の主体は `withdrawals`/`payout_ledger`。

## 2. データの流れ（現状）

1) 閲覧発生 → `event_log` に保存。

2) 日次確定（昨日分） → バッチで `creator_daily` にUPSERT（`payout_day` に日次収益）。

3) 月次締め（前月分） → `creator_monthly` に集約 → `payout_ledger` を更新（前月の確定額/未払い残を反映）。

4) おさいふ表示
   - 「出金可能額（withdrawable）」＝「前月までの `payout_ledger.unpaid_balance` 合計 − 申請中（on-hold）」
   - 「今月の実績（推定収益）」＝ 当月の `creator_daily.payout_day` 合計（実質「昨日まで」）

5) 出金申請
   - `withdrawals` を作成（72h クールダウン、KYC チェック）。
   - `ledger_entries` に `withdrawal_hold` を記録（証跡）。

6) 送金/着金
   - バッチで Stripe Transfer を作成 → `transfers` 記録。
   - Stripe の自動 Payout 実行。Webhook `payout.paid` で `withdrawals` を `paid` に。併せて `payout_ledger` を古い月から順に消し込み、`payout_transactions` を記録。

## 3. API と UI（現状）

- `GET /api/wallet/summary`
  - withdrawable_balance: 前月までの未払い合計 − 申請中（on-hold）
  - this_month_estimated: 当月（昨日まで）の推定収益合計
  - payouts_enabled, minimum_payout_yen, on_hold 等

- `GET /api/wallet/current`
  - 今月の PV/クリック/推定収益（昨日まで合計）、代表的な `cpc_dynamic` など

- フロント `app/static/js/wallet-ui.js` が上記APIを取得してカード表示。

## 4. 変更方針（A案: 「昨日まで申請可能」への最小改修）

### 4.1 定義（表示＝申請可能額を一致）

同じ式で「おさいふ表示」と「申請上限」を算出する。

- 記号
  - `this_month` = 本日JSTの月初
  - `yesterday` = 本日JST − 1日

- 加算側
  - `unpaid_prev` = Σ `payout_ledger.unpaid_balance`（`month < this_month`）
  - `current_month_ytd` = Σ `creator_daily.payout_day`（`this_month ≤ day ≤ yesterday`）

- 控除側
  - `on_hold` = Σ `withdrawals.amount`（`status in ('requested','pending_review','approved','transferring','payout_pending')`）
  - `paid_this_month` = Σ `withdrawals.amount`（`status='paid'` かつ `paid_at` が当月内）

- 申請可能額（表示額）
  - `withdrawable_balance_now = max(unpaid_prev + current_month_ytd - on_hold - paid_this_month, 0)`

ポイント:
- これにより、「昨日までの当月分」も即申請対象に含まれる。
- 既に当月中に支払済みの分は控除され、二重計上を防ぐ。
- 前月分の支払いは `payout_ledger` に反映済みのため二重控除にはならない。

### 4.2 API 改修

- `GET /api/wallet/summary`
  - `withdrawable_balance` を上記式に変更
  - `as_of_date = yesterday`, `as_of_label = "昨日まで反映"` を返却

- `POST /api/me/withdrawals`
  - 上限算出を同じ式に揃え、表示額＝申請可能額を一致させる

### 4.3 Webhook/台帳の整合

- Webhook `payout.paid`
  - まず従来通り `payout_ledger`（過去月）を古い順に消し込み。
  - なお当月分については、`withdrawals.status='paid'` と `paid_at` を参照し、上式の `paid_this_month` 控除で自然に反映される（A案では専用の仕訳追加は不要）。

- 月次締め処理
  - 現状どおり `creator_daily` → `creator_monthly` → `payout_ledger` を更新。
  - 当月中に既払分がある場合は、翌月の締めに影響しない（A案では表示/上限は上式で制御）。

## 5. テーブルの役割（簡潔まとめ）

- 収益の確定/見える化: `creator_daily`（昨日まで）、`creator_monthly`（前月サマリ）
- 未払いの公式台帳: `payout_ledger`（現状は月単位）
- 申請〜着金フロー: `withdrawals`（申請）、`transfers`（Stripe Transfer）、`payouts`（Stripe Payout）、`payout_transactions`（履歴）
- 監査/証跡: `ledger_entries`（任意。現状は on-hold 記録など）

## 6. UI 文言（例）

- 金額カード: 「昨日までの実績を反映」「申請中の金額は差し引いて表示」
- ボタン活性: `withdrawable_balance_now >= minimum_payout_yen` かつ `payouts_enabled` かつ `on_hold == 0`

## 7. 今後の拡張メモ（任意）

- 日次台帳化（`payout_ledger_daily`）: モデルの直感性が上がるが変更範囲が大きい。A案完了後に再検討。
- 速報表示: 当日分の暫定（未確定）集計を別フィールドで返し、カードにラベルを付与。
- キャッシュ: 必要なら `wallet_balances` を導入（冪等キー/再計算戦略が必須）。


