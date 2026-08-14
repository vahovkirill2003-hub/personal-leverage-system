# Personal Leverage System
## State/Gate/Authority Technical Specification v0.2

**Статус:** кандидат на пользовательскую приёмку; не принят. До приёмки действует `17-state-gate-authority-tech-spec-v0.1.md`  
**Дата:** 14 августа 2026  
**Основание:** принятая для стадии реализации `17-state-gate-authority-tech-spec-v0.1.md`; кандидат `03-state-machine-v2.1.md` (§9.1 routing policy, продуктовое решение `PLS-068`); решения `PLS-069`–`PLS-072` журнала стадии `26 v0.1`  
**Область:** формальные application commands, модель вычисления guards, транзакционный протокол переходов, протоколы Gate Engine и Consent/Authority Engine, lifecycle административного `diagnostic hold` (закрытие `AAR-R2`, часть 1 из 2), инварианты и обязательные тестовые классы  
**За рамками:** изменение baseline, перечня состояний/статусов/guards (принадлежит `03`), критериев гейтов (принадлежит `05`), API-транспорта, промптов, кода  
**Добавлено в v0.2:** RuleCatalog как исполнимая форма таблиц `03`, application-инвариант `SM-APP-01` и распределение тестовых классов T01, T02, T20 по задачам

---

## 0. Нормативный статус

Перечни состояний, событий, статусов и guards `G01–G28` нормативно принадлежат `03-state-machine-v2.md` §6 и не дублируются здесь во избежание расхождения копий: настоящая спецификация ссылается на них по идентификаторам и определяет **технический способ исполнения**. Критерии и допустимые результаты гейтов принадлежат `05-gates-v2.md`. Конфликт настоящего текста с ними — дефект спецификации.

## 1. Application Commands

### 1.1. Общий контракт команды

Каждая команда: typed payload по схеме; `actor` (user/system/timer/admin); `idempotency_key` по реестру `14` §4; `expected_case_version` (обязателен для всех команд, изменяющих projection); ссылки только на существующие записи (валидация до исполнения). Текст модели никогда не является командой: модельный результат становится командой только после доменной валидации детерминированным кодом (§4 архитектуры).

### 1.2. Реестр команд

| Команда | Actor | Предусловия (сверх guards `03`) | Производит |
|---|---|---|---|
| `SubmitOpportunity` | Кирилл | Нет активного slot-конфликта | case, event, вход в INTAKE |
| `ProvideClarification` / `ProvideFact` | Кирилл | Открытый запрос | event, fact_record |
| `DismissPreExperiment` | system/Кирилл | `G27`; полная административная запись `PLS-063` | `pre_experiment_dismissal`, event; slot освобождается; продуктовый статус не создаётся |
| `PublishRevision` | system (Revision Manager) | Merge validator пройден | dossier_revision (immutable), event |
| `OpenGateAttempt` | system (Gate Engine) | Порядок TR→SA→UA (`05` §2); exact revision | gate_attempt, gate_review_session (TR/SA) |
| `RecordPassFindings` | system (Agent Runtime) | Открытая session; pass из Coverage Plan | finding*, coverage_cell updates |
| `SubmitGateProposal` | system | Coverage Validator `COMPLETE`; independence checks §6.1 архитектуры | — (вход для `CommitGateRecord`) |
| `CommitGateRecord` | system (Gate Engine) | Ровно один на attempt; допустимый result своего gate_type | gate_record, defect*, event, transition при применимости |
| `IssueDecisionIntent` | system | Decision-момент `05`/`PLS-055`+; exact revision+hash | decision_intent, outbox(decision) |
| `ConsumeDecisionIntent` | Кирилл (callback) | Все guards §8.3 архитектуры; CAS pending→consumed | consent / gate_record(UA) / grant / event |
| `GrantAuthority` / `RequestExpense` | system→Кирилл | Consent exact-bound; expense-поля полны | authority_grant / expense |
| `RecordExternalAction` | Кирилл | Активный grant; contract полон | external_action(факт), evidence links |
| `RecordEvidence` / `RecordAttestation` | Кирилл/system | Объект загружен и верифицирован либо полная аттестация `PLS-052` | evidence |
| `RecordConditionOutcome` | system/Кирилл | condition_record существует; для stop — `PLS-032` поля | review_stop_record, event, transition |
| `OpenCycleReview` / `ResolveCycleReview` | system→Кирилл | Триггер `PLS-062` | cycle_review_record |
| `CompleteClosure` | system | `G16` и guards закрытия | closure, event, transition |
| `CommitDecisionUpdate` | Кирилл | `G17/G18/G23/G24` по применимости | decision_update, terminal transition |
| `RegisterLateEvidence` | Кирилл/system | `G26`; терминальный case | late_evidence; **никаких** изменений case |
| `CreateLinkedCase` | Кирилл | Границы `PLS-053` | новый case; отсутствие копирования scopes |
| `FireTimer` | scheduler | claim по lease; firing_idempotency_key | event по kind таймера |
| `EnterDiagnosticHold` / `ExitDiagnosticHold` | system(recovery)/admin | Раздел 5 | hold-поля case, event, outbox(informational) |
| `ConfirmRestoreResume` | Кирилл | Divergence report предъявлен | событие `RESTORE_RESUME_CONFIRMED` (`14` §10.3) |
| `EnterTransportMaintenance` / `ExitTransportMaintenance` | admin | Процедура `19` §1.4; pending outbox сохраняется, logical ids неизменны | событие maintenance, пауза/возобновление выпуска Decision messages |
| `SupersedePendingIntents` | admin/system(restore) | Основание: restore (`14` §10.3), ротация (`19` §1.4) либо инцидент (`21` §5); обязательный reason | массовый перевод `pending`→`superseded` + события; перевыпуск отдельными `IssueDecisionIntent` |

**Дополнение v0.2: доменные команды правил, не имевшие командного пути в v0.1.** Реестр v0.1 покрывал полномочия, гейты, время и администрирование, но часть правил `03` (завершение подготовительных стадий, маршрутизация возвратов, разрешение эскалации и review condition, нагрузка, паузы, внешнее ожидание) командного пути не имела. Ниже — 16 команд, закрывающих этот разрыв; полное покрытие 78/78 доказывается таблицей §1.5.

| Команда | Actor | Предусловия (сверх guards `03`) | Производит |
|---|---|---|---|
| `CompleteStage` | system | Стадия соответствует текущему состоянию; guard стадии `G01`–`G04` | event, переход к следующей подготовительной стадии |
| `SkipPlannedAction` | Кирилл/system | Действие входит в принятый план; причина и влияние на сигнал зафиксированы | event `PLANNED_ACTION_SKIPPED`, переход в `EVIDENCE_COLLECTION` |
| `RouteRework` | system | Состояние `REWORK_REQUIRED`; ближайший источник вычислен по записи дефекта | event, переход к вычисленному источнику (multi-target, §1.3) |
| `RouteRevalidation` | system | Состояние `REVALIDATION_REQUIRED`; источник изменения вычислен по записи изменения | event, переход к вычисленному источнику (multi-target, §1.3) |
| `DetectMaterialChange` | system | Изменение входит в перечень `03` §15; при сомнении — презумпция материальности | event `MATERIAL_CHANGE_DETECTED`, переход в `REVALIDATION_REQUIRED`, аннулирование применимости прежних гейтов |
| `ResolveEscalation` | Кирилл | Состояние `TECHNICAL_REVIEW_ESCALATION`; выбран один из допустимых путей; «принять дефект как есть» отклоняется командой | event, переход в `REWORK_REQUIRED` либо `EXPERIMENT_CLOSURE` |
| `ReclassifyDefect` | system (роль reviewer) | Обоснование ревьюера; запрещённые категории `PLS-061` исключены; independence §6.1 архитектуры | event `REVIEWER_RECLASSIFIED_GAP`, переход в `TECHNICAL_REVIEW` |
| `ResumeFromPause` | system/Кирилл | `G14_FRESHNESS_CHECKED`; зафиксированное состояние возврата существует | event, переход к состоянию возврата либо в `DECISION_UPDATE` |
| `RecordRelevanceOutcome` | Кирилл/system | Потеря либо подтверждение актуальности; после входа в Planning цель вычисляется по `03 v2.1` §9.1 (`PLS-068`) | event `RELEVANCE_LOST`/`RELEVANCE_CONFIRMED`, переход к вычисленной цели либо административный disposition до Planning |
| `StartExternalWait` | system | Зависимость, контрольный срок и ожидаемое доказательство определены | event, переход в `PAUSED_EXTERNAL`, timer контрольного срока |
| `RecordExternalResponse` | Кирилл/system | Ответ относится к текущему эксперименту; абсолютный deadline не достигнут | event, связь свидетельства, переход в `EVIDENCE_COLLECTION` |
| `GrantAdditionalTime` | Кирилл | Приостановленное подготовительное состояние; указан конкретный объём времени | time_grant, event `ADDITIONAL_TIME_APPROVED` (§1.4), новый контрольный момент |
| `NarrowScopeOrAddData` | Кирилл | Приостановленное подготовительное состояние; материальность определена | event, переход в `REWORK_REQUIRED` либо `REVALIDATION_REQUIRED` (multi-target, §1.3) |
| `CloseCaseByUser` | Кирилл | Вход в Experiment Planning состоялся; решение явно зафиксировано | event, переход в `EXPERIMENT_CLOSURE` |
| `RecordWorkloadOutcome` | system/Кирилл | Workload ledger ISO-недели; при одобрении превышения изменение материально | event, переход в `EXECUTION` (приостановка), `EVIDENCE_COLLECTION` либо `REVALIDATION_REQUIRED` |
| `BlockUnapprovedExpense` | system | `G10_EXPENSE_AUTHORIZED` не выполнен | event `UNAPPROVED_EXPENSE_DETECTED`, блокировка расхода и связанного действия; состояние не меняется |

Итого реестр v0.2: **40 команд** (24 из v0.1 без изменений + 16 новых). Команды, отсутствующие в реестре, не существуют: незарегистрированный путь записи — дефект реализации.

### 1.3. RuleCatalog

RuleCatalog — исполнимая форма таблиц `03`, а не новый нормативный источник: он не добавляет, не удаляет и не переформулирует ни одного правила. Нормативным первоисточником остаётся `03` (до приёмки `03 v2.1` — `03-state-machine-v2.md`); расхождение каталога с `03` — дефект реализации каталога.

**Состав: ровно 78 правил.** Каталог строится детерминированным разбором таблиц `03` с шестью колонками и покрывает их полностью:

| Источник в `03` | Правил |
|---|---:|
| §7 Разрешённые переходы: основной контур | 27 |
| §8 Действия, возвраты и повторные гейты | 21 |
| §9 Ожидания, таймауты и актуальность | 16 |
| §10.1 Подготовка | 6 |
| §10.2 Нагрузка и расходы | 4 |
| §10.3 Необратимый предел | 2 |
| §16.1 Поздний внешний ответ | 2 |
| **Итого RuleCatalog** | **78** |

Таблица §11 «Запрещённые и опасные переходы» (12 строк) правилами каталога не является: это отрицательные утверждения, каждое из которых закрывается тестом T20. Полный разбор таблиц `03` даёт 90 строк = 78 правил каталога + 12 запретов.

**Outcome kinds.** Каждое правило каталога имеет ровно один вид исхода:

| Outcome kind | Правил | Смысл | Пример |
|---|---:|---|---|
| `STATE_TRANSITION` | 59 | Смена состояния кейса | §7 `DOSSIER_READY` → `TECHNICAL_REVIEW` |
| `SELF_TRANSITION` | 10 | Событие и обязательные записи без смены состояния | §10.1 `PREPARATION_LIMIT_REACHED` («то же состояние; подготовка приостановлена») |
| `ADMINISTRATIVE_DISPOSITION` | 7 | Завершение административной обработки входа до Experiment Planning; продуктовый статус и новое состояние не создаются (`PLS-063`) | §7 `INTAKE` + `G27` |
| `TERMINAL_ANNOTATION` | 1 | Запись late evidence к терминальному кейсу без смены состояния и без пересчёта зачёта (`G26`, `PLS-038`) | §16.1, строка 1 |
| `LINKED_CASE_CREATION` | 1 | Создание нового связанного кейса; старый кейс не изменяется (`PLS-053`) | §16.1, строка 2 |

Обязательные атрибуты правила: идентификатор `R01`–`R78`; ссылка на раздел и строку `03`; множество исходных состояний; событие или условие; перечень guards; outcome kind; целевое состояние или множество целей; обязательные записи; признак необходимости подтверждения Кирилла.

**Multi-target правила.** Правило, называющее более одной цели, остаётся одним правилом с обязательным предикатом маршрутизации по `03 v2.1` §9.1: цель вычисляется по авторитетным записям кейса, никогда не принимается от вызывающей стороны (`caller-supplied target`), а вычисленная цель, значение предиката и прочитанные записи входят в обязательные записи перехода. Расхождение предложенной и вычисленной цели — отказ команды без частичных эффектов (§8).

**Верификация каталога.** Полнота 78/78 и отсутствие правил вне `03` проверяются T01; отклонение недокументированных переходов — T01 и T20.


### 1.4. TriggerRegistry — закрытый тип входных событий

Правило каталога запускается **триггером**. Множество триггеров закрыто и содержит 65 идентификаторов: `execute_trigger` (§3) принимает только идентификатор из настоящего реестра, любой другой вход отклоняется до чтения состояния. Прозаические формулировки столбца «Событие» в `03` получают технические идентификаторы; продуктовых событий они не создают и `03` §4 не изменяют.

| Класс триггера | Количество | Состав |
|---|---:|---|
| Каталог событий `03 v2.1` §4 | 52 | полный перечень продуктовых событий |
| − journal-only события | −5 | `EXTERNAL_ACTION_REQUESTED`, `PACKAGE_BOUNDARY_REACHED`, `NON_MATERIAL_CHANGE_RECORDED`, `RELEVANCE_CONFIRMED`, `LATE_EVIDENCE_RECORDED` — правил не запускают (`03 v2.1` §4) |
| = продуктовые события, используемые правилами | 47 | каждое связано минимум с одним правилом |
| + разделение `DECISION_DEFERRED` по стороне ожидания | +1 | `DECISION_DEFERRED_BY_USER`, `DECISION_DEFERRED_BY_EXTERNAL` — оба отображаются в продуктовое событие `DECISION_DEFERRED` |
| + технические триггеры прозаических правил | +17 | перечислены ниже |
| **Итого закрытый тип** | **65** | 52 − 5 + 1 + 17 |

`ADDITIONAL_TIME_APPROVED` входит в 52 события каталога и отдельным слагаемым не добавляется.

Технические триггеры прозаических правил:

| Правило | Триггер | Формулировка `03` |
|---|---|---|
| R28 | `TR_ACTION_WITHIN_PACKAGE` | Действие внутри бесплатного пакета |
| R29 | `TR_ACTION_OUTSIDE_PACKAGE_AUTHORIZED` | Действие вне пакета, но без материального изменения |
| R38 | `TR_REWORK_ROUTED` | Дефект маршрутизирован |
| R40 | `TR_REVALIDATION_ROUTED` | Изменение маршрутизировано |
| R41 | `TR_ESCALATION_RESOLUTION_CHOSEN` | Кирилл выбирает исправление/сужение/данные/ресурс |
| R43 | `TR_ESCALATION_CLOSURE_CHOSEN` | Кирилл выбирает Closure |
| R44 | `TR_REVIEW_CONTINUE_UNCHANGED` | Продолжить без материального изменения |
| R46 | `TR_REVIEW_REPLAN_MATERIAL` | Материально перепланировать |
| R47 | `TR_REVIEW_CLOSE_STOP_OR_INCONCLUSIVE` | Закрыть stop/inconclusive |
| R48 | `TR_UNRECORDED_EVIDENCE_FOUND` | Найдено незарегистрированное доступное свидетельство |
| R52 | `TR_USER_RESPONSE_RECEIVED` | Ответ получен |
| R61 | `TR_DEFERRED_CONDITION_MET` | Условие наступило |
| R68 | `TR_SCOPE_NARROWED_OR_DATA_ADDED` | Scope сужен или получены новые данные |
| R70 | `TR_USER_CLOSES_CASE` | Кирилл закрывает кейс |
| R72 | `TR_WORKLOAD_LIMIT_NOT_EXTENDED` | Кирилл не расширяет лимит |
| R73 | `TR_WORKLOAD_EXCESS_APPROVED` | Кирилл одобряет превышение |
| R78 | `TR_LATE_RESPONSE_REQUIRES_NEW_CASE` | Поздний ответ требует нового решения или действия |

**Journal-only события** (5): `EXTERNAL_ACTION_REQUESTED`, `PACKAGE_BOUNDARY_REACHED`, `NON_MATERIAL_CHANGE_RECORDED`, `RELEVANCE_CONFIRMED`, `LATE_EVIDENCE_RECORDED`. Они записываются в ledger как наблюдаемые факты, правил не запускают и в закрытый тип входных триггеров `execute_trigger` не входят; квалификация принадлежит `03 v2.1` §4.

**`ADDITIONAL_TIME_APPROVED`** входит в каталог `03 v2.1` §4 (группа «Подготовка») и является обычным продуктовым триггером правила R67. Находка `AUD-N2` закрыта редакционной erratum версии `03 v2.1`; расхождения между каталогом событий и таблицами переходов настоящая спецификация не фиксирует.

**Детерминизм разрешения.** Резолвер по (состояние, режим, триггер, авторитетный контекст) обязан вернуть ровно одно правило. Полный разбор `03 v2.1` даёт 80 пар «состояние + триггер» на 78 правил и ровно две пары с более чем одним правилом:

| Пара | Правила | Дискриминатор |
|---|---|---|
| `DECISION_UPDATE` + `DECISION_RECORDED` | R26, R27 | `G18_COUNTED` — взаимоисключающие ветви, третьего исхода нет |
| `DECISION_UPDATE` + `DECISION_DEFERRED` | R59, R60 | сторона ожидания: `DECISION_DEFERRED_BY_USER` → `PAUSED_USER`, `DECISION_DEFERRED_BY_EXTERNAL` → `PAUSED_EXTERNAL` |

Ноль или более одного подходящего правила после применения дискриминаторов — отказ команды без частичных эффектов (fail closed), а не выбор по умолчанию.

### 1.5. Покрытие правил командами: 78/78

Каждое правило каталога имеет ровно один командный путь. Ни одно правило не исполняется вне реестра §1.2.

| Команда | Правила |
|---|---|
| `SubmitOpportunity` | R01 |
| `CompleteStage` | R02, R04, R06, R08 |
| `DismissPreExperiment` | R03, R05, R07, R32, R54, R63, R69 |
| `PublishRevision` | R09 |
| `CommitGateRecord` | R10, R11, R12, R34, R35, R36 |
| `ConsumeDecisionIntent` | R13, R14, R15, R16, R17, R37, R45, R51 |
| `RecordExternalAction` | R18, R28, R29 |
| `RecordConditionOutcome` | R19, R21, R22, R23, R33, R44, R46, R47 |
| `RecordEvidence` / `RecordAttestation` | R20, R48 |
| `FireTimer` | R24, R49, R50, R58, R62, R65, R66, R75, R76 |
| `CompleteClosure` | R25 |
| `CommitDecisionUpdate` | R26, R27, R59, R60 |
| `RequestExpense` | R30 |
| `SkipPlannedAction` | R31 |
| `RouteRework` | R38 |
| `DetectMaterialChange` | R39, R53 |
| `RouteRevalidation` | R40 |
| `ResolveEscalation` | R41, R43 |
| `ReclassifyDefect` | R42 |
| `ResumeFromPause` | R52, R61 |
| `RecordRelevanceOutcome` | R55, R64 |
| `StartExternalWait` | R56 |
| `RecordExternalResponse` | R57 |
| `GrantAdditionalTime` | R67 |
| `NarrowScopeOrAddData` | R68 |
| `CloseCaseByUser` | R70 |
| `RecordWorkloadOutcome` | R71, R72, R73 |
| `BlockUnapprovedExpense` | R74 |
| `RegisterLateEvidence` | R77 |
| `CreateLinkedCase` | R78 |

Сумма правил по строкам таблицы — 78, пересечений нет. Остальные 10 команд реестра §1.2 (`ProvideClarification`/`ProvideFact`, `OpenGateAttempt`, `RecordPassFindings`, `SubmitGateProposal`, `IssueDecisionIntent`, `GrantAuthority`, `OpenCycleReview`/`ResolveCycleReview`, `EnterDiagnosticHold`/`ExitDiagnosticHold`, `ConfirmRestoreResume`, `EnterTransportMaintenance`/`ExitTransportMaintenance`, `SupersedePendingIntents`) правил `03` не исполняют: они обслуживают подготовку данных, гейтовую сессию, транспорт и администрирование. Покрытие 78/78 и отсутствие правил без команды проверяются T01.

## 2. Модель вычисления guards

1. Guard — чистая функция от канонических строк БД и `now()` транзакции; никаких сетевых вызовов и модельных результатов внутри guard.
2. Каждый вердикт guard фиксируется в `state_transition.guard_results_ref`: id guard-а, версия правила, прочитанные факты (ссылками), вердикт, причина отказа.
3. Версия реестра guards привязана к версии `03`; изменение семантики guard возможно только новой версией `03` по правилам baseline.
4. Отказ любого guard отменяет транзакцию целиком; частичные эффекты запрещены.
5. Guards полномочий (расход, действие, deadline) вычисляются синхронно в момент команды и никогда не кэшируются.

## 3. Транзакционный протокол перехода и исполнительный API

### 3.1. Публичная и приватная поверхности

Прикладной слой имеет **ровно одну публичную точку записи состояния**:

```
execute_trigger(
    case_id,
    expected_case_version,   # обязателен для существующего кейса; отсутствует для создания (§3.7)
    trigger_id,          # только из TriggerRegistry §1.4
    actor,               # user | system | timer | admin
    idempotency_key,     # реестр 14 §4
    payload              # typed, по схеме команды реестра §1.2
) -> TransitionResult | Conflict | Rejected
```

Чего в сигнатуре нет и что отклоняется до чтения состояния:

1. `to_state` — целевое состояние вычисляется машиной и вызывающей стороной не передаётся ни в каком виде;
2. перечень guards — выбирается из разрешённого правила, а не из аргументов;
3. `rule_id` — вызывающая сторона не выбирает правило;
4. любое поле вне схемы команды — вход отклоняется целиком (`Rejected`); частичное чтение и «мягкое игнорирование» лишних полей запрещены.

Функция, применяющая переход (`apply_transition` или её эквивалент), **приватна**: она принимает только уже разрешённое правило и вычисленный effect bundle и не экспортируется за границу модуля state machine. Передача произвольных `to_state` и guards в неё невозможна по контракту API, а не только по соглашению: отсутствие такой функции в публичном интерфейсе проверяется контрактным тестом класса T01, а отсутствие обходных путей записи в кодовой базе — архитектурным guardrail `SM-APP-01` (§7.1).

### 3.2. Выбор commit-протокола по outcome kind

Loader авторитетного контекста, resolver правила и выбор guards (§3.3, шаги 1–7) общие для всех правил; различается только commit. **Commit-протокол зависит от outcome kind разрешённого правила**: часть исходов каталога не является переходом состояния, и требовать для них `state_transition` означало бы противоречить самим правилам.

| Outcome kind | Правил | Commit-протокол | `state_transition` | `case` и `case_version` |
|---|---:|---|---|---|
| `STATE_TRANSITION` | 59 | §3.3 transition protocol — 58 правил; R01 — creation protocol §3.7 | пишется | state и version обновляются; для R01 строка `case` создаётся |
| `SELF_TRANSITION` | 10 | §3.3 transition protocol | пишется, `from_state = to_state` | state не меняется, version+1 |
| `ADMINISTRATIVE_DISPOSITION` | 7 | §3.4 non-transition commit | **не пишется** | не изменяются |
| `TERMINAL_ANNOTATION` | 1 | §3.5 late-evidence commit | **не пишется** | не изменяются |
| `LINKED_CASE_CREATION` | 1 | §3.6 linked-case commit | пишется только для нового кейса | старый кейс не изменяется |
| **Итого** | **78** | | | |

Разложение правил по kind ведёт RuleCatalog §1.3 и проверяется T01: `SELF_TRANSITION` — R28, R29, R30, R49, R65, R66, R67, R71, R74, R76; `ADMINISTRATIVE_DISPOSITION` — R03, R05, R07, R32, R54, R63, R69; `TERMINAL_ANNOTATION` — R77; `LINKED_CASE_CREATION` — R78; creation — R01; остальные 58 — `STATE_TRANSITION` по transition protocol.

Ошибка соответствия «kind правила ↔ применённый протокол» — отказ без частичных эффектов, а не выбор ближайшего протокола.

### 3.3. Transition protocol — `STATE_TRANSITION` и `SELF_TRANSITION`

Одна DB-транзакция, строго в порядке:

1. `SELECT … FOR UPDATE` строки `case` (transaction-scoped lock).
2. Проверка `expected_case_version`; несовпадение → `Conflict`, команда не переинтерпретируется.
3. Проверка terminal lock и diagnostic hold (раздел 5).
4. **Loader авторитетного контекста:** чтение канонических строк, необходимых для разрешения правила, вычисления guards и routing-предикатов (состояние и режим, редакция, gate records и counter, anchor и deadlines, полномочия и расходы, реестр свидетельств, hold-поля). Loader выполняется **после** lock и только по каноническим строкам: projection, кэш, модельный вывод и содержимое `payload` авторитетным контекстом не являются.
5. **Разрешение правила машиной:** резолвер по (состояние, режим, `trigger_id`, авторитетный контекст) выбирает ровно одно правило RuleCatalog (§1.3; дискриминаторы §1.4). Ноль или более одного кандидата — `Rejected` без частичных эффектов.
6. **Выбор guards из правила:** вычисляются guards, перечисленные в разрешённом правиле, и только они; вердикты записываются по §2. Отказ любого guard отменяет транзакцию целиком.
7. **Routing multi-target правил:** целевое состояние вычисляется предикатом правила (`03 v2.1` §9.1, `PLS-068`). Если `payload` содержит ожидаемую вызывающей стороной цель, она используется исключительно для сверки; расхождение — `Rejected`.
8. **Вычисление полного effect bundle:** событие, `state_transition`, обновление `case` (state, version+1, при терминале — status и `terminal_locked_at`, снятие slot), сопутствующие вставки (anchor при `G28`, timers по kind, outbox, доменные записи правила). Bundle вычисляется целиком до первой записи.
9. **Приватный commit bundle:** записи применяются одной операцией внутри той же транзакции; частичное применение bundle невозможно.
10. COMMIT. Модельные и сетевые вызовы — только вне этой транзакции; их результат возвращается отдельной командой с новым `expected_case_version`.

`EXPERIMENT_STARTED`: INSERT `experiment_anchor` в той же транзакции, что UA gate_record и переход в EXECUTION (`PLS-065`); повторный INSERT невозможен (set-once).

### 3.4. Non-transition commit — `ADMINISTRATIVE_DISPOSITION`

Правила R03, R05, R07, R32, R54, R63, R69 завершают административную обработку входа до Experiment Planning (`PLS-063`) и **не создают** ни перехода, ни продуктового статуса.

1. `SELECT … FOR UPDATE` строки `case`; проверка `expected_case_version`; проверка terminal lock и hold.
2. Loader и resolver по §3.3, шаги 4–6; обязателен `G27_PRE_EXPERIMENT_DISMISSIBLE`.
3. Атомарный commit bundle: INSERT `event`; INSERT `pre_experiment_dismissal` со всеми девятью обязательными элементами (`03` §6); DELETE строки `active_experiment_slot`.
4. `state_transition` **не пишется**; `case.state`, `case.status` и `case.version` **не изменяются**: правило не переводит кейс, а прекращает обработку входа.
5. COMMIT.

Согласование с `14` v0.2: ограничение «`state_transition` пишется только в транзакции, обновляющей `case`» соблюдается тем, что строка не создаётся вовсе; `pre_experiment_dismissal` не обязана case-у в терминальном смысле и статуса не создаёт.

**Наблюдение, вынесенное отдельно.** Признака «административная обработка входа завершена» на строке `case` в `14` v0.2 §3 нет, поэтому запрет последующих команд по такому кейсу опирается на снятие slot и на отсутствие применимых правил, а не на отдельный столбец. Настоящая спецификация столбца не вводит: если он нужен, это errata к `14`, а не решение стадии.

### 3.5. Late-evidence commit — `TERMINAL_ANNOTATION`

Правило R77 (`03` §16.1, `G26_LATE_EVIDENCE_ONLY`, `PLS-038`):

1. `SELECT … FOR UPDATE` строки терминального `case` — только для сериализации; запись в строку не производится.
2. Проверка терминальности и `G26`.
3. Атомарный commit bundle: INSERT `event`; INSERT `evidence`; INSERT `late_evidence` (`terminal_case_id`, `evidence_id`, `received_at`).
4. `state_transition` **не пишется**; `case.state`, `case.status`, `case.version` и пилотный зачёт **не изменяются** — инвариант I6.
5. COMMIT.

`expected_case_version` проверяется, но не инкрементируется: отсутствие инкремента здесь — свойство правила, а не пропуск конкурентного контроля.

### 3.6. Linked-case commit — `LINKED_CASE_CREATION`

Правило R78 (`03` §16.1, `PLS-053`): поздний ответ требует нового решения или действия.

1. Старый терминальный `case` **не изменяется**: ни состояния, ни статуса, ни версии, ни зачёта. Если сам поздний ответ ещё не зарегистрирован, он фиксируется правилом R77 по §3.5 отдельной командой.
2. Новый кейс создаётся creation protocol §3.7 в той же транзакции.
3. INSERT `linked_case` (`old_case_id`, `new_case_id`, `relation_type`, ссылки на старый и новый вопрос, разницу baseline).
4. Копирование grants, consents, gate records, счётчика возвратов и полномочий отсутствует как механизм (`14` §3, anti-inheritance): новый кейс начинает с нуля и проходит проверку актуальности заново.
5. COMMIT.

### 3.7. Creation protocol — создание кейса (R01)

Строки `case` ещё нет, поэтому `SELECT … FOR UPDATE` по ней невозможен, а `expected_case_version` неприменим и в команде отсутствует.

1. Сериализация выполняется не блокировкой строки `case`, а уникальными ограничениями: INSERT `active_experiment_slot` под `UNIQUE(user_scope)` (`14` §3) — конфликт означает невыполненный `G01_SCOPE` и отказ; UNIQUE `idempotency_key` — повтор входа не создаёт второго кейса (T06).
2. Loader читает то, что существует вне кейса: занятость slot, исходное обращение, идемпотентный ключ.
3. Resolver разрешает единственное правило R01; guards берутся из него.
4. Атомарный commit bundle: INSERT `case` (`version = 1`, state `INTAKE`); INSERT `event` `CASE_SUBMITTED`; INSERT `state_transition` с пустым `from_state` и `case_version_after = 1`; обязательные записи правила (сообщение, дата, материалы, baseline).
5. COMMIT.

Пустой `from_state` означает вход в систему, а не переход из состояния. Если реализация `14` §3 потребует `NOT NULL` для `from_state`, расхождение возвращается как дефект спецификации `14` и разрешается её версией-преемником, а не обходом в коде.

### 3.8. Fail-closed свойства протоколов

| Свойство | Механизм | Проверяется |
|---|---|---|
| Целевое состояние не приходит извне | отсутствует в сигнатуре `execute_trigger`; вычисляется на шаге 7 | T01, T20 |
| Guards не приходят извне | выбираются из разрешённого правила на шаге 6 | T01, T02 |
| Правило не выбирается вызывающей стороной | резолвер шага 5; ноль либо несколько кандидатов → `Rejected` | T01 |
| Авторитетный контекст читается после lock и только из канона | loader шага 4 | T05 (гонка версий), T18 |
| Нет частичных эффектов | bundle вычисляется до записи и применяется приватным commit | T05, T06 |
| Неизвестный триггер отклоняется | закрытый TriggerRegistry §1.4 | T20 |
| Обход публичной поверхности | приватная `apply_transition`; guardrail `SM-APP-01` §7.1; правила и роли БД `14` §5/§12 | статический guardrail, T03, T04 |
| Протокол соответствует outcome kind правила | выбор протокола §3.2; несоответствие — отказ без частичных эффектов | T01, T20 |
| Нетранзиционные исходы не пишут `state_transition` | §§3.4–3.6 | T01, T03 |
| Late evidence не меняет case и версию | §3.5, инвариант I6 | T02 (I6), T03 |
| Создание кейса сериализуется без строки `case` | §3.7: `UNIQUE(user_scope)` slot + UNIQUE `idempotency_key` | T05, T06 |

## 4. Протоколы Gate и Authority Engines

**Gate Engine.** Attempt открывается на exact revision; session (TR/SA) строит детерминированный Coverage Plan до первого Model Call; findings и cells — по `14` §3.4; Coverage Validator — детерминированная функция полноты (все 27 областей + все edges, отсутствие null/INCONCLUSIVE, все findings в synthesis, совпадение hashes); только после `COMPLETE` допускается `CommitGateRecord`. Counter — view `tr_return_counter`; `THIRD_MANDATORY_DEFECT` вычисляется по нему в момент команды. Independence: отклонение proposal при совпадении actor_run с producer/ancestor, несоответствии role/purpose/session.

**Consent/Authority Engine.** Intent выпускается только для decision-моментов; consume — по протоколу §8.3 архитектуры с повторной проверкой всех транспортных и доменных guards в одной транзакции с созданием consent/record. Grant scope immutable; изменение любого параметра расхода/действия инвалидирует старый intent/grant и требует нового цикла. Пакетные consents допускаются только для заранее перечисленных бесплатных действий (`PLS-023`) и никогда не содержат денежного поля.

## 5. Diagnostic Hold — lifecycle (закрытие `AAR-R2`, спецификационная часть)

| Аспект | Правило |
|---|---|
| Вход | Только `EnterDiagnosticHold` от recovery/integrity job или admin-команды с обязательным `reason_event_id` (какое расхождение обнаружено, какие строки). Автоматический вход — только при расхождении projection↔ledger/hashes (`14` §10.2) |
| Эффект | Блокируются все команды, изменяющие case, кроме: `ExitDiagnosticHold`, диагностических read-only, `RegisterLateEvidence` (терминальные case) и `FireTimer` в режиме «материализовать событие без перехода» |
| Что hold НЕ делает | Не создаёт состояния/статуса; не переносит и не приостанавливает `absolute_deadline`, `due_at` таймеров, preparation ledger; не отменяет day-14 guard (он синхронный и сработает при первой команде после выхода) |
| Timers во время hold | Scheduler материализует overdue-события с пометкой `held`; их доменная обработка выполняется немедленно после выхода в исходном порядке `due_at` |
| Уведомление | Вход и выход всегда создают informational outbox Кириллу с причиной; decision messages во время hold не выпускаются |
| Выход | Только явная admin-команда `ExitDiagnosticHold` после устранения расхождения compensating-командами (не правкой строк); в trace — что исправлено и каким событием |
| 45/60 во время hold | Preparation-интервалы во время hold закрыты (системная работа не идёт), время не начисляется и не списывается |

Операционная часть закрытия `AAR-R2` (runbook-процедуры) — Deployment and Operations Runbook.

## 6. Deadlines и время

Union-подсчёт бюджета, 45/60-события, immutable старт и day-14 исполняются по `10` архитектуры и структурам `14` §3.7. Дополнительно нормируется: `PREPARATION_LIMIT_REACHED` блокирует создание preparation jobs и применение поздних model results; предъявление лучшего результата Кириллу строится детерминированной projection без новых Model Calls и не учитывается в бюджете (уточнение `AAR-N2`, закрыто здесь).

## 7. Инварианты исполнения (сводно)

I1 один gate_record на attempt; I2 set-once anchor; I3 единственный slot; I4 terminal lock; I5 counter не сбрасывается ничем, кроме нового case; I6 late evidence не меняет case; I7 linked case без наследования; I8 никакая команда не принимает model text как значение состояния; I9 расход exact-bound и одноразовый; I10 hold не двигает время. Каждый инвариант имеет обязательный тестовый класс (раздел 11 + `14` приложение A).

### 7.1. `SM-APP-01` — ненормативный application-инвариант

`SM-APP-01`: единственный путь записи состояния кейса — команды реестра §1.2, исполняемые транзакционным протоколом §3; прикладной код вне этого протокола не выполняет прямых записей в таблицы состояния и журнала (`INSERT`/`UPDATE`/`DELETE` в обход команд).

Статус и границы:

1. `SM-APP-01` **не входит** в нормативный перечень инвариантов I1–I10 §7 и **не входит** в тестовый класс T02: T02 проверяет только I1–I10 под случайными последовательностями команд, и его состав настоящей версией не изменяется.
2. `SM-APP-01` — архитектурное правило прикладного слоя, а не физическая гарантия. Физические гарантии дают правила БД `14` §5 и роли `14` §12, проверяемые T03 и T04 («злонамеренный worker» под ролью `pls_worker`).
3. Проверка `SM-APP-01` — **обязательный архитектурный guardrail**: статический тест над исходным кодом, который отклоняет появление путей записи в обход реестра команд. Он утверждает отсутствие такого пути в кодовой базе на момент прогона, а не невозможность прямого `INSERT` как таковую; обход через сторонний процесс, миграцию или прямой доступ к БД он не закрывает и закрывать не обязан — это предмет `14` §5/§12, T03 и T04.
4. Нарушение guardrail блокирует релиз как дефект реализации; переклассификация в дефект спецификации требует записи журнала стадии.


## 8. Отказы

Любая неопределённость → отказ команды без частичных эффектов (fail closed for authority); история и outbox — fail durable (§11 архитектуры). Conflict `expected_case_version` всегда возвращается инициатору с актуальной projection.

## 9. Traceability

Команды↔решения: `DismissPreExperiment`→`PLS-063`; `CommitGateRecord`+counter→`PLS-029/058/066/039`; `ConsumeDecisionIntent`→`PLS-009/023/026/035/055/060`; `RecordConditionOutcome`→`PLS-014/032/040`; `CommitDecisionUpdate`→`PLS-028/036/047/056/059`; `RegisterLateEvidence`→`PLS-038`; `CreateLinkedCase`→`PLS-053`; anchor→`PLS-065/037`; hold→`AAR-R2`; `ConfirmRestoreResume`→`AAR-M1`.

## 10. Обязательные тестовые классы

Exhaustive transition tests по таблицам `03`; property-тесты недопустимых переходов; конкурентные тесты команд (lock/version); idempotency всех ключей `14` §4; set-once/slot/terminal; counter через revisions/pauses/Execution; hold: вход/выход/timers/day-14; restore-resume protocol; независимость ролей и невозможность самоприёмки; блок действий после absolute deadline из каждого нетерминального состояния.

### 10.1. Распределение тестовых классов T01, T02, T20 по задачам

Правило распределённого T-класса (`PLS-067`) применяется к T01, T02 и T20 по решениям `PLS-070`–`PLS-072` журнала стадии `26 v0.1`. Тексты классов и критерии PASS `22` §1, а также гейты фаз `22` §4, не изменяются; распределяется только адресация работы и момент объявления полного PASS.

| Класс | Часть | Владелец | Содержание |
|---|---|---|---|
| T01 | доменные команды и контракты эффектов | TB-07…TB-10 | команды реестра §1.2 и их эффекты как предусловие исполнимости правил каталога |
| T01 | полный PASS | **TB-13** | full mock-contour PASS: все 78 правил RuleCatalog исполняются на синтетических авторитетных данных и mock-адаптерах инфраструктуры, без реальных моделей |
| T02 | I1 — один `gate_record` на attempt | TB-08 | Gate Engine: ровно один record на attempt |
| T02 | I2 — set-once anchor | TB-10 | `experiment_anchor` устанавливается однократно |
| T02 | I3 — единственный slot | TB-06 | доменная проверка `G01`; DB-правило — TB-04 |
| T02 | I4 — terminal lock | TB-06 | терминальные состояния не покидаются; DB-правило — TB-04 |
| T02 | I5 — counter не сбрасывается ничем, кроме нового case | TB-08 | `tr_return_counter` |
| T02 | I6 — late evidence не меняет case | TB-07 | команда `RegisterLateEvidence`, правило R77 |
| T02 | I7 — linked case без наследования | TB-07 | команда `CreateLinkedCase`, правило R78 |
| T02 | I8 — ни одна команда не принимает model text как значение состояния | TB-06, TB-07 | граница command/state-machine |
| T02 | I9 — расход exact-bound и одноразовый | TB-09 | Consent/Authority Engine |
| T02 | I10 — hold не двигает время | TB-11 | diagnostic hold |
| T02 | regression на границе model-proposal | TB-23 | отдельный regression-тест конвейера валидации `18` §6; полный T02 не блокирует |
| T02 | полный mock-PASS | **TB-13** | property-прогон I1–I10 одной генерацией на mock-контуре |
| T20 | `BLOCKED_COVERAGE_OR_BUDGET` | TB-08 | единственный релевантный для T20 `BLOCKED_*`: статус `gate_attempt` при недостатке покрытия или бюджета, `PASS` невозможен |
| T20 | полный PASS на mock-контуре | **TB-13** | все запрещённые маршруты §11 `03`, границы `PRE_EXPERIMENT_DISMISSED`, недостижимость прямого `CLOSED_NOT_COUNTED`, действия после deadline |

`PROVIDER_DATA_POLICY_BLOCKED` относится к Data Policy Registry (`19` §2, архитектура §12.6.4–6) и проверяется классом T12 в задаче TB-20; в состав T20 он не входит.

Инфраструктурные задачи TB-26 (Evidence/Artifact Service) и TB-29 (scheduler runtime) полный mock-PASS T01 **не блокируют**: на mock-контуре их адаптеры заменяются синтетическими, а реальные свойства storage и scheduler проверяются собственными классами T13, T07 и частью T05 позднее. Это не ослабляет `PLS-067`: часть T05, закреплённая за TB-29, остаётся обязательной до гейта подключения реальных моделей.

Каждый инвариант I1–I10 имеет task-local владельца; ни один не остаётся без адресата. До закрытия всех частей класс имеет статус `PARTIAL` с явным перечнем; полный `PASS` фиксируется записью журнала стадии, а не отчётом задачи.


## 11. Открытые пункты

Нет открытых решений Кирилла. Runbook-часть `AAR-R2` остаётся обязательством документа 6 стадии.

Вопрос `OPEN-01` пересборки пакета — «какие `BLOCKED_*` входят в T20» — закрыт решением `PLS-070` (§10.1) и открытым не является.

## 12. Changelog v0 (проверка по контуру `15`)

| Находка | Severity | Закрытие |
|---|---|---|
| SGV-1 — первоначальный черновик не определял поведение timers внутри hold, создавая риск «тихой» потери overdue-событий | MINOR | §5: материализация с пометкой `held` и упорядоченная обработка после выхода |
| SGV-2 — не был нормирован статус limit-презентации на 60-й минуте (перенесённая `AAR-N2`) | MINOR | §6: детерминированная projection вне бюджета; `AAR-N2` закрыта |
| SGV-3 — реестр команд не содержал `ConfirmRestoreResume`, разрывая протокол `14` §10.3 | MINOR | §1.2: команда добавлена с предусловием предъявленного divergence report |

Проверка выполнена автором по принятому контуру `15`; повторная независимость — сводным аудитом пакета.

---

## 13. Changelog v0.2

| Изменение против v0.1 | Основание |
|---|---|
| Добавлен §1.3 RuleCatalog: 78 правил, разложение по разделам `03`, пять outcome kinds, обязательные атрибуты, требование детерминированной routing policy для multi-target правил | `PLS-069`; `03 v2.1` §9.1 |
| Добавлен §7.1 `SM-APP-01` как ненормативный application-инвариант вне I1–I10 и вне T02; статический тест назван обязательным архитектурным guardrail, а не физической гарантией невозможности прямого `INSERT` | `PLS-069` |
| Добавлен §10.1: распределение T01, T02 и T20 по задачам; каждый из I1–I10 закреплён за task-local владельцем; `PROVIDER_DATA_POLICY_BLOCKED` исключён из T20; TB-26 и TB-29 не блокируют mock-PASS T01 | `PLS-070`–`PLS-072` |
| §1.2 дополнен 16 доменными командами (реестр 24 → 40): правила `03`, не имевшие командного пути в v0.1, его получили | `PLS-069` |
| Добавлен §1.4 TriggerRegistry: закрытый тип из 65 входных триггеров (52 − 5 + 1 + 17), технические идентификаторы 17 прозаических правил, journal-only события, две пары коллизий и их дискриминаторы | `PLS-069`, `03 v2.1` §4 |
| Добавлен §1.5: покрытие 78/78 правил командами | `PLS-069` |
| §3 переписан: публичный `execute_trigger` без `to_state`, `rule_id` и guards; loader авторитетного контекста после lock; разрешение правила машиной; выбор guards из правила; routing multi-target; приватный commit полного effect bundle; таблица fail-closed свойств | `PLS-069` |
| §3.2: commit-протокол выбирается по outcome kind; §§3.4–3.7 добавлены — non-transition commit для `ADMINISTRATIVE_DISPOSITION`, late-evidence commit для `TERMINAL_ANNOTATION`, linked-case commit и creation protocol для R01 без `FOR UPDATE` по несуществующей строке | `PLS-069` |
| §1.4: `ADDITIONAL_TIME_APPROVED` — обычный продуктовый триггер каталога `03 v2.1` §4; расхождение каталога и таблиц переходов спецификацией больше не фиксируется | `AUD-N2` закрыта `03 v2.1` |

Не изменены: 24 команды v0.1 (дополнены новыми, ни одна не удалена и не переформулирована), модель guards §2, протоколы Gate/Authority Engines §4, diagnostic hold §5, время §6, инварианты I1–I10 §7, отказы §8, traceability §9, обязательные тестовые классы §10, changelog v0 §12.


*Спецификация не изменяет `03`, `05`, baseline и архитектуру v1.1; тексты классов и гейтов `22` не изменяет.*
