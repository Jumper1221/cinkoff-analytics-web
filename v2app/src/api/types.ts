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
