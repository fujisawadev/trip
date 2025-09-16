# おさいふ QA テストケース

対象: 昨日まで申請可能仕様（A案）、および関連UI/APIの整合

## 0. 前提/設定
- 最低出金額: `MIN_PAYOUT_YEN=3000`（必要に応じて1,000に変更可）
- JST基準。`creator_daily` は「昨日」分が日次確定。
- KYC/口座状態は `stripe_accounts` の `payouts_enabled` で判定。

## 1. サマリーAPI（/api/wallet/summary）
- 計算式: `withdrawable = unpaid_prev + current_month_ytd - on_hold - paid_this_month`
  - `unpaid_prev`: `payout_ledger.unpaid_balance`（< 当月月初）
  - `current_month_ytd`: `creator_daily.payout_day`（当月月初〜昨日）
  - `on_hold`: `withdrawals.amount`（status in requested/pending_review/approved/transferring/payout_pending）
  - `paid_this_month`: `payout_transactions.amount`（当月内の paid_at）
- 期待レスポンス項目:
  - `withdrawable_balance`（整数丸め）
  - `as_of_date`（昨日）/ `as_of_label`
  - `minimum_payout_yen`, `payouts_enabled`, `has_stripe_account`, `on_hold`

テスト:
- T1-1: 前月=12,000 / 当月=7,000 / on_hold=2,000 / paid_this_month=1,514 → 15,486
- T1-2: 当月YTD=0、その他0 → 0
- T1-3: on_hold > 合計時は0にクリップされる

## 2. おさいふカード（new_analytics.html + wallet-ui.js）
- 表示: 「もらえるお金」「(更新日時: M/D)」
- ボタン活性条件: `withdrawable >= MIN` かつ `payouts_enabled` かつ `on_hold==0`
- 非活性理由（中央揃え）
  - 最低額未達: 非表示
  - 最低額達成だが非活性: 「受取設定が未完了」/「処理中の出金申請があります」

テスト:
- T2-1: withdrawable=2,999 → ボタン非活性、理由非表示
- T2-2: 3,000＆KYC未完了 → 非活性、理由「受取設定未完了」
- T2-3: 3,000＆KYC済＆on_hold>0 → 非活性、理由「処理中…」
- T2-4: 3,000＆KYC済＆on_hold=0 → 活性、理由なし
- T2-5: as_of 表示が「昨日のM/D」になる

## 3. 出金申請API（POST /api/me/withdrawals）
- 上限算出はサマリーと同一式
- 3,000未満: 400 below_minimum
- KYC未完了: 409 payouts_not_enabled
- 受理: 202、`status=requested`（大型は pending_review）、72hクールダウン

テスト:
- T3-1: 最低額未達 → 400
- T3-2: KYC未完了 → 409
- T3-3: 正常 → 202、以降 on_hold に反映

## 4. 出金状況の履歴（/api/wallet/payouts + UI）
- API: `payout_transactions`（paid）＋ `withdrawals`（申請中系）を混在で返却
  - `type`: payout|withdrawal
  - 日付: payoutは`paid_at`、withdrawalは`requested_at`
  - `status`: paid or 各申請ステータス
- UI: タイトル「出金の履歴」。申請中の行にも日付が表示される

テスト:
- T4-1: 申請直後 → 履歴に「⏳ 申請中」、日付=requested_at
- T4-2: transferring/payout_pending → ステータス表示が適切
- T4-3: paid 到達 → 「✅ 着金済み」、日付=paid_at

## 5. 設定画面リンク制御（settings.html）
- 口座設定リンクの非活性条件: `withdrawable < MIN` かつ `has_stripe_account == false`
  - 初心者はまず3,000円到達まで非活性
  - 既に口座ありのユーザーは0円でも常に有効
- 案内文: 「まずは最低出金額（¥N）を達成してください。」

テスト:
- T5-1: 初心者（未達＆Stripe未作成）→ リンク非活性＋案内文
- T5-2: 未達でもStripe口座あり → リンク有効、案内文なし
- T5-3: 達成済 → リンク有効、案内文なし

## 6. 端数/丸め・境界
- 丸め: 表示は整数円（四捨五入）
- 昨日の日付境界（JST）: 0時台は「前日」までの反映
- 0円・負数クリップ・大量on_holdの挙動

テスト:
- T6-1: `paid_this_month` が小数を含む → 表示丸め整合
- T6-2: タイムゾーン跨ぎ直後に as_of が「昨日」
- T6-3: 合計−on_hold−paid_this_month < 0 → 0表示

## 7. 回帰
- 既存の「前月まで表示」時代の処理との互換（`payout_ledger` の更新・Webhook消し込み）
- 異常系：APIエラー時のUIフォールバック（0%表示、トースト）

---
実データ準備には `scripts/seed_wallet_demo.py` を使用（user_id=1向け）。必要に応じて金額・件数を調整してください。
