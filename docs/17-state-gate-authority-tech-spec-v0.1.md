# Personal Leverage System
## State/Gate/Authority Technical Specification v0.1

**Статус:** кандидат на пользовательскую приёмку (проверка по контуру `15` — раздел 12)  
**Дата:** 6 августа 2026  
**Основание:** архитектура `11-technical-architecture-v1.1.md`; принятая `14-data-model-persistence-spec-v0.1.md`; продуктовый baseline v2 (`03-state-machine-v2.md`, `05-gates-v2.md` — нормативные первоисточники состояний, guards и гейтов)  
**Область:** формальные application commands, модель вычисления guards, транзакционный протокол переходов, протоколы Gate Engine и Consent/Authority Engine, lifecycle административного `diagnostic hold` (закрытие `AAR-R2`, часть 1 из 2), инварианты и обязательные тестовые классы  
**За рамками:** изменение baseline, перечня состояний/статусов/guards (принадлежит `03`), критериев гейтов (принадлежит `05`), API-транспорта, промптов, кода

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

Команды, отсутствующие в реестре, не существуют: незарегистрированный путь записи — дефект реализации.

## 2. Модель вычисления guards

1. Guard — чистая функция от канонических строк БД и `now()` транзакции; никаких сетевых вызовов и модельных результатов внутри guard.
2. Каждый вердикт guard фиксируется в `state_transition.guard_results_ref`: id guard-а, версия правила, прочитанные факты (ссылками), вердикт, причина отказа.
3. Версия реестра guards привязана к версии `03`; изменение семантики guard возможно только новой версией `03` по правилам baseline.
4. Отказ любого guard отменяет транзакцию целиком; частичные эффекты запрещены.
5. Guards полномочий (расход, действие, deadline) вычисляются синхронно в момент команды и никогда не кэшируются.

## 3. Транзакционный протокол перехода

Одна DB-транзакция, строго в порядке:

1. `SELECT … FOR UPDATE` строки `case` (transaction-scoped lock).
2. Проверка `expected_case_version`; несовпадение → conflict, команда не переинтерпретируется.
3. Проверка terminal lock и diagnostic hold (раздел 5).
4. Вычисление guards; запись вердиктов.
5. INSERT `event`; INSERT `state_transition`; UPDATE `case` (state, version+1, при терминале — status и terminal_locked_at, снятие slot); сопутствующие INSERT (anchor при `G28`, timers по kind, outbox).
6. COMMIT. Модельные и сетевые вызовы — только вне этой транзакции; их результат возвращается отдельной командой с новым `expected_case_version`.

`EXPERIMENT_STARTED`: INSERT `experiment_anchor` в той же транзакции, что UA gate_record и переход в EXECUTION (`PLS-065`); повторный INSERT невозможен (set-once).

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

## 8. Отказы

Любая неопределённость → отказ команды без частичных эффектов (fail closed for authority); история и outbox — fail durable (§11 архитектуры). Conflict `expected_case_version` всегда возвращается инициатору с актуальной projection.

## 9. Traceability

Команды↔решения: `DismissPreExperiment`→`PLS-063`; `CommitGateRecord`+counter→`PLS-029/058/066/039`; `ConsumeDecisionIntent`→`PLS-009/023/026/035/055/060`; `RecordConditionOutcome`→`PLS-014/032/040`; `CommitDecisionUpdate`→`PLS-028/036/047/056/059`; `RegisterLateEvidence`→`PLS-038`; `CreateLinkedCase`→`PLS-053`; anchor→`PLS-065/037`; hold→`AAR-R2`; `ConfirmRestoreResume`→`AAR-M1`.

## 10. Обязательные тестовые классы

Exhaustive transition tests по таблицам `03`; property-тесты недопустимых переходов; конкурентные тесты команд (lock/version); idempotency всех ключей `14` §4; set-once/slot/terminal; counter через revisions/pauses/Execution; hold: вход/выход/timers/day-14; restore-resume protocol; независимость ролей и невозможность самоприёмки; блок действий после absolute deadline из каждого нетерминального состояния.

## 11. Открытые пункты

Нет открытых решений Кирилла. Runbook-часть `AAR-R2` остаётся обязательством документа 6 стадии.

## 12. Changelog v0 (проверка по контуру `15`)

| Находка | Severity | Закрытие |
|---|---|---|
| SGV-1 — первоначальный черновик не определял поведение timers внутри hold, создавая риск «тихой» потери overdue-событий | MINOR | §5: материализация с пометкой `held` и упорядоченная обработка после выхода |
| SGV-2 — не был нормирован статус limit-презентации на 60-й минуте (перенесённая `AAR-N2`) | MINOR | §6: детерминированная projection вне бюджета; `AAR-N2` закрыта |
| SGV-3 — реестр команд не содержал `ConfirmRestoreResume`, разрывая протокол `14` §10.3 | MINOR | §1.2: команда добавлена с предусловием предъявленного divergence report |

Проверка выполнена автором по принятому контуру `15`; повторная независимость — сводным аудитом пакета.

---

*Спецификация не изменяет `03`, `05`, baseline и архитектуру v1.1.*
