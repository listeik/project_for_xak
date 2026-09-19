# Протокол контрольных расчётов

Сформирован исполнением модели `2.2-evidence`: 2026-09-19T17:29:54.959770+00:00.
Исходные данные: `ed0bb86c74495bb7`; план: `43c3f0ac1761eb0e589133a6fa16b9a095f39b08ef38d318c632d61ee922d1c1`.

Воспроизведение: `python tools/build_contest_evidence.py`. Данные V01–V10 взяты из `validation/expected_checks.json`; номера и смысл организатора сохранены. E01–E32 — дополнительные проверки, включая договорную доступность мощности, сроки C и общие земные сбои. Допуск: абсолютный 1e-7, относительный 1e-9. Это исполняемый протокол, не отдельный pytest-набор.

| ID | Входные данные | Ожидаемый результат | Фактический результат | Статус |
|---|---|---|---|---|
| "V01" | {"opening": 10, "delivered": 30, "losses": 2, "served": 25} | {"closing_inventory_t": 13} | {"closing_inventory_t": 13} | "PASSED" |
| "V02" | {"available": 8, "demand": 10} | {"served_t": 8, "shortage_t": 2, "closing_inventory_t": 0} | {"served_t": 8, "shortage_t": 2, "closing_inventory_t": 0.0} | "PASSED" |
| "V03" | {"order": 50, "reserved": 100, "TOP": 0.7, "price": 2} | {"payable_volume_t": 70, "variable_payment_mln": 140} | {"payable_volume_t": 70.0, "variable_payment_mln": 140.0} | "PASSED" |
| "V04" | {"same_as": "V03"} | {"variable_payment_mln": 140} | {"variable_payment_mln": 140.0} | "PASSED" |
| "V05" | {"annual_capacity": 100, "rate": 0.4, "period_fraction": 0.5} | {"reservation_payment_mln": 20} | {"reservation_payment_mln": 20.0} | "PASSED" |
| "V06" | {"gross": 20, "loss_rate": 0.05} | {"losses_t": 1} | {"losses_t": 1.0} | "PASSED" |
| "V07" | {"annual_demand": 365} | {"reserve_t": 45} | {"reserve_t": 45.0} | "PASSED" |
| "V08" | {"reserved": 12, "capacity": 10} | {"violation": "CAPACITY_EXCEEDED", "excess_t": 2} | {"violation": "CAPACITY_EXCEEDED", "excess_t": 2} | "PASSED" |
| "V09" | {"total_demand": 100, "critical_subset": 60} | {"total_demand_t": 100} | {"total_demand_t": 100} | "PASSED" |
| "V10" | {"planned": 20, "share": 0.5, "reliability_metadata": 0.8} | {"actual_delivery_t": 10} | {"actual_delivery_t": 10.0} | "PASSED" |
| "E01" | {"gross": 100, "loss_rates": [0.045, 0.012]} | {"base_losses": 4.5, "zbo_losses": 1.2} | {"base_losses": 4.5, "zbo_losses": 1.2} | "PASSED" |
| "E02" | {"capex_2037": 1800, "additional_2040": 1000} | {"violations": 0} | {"violations": 0} | "PASSED" |
| "E03" | {"capex_2037": 1801, "additional_2040": 1000} | {"violations": 2} | {"violations": 2} | "PASSED" |
| "E04" | {"D2038": 80, "D2039": 110, "scenario": "MANDATORY_STRESS"} | {"D2038": 44.0, "D2039": 82.5} | {"D2038": 44.0, "D2039": 82.5} | "PASSED" |
| "E05" | {"source": "D", "year": 2037} | {"active_days": 0} | {"active_days": 0} | "PASSED" |
| "E06" | {"net_startup_t": 15, "loss_rate": 0.045, "price": 6.2} | {"gross_t": 15.706806282722514, "procurement_mln": 97.38219895287959, "order_date": "2034-01-01", "accounting_year": 2035} | {"gross_t": 15.706806282722514, "procurement_mln": 97.38219895287959, "order_date": "2034-01-01", "accounting_year": 2035} | "PASSED" |
| "E07" | {"plan": "default BASE", "tolerance_t": 1e-07} | {"balance_closes": true, "feasible": true} | {"balance_closes": true, "feasible": true} | "PASSED" |
| "E08" | {"demand_profile": "LOW"} | {"total_demand": 1112.0} | {"total_demand": 1112.0} | "PASSED" |
| "E09" | {"demand_profile": "HIGH"} | {"total_demand": 1673.0} | {"total_demand": 1673.0} | "PASSED" |
| "E10" | {"A2035": -1} | {"rejected": true} | {"rejected": true} | "PASSED" |
| "E11" | {"demand_factor": 0} | {"cost_per_ton_is_null": true} | {"cost_per_ton_is_null": true} | "PASSED" |
| "E12" | {"scenario": "MANDATORY_STRESS", "zbo": false} | {"loss_limit_years": [2038, 2039, 2040]} | {"loss_limit_years": [2038, 2039, 2040]} | "PASSED" |
| "E13" | {"shock_year": 2038, "change_A2038": -1} | {"contract_change_rejected": true} | {"contract_change_rejected": true} | "PASSED" |
| "E14" | {"extra_source": "F", "last_year": 2042} | {"years": 8, "sources": 6, "balance_closes": true} | {"years": 8, "sources": 6, "balance_closes": true} | "PASSED" |
| "E15" | {"scenario": "MANDATORY_STRESS", "plan": "default"} | {"shortage_warnings": 3} | {"shortage_warnings": 3} | "PASSED" |
| "E16" | {"decision": "2038-01-01", "B_lead_months": 4, "E_lead_weeks": 6} | {"B_first": "2038-05-03", "B_days": 243, "E_first": "2038-02-12", "E_days": 323} | {"B_first": "2038-05-03", "B_days": 243, "E_first": "2038-02-12", "E_days": 323} | "PASSED" |
| "E17" | {"plan": "STRESS, advance B reservation 110 t/year from 2038", "baseline_B2038": 0} | {"full_recovery": true, "B_topup_positive": true, "critical_shortage": 0.0, "total_shortage": 0.0} | {"full_recovery": true, "B_topup_positive": true, "critical_shortage": 1.9184653865522705e-12, "total_shortage": 1.8189894035458565e-12} | "PASSED" |
| "E18" | {"decision": "2038-01-01", "policy": "preserve commitments"} | {"commitments_unchanged": true, "historical_stock_unchanged": true} | {"commitments_unchanged": true, "historical_stock_unchanged": true} | "PASSED" |
| "E19" | {"B_topup_t": 74, "B_window_days": 243, "capacity_t_per_year": 110} | {"rate_violation": true} | {"rate_violation": true} | "PASSED" |
| "E20" | {"A_order": 50, "A_topup": 10, "paid_annual_capacity": 100, "TOP": 0.7} | {"payable_t": 70.0, "new_reservation_mln": 0.0, "incremental_procurement_mln": 0.0} | {"payable_t": 70.0, "new_reservation_mln": 0.0, "incremental_procurement_mln": 0.0} | "PASSED" |
| "E21" | {"demand_factor_from_2038": 2, "B_delivery_from_2038": 0} | {"full_recovery": false, "avoided_shortage_positive": true, "residual_critical_positive": true, "reserve_violation_visible": true, "E_years": [2039, 2040]} | {"full_recovery": false, "avoided_shortage_positive": true, "residual_critical_positive": true, "reserve_violation_visible": true, "E_years": [2039, 2040]} | "PASSED" |
| "E22" | {"E_topup_each_year_2038_2040": 1} | {"streak_rejected": true} | {"streak_rejected": true} | "PASSED" |
| "E23" | {"plan": "adapted default", "discount_rate": 0.08} | {"daily_material_residual": 0.0, "npv_matches_annual_cash": true, "component_procurement_matches": true} | {"daily_material_residual": 4.284572696633404e-12, "npv_matches_annual_cash": true, "component_procurement_matches": true} | "PASSED" |
| "E24" | {"topups": ["negative", "before decision"]} | {"schema_rejections": [true, true]} | {"schema_rejections": [true, true]} | "PASSED" |
| "E25" | {"C_topup_in_shock_year": 1.0, "C_preparation_months": 24, "exercise_year": 2037} | {"unavailable_topup_flagged": true, "additional_delivered": 0.0} | {"unavailable_topup_flagged": true, "additional_delivered": 0.0} | "PASSED" |
| "E26" | {"CAPEX_through_2037": 1790, "limit": 1800} | {"headroom_mln": 10.0, "warning": true} | {"headroom_mln": 10.0, "warning": true} | "PASSED" |
| "E27" | {"B_booking": 0, "B_topup": 1, "policy": "booked_only"} | {"unsecured_flag": true} | {"unsecured_flag": true} | "PASSED" |
| "E28" | {"B_topup": 1, "policy": "conditional_market", "new_fraction": 1} | {"unsecured_flag": false} | {"unsecured_flag": false} | "PASSED" |
| "E29" | {"C_exercise": 2035, "preparation_months": 24, "delivery_months": 4} | {"commission": "2037-01-01", "topup_first": "2038-05-03"} | {"commission": "2037-01-01", "topup_first": "2038-05-03"} | "PASSED" |
| "E30" | {"common_earth_delivery": 0.5, "year": 2038, "D_independent": true} | {"A_delivered": 95.0, "D_delivered": 80.0, "scenario": "BASE"} | {"A_delivered": 95.0, "D_delivered": 80.0, "scenario": "BASE"} | "PASSED" |
| "E31" | {"plan": "default STRESS", "no_extra_booking": true} | {"full_recovery": false, "shortage_t": 147.828, "no_new_capacity": true} | {"full_recovery": false, "shortage_t": 147.82799999999838, "no_new_capacity": true} | "PASSED" |
| "E32" | {"A_rebooked": 40, "original_capacity": 100, "TOP": 0.7} | {"reserved_rate": 100.0, "payable_t": 70.0} | {"reserved_rate": 100.0, "payable_t": 70.0} | "PASSED" |

## Дополнительные интеграционные доказательства

- BASE и STRESS: шесть оптимизированных вариантов, независимый пересчёт суточным ядром; результаты `results/strategy_comparison.csv`.
- Реакция только в пределах брони: `results/adapted_stress_plan.json`; условный рынок: `results/conditional_stress_plan.json`. Варианты `results/decision_comparison.csv`; обоснование `results/policy_comparison.csv`. Подготовленная стратегия выбирается до шока.
- Расширение: `results/extended_plan_2042.json` содержит входы и полный результат оптимизации с F и восемью годами.
- Начальный запас закупается до открытия 2035, а расход относится к 2035 по раскрытой конвенции. Это не бесплатный запас и не второе списание CAPEX.
- Успех арифметических проверок не доказывает оптимальность инвестиций, достоверность исследовательских вероятностей или физическую реализуемость Mars-Cargo.
- Эталонные CSV/YAML не изменялись. При изменении модели данный документ и результаты нужно генерировать повторно.
