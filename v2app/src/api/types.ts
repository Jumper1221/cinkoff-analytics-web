// Типы ответов бэка (ручные, строго по факту; проверены curl'ом 24.09.2026)
export interface Kpi {
  orders_today: number; orders_30d: number; sum_30d: number; shipped_30: number; avg_30: number
}
export interface MonthlyRow { year: number; month: number; cnt: number; total: number; done_cnt: number }
export interface StatusRow { status: string; cnt: number }
export interface TopItem { name: string; units: number; revenue: number }
export interface TopContractor { name: string; orders: number; revenue: number }
export interface Freshness { last_order: string; total: number; total_orders: number }
export interface LeadRow { label: string; median_days: number; p90_days: number; shipped: number }
export interface CancelRow { label: string; orders: number; canceled: number; pct: number }
export interface StaleRow {
  order_id: number; number: string; order_date: string; order_status: string
  contractor_name: string; branch_name: string; sum: number; age_days: number
}
export interface CompareRow {
  orders: number; revenue: number; avg_check: number; canceled: number; label: string; kind: string
  prev_orders?: number; prev_revenue?: number; d_orders?: number; d_revenue?: number
  p_orders?: number; p_revenue?: number
}
export interface YearRow { year: number; cnt: number; revenue: number; avg_check: number; done_cnt: number }
export interface OrdersPage { items: OrderRow[]; total: number }
export interface OrderRow {
  id: number; order_id: number; number: string; order_date: string; order_status: string
  contractor_name: string; branch_name: string; sum: number
}

// ── R2-эндпоинты ──
export interface AbcRow { name: string; revenue: number; units: number; share_pct: number; cum_share_pct: number; abc: 'A' | 'B' | 'C' }
export interface RemRow { nomenclature_id: string; full_name: string | null; storage_id: string; branch: string; qty: number; delivery_date: string | null; snapshot_date: string }
export interface RemDates { dates: string[] }
export interface RemHistPoint { date: string; qty: number; items: number }
export interface RemHist { dates: string[]; series: Record<string, RemHistPoint[]> }
export interface CatalogHit { id_1c: string; full_name: string; group_name?: string }
export interface PricePoint { branch_id_1c?: string; branch: string; price: number; discount_pct?: number; discount_price: number; version_date?: string }
export interface CardInfo { id_1c: string; full_name: string; color?: string; thickness?: string; surface?: string; [k: string]: unknown }
export interface ForecastRow { id_1c: string; name: string; spent: number; rate_day: number; stock: number; days_left: number; orders_cnt: number; flag: 'crit' | 'warn' | 'ok' }
export interface PairRow { a_name: string; b_name: string; cnt: number }
export interface CohortsResp {
  new_by_month: { month: string; newcnt: number }[]
  active_by_month: { month: string; active_branches: number; orders_cnt: number }[]
  retention: { month: string; branches_this_m: number; returned_next3: number }[]
  top_branches: { branch: string; orders_cnt: number; revenue: number }[]
}
export interface HeatmapResp { years: number[]; matrix: Record<string, number[]> }
export interface BranchRow { id_1c: string; name: string; address: string; [k: string]: unknown }
