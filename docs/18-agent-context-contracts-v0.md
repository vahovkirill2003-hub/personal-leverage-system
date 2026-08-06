# Personal Leverage System
## Agent and Context Contracts v0

**Статус:** кандидат на пользовательскую приёмку (проверка по контуру `15` — раздел 10)  
**Дата:** 6 августа 2026  
**Основание:** архитектура `11-technical-architecture-v1.1.md` §§5–6, 12.2–12.3, 12.6; принятые `14 v0.1` и `17 v0`  
**Область:** контракты входа/выхода каждой роли, единый конверт structured result, правила сборки Context Packages, реестр и матрица разрешений client-side tools, контракт делегирования, конвейер валидации, eval-критерии ролей  
**За рамками:** тексты системных промптов, выбор конкретных моделей/провайдеров, изменение ролей и лимитов архитектуры §5.2, API-транспорт, код

---

## 0. Нормативный статус

Роли, их лимиты контекста, глубина делегирования и запреты нормативно заданы архитектурой §5.2 и не изменяются. Настоящий документ формализует **машинные контракты** обмена: что именно роль получает, что обязана вернуть и как результат проверяется до превращения в команду `17` §1.

## 1. Единый конверт structured result

Каждый результат любой роли — один JSON-объект конверта:

| Поле | Обязательность | Назначение |
|---|---|---|
| `schema_version`, `result_type` | всегда | Версионирование контракта; несоответствие → `FAILED_VALIDATION` без интерпретации |
| `case_id`, `input_revision_id`, `input_hashes` | всегда | Точная привязка к объекту работы; расхождение с Agent Run → отказ |
| `agent_run_ref`, `pass_ref` | всегда / для gate-passes | Причинность |
| `payload` | всегда | Типоспецифическое содержимое (раздел 2) |
| `provenance` | всегда | Для каждого содержательного утверждения — ссылка на canonical record / fact_record / evidence id либо явная пометка `assumption` |
| `assumptions`, `unresolved_items` | всегда (допустимо пусто) | Честная неполнота вместо молчаливой |
| `confidence` | всегда | Только качественная шкала `PLS-048`; числовые вероятности отклоняются валидатором без обоснованной модели |
| `rationale_brief` | всегда | Краткое основание; полный chain-of-thought не запрашивается и не хранится (§12.7) |

Запрещено в любом конверте: новые идентификаторы полномочий/записей, не существующие в БД; текст, помеченный `UNTRUSTED_CONTENT`, вне цитатных полей; инструкции системе.

## 2. Типы результата по ролям

| `result_type` | Роль | Ключевые поля payload | Детерминированный приёмник |
|---|---|---|---|
| `orchestration_proposal` | Orchestrator (optional call) | classified_intent; missing_inputs[]; proposed_next_command (из реестра `17` §1.2) | Workflow Orchestrator: команда исполняется только если допустима guards |
| `plan_proposal` | Planner | experiment_outline (цель, решающее неизвестное, действия); `chunk_manifest[]`: chunk_id, цель, input_refs, dependencies, acceptance_criteria, expected_evidence, budget; evidence_plan; risk_notes | Dossier validator: полнота против областей 3/9/11–16 |
| `chunk_result` | Worker | chunk_id; outputs[] c назначением в области; proposed_canonical_links; delta_summary | Merge validator: зависимости, stale inputs, конфликты, provenance |
| `subagent_result` | субагент | как `chunk_result` + parent_chunk_id | Только через принявшего Worker; автослияние запрещено |
| `verification_pass_result` | TR/SA pass | По каждой назначенной area/edge: element_id → outcome (`CHECKED_OK/FINDING/NOT_APPLICABLE/INCONCLUSIVE`) + criterion_ref + finding_drafts[] (class, severity, affected_refs, counterexample) | Coverage cells + immutable findings (`14` §3.4) |
| `synthesis_result` | TR/SA synthesis | consolidated_findings[] (только ссылки на зарегистрированные finding_ids + дедупликация/связи); gap_classification по `PLS-061`; result_recommendation из допустимого множества `05` | Coverage Validator: полнота представления всех finding_ids; затем Gate Engine |
| `technical_review_proposal` / `system_acceptance_proposal` | TR / SA | Итог synthesis + единый полный defect/gap list | Gate Engine: independence + допустимый result |

`NOT_APPLICABLE` в verification-результате обязан содержать `normative_basis_ref`; без него ячейка считается незаполненной.

## 3. Context Package: правила сборки

1. Только Context Builder собирает пакеты; роль не может дозапросить произвольные данные — только объявить `missing_inputs`, порождающие новую сборку.
2. Состав — по allowlist полей роли и задачи (§12.2); персональные данные включаются минимально необходимым подмножеством; redaction report сохраняется в manifest пакета.
3. `package_hash` фиксируется до вызова и попадает в Model Call и (для гейтов) в Gate Record.
4. Бюджеты §5.2 (4k/12k/16k/20k нормализованных токенов) считаются до вызова; превышение → `CONTEXT_BUDGET_EXCEEDED` и chunk-декомпозиция либо остановка run — молчаливое усечение обязательного содержания запрещено.
5. `UNTRUSTED_CONTENT` — отдельные data-блоки с provenance, никогда не конкатенируются с инструкциями роли (§12.3).
6. Verification-пакеты (TR/SA) собираются только из канона: worker rationale, черновики и чужие session-материалы не включаются.

## 4. Client-side tools: реестр и матрица

Реестр v1 (исчерпывающий; provider-hosted tools запрещены §12.6.8):

| Tool | Операция | Ограничения |
|---|---|---|
| `fetch_public_page` | GET разрешённого host | Host-allowlist по задаче; MIME text/html+pdf; лимиты размера/времени; результат → snapshot object + fact_record, метка `UNTRUSTED_CONTENT` |
| `read_dossier_record` | Чтение канонической записи по id | Только записи в scope пакета роли |
| `read_evidence_object` | Чтение объекта по artifact id | Только evidence текущего case; presigned GET короткого срока |
| `calculate` | Детерминированные вычисления | Без сети и side-effects |

Матрица: Orchestrator — только `read_dossier_record`; Planner — все read + `fetch_public_page`, `calculate`; Worker — все четыре; субагент — по manifest, подмножество Worker; TR/SA — `read_dossier_record`, `read_evidence_object`, `fetch_public_page` (только re-check уже заявленных источников), `calculate`; User Acceptor — не модельная роль, tools не применимы. Любой tool-вызов исполняется исключительно Tool & Fact Verification Gateway после argument/host/budget-проверок; tool proposal модели — только предложение.

## 5. Делегирование

Контракт субагента (единственная форма): pseudonymous case ref; цель подзадачи; минимальные input_refs; budget; acceptance_criteria; запреты; deadline; parent_run. Глубина 1, максимум 2 дочерних run, только по chunk_manifest. Передача consents, секретов, полного dossier и полномочий запрещена контрактно и проверяется redaction-контролем пакета.

## 6. Конвейер валидации результата

1. **Синтаксис:** JSON Schema конверта и payload; при отказе — один format repair (только сериализация, без новых findings/фактов).
2. **Контракт:** enum-поля из допустимых множеств; все refs существуют в БД и находятся в scope пакета; hashes совпадают.
3. **Домен:** запреты роли (§5.2 «Не вправе»); `PLS-048/049` шкалы; отсутствие новых идентификаторов полномочий; для synthesis — полнота finding_ids.
4. Итог: `VALIDATED` → результат допускается как вход команды `17`; иначе `FAILED_VALIDATION` с сохранением сырого результата как non-canonical proposal.

## 7. Eval-критерии ролей (обязательные до реализации гейтов на реальных моделях)

| Роль | Обязательные evals | Fixture-минимум |
|---|---|---|
| Planner | Полнота chunk_manifest против областей; отсутствие действий вне полномочий | Кейс с конфликтом приоритетов `PLS-011` |
| Worker | Provenance-дисциплина; честные unresolved | Пакет с заведомо отсутствующим фактом |
| TR | Обнаружение засеянных дефектов ≥ заданного порога; нулевая толерантность к пропуску cross-area противоречия, разнесённого по passes | Oversized-досье с ≥3 засеянными противоречиями (ADR-015) |
| SA | Корректная классификация запрещённых пробелов `PLS-061`; отказ принять запрещённую категорию | Fixture c пограничными gap-категориями |
| Все | Устойчивость к prompt injection во входных `UNTRUSTED_CONTENT`; отсутствие утечки redacted-полей в выводе | Injection- и minimization-fixtures §19.1 архитектуры |

Пороги evals — эксплуатационные настройки; их значения фиксируются в Verification Plan, а не здесь.

## 8. Traceability

Конверт/шкалы→`PLS-048/049`; provenance→`PLS-012/046`; verification-контракты→`PLS-026/027/061`, ADR-015; делегирование→§5.3 архитектуры; tools→`PLS-010/012`, §12.6; минимизация→`PLS-045/054`, §12.2.

## 9. Открытые пункты

Нет открытых решений Кирилла. Тексты промптов и модельный routing — вне scope, по §20.5 не входят в семь документов и появляются на реализации под eval-контролем раздела 7.

## 10. Changelog v0 (проверка по контуру `15`)

| Находка | Severity | Закрытие |
|---|---|---|
| ACV-1 — конверт не требовал `input_hashes`/`schema_version`, позволяя применить результат к смещённому входу | MINOR | §1: поля обязательны, расхождение → отказ |
| ACV-2 — verification-результат не обязывал `normative_basis_ref` для `NOT_APPLICABLE`, позволяя «пустую» ячейку под видом неприменимости | MINOR | §2: basis обязателен, иначе ячейка не заполнена |
| ACV-3 — eval-набор не содержал негативного теста на misclassification запрещённых пробелов `PLS-061` | MINOR | §7: обязательный SA-fixture с пограничными категориями |

---

*Документ не изменяет роли, лимиты и запреты архитектуры §5 и продуктовый baseline.*
