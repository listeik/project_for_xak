"""Generate measured, consistent contest evidence. Run from the repository root."""
from __future__ import annotations

from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.core.analytics import build_report
from app.core.balance_engine import default_plan
from app.core.configuration import extended_plan
from app.core.optimizer import optimize_supply_plan
from app.schemas.plan import PlanRequest


def dump(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def main():
    output=ROOT/"results"
    output.mkdir(exist_ok=True)
    plan=PlanRequest.model_validate(default_plan()).model_dump()
    report=build_report(plan)
    if not report["validation"]["passed"]:
        raise RuntimeError("Verification failed; no PASSED protocol may be published.")
    extended=optimize_supply_plan(PlanRequest.model_validate(extended_plan(plan)).model_dump())
    dump(output/"contest_report.json",report)
    dump(output/"validation_results.json",report["validation"])
    dump(output/"extended_plan_2042.json",extended)
    for scenario in ("base","stress"):
        for row in report["comparisons"][scenario]["rows"]:
            dump(output/f"{row['strategy_id']}_{scenario}_plan.json",row["plan"])
    for key in ("resilient_base_plan","resilient_stress_plan"):
        if key in report["comparisons"]["resilience"]:
            dump(output/f"{key}.json",report["comparisons"]["resilience"][key])
    fields=["scenario","strategy","npv","total_capex","min_service_level","min_critical_service_level","max_annual_shortage","total_shortage","cost_per_served_ton","feasible"]
    with (output/"strategy_comparison.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=fields)
        writer.writeheader()
        for scenario in ("base","stress"):
            for row in report["comparisons"][scenario]["rows"]:
                writer.writerow({"scenario":scenario,"strategy":row["name"],**{k:row["kpi"][k] for k in fields[2:]}})
    with (output/"risk_register.csv").open("w",encoding="utf-8-sig",newline="") as file:
        rows=report["risk_register"]["rows"]
        fields=["id","risk_name","cause","period","owner","impact_tons","impact_cost_mln","impact_service_level","mitigation_measure","mitigation_cost_mln","residual_shortage_t","measure_status"]
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({**{k:row[k] for k in fields if k in row},"residual_shortage_t":row["residual_risk"]["total_shortage"]})
    def cell(value):
        return json.dumps(value,ensure_ascii=False).replace("|","\\|")
    lines=["# Протокол контрольных расчётов", "", f"Сформирован исполнением модели `{report['model_version']}`: {report['generated_at']}.",
           f"Исходные данные: `{report['input_version']}`; план: `{report['plan_hash']}`.", "",
           "Воспроизведение: `python tools/build_contest_evidence.py`. Данные V01–V10 взяты из `validation/expected_checks.json`; номера и смысл организатора сохранены. E01–E15 — дополнительные проверки. Допуск: абсолютный 1e-7, относительный 1e-9. Это исполняемый протокол, не отдельный pytest-набор.","",
           "| ID | Входные данные | Ожидаемый результат | Фактический результат | Статус |", "|---|---|---|---|---|"]
    for row in report["validation"]["rows"]:
        lines.append("| "+" | ".join(cell(row[key]) for key in ("test_id","inputs","expected","actual","status"))+" |")
    lines.extend(["", "## Дополнительные интеграционные доказательства", "",
                  "- BASE и STRESS: шесть оптимизированных вариантов, независимый пересчёт суточным ядром; результаты `results/strategy_comparison.csv`.",
                  "- Расширение: `results/extended_plan_2042.json` содержит входы и полный результат оптимизации с F и восемью годами.",
                  "- Начальный запас закупается до открытия 2035, а расход относится к 2035 по раскрытой конвенции. Это не бесплатный запас и не второе списание CAPEX.",
                  "- Успех арифметических проверок не доказывает оптимальность инвестиций, достоверность исследовательских вероятностей или физическую реализуемость Mars-Cargo.",
                  "- Эталонные CSV/YAML не изменялись. При изменении модели данный документ и результаты нужно генерировать повторно."])
    (ROOT/"docs/validation_protocol.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    r=report["comparisons"]["resilience"]
    lines=["# Одностраничное резюме сравнения", "", f"Модель {report['model_version']}; данные {report['input_version']}; план {report['plan_hash'][:12]}.",
           "Все суммы — млн условных денежных единиц в постоянных ценах 2035; ставка 8%, затраты приведены к началу 2035. Сервис 100% является выбранной целью оптимизатора, более строгой, чем пороги BASE.", "",
           "| Стратегия | NPV BASE | NPV STRESS | CAPEX |", "|---|---:|---:|---:|"]
    for base,stress in zip(report["comparisons"]["base"]["rows"],report["comparisons"]["stress"]["rows"]):
        lines.append(f"| {base['name']} | {base['kpi']['npv']:.2f} | {stress['kpi']['npv']:.2f} | {base['kpi']['total_capex']:.0f} |")
    if r["status"]=="calculated":
        lines.extend(["",f"Самый дешёвый номинальный вариант среди трёх: {r['naive_strategy']}. При неизменных заказах он даёт {r['naive_stress_shortage_t']:.2f} т дефицита в обязательном стрессе.",
          f"Построена условная политика {r['resilient_strategy']}: NPV в BASE {r['resilient_base_npv']:.2f}; цена устойчивости {r['price_of_resilience_mln']:.2f}; предотвращённый дефицит {r['avoided_shortage_t']:.2f} т. Контракты, размещённые до 2038, общие для обоих вариантов; поздние заказы различаются при соблюдении lead time.",
          "Это минимум среди построенных пар, а не глобальный робастный оптимум. Цена предотвращённого срыва миссий не задана: денежный ущерб не выдумывается."])
    lines.extend(["", "Дефолтный пользовательский план отличается от оптимизированных шаблонов. Его границы до первого дефицита:"])
    for limit in report["crash_limits"]["limits"]:
        lines.append(f"- {limit['parameter']}: {limit['safe_value']} ({limit['status']}).")
    lines.extend(["", "Доказательства: `contest_report.json`, `validation_results.json`, сохранённые планы и сравнительный CSV в `results/`. Риски — сценарные, без назначенных вероятностей. Прогноз после 2040 и дополнительный источник — синтетическая проверка архитектуры."])
    (ROOT/"docs/scenario_summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Generated {len(report['validation']['rows'])} passing controls; report {report['plan_hash'][:12]}; extension feasible={extended['result']['feasible']}.")


if __name__=="__main__":
    main()
