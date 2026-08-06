# Personal Leverage System
## Independent Architecture Audit v0: независимый системный аудит `11-technical-architecture-v1.md`

**Статус:** завершённый независимый аудит
**Дата:** 6 августа 2026
**Аудитор:** независимая проверочная роль (Claude), не являющаяся продолжателем архитектора
**Основание:** пакет из девяти файлов манифеста заказчика; нормативный приоритет продуктового baseline v2 и решений `PLS-001–PLS-066`
**За рамками:** перепроектирование архитектуры, создание v2, ADR, схем данных, API, промптов, task breakdown и кода

---

## 1. File Integrity

Размеры и SHA-256 всех девяти файлов вычислены независимо (GNU coreutils `stat`, `sha256sum`) и сверены с манифестом заказчика.

| Файл | Байт (факт/манифест) | SHA-256 (факт) | Совпадение |
|---|---|---|---|
| `01-vision-v2.md` | 39143 / 39143 | `6f841b1550f112a0a96ce18c061898a557ebffe22b3600ae7aeff4f781eb8597` | PASS |
| `02-workflow-spec-v2.md` | 65390 / 65390 | `c618056d7712056f3a8315de597318f27df34f2dc92a1578d42f75451fa6e071` | PASS |
| `03-state-machine-v2.md` | 83779 / 83779 | `a06d7febc99c86761cc90d1f8f383cda3fade4b6a789e7a342c1c94254960548` | PASS |
| `04-dossier-contract-v2.md` | 118507 / 118507 | `5b8b2b9bfd08e268418bf4ebe4beb5ded70d7b48751559dd6741bc78b2018d8f` | PASS |
| `05-gates-v2.md` | 128151 / 128151 | `8c72b803a0b4362cccd672a6cbc17a58a6d4ac9282b48c2c3b14dc5215749831` | PASS |
| `08-audit-closure-verification-v0.md` | 33224 / 33224 | `6e3bd1474d514e951f26dce523079d9e84ffa62b6df30dd2465e43a37d868737` | PASS |
| `09-product-baseline-acceptance-v0.md` | 8213 / 8213 | `05ca7bb44650d5c6eaa72ef0ac5e52036201595ee9085c6bf99dbcd1f6b5db68` | PASS |
| `10-decisions-log-v2.md` | 73083 / 73083 | `880e4f26edd855cb351b3ab77188728b0fe02c7d4d0922e6226a98da2b09d2e6` | PASS |
| `11-technical-architecture-v1.md` | 162771 / 162771 | `9450ddacd528fe21268ee53df3ea4d44e0b8cf7b46de54d7109112dfe1320195` | PASS |

Примечание процедуры: первоначальная передача пакета была неполной (отсутствовали файлы `08` и `11`, присутствовал внесистемный `07-audit-resolution-v0.md`). Недостающие файлы были догружены; финальный пакет совпал с манифестом полностью. Файл `07` в содержательном аудите не использовался. Загруженный дополнительно `11-technical-architecture-v1.md` при повторной загрузке совпал с манифестом побайтно, что исключает подмену между попытками.

**File Integrity Gate: PASS.** Содержательный аудит разрешён.

## 2. Verdict

# `PASS WITH REQUIRED CORRECTIONS`

`11-technical-architecture-v1.md` может быть принят как технический архитектурный baseline при условии закрытия одной находки `MAJOR` (AAR-M1) и явного решения заказчика о маршруте закрытия двух находок `MINOR` (AAR-R1, AAR-R2). Находок класса `BLOCKER` нет. Нарушений продуктового baseline v2 и решений `PLS-001–PLS-066` — ослаблений, расширений полномочий, изменений маршрутов, шестого статуса, изменения сроков или критериев зачёта, обходов гейтов, молчаливых продуктовых требований — не обнаружено.

## 3. Executive Summary

Архитектура выдержала попытку опровержения. Детерминированное ядро с proposal-only-контрактом модельных выходов, серверными typed commands, guards и append-only-историей не оставило найденного пути, по которому LLM, tool proposal, Telegram-сообщение или provider-side state могли бы изменить состояние, пройти guard, создать Gate Record, разрешить расход, создать Consent/Authority Grant, перенести deadline, переоткрыть терминальный кейс или наследовать полномочия. Независимость Worker → Technical Reviewer → System Acceptor → Кирилл обеспечена раздельными Agent Runs, purposes, Context Packages, Gate Review Sessions и запретом наследования provider identifiers; самоприёмка программно отклоняется. Механизм Gate Review Session с детерминированным Coverage Plan/Matrix на все 27 областей и cross-area инварианты делает неполноту проверки fail-closed: `PASS` без полного покрытия невозможен.

Трассировка всех решений `PLS-001–PLS-066` подтверждена: 66 из 66 имеют механизм, компонента-владельца и способ проверки; `MISSING` и `CONFLICT` отсутствуют. Временные инварианты (объединение preparation-интервалов, 45/60 минут, однократный `EXPERIMENT_STARTED`, абсолютный день 14, пожизненный TR-counter, terminal lock) корректно перенесены в технические механизмы, устойчивые к параллельности, повторам и перезапускам. Изменяемые технологические факты выборочно проверены по актуальным официальным источникам и подтверждены: Railway классифицирует свои DB-шаблоны как unmanaged; R2 документирует частичную S3-совместимость; OpenAI `store:false` существует и корректно не трактуется архитектурой как нулевая retention.

Существенная неполнота обнаружена в одном месте: процедура восстановления из backup/PITR (§15.3) проверяет целостность данных, но не определяет реконсиляцию артефактов полномочий и транспорта после отката — восстановленные в `pending` уже использованные Decision Intents, повторную доставку decision-сообщений из восстановленного outbox и расхождение канона с фактически принятыми в утраченном окне решениями (AAR-M1). Это неполнота значимого механизма, а не обход baseline: все guards (identity, revision hash, one-time CAS) продолжают действовать, и полномочие не может получить никто, кроме Кирилла.

## 4. Scope and Method

Проверялся только пакет из девяти файлов манифеста; более ранние версии — вне области. Метод: (1) полное чтение `11-technical-architecture-v1.md`; (2) полное чтение `10-decisions-log-v2.md` и реестра всех 66 решений; (3) целевые доказательные проверки нормативных мест `01–05` (guards `G25/G27/G28`, таблицы терминальных состояний и дня 14, §5.6/§7.10 Workflow, §2.3/§6 и требование 27-областной полноты Gates, перечень 27 областей и §27 Dossier, критерий пилота Vision §14); (4) чтение вердикта и матрицы `08-audit-closure-verification-v0.md` (PASS) и акта `09-product-baseline-acceptance-v0.md`; (5) построчная трассировка §16 архитектуры против журнала; (6) атакующие проходы по десяти обязательным направлениям; (7) прогон 25 обязательных adversarial-сценариев и дополнительных сценариев аудитора; (8) выборочная проверка изменяемых технологических фактов по актуальным официальным источникам (раздел 12). Проверка носит доказательный характер: каждое `PASS` опирается на конкретный раздел документа, каждая находка — на контрпример. Аудитор не проектировал исправления сверх минимальных условий закрытия.

Ограничение метода: аудит устанавливает наличие и непротиворечивость архитектурных механизмов, а не их корректную реализацию; чек-лист §19 архитектуры честно фиксирует то же ограничение.

## 5. Findings Register

| ID | Severity | Раздел | Нарушенное правило / основание | Контрпример | Последствия | Минимальное условие закрытия |
|---|---|---|---|---|---|---|
| `AAR-M1` | **MAJOR** | §15.3, §8.4–8.5, §11.1 | Принцип «fail closed for authority» (§11) не распространён на восстановление; обязательный сценарий аудита «restore возвращает старые pending outbox и timers»; точная привязка решений (`PLS-009`, `PLS-050`) в утраченном окне | PITR-restore на точку T−30 мин. Decision Intent, использованный (`consumed`) в T−10, восстановлен как `pending`; Telegram повторяет неподтверждённый callback либо Кирилл повторно нажимает живую кнопку старого сообщения — система принимает решение «впервые», не зная, что оно уже принималось и, возможно, исполнялось; параллельно восстановленный outbox повторно доставляет decision-сообщения; события утраченного окна (consents, evidence, расходы) расходятся с внешней реальностью без обязательного отчёта о расхождении | Молчаливое расхождение канона с фактическими решениями и внешними действиями; дублированные активные decision-кнопки; риск непреднамеренного повторного согласия. Полномочие третьему лицу не утекает (все guards identity/revision/CAS действуют), но exactness и честность истории нарушаются | Дополнить restore-процедуру обязательным post-restore шагом: перевод **всех** восстановленных `pending` Decision Intents в `superseded` с перевыпуском актуальных summary (по образцу §8.5); реконсиляция outbox по logical notification id; обязательный divergence report по утраченному окну с явным подтверждением Кирилла до возобновления decision-потока. Закрывается точечной правкой v1.1 либо обязательным пунктом Deployment/Operations Runbook + Persistence Specification по явному решению Кирилла |
| `AAR-R1` | MINOR | §12.1, §3.2 | Требование аудита оценить достаточность модульного разделения при общем доступе Worker к БД и credentials | Матрица доступа §12.1 не указывает DB-доступ Worker-процесса, хотя именно Worker исполняет Agent Runs и канонические записи; enforcement границы «Model Gateway не имеет DB command credentials» внутри одного процесса — дисциплина кода, а не проверяемое ограничение; DB-роли/гранты по процессам не определены | Ошибка/уязвимость в коде Worker теоретически имеет полный write-путь; заявленная в §17 №1 граница выглядит сильнее фактической | Полная непротиворечивая privilege matrix per process (включая Worker↔DB), явная фиксация intra-process trust assumption и определение DB-ролей/грантов в Security + Data Model Specifications; тестовый класс на гранты |
| `AAR-R2` | MINOR | §9.3 | Полнота state/time-контура; недопустимость скрытых квазисостояний | Административный `diagnostic hold` блокирует кейс при расхождении projection/ledger, но его lifecycle не определён: условия входа/выхода, уведомление Кирилла, поведение активных timers, 45/60-событий и внешних ожиданий во время hold | Возможен «тихо застрявший» кейс; day 14 защищён immutable deadline, но операционные события в hold не определены | Определить hold в State/Gate Technical Specification и Runbook с инвариантами: hold не создаёт переходов и статусов, не переносит deadlines и timers, всегда уведомляет Кирилла, выход — только явной административной командой с trace |
| `AAR-N1` | NOTE | §5.4, §13.2 | — | Полное 27-областное покрытие применено и к Technical Review, тогда как Gates v2 нормативно закрепляет 27-областную полноту за System Acceptance (05 §…, «соответствие всех 27 логических областей»), а TR — за качеством полного представленного входа. Усиление, не ослабление; удваивает стоимость/время sessions внутри общего 60-минутного бюджета, эмпирических ориентиров нет | Риск систематического упирания в `PREPARATION_LIMIT_REACHED`; поведение при лимите честное (fail-closed, PBС на 45') | Вход `ADR-CANDIDATE-015`: пилотная калибровка и решение о технически-обусловленном сужении TR Coverage Plan без ослабления SA-полноты |
| `AAR-N2` | NOTE | §10.2 | — | PLS-064 требует на 60-й минуте показать лучший результат/дефекты/оценку, при этом новые preparation jobs заблокированы; статус самой limit-презентации не оговорён | Двусмысленность на границе лимита | Явно зафиксировать: limit-презентация строится детерминированно из имеющихся записей без новых Model Calls и не является UA-summary |
| `AAR-N3` | NOTE | §16 (PLS-008) | — | Семантика «недели» лимита 5 часов (календарная/скользящая, timezone) не определена | Неоднозначность guard | Определить в Data Model Specification |
| `AAR-N4` | NOTE | §5.4 | — | Coverage Validator гарантирует, что ни одно зарегистрированное finding не потеряно synthesis, но не может принудить модель зарегистрировать невысказанное finding | Остаточная модельная ошибка; честно раскрыта в §16 | Принять как residual risk; alternate-provider review по §6.1 как опция глубины |
| `AAR-N5` | NOTE | §16 | — | Строка трассировки `PLS-013/054/055` объединяет три разных механизма в одной ячейке, хотя каждый механизм отдельно существует (§§8.2, 9, 12.2) | Редакционная неточность без пробела покрытия | Редакционно при следующей версии |

## 6. Traceability Matrix `PLS-001–PLS-066`

Все 66 решений найдены в §16 архитектуры; полнота перечня подтверждена сплошным пересчётом идентификаторов. Смысл каждого решения сверен с полным текстом `10-decisions-log-v2.md`. Группировка аудита следует группировке §16 после проверки, что механизмы в группе действительно общие (единственное исключение отмечено в `AAR-N5`; покрытие при этом полное).

| PLS-IDs | Механизм (проверенный) | Владелец | Проверяемость тестом | Обход найден | Семантика изменена | Статус |
|---|---|---|---|---|---|---|
| 001, 002, 004, 063 | Intake-guard, закрытый pre-Planning disposition без шестого статуса (совп. с 03 §§2–10, `G27`) | API, State Machine | Да | Нет | Нет | FULL |
| 003, 043, 044, 046 | Единый Dossier aggregate, 27 областей (список §5.4 побуквенно совпадает с 04 §4), три слоя, один источник истины | Dossier, Gate Engine | Да | Нет | Нет | FULL |
| 005, 037, 065 | Однократный `EXPERIMENT_STARTED`/set-once, immutable absolute deadline, синхронный time-guard (совп. с 03 §10.3, `G28`) | State Machine, Scheduler | Да | Нет | Нет | FULL |
| 006, 020, 021, 041, 042 | Countability engine, предикат квалифицирующего действия, агрегат двух `CLOSED_COUNTED` (совп. с 01 §14) | Closure Engine | Да | Нет | Нет | FULL (оценочное ядро 006 — PRODUCT_ONLY, механизм записи FULL) |
| 007, 019, 064 | Union preparation-интервалов, единый ledger, 45/60-события, Gate Records в бюджете (совп. с 05: «Gate Record нельзя вынести за границу лимита») | Scheduler, Cost, SM | Да | Нет | Нет | FULL |
| 008 | Workload budget + guard 5 ч/нед | Consent Engine | Да | Нет | Нет | FULL (семантика недели — AAR-N3) |
| 009, 023 | Exact one-time Expense Request/Grant, аутентифицированный Intent; инфраструктурные решения отдельны | Consent, Telegram, Cost | Да | Нет | Нет | FULL |
| 010 | Read/draft-only runtime; отсутствие outbound-коннекторов в v1 | Tool/Model Gateway | Да | Нет | Нет | FULL |
| 011 | Версионированный порядок приоритетов в policy snapshot | Context Builder, Dossier | Да | Нет | Нет | FULL / оценка PRODUCT_ONLY |
| 012 | Fact Record c source/date/snapshot/hash/freshness; только client-side read-only tools | Fact Gateway | Да | Нет | Нет | FULL |
| 013, 054, 055 | Canon в PostgreSQL/objects; retention per case до UA (§12.2); decision-моменты §8.2 совпадают с PLS-055 (доп. моменты обоснованы `PLS-026/053/064`, не молчаливые добавления) | Dossier/Evidence, Telegram | Да | Нет | Нет | FULL |
| 014, 015 | Версионированные conditions, evidence-to-decision chain | Dossier, SM, Closure | Да | Нет | Нет | FULL / 015 оценочно PRODUCT_ONLY |
| 016, 030, 047, 056 | Baseline snapshot, 0–100, сравнение, оценка цикла — запись входов и явного решения | Dossier, Decision Update | Да | Нет | Нет | FULL / оценочные ядра PRODUCT_ONLY |
| 017, 018 | Роль/run/модуль/сервис разделены; стадия ≠ агент; провайдерная изоляция | Agent Runtime, Gateways | Да | Нет | Нет | FULL |
| 022, 050, 051, 060 | Каждая правка — revision; materiality; doubt→material; carry-forward только владельцем | Revision Manager, Gate Engine | Да | Нет | Нет | FULL |
| 024, 025, 040 | Durable 24/72h timers, control deadline 3 раб. дня ≤ day 14, разные возвраты таймаутов | Scheduler, SM | Да | Нет | Нет | FULL |
| 026, 027, 061 | Gap taxonomy, validator запрещённых категорий, поштучное принятие | SA, Gate Engine | Да | Нет | Нет | FULL |
| 028 | Пять параметров отсрочки + fallback timer | Decision Update, Scheduler | Да | Нет | Нет | FULL |
| 029, 039, 058, 066 | Один Attempt/Session/Proposal/Record; пожизненный counter из ledger; эскалация | Gate Engine, Validator | Да | Нет | Нет | FULL |
| 031, 033, 034, 036, 057, 059 | Точный enum статусов и transition table; узкий `G25`; отказ после приёмки через Closure/DU (совп. с 03 §13) | State Machine, Dossier | Да | Нет | Нет | FULL |
| 032 | Stop justification record с обязательными полями | Closure Engine | Да | Нет | Нет | FULL |
| 035 | Точный `RESUMPTION_ONLY` + freshness/no-material guards | SM, Gate Engine | Да | Нет | Нет | FULL |
| 038 | Terminal lock + append-only late evidence | SM, Evidence | Да | Нет | Нет | FULL |
| 045 | Depth policy; триггеры только повышают глубину | Context Builder, Validator | Да | Нет | Нет | FULL |
| 048, 049 | Качественная уверенность; четыре уровня силы с основанием | Fact/Evidence Service | Да | Нет | Нет | FULL |
| 052 | Полная аттестация; сила по умолчанию ≤ умеренной | Evidence, Consent | Да | Нет | Нет | FULL |
| 053 | Linked Case: новый identity/counter, нулевое наследование | SM, Consent Engine | Да | Нет | Нет | FULL |
| 062 | Cycle Review не гейт; не сбрасывает counter, не продлевает day 14 | Orchestrator, Gate Engine | Да | Нет | Нет | FULL |

**Итог: 66/66 — FULL; MISSING — 0; CONFLICT — 0; PARTIAL — 0.** Решения `PLS-006/011/015/016/030/047/056` содержат оценочную продуктовую семантику; архитектура корректно не автоматизирует само ценностное решение (механизм — запись входов и явного решения Кирилла), что зафиксировано и в самой архитектуре после §16.

## 7. Deterministic Authority Audit

Атака велась по каждому запрещённому эффекту. Найденных путей нет.

| Атакуемый эффект | Попытка | Результат |
|---|---|---|
| Изменить состояние | Модельный текст как событие; injected «команда» в документе; Telegram free-text «да» | Провал: только typed application command после серверной валидации (§4); Orchestrator не принимает LLM-текст как событие (§3.1); free-text не связывается с Intent (§8.4) |
| Пройти guard | Structured output как «доказательство» | Провал: Structured Outputs прямо не считаются истинностью (§14.3); guards пересчитываются State Machine по canonical records |
| Создать Gate Record | Model proposal; synthesis-текст; format repair | Провал: record пишет только Gate Engine после validator `COMPLETE` (§5.4.6); format repair не создаёт record (§0, §13.2) |
| Разрешить расход | Повторный callback; изменённая сумма; billing limit как «разрешение» | Провал: one-time CAS + unique consent key (§11); binding к amount/currency/purpose/revision (§11); billing limit явно не полномочие (§13.4) |
| Создать Consent/Grant | Forwarded message; group chat; чужой account; provider tool | Провал: allowlist `from.id`/private chat, forwarded — только недоверенный материал (§8.1); hosted tools запрещены (§12.6.8) |
| Установить/перенести deadline | Contract-поле «дата начала»; повторная приёмка; Scheduler restart | Провал: set-once rule, immutable absolute deadline, synchronous DB-time guard (§10.3; совп. с 03 §10.3) |
| Переоткрыть терминальный кейс | Late evidence; админ-правка | Провал: terminal lock; late evidence append-only; admin mutation только через commands/ledger (§9.1, §12.1) |
| Наследовать полномочия | Linked case | Провал: пустые scopes нового case, anti-inheritance invariant (§4, §17 №15) |

Достаточность модульного разделения внутри одного runtime: архитектурно достаточна для запрета model-driven записей (модельный вывод — данные, единственный write-путь — валидируемые commands), но enforcement внутри Worker-процесса остаётся кодовой дисциплиной без специфицированных DB-грантов — см. `AAR-R1`. Это принятое следствие выбора монолита (`ADR-CANDIDATE-001`), требующее явной фиксации, а не дефект контура полномочий.

## 8. Role and Gate Independence Audit

| Проверка | Результат | Доказательство |
|---|---|---|
| Worker → Technical Reviewer | PASS | Разные runs/purposes; reviewer run не может иметь producer среди ancestors; контекст только из canonical snapshot (§6.1) |
| Technical Reviewer → System Acceptor | PASS | Собственные Attempt/Session/run/context/provider calls; TR Record неизменяем; SA не переписывает TR findings (§5.2, §6.1) |
| System Acceptor → Кирилл | PASS | UA только из серверного one-time Intent единственного configured user id (§6.1, §8.3) |
| production/verification purpose | PASS | `purpose` неизменяем; один Model Call не может принадлежать обеим сторонам (§5.1) |
| Ancestry checks | PASS | Отклонение Gate Proposal при совпадении actor с producer/merger/ancestor (§6.1) |
| Независимые Context Packages | PASS | Сборка из канона; запрет thread/session IDs производителя (§6.1) |
| Provider session isolation | PASS | Stateless-by-default; запрет reuse между ролями/кейсами/purposes; within-run исключение audited (§12.6.2–3) |
| Самоприёмка | PASS | Программный отказ Gate Engine (§6.1) |

**Атака Gate Review Session:** (а) покрытие 27 областей — детерминированный Plan из manifest, `NOT_YET_APPLICABLE` только с нормативным основанием, пустая ячейка запрещена (§5.4); (б) cross-area связи — отдельный реестр направленных edges, каждая назначена pass'у; разделение противоречия между двумя calls парируется передачей конкретных edges и полной cross-area matrix в synthesis; (в) сокрытие finding synthesis'ом — невозможно для зарегистрированных findings: validator сверяет полноту представления по ID immutable-записей (остаточный риск незарегистрированного finding — `AAR-N4`); (г) ложное заполнение Coverage Matrix моделью — Matrix ведётся детерминированным кодом по input/result hashes, а не самоотчётом модели; (д) timeout/partial/format repair/cost limit/новая редакция — соответственно: новый Model Call с применением максимум одного результата; `BLOCKED_COVERAGE_OR_BUDGET` без `PASS`; repair без новых findings; suspension с сохранённой Matrix; новая материальная редакция = новый Attempt (§5.4, §13.2); (е) ровно один Gate Record на Attempt — validator `COMPLETE` → один Proposal → атомарно один Record (§5.4.6, §19). Реалистичность 60-минутного бюджета для TR+SA — см. `AAR-N1`: механизм честен при недостатке времени (fail-closed, без обхода гейтов), эмпирическая достаточность отложена самим baseline (`PLS-064`, принятая некритичная калибровка акта `09`).

## 9. State/Time/Concurrency Audit

| Механизм | Результат | Основание |
|---|---|---|
| Optimistic locking / `case_version` | PASS | §9.3; конфликт не применяется автоматически к новому смыслу |
| Transaction-scoped locks | PASS | Row lock на критических командах (§9.3) |
| Единственный активный эксперимент | PASS | Уникальное ограничение (§9.3); `PRE_EXPERIMENT_DISMISSED` слот не занимает (совп. с `PLS-063`) |
| Idempotency по источникам | PASS | update_id, Intent, timer firing, run attempt, outbox, expense/action (§9.3) |
| Inbox/outbox | PASS | Одна транзакция событие+projection+outbox (§11.1) |
| Immutable `experiment_started_at` | PASS | Set-once + unique (§10.3) |
| Абсолютный день 14 | PASS | Synchronous DB-time guard, независим от Scheduler; блок новых action intents (§10.3); полное соответствие 03 §10.3 (обе строки таблицы) |
| Preparation interval union | PASS | Параллельность считается один раз; conservative no-undercount при crash (§10.1) |
| Crash reconciliation | PASS | Lease/heartbeat, консервативный учёт (§10.1); reclaim jobs, overdue scan (§15.3) |
| 45/60-минутные события | PASS | Идемпотентные `PREPARATION_BUDGET_CHECK`/`PREPARATION_LIMIT_REACHED` (§10.2); граница «первое предъявление UA» совпадает с `PLS-064` |
| Ожидания 24/72 ч | PASS | Durable timers (§10.4; совп. `PLS-024`) |
| Внешний контрольный срок | PASS | 3 раб. дня ≤ absolute deadline; calendar/timezone с Timer (§10.4; совп. `PLS-025`) |
| Пожизненный TR-counter | PASS | Агрегат по ledger; projection — кэш со сверкой (§6.1; совп. 02 §5.6, 05 §6) |
| Terminal lock | PASS | §9.1; выход запрещён, late evidence append-only |
| Linked cases / late evidence | PASS | §4, §16 (`PLS-038/053`) |

## 10. Persistence and Recovery Audit

Канонические projections, append-only records, revisions c parent/delta/hash, evidence objects c application-level SHA-256, durable timers, outbox, reconstruction/replay (recovery job со сверкой projection↔transitions↔hashes), backup (snapshot/PITR + независимый logical dump + object manifest/copy), restore validation (ежемесячный test restore) — определены (§9, §15.3).

Смоделированные отказы: частично восстановленная БД → recovery job блокирует кейс в diagnostic hold (lifecycle hold — `AAR-R2`); несовпавший object storage → integrity scan, потеря не маскируется metadata (§12.4, §11); повреждённая current projection → rebuild из snapshot+событий, расхождение → hold (§9.3); **дубли outbox и восстановленные pending Intents после restore → механизм не определён — `AAR-M1` (MAJOR)**. Это единственный существенный пробел контура persistence/recovery.

## 11. Telegram/Security/Data Audit

Webhook secret (constant-time, до парсинга), единственный `telegram_user_id` + private `chat.id` allowlist, opaque one-time callback (hash в БД, TTL, CAS, без PII/полномочий в payload), exact revision binding + content hash, expiry, повторное нажатие → прежний outcome, старая редакция → `superseded` no-op, forwarded/group/чужой account → security no-op без создания решения, независимая ротация webhook secret и bot token через maintenance mode с supersede pending Intents, потеря/редактирование Telegram-сообщения → пересоздаваемая projection — все проверки PASS (§8, §11). Прочее: секреты вне кода/промптов/логов, среды разделены, DLP/redaction перед Gateway, `UNTRUSTED_CONTENT`-канал против prompt injection, файловый контур (MIME/hash/quarantine/immutable keys), retention/deletion с tombstone (§12.1–12.5) — PASS. Единственное замечание контура — неполная privilege matrix (`AAR-R1`).

## 12. Infrastructure/Cost/Operability Audit

Изменяемые факты проверены по актуальным официальным источникам на дату аудита:

- **Railway PostgreSQL:** официальная документация (docs.railway.com/databases) прямо называет database templates «unmanaged services» с ответственностью владельца за backups, tuning, security, monitoring. Характеристика архитектуры (§14.2, `ARC-M1`) точна и не опирается на рекламные заявления; сравнение трёх операционных вариантов честно.
- **Cloudflare R2:** официальные docs (developers.cloudflare.com/r2/api/s3/api/) публикуют таблицы implemented/unimplemented S3-операций (например, S3 POST-upload не поддерживается). Подход §9.4 «проверенный поднабор + conformance tests, никакой полной совместимости» адекватен реальности; buckets приватны по умолчанию, публичный доступ требует явной настройки — согласуется с запретом public buckets.
- **OpenAI:** параметр `store:false` существует (Responses/Chat Completions); при этом действует ненулевая residual retention (abuse monitoring, feature-specific state), ZDR — отдельное одобряемое предложение. Формулировка §12.6.4 («не трактуется как нулевая общая retention») подтверждена официальной страницей data controls.
- **Anthropic:** политика API retention/training существует и изменяется во времени; архитектура не фиксирует устаревающие значения, а требует датированный Data Policy Registry с fail-closed preflight — корректная конструкция для изменяемого факта.

Python/FastAPI/aiogram/PostgreSQL jobs/три процесса из одного образа/Sentry — зрелый, реалистичный для одного разработчика стек без избыточной инфраструктуры; single-node без HA честно заявлен допущением с fallback на managed provider. Cost envelope (§13.2–13.3) покрывает все обязательные категории: `web/worker/scheduler`, PostgreSQL, storage, backup/PITR, monitoring, network/egress, test environment, модели, retries и Gate Review Sessions. Поведение при hard billing limit раскрыто честно: внутренний stop-порог ниже провайдерского, guards/deadlines переживают полный shutdown по immutable timestamps, «limit ≠ разрешение» зафиксировано явно (§13.3–13.4, §11). PASS; финансовая жизнеспособность конкретных тарифов сознательно вынесена в §20.2 до production.

## 13. Adversarial Scenario Matrix

25 обязательных сценариев + 3 дополнительных аудитора.

| № | Сценарий | Механизм | Результат |
|---|---|---|---|
| 1 | LLM изменяет состояние | Proposal-only, typed commands, серверные guards | DEFENDED |
| 2 | Worker принимает свою работу | purpose/ancestry checks | DEFENDED |
| 3 | Reviewer использует provider session Worker | Запрет reuse identifiers, canonical context | DEFENDED |
| 4 | SA использует скрытый контекст Reviewer | Собственные Session/run/context; provider-state не передаётся | DEFENDED |
| 5 | Большое досье теряет обязательную область | Coverage Plan 27 областей; пустая ячейка запрещена; validator | DEFENDED |
| 6 | Cross-area противоречие разделено между calls | Реестр направленных edges, назначение pass'ам, полная matrix в synthesis | DEFENDED |
| 7 | Synthesis скрывает finding | Validator сверяет полноту по immutable finding IDs | DEFENDED (residual: незарегистрированное finding — AAR-N4) |
| 8 | Cost limit в середине Gate Review Session | `BLOCKED_COVERAGE_OR_BUDGET`; suspension; `PASS` невозможен | DEFENDED |
| 9 | Session после паузы продолжает изменённую revision | Binding к revision hash; новая материальная revision = новый Attempt | DEFENDED |
| 10 | Повторный callback дважды разрешает расход | One-time CAS + unique consent key | DEFENDED |
| 11 | Старый Intent к новой редакции | Revision/hash guard; `superseded` no-op | DEFENDED |
| 12 | Две команды одновременно | Row lock + `case_version` conflict | DEFENDED |
| 13 | Model timeout — два применённых результата | Отдельные Model Calls, применяется максимум один optimistic command | DEFENDED |
| 14 | DB commit без Telegram notification | Transactional outbox | DEFENDED |
| 15 | Scheduler не работал в день 14 | Synchronous DB-time guard независим от timer | DEFENDED |
| 16 | Новая revision/пауза сбрасывает preparation/TR-counter | Непрерывный interval ledger; counter из ledger | DEFENDED |
| 17 | Linked case наследует Authority Grant | `case_id`-scope, пустые новые scopes, invariant test | DEFENDED |
| 18 | Terminal case получает late evidence | Terminal lock; append-only запись без смены статуса | DEFENDED |
| 19 | Evidence существует только в prompt | Требование Evidence Record + object/hash/provenance либо полной аттестации | DEFENDED |
| 20 | Metadata есть, файл потерян | Integrity scan; потеря = Event/Defect; Closure блокируется | DEFENDED |
| 21 | R2 не поддерживает операцию | Pre-production conformance; adapter readiness fail-closed | DEFENDED |
| 22 | Restore возвращает старые pending outbox/timers | Timers — idempotent firing по сохранённому `due_at`: DEFENDED; **outbox/Decision Intents — механизм реконсиляции не определён** | **PARTIAL → AAR-M1** |
| 23 | Provider switch меняет семантику structured result | Native adapters, pinned contract, conformance fixtures, повторная semantic validation | DEFENDED |
| 24 | Недоверенный документ вызывает tool | `UNTRUSTED_CONTENT`-канал; tool исполняет только Gateway после allowlist | DEFENDED |
| 25 | Чужой account/group/forwarded создаёт решение | Webhook secret + allowlist; security no-op | DEFENDED |
| 26* | Non-material revision опубликована во время приостановленной session | Session привязана к exact revision; перенос — только carry-forward владельцем гейта после Record (`PLS-050`) | DEFENDED |
| 27* | Ошибка/инъекция кода в Worker-процессе с общими credentials | Кодовая дисциплина монолита; DB-гранты per process не специфицированы | PARTIAL → AAR-R1 (принятое следствие монолита, требует фиксации) |
| 28* | Расхождение projection/ledger «замораживает» кейс без правил выхода | Diagnostic hold объявлен, lifecycle не определён | PARTIAL → AAR-R2 |

Итог: 25/25 обязательных сценариев рассмотрены; 24 полностью защищены, один (№22) частично — источник `AAR-M1`.

## 14. Residual Risks and Required ADR

1. Коррелированная модельная ошибка при одном провайдере для Worker и Reviewer — честно раскрыта (§6.1); опция alternate-provider review отложена до измерений (`ADR-CANDIDATE-005/006`).
2. Незарегистрированное модельное finding (AAR-N4) — неустранимый вероятностный остаток; смягчается полнотой coverage и seeded-contradiction тестами (`ADR-CANDIDATE-015`).
3. Достаточность 60 минут для полных TR+SA sessions (AAR-N1) — калибровка на двух пилотных циклах, принятая baseline.
4. Точность пользовательской аттестации действий и self-report времени (`PLS-008/052`) — продуктово принятая граница; сила evidence ограничена.
5. Single-node без HA, доверие к host clock, средняя owner-нагрузка unmanaged PostgreSQL — раскрыты; закрываются `ADR-CANDIDATE-012/013` и restore rehearsal до production.
6. Обязательные к последующему утверждению ADR: `ADR-CANDIDATE-005–009, 012–015` (перечень §18/§20.4 архитектуры полон и согласуется с находками; AAR-M1 добавляет обязательное содержание в `ADR-CANDIDATE-013`/Runbook).

## 15. Architecture Readiness Decision

`11-technical-architecture-v1.md` **готов к принятию как технический архитектурный baseline при закрытии `AAR-M1` и маршрутизации `AAR-R1`/`AAR-R2`** в поименованные документы следующей стадии. Переход к Data Model and Persistence Specification, State/Gate/Authority Technical Specification, Agent and Context Contracts, Integration/API Specification, Security и Operations Specifications и Verification Plan допустим после этого; заявленный в §20.5 порядок документов корректен. Настоящий аудит **не является пользовательской приёмкой и не разрешает переход к task breakdown или коду**; операционные предусловия §20.2 (оплата/доступность/data policy провайдеров, датированный cost envelope, restore rehearsal, storage conformance) сохраняют силу независимо от вердикта.

## 16. Требуемые решения Кирилла

1. **По `AAR-M1`:** выбрать маршрут закрытия — точечная редакция архитектуры (v1.1 с изменением только §15.3/§8) либо обязательный, явно поименованный пункт в Deployment and Operations Runbook и Data Model/Persistence Specification. До выбранного закрытия production restore-процедура не считается определённой.
2. **По `AAR-R1` и `AAR-R2`:** подтвердить отнесение закрытия в Security Specification / Data Model Specification (`AAR-R1`) и State/Gate Technical Specification + Runbook (`AAR-R2`) как обязательных пунктов их приёмки.
3. **По `AAR-N1`:** подтвердить, что вопрос объёма TR Coverage Plan (полные 27 областей против технически-обусловленного подмножества без ослабления SA-полноты) входит в `ADR-CANDIDATE-015` и решается по данным пилотной калибровки.
4. **Принять реестр остаточных рисков** раздела 14 как раскрытый.
5. **Провести пользовательскую приёмку** архитектурного baseline (с учётом выбранного маршрута закрытия `AAR-M1`) отдельным актом; настоящий аудит её не заменяет.

---

*Аудит выполнен строго в верификационной роли: исходные девять файлов не изменялись; v2 архитектуры, ADR, схемы данных, API, промпты, task breakdown и код не создавались.*
