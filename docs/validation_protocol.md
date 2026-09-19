# Протокол контрольных расчётов

Сформирован исполнением модели `2.0-analytics`: 2026-09-19T12:02:03.179955+00:00.
Исходные данные: `ed0bb86c74495bb7`; план: `deb759ce8ffae0180bba6ff9c6db1d2d3d896db2dc4fc78c7dced9d21fd98925`.

Воспроизведение: `python tools/build_contest_evidence.py`. Данные V01–V10 взяты из `validation/expected_checks.json`; номера и смысл организатора сохранены. E01–E15 — дополнительные проверки. Допуск: абсолютный 1e-7, относительный 1e-9. Это исполняемый протокол, не отдельный pytest-набор.

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

## Дополнительные интеграционные доказательства

- BASE и STRESS: шесть оптимизированных вариантов, независимый пересчёт суточным ядром; результаты `results/strategy_comparison.csv`.
- Расширение: `results/extended_plan_2042.json` содержит входы и полный результат оптимизации с F и восемью годами.
- Начальный запас закупается до открытия 2035, а расход относится к 2035 по раскрытой конвенции. Это не бесплатный запас и не второе списание CAPEX.
- Успех арифметических проверок не доказывает оптимальность инвестиций, достоверность исследовательских вероятностей или физическую реализуемость Mars-Cargo.
- Эталонные CSV/YAML не изменялись. При изменении модели данный документ и результаты нужно генерировать повторно.
