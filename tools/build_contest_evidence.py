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


def main(report=None):
    output=ROOT/"results"
    output.mkdir(exist_ok=True)
    plan=PlanRequest.model_validate(default_plan()).model_dump()
    if report is None:
        report=build_report(plan)
    if not report["validation"]["passed"]:
        raise RuntimeError("Verification failed; no PASSED protocol may be published.")
    extended=optimize_supply_plan(PlanRequest.model_validate(extended_plan(plan)).model_dump())
    dump(output/"contest_report.json",report)
    dump(output/"validation_results.json",report["validation"])
    dump(output/"extended_plan_2042.json",extended)
    if report["stress_impact"]["conditional_adaptation"]:
        dump(output/"conditional_stress_plan.json",report["stress_impact"]["conditional_adaptation"]["plan"])
    decision=report["comparisons"]["decision_case"]
    recommendation=decision["recommendation"]
    if recommendation["status"]=="calculated":
        dump(output/"recommended_plan.json",recommendation["plan"])
        recommended_row=next(r for r in decision["rows"] if r["strategy_id"]==recommendation["strategy_id"])
        for scenario in ("mandatory","common_earth"):
            if recommended_row[scenario]["plan"]:
                dump(output/f"recommended_{scenario}_plan.json",recommended_row[scenario]["plan"])
    with (output/"policy_comparison.csv").open("w",encoding="utf-8-sig",newline="") as file:
        fields=["strategy","base_npv","mandatory_full_recovery","common_total_shortage","common_critical_shortage","common_min_critical_service","common_feasible","error"]
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for row in decision["rows"]:
            common=row["common_earth"]["after"] or {}
            writer.writerow({"strategy":row["name"],"base_npv":row["base"]["npv"],"mandatory_full_recovery":row["mandatory"]["full_recovery"],
                "common_total_shortage":common.get("total_shortage"),"common_critical_shortage":common.get("total_critical_shortage"),
                "common_min_critical_service":common.get("min_critical_service_level"),"common_feasible":common.get("feasible"),
                "error":row["common_earth"]["error"] or row["mandatory"]["error"]})
    if report["stress_impact"]["adaptation"]:
        dump(output/"adapted_stress_plan.json",report["stress_impact"]["adaptation"]["plan"])
        actions=report["stress_impact"]["adaptation"]["actions"]
        with (output/"response_actions.csv").open("w",encoding="utf-8-sig",newline="") as file:
            writer=csv.DictWriter(file,fieldnames=["kind","year","source","before_t","ordered_t","delivered_t","first_order_date","first_arrival_date","procurement_mln","reservation_mln"])
            writer.writeheader();writer.writerows(actions)
    with (output/"decision_comparison.csv").open("w",encoding="utf-8-sig",newline="") as file:
        fields=["variant","npv","min_service_level","min_critical_service_level","total_shortage","total_critical_shortage","feasible"]
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for row in report["decision_comparison"]["rows"]:
            writer.writerow({"variant":row["name"],**{k:row["kpi"][k] for k in fields[1:]}})
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
           "Воспроизведение: `python tools/build_contest_evidence.py`. Данные V01–V10 взяты из `validation/expected_checks.json`; номера и смысл организатора сохранены. E01–E32 — дополнительные проверки, включая договорную доступность мощности, сроки C и общие земные сбои. Допуск: абсолютный 1e-7, относительный 1e-9. Это исполняемый протокол, не отдельный pytest-набор.","",
           "| ID | Входные данные | Ожидаемый результат | Фактический результат | Статус |", "|---|---|---|---|---|"]
    for row in report["validation"]["rows"]:
        lines.append("| "+" | ".join(cell(row[key]) for key in ("test_id","inputs","expected","actual","status"))+" |")
    lines.extend(["", "## Дополнительные интеграционные доказательства", "",
                  "- BASE и STRESS: шесть оптимизированных вариантов, независимый пересчёт суточным ядром; результаты `results/strategy_comparison.csv`.",
                  "- Реакция только в пределах брони: `results/adapted_stress_plan.json`; условный рынок: `results/conditional_stress_plan.json`. Варианты `results/decision_comparison.csv`; обоснование `results/policy_comparison.csv`. Подготовленная стратегия выбирается до шока.",
                  "- Расширение: `results/extended_plan_2042.json` содержит входы и полный результат оптимизации с F и восемью годами.",
                  "- Начальный запас закупается до открытия 2035, а расход относится к 2035 по раскрытой конвенции. Это не бесплатный запас и не второе списание CAPEX.",
                  "- Успех арифметических проверок не доказывает оптимальность инвестиций, достоверность исследовательских вероятностей или физическую реализуемость Mars-Cargo.",
                  "- Эталонные CSV/YAML не изменялись. При изменении модели данный документ и результаты нужно генерировать повторно."])
    (ROOT/"docs/validation_protocol.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    r=report["comparisons"]["resilience"]
    lines=["# Одностраничное резюме сравнения", "", f"Модель {report['model_version']}; данные {report['input_version']}; план {report['plan_hash'][:12]}.",
           "Все суммы — млн условных денежных единиц в постоянных ценах 2035; ставка 8%, затраты приведены к началу 2035. Сервис 100% является выбранной целью оптимизатора, более строгой, чем пороги BASE.", "",
           "В первой таблице закупки оптимизированы отдельно с предварительным знанием каждого сценария. Это сравнение инвестиционных шаблонов; реакция исходного плана и обоснование рекомендации показаны отдельно ниже.", "",
           "| Стратегия | NPV BASE | NPV STRESS | CAPEX |", "|---|---:|---:|---:|"]
    for base,stress in zip(report["comparisons"]["base"]["rows"],report["comparisons"]["stress"]["rows"]):
        lines.append(f"| {base['name']} | {base['kpi']['npv']:.2f} | {stress['kpi']['npv']:.2f} | {base['kpi']['total_capex']:.0f} |")
    if r["status"]=="calculated":
        lines.extend(["",f"Самый дешёвый номинальный вариант среди трёх: {r['naive_strategy']}. При неизменных заказах он даёт {r['naive_stress_shortage_t']:.2f} т дефицита в обязательном стрессе.",
          f"Построена условная политика {r['resilient_strategy']}: NPV в BASE {r['resilient_base_npv']:.2f}; доплата за подготовку {r['price_of_resilience_mln']:.2f}; предотвращённый дефицит {r['avoided_shortage_t']:.2f} т. Полная стоимость в STRESS {r['resilient_stress_npv']:.2f}: реакция не бесплатна. Контракты, размещённые до 2038, общие для обоих вариантов; поздние заказы и дозаказы различаются при соблюдении lead time.",
          "Это минимум среди трёх номинальных шаблонов и вариантов с физическим буфером +50% при неизменном нормативе резерва и предварительной бронью B 110 т/год с 2038; не глобальный робастный оптимум. Цена срыва миссий не задана."])
    lines.extend(["", "## Исходный план и реакция", "", "| Вариант | NPV, млн | Дефицит, т | Критический дефицит, т |", "|---|---:|---:|---:|"])
    for row in report["decision_comparison"]["rows"]:
        k=row["kpi"]
        lines.append(f"| {row['name']} | {k['npv']:.2f} | {k['total_shortage']:.2f} | {k['total_critical_shortage']:.2f} |")
    lines.append("Подготовленная стратегия может менять инвестиции и ранние решения. Её нельзя применить задним числом вместо реакции исходного плана.")
    tradeoff=report["service_tradeoff"]
    if tradeoff["status"]=="calculated":
        lines.append(f"При фиксированных исходных инвестициях минимальные годовые требования BASE 97%/99% стоят {tradeoff['minimum_service']['kpi']['npv']:.2f} млн NPV; 100% обслуживания — {tradeoff['full_service']['kpi']['npv']:.2f}. Доплата {tradeoff['premium_for_full_service_mln']:.2f} млн. Это раскрывает цену запаса по сервису, а не доказывает предпочтительность любой цели.")
    lines.extend(["", "Дефолтный пользовательский план отличается от оптимизированных шаблонов. Его границы до первого дефицита:"])
    for limit in report["crash_limits"]["limits"]:
        lines.append(f"- {limit['parameter']}: {limit['safe_value']} ({limit['status']}).")
    if recommendation["status"]=="calculated":
        def n(value):
            return f"{value:,.2f}".replace(","," ").replace(".",",")
        lines.extend(["", "## Выбор с учётом общего земного сбоя", "",
            f"Рекомендуемый кандидат — **{recommendation['name']}**: по отношению к «{recommendation['cost_reference_name']}» доплата BASE {n(recommendation['premium_base_mln'])} млн NPV, сокращение дефицита общего земного сбоя {n(recommendation['avoided_common_shortage_t'])} т. Остаток {n(recommendation['common_earth']['total_shortage'])} т; критический {n(recommendation['common_earth']['total_critical_shortage'])} т. Формальные ограничения общего сбоя: {'выполнены' if recommendation['common_earth']['feasible'] else 'есть нарушения'}.",
            "Общий сбой A/B/C/E до 50% в 2038–2039 и независимость D — допущения команды. Это отдельный сценарий. Рекомендация среди проверенных кандидатов условна; основание выбора и полные стоимости — в [decision_brief.md](decision_brief.md)."])
    lines.extend(["", "Доказательства: `contest_report.json`, `validation_results.json`, сохранённые планы и сравнительный CSV в `results/`. Риски — сценарные, без назначенных вероятностей. Прогноз после 2040 и дополнительный источник — синтетическая проверка архитектуры."])
    (ROOT/"docs/scenario_summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    write_decision_brief(report)
    print(f"Generated {len(report['validation']['rows'])} passing controls; report {report['plan_hash'][:12]}; extension feasible={extended['result']['feasible']}.")


def write_decision_brief(report):
    study=report["comparisons"]["decision_case"];choice=study["recommendation"]
    def n(value):
        return f"{value:,.2f}".replace(","," ").replace(".",",")
    lines=["# Обоснование решения для защиты", "",f"Модель {report['model_version']}; данные {report['input_version']}; план {report['plan_hash']}. Все деньги — млн условных единиц 2035, NPV к началу 2035.","",
           "## Управленческое решение",""]
    if choice["status"]=="calculated":
        lines.extend([f"Рекомендуемый кандидат: **{choice['name']}**. {choice['rule']}","",
            f"По отношению к «{choice['cost_reference_name']}» доплата в BASE составляет **{n(choice['premium_base_mln'])} млн NPV**. В общем земном сбое это сокращает дефицит на **{n(choice['avoided_common_shortage_t'])} т**, из них критический — на **{n(choice['avoided_common_critical_t'])} т**.","",
            f"Стоимость: BASE {n(choice['base']['npv'])}; обязательный STRESS после реакции {n(choice['mandatory']['npv'])}; общий земной сбой {n(choice['common_earth']['npv'])}. При дефиците меньшая стоимость не означает равноценную экономию.","",
            f"Остаток в общем земном сбое: дефицит {n(choice['common_earth']['total_shortage'])} т, критический {n(choice['common_earth']['total_critical_shortage'])} т; минимальный критический сервис {n(choice['common_earth']['min_critical_service_level']*100)}%. Формальные ограничения: {'выполнены' if choice['common_earth']['feasible'] else 'есть нарушения; см. сохранённый расчёт'}. Полная защита от всех сбоев не заявляется.","",choice["limits"],""])
        if choice["unverified_candidates"]:
            lines.append("Не подтверждены решателем и исключены из ранжирования общего сбоя: "+", ".join(choice["unverified_candidates"])+".")
    else:
        lines.append(choice["message"])
    lines.extend(["## Сравнение альтернатив", "",study["preparation"],"", "| Кандидат | NPV BASE | Полное восстановление STRESS | Общий сбой: дефицит / критический, т |", "|---|---:|---|---:|"])
    for row in study["rows"]:
        common=row["common_earth"]["after"]
        value=f"{n(common['total_shortage'])} / {n(common['total_critical_shortage'])}" if common else "Не подтверждено"
        lines.append(f"| {row['name']} | {n(row['base']['npv'])} | {'Да' if row['mandatory']['full_recovery'] else 'Нет / не подтверждено'} | {value} |")
    lines.extend(["", "## Сценарий, триггер и действие", "",
        "- До 2038: утвердить инвестиции, физический буфер и рамочные договоры мощности, включая B. Оплата мощности учитывается даже при нулевой закупке. Крупные CAPEX и сроки ввода не меняются задним числом.",
        "- 1 января 2038, обязательный шок: подтвердить рост спроса и фактическую долю D, активировать доступную бронь. Первый приход B — не раньше 3 мая; до него нужен физический запас и исходные поставки. Точные объёмы/даты находятся в действиях сохранённого STRESS-плана.",
        "- Общий земной сбой: отдельно ограничить A/B/C/E до 50% в 2038–2039. Проверить физическую доступность D; бронирование земной мощности само по себе не устраняет общий отказ.",
        "- Если поставщик предлагает новый контракт: проверить подтверждённый объём и срок, рассчитать условный вариант отдельно. Свободная номинальная мощность не является подтверждением договора.",
        "- При оставшемся дефиците: зафиксировать неудовлетворённый спрос и нарушения резерва, уведомить владельцев миссий о потребности пересогласовать программу. Перенос миссий и его стоимость в текущем расчёте не моделируются.", "", "## Факты и допущения", ""])
    for item in report["evidence_register"]:
        source=f"[Первоисточник]({item['source']})" if item["source"].startswith("https://") else item["source"]
        lines.extend([f"**{item['id']} — {item['kind']}: {item['title']}.** {item['claim']} Основание: {source}. Граница: {item['limitation']}",""])
    lines.extend(["## Когда менять рекомендацию", "",
        "Если договорная бронь недоступна, ввод D задержан, общий земной сбой затрагивает D либо срок доставки C отличается от принятого — пересчитать все альтернативы. Сценарная рекомендация не является прогнозом или минимумом ожидаемых затрат: вероятности не заданы.","",
        "Проверяемость: [протокол](validation_protocol.md), [сценарное резюме](scenario_summary.md), `results/contest_report.json`, `results/policy_comparison.csv`, рекомендуемые планы. Исходные CASE_INPUT не менялись. Краткая заметка не заменяет финальную конкурсную записку 8–12 страниц."])
    (ROOT/"docs/decision_brief.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
