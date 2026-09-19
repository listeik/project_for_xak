export type SourceId = string;
export type Scenario = 'BASE' | 'MANDATORY_STRESS';
export type DemandProfile = 'BASE' | 'LOW' | 'HIGH';
export type Orders = Record<SourceId, number>;
export interface Investments {
  zbo_year: number | null;
  option_c_year: number | null;
  exercise_c_year: number | null;
  isru_funding_year: number | null;
}
export interface Plan {
  plan_id: string;
  yearly_orders: Record<string, Orders>;
  yearly_reservations: Record<string, Partial<Orders>> | null;
  investments: Investments;
  scenario: Scenario;
  demand_profile: DemandProfile;
  initial_inventory_t: number;
  discount_rate: number;
  c_lead_months: number;
  d_lead_months: number;
  demand_factor: number;
  price_factor: number;
  reserve_target_days: number;
  research_config: { config_id: string; assumptions: string; extra_sources: Source[]; future_demand: {year:number}[] } | null;
  research_shock: {scenario_id:string; description:string; start_year:number; end_year:number; demand_factor:number; sources:Record<string,{price_factor:number; delivery_factor:number; delay_months:number; capacity_factor:number}>; combination_rule:'standalone'|'multiply_independent_effects'} | null;
  contract_lock: Record<string, unknown> | null;
}
export interface Source {
  source_id: SourceId;
  name: string;
  capacity_t_per_year: number;
  variable_cost_mln_per_t: number;
  reservation_rate_mln_per_t_year_capacity: number;
  take_or_pay_share: number;
  lead_time_min_value: number;
  lead_time_max_value: number;
  lead_time_unit: string;
}
export interface CaseData {
  years: number[];
  sources: Source[];
  input_version: string;
  units: Record<string, string>;
}
export interface SourceContract {
  ordered_t: number;
  delivered_t: number;
  price_per_t: number;
  reserved_capacity_t_per_year: number;
  available_capacity_t: number;
  delivery_share: number;
  active_days: number;
  lead_days: number;
  payable_volume_t: number;
  procurement: number;
  reservation: number;
  first_arrival_date?: string | null;
}
export interface AnnualBalance {
  year: number;
  start_inventory: number;
  inflow: number;
  losses: number;
  served_total: number;
  served_critical: number;
  end_inventory: number;
  shortage: number;
  has_shortage: boolean;
  critical_shortage: number;
  demand_total: number;
  demand_critical: number;
  reserve_required: number;
  service_level: number;
  critical_service_level: number;
  service_below_target: boolean;
  critical_service_below_target: boolean;
  storage_capacity: number;
  loss_rate: number;
  zbo_active: boolean;
  shortage_days: number;
  procurement: number;
  reservation: number;
  holding: number;
  fixed_opex: number;
  capex: number;
  opex: number;
  total_cost: number;
  npv: number;
  source_breakdown: Record<SourceId, SourceContract>;
}
export interface Violation {
  code: string;
  year: number | null;
  source: string | null;
  actual: number | null;
  limit: number | null;
  unit?: string;
  message: string;
}
export interface InventoryPoint {
  year: number;
  day: number;
  date: string;
  inventory: number;
  reserve: number;
  capacity: number;
  inflow: number;
  shortage: number;
}
export interface Calculation {
  plan_id: string;
  scenario: Scenario;
  scenario_id: string;
  demand_profile: DemandProfile;
  input_version: string;
  model_version: string;
  feasible: boolean;
  annual_balances: AnnualBalance[];
  kpi_summary: {
    npv: number;
    total_cost: number;
    cost_per_served_ton: number | null;
    discounted_cost_per_served_ton: number | null;
    max_annual_shortage: number;
    horizon_capex_limit: number;
    min_service_level: number;
    min_critical_service_level: number;
    total_capex: number;
    total_opex: number;
    capex_through_2037: number;
    capex_limit_2037: number;
    capex_limit_2040: number;
    total_shortage: number;
    end_inventory: number;
    violation_count: number;
    warning_count: number;
    has_shortage: boolean;
  };
  service_targets: { total: number; critical: number };
  violations: string[];
  violation_details: Violation[];
  warning_details: Violation[];
  inventory_trace: InventoryPoint[];
  source_schedule: Array<SourceContract & { source_id: SourceId; source_name: string; year: number; kind: string; first_order_date: string | null; first_arrival_date: string | null }>;
  financial_breakdown: { annual: AnnualBalance[] };
  assumptions: { research_factors_active: boolean; reserve_target_days: number; research_shock: Plan['research_shock'] };
}
export interface Optimization {
  status: string;
  npv_before: number;
  npv_after: number;
  savings: number;
  baseline_feasible: boolean;
  baseline_shortage_t: number;
  baseline_has_shortage: boolean;
  elapsed_seconds: number;
  explanation: string;
}
export interface OptimizedResponse { plan: Plan; result: Calculation; optimization: Optimization }
export interface Snapshot { plan: Plan; result: Calculation }
