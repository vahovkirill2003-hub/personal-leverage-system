# Personal Leverage System
## Data Model and Persistence Specification v0.3

**Статус:** кандидат на пользовательскую приёмку; не принят. После приёмки заменяет `14-data-model-persistence-spec-v0.2.md` в части трёх технических errata схемы — `pre_experiment_dismissal` (§3.1), `state_transition.from_state` (§3.3) и `command_receipt` (§3.3, §4). В остальном идентична v0.2; v0.1 и v0.2 сохраняются и не редактируются. Продуктовая семантика не изменена, нового `PLS-ID` не требуется  
**Дата:** 14 августа 2026  
**Основание:** архитектурный baseline `11-technical-architecture-v1.1.md` (168448 байт, `faf6e5…30c22`), акт `13-architecture-baseline-acceptance-v0.md` (8073 байта, `0d9454…79aa`), продуктовый baseline v2 и решения `PLS-001–PLS-066`; errata `PAV-2` отчёта `24-independent-package-audit-v0.md` §2, принятая Кириллом (`24` §5 п. 1); технические errata `DMV-4`–`DMV-6`, выявленные при сверке `17 v0.2` §§3.4 и 3.7 с фактической схемой  
**Область:** логическая модель данных, ключи и идентификаторы, database-инварианты и constraints, реестр idempotency keys, политика миграций, recovery projections и данные post-restore реконсиляции, retention, матрица DB-привилегий процессов (часть закрытия `AAR-R1`)  
**За рамками:** DDL/SQL-код, конкретные типы конкретной версии PostgreSQL, индексная оптимизация, промпты, API, task breakdown, изменение baseline

---

## 0. Нормативный статус

Спецификация реализует, но не изменяет архитектуру v1.1 и продуктовый baseline. Расхождение с ними — дефект спецификации. Все имена сущностей и полей — логические; физические имена фиксируются при реализации без изменения семантики. Все timestamps — UTC (`timestamptz`); отображение — в configured timezone кейса.

Обязательства настоящего документа из акта `13`: часть закрытия `AAR-R1` (раздел 12) и данные post-restore реконсиляции `AAR-M1` (раздел 10.3). Приёмка документа без этих разделов недопустима.

## 1. Принципы модели

1. **Append-only история, изменяемые projections.** Исторические сущности (раздел 3, столбец «Изм.») никогда не получают UPDATE/DELETE обычным workflow; текущее состояние — отдельные projection-строки с optimistic `case_version`.
2. **Один источник истины записи** (`PLS-046`): содержательная запись живёт в одном месте; представления ссылаются по id.
3. **Content addressing.** Досье-редакции, артефакты и context packages имеют SHA-256 content hash; объекты в storage адресуются immutable key, включающим hash.
4. **Полномочия — только записями.** Consent/Grant/Gate Record существуют как строки с точной привязкой к `revision_id` + hash; отсутствие строки означает отсутствие полномочия (fail closed).
5. **Время — только из БД.** Guards читают `now()` транзакции; сохранённые `due_at`/`deadline` не пересчитываются.

## 2. Идентификаторы и ключи

- Все первичные ключи — UUIDv7 (монотонность по времени для append-only таблиц), кроме указанных естественных ключей.
- `revision_number` — монотонный целочисленный счётчик внутри `case_id`, уникален парой (`case_id`, `revision_number`).
- Внешние идентификаторы (Telegram `update_id`, `message_id`, provider ids) хранятся как атрибуты, никогда как первичные ключи доменных сущностей.
- Секреты и токены хранятся только как SHA-256 hash (`decision_intent.token_hash`, `model_call.provider_state_id_hash`).

## 3. Логическая модель

Формат: сущность → ключевые поля → constraints. «Изм.»: A = append-only; P = projection (optimistic); I = immutable после публикации.

### 3.1. Ядро кейса

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `case` | id; created_at; current_state; current_status (null вне состояний, имеющих продуктовый статус `PLS-031`); case_version; current_revision_id→dossier_revision; depth_level (min/std/elevated); timezone; terminal_locked_at; diagnostic_hold (bool, reason_event_id) | `case_version` строго возрастает; CHECK: current_status ∈ {CLOSED_COUNTED, CLOSED_NOT_COUNTED, REJECTED_BEFORE_EXECUTION, PAUSED_USER, PAUSED_EXTERNAL} либо null; CHECK: current_status задан ⇔ current_state является состоянием с продуктовым статусом `PLS-031`, и тогда current_status = current_state; CHECK: terminal_locked_at задан ⇔ current_status ∈ {CLOSED_COUNTED, CLOSED_NOT_COUNTED, REJECTED_BEFORE_EXECUTION} — pause-статусы terminal lock не создают; при terminal_locked_at любые UPDATE кроме diagnostic-полей отклоняются rule-ом | P |
| `experiment_anchor` | case_id (PK, FK); experiment_started_at; accepted_duration_days (3–14); planned_deadline_at; absolute_deadline_at | Отдельная таблица реализует set-once (`PLS-065`): INSERT-only, UPDATE/DELETE запрещены database rule; CHECK `absolute_deadline_at <= experiment_started_at + interval '14 days'`; единственная строка на case | I |
| `active_experiment_slot` | user_scope (константа single-user); case_id | UNIQUE(user_scope): физически невозможен второй активный эксперимент; строка удаляется при терминале/`PRE_EXPERIMENT_DISMISSED` | P |
| `pre_experiment_dismissal` | id; **case_id → `case`, NOT NULL, UNIQUE**; original_request_ref; dismissed_at; stage (INTAKE/CLARIFICATION/FACT_UNKNOWN_MAPPING); reason (закрытый enum пяти оснований `PLS-063`); applied_rule; actual_system_time_sec; user_confirmation_event_id (null, обязателен только при зависимости от выбора); no_external_action, no_expense, no_obligation (bool, все true); disposition | **Каноническая отметка административного прекращения кейса:** FK на `case`, UNIQUE(case_id) — не более одного disposition на кейс. Статуса и состояния по-прежнему не создаёт (`PLS-063`), но её существование, а не отсутствие строки slot, является доказательством прекращения; CHECK все три «отсутствия» = true | A |

### 3.2. Досье и редакции

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `dossier` | id; case_id (UNIQUE) | 1:1 с case | P |
| `dossier_revision` | id; dossier_id; revision_number; parent_revision_id; content_hash; materiality (material/non_material/undetermined); delta_ref; created_by_run_id; published_at | UNIQUE(dossier_id, revision_number); UNIQUE(dossier_id, content_hash); `undetermined` трактуется гейтами как material (`PLS-051`); после published_at — immutable rule | I |
| `area_record` | id; dossier_id; area_id (1–27); canonical_record_ref; not_applicable (bool) + normative_basis | 27 областей — логические (`PLS-043`): area_record ссылается на канонические записи, не дублирует; NOT NULL basis при not_applicable | P→I в составе revision snapshot |
| `carry_forward` | id; gate_type; source_gate_record_id; source_revision_id; target_revision_id; full_delta_ref; materiality_evidence_ref; scope; exclusions; owner_actor (роль/Кирилл); created_at | Владелец соответствует gate_type (`PLS-050/060`); запрещённые расширения проверяются Gate Engine до INSERT; immutable | A |

### 3.3. События и переходы

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `event` | id; case_id (nullable: null допустим только для security/system событий вне кейса, например отклонённый чужой callback); type; actor_type (user/system/agent_run/timer/admin); actor_id; occurred_at; recorded_at; causation_id→event; correlation_id; payload_ref | Append-only rule; causation допускает null только для корневых входов; security event хранит минимальный состав без содержимого сообщения (§8.1 архитектуры) | A |
| `state_transition` | id; case_id; event_id; from_state (**NULL допустим только для genesis-перехода**); to_state; guard_results_ref (правило, версия, факты, вердикт по каждому guard); case_version_before/after | Пара (case_id, case_version_after) UNIQUE; запись только в транзакции, обновляющей `case`; CHECK genesis: `(case_version_before = 0 AND case_version_after = 1 AND from_state IS NULL AND to_state = 'INTAKE') OR (case_version_before > 0 AND from_state IS NOT NULL AND case_version_after = case_version_before + 1)` | A |
| `inbox` | bot_id; update_id; received_at; processing_result_ref | PK(bot_id, update_id) — дедупликация Telegram | A |
| `command_receipt` | id; command_type; idempotency_key; case_id (nullable — для создающих команд кейса ещё нет); actor_type; received_at; outcome_ref (ссылка на созданные записи либо на отказ); outcome_kind (applied/conflict/rejected) | **UNIQUE(command_type, idempotency_key)** — доменная идемпотентность любой команды реестра `17` §1.2 независимо от транспорта; повтор возвращает сохранённый outcome и второго доменного эффекта не создаёт; append-only | A |
| `outbox` | id; logical_notification_id; case_id; kind (informational/decision); payload_ref; created_tx_event_id; status (pending/delivering/delivered/terminal_error); attempts; delivered_at; telegram_message_id | UNIQUE(logical_notification_id); запись в одной транзакции с событием; delivery-поля — единственные изменяемые | P (delivery), A (создание) |

### 3.4. Гейты

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `gate_attempt` | id; case_id; gate_type (TR/SA/UA); mode (INITIAL/REVALIDATED/RESUMPTION_ONLY для UA); revision_id; content_hash; criteria_version; status (open/blocked_coverage_or_budget/completed) | UNIQUE открытого attempt на (case_id, gate_type, revision_id); revision после старта не заменяется | P до completed |
| `gate_review_session` | id; gate_attempt_id (UNIQUE); role; purpose='verification'; policy_versions; call_count_limit; cost_limit; status | Ровно одна session на attempt (TR/SA); привязка к exact revision через attempt | P |
| `coverage_cell` | id; session_id; element_kind (area/edge); element_id; assigned_pass; input_hashes; criterion; outcome (CHECKED_OK/FINDING/NOT_APPLICABLE/INCONCLUSIVE, null=не заполнено); finding_ids; validation_status | UNIQUE(session_id, element_kind, element_id); validator требует отсутствие null и INCONCLUSIVE для PASS | P→I при завершении session |
| `finding` | id; session_id; pass_call_id; class; severity; affected_refs; criterion; counterexample; created_at; superseded_by_finding_id | Immutable; исправление классификации — новая связанная запись | A |
| `gate_record` | id; gate_attempt_id (UNIQUE); gate_type; mode; case_id; revision_id; content_hash; result (закрытые enum по 05 §§6/…); actor_run_id / user_decision_intent_id; criteria_version; context_package_hash; defect_ids; gap_ids; created_at | UNIQUE(gate_attempt_id) — ровно один record на attempt; CHECK: result из допустимого множества своего gate_type; INSERT только при coverage validator `COMPLETE` (application invariant, тестируемый) | A |
| `defect` | id; case_id; source_gate_record_id; class (критический/обязательный/раскрываемый пробел/NOTE по 05 §3); criterion; affected_refs; status_current + история событиями | Исходная запись immutable | A+P(status) |
| `tr_return_counter` (view) | case_id; count = SELECT count(*) FROM gate_record WHERE case_id=… AND result='TECH_REVIEW_RETURNED' | Не таблица: вычислим из ledger (`PLS-066`); кэш в case-projection сверяется с view | — |

### 3.5. Полномочия и решения Кирилла

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `decision_intent` | id; token_hash (UNIQUE); case_id; revision_id; content_hash; kind (UA/action/expense/gap/extra_time/review_stop/closure_obligation/decision_update/linked_case); subject_refs; amount, currency, purpose (для expense); shown_risks_ref; allowed_responses; created_at; expires_at; nonce; status (pending/consumed/expired/superseded); consumed_at; outcome_ref | CAS-переход pending→consumed единственно допустим для исполнения; UNIQUE(idempotency_key); expense-поля NOT NULL при kind=expense | P (status), иначе I |
| `consent` | id; case_id; decision_intent_id (UNIQUE); revision_id+hash; subject; shown_risks_ref; decided_at; revoked_by_consent_id | Append-only; отзыв — новой записью | A |
| `authority_grant` | id; case_id; consent_id; scope (action_ref, data, addressee, amount/currency/purpose); valid_until; status (active/consumed/revoked/inapplicable) + события | Scope не расширяется UPDATE-ом (immutable columns rule); привязка к exact revision через consent | A+P(status) |
| `expense` | id; case_id; request (amount, currency, purpose, action_ref, risk, term); authorization_grant_id; actual_fact_ref | Изменение любого поля request = новый expense (`PLS-009/023`); UNIQUE consent на request | A |
| `external_action` | id; case_id; contract_ref (полный Action Contract); authority_grant_id; planned_version; executed_at; executed_by='Кирилл' (v1); evidence_links | План версионируется новыми строками; факт append-only | A |
| `workload_ledger` | id; case_id; week_key; reported_minutes; source_ref | Guard 5 ч/нед (`PLS-008`) по агрегату week_key; определение недели — раздел 13, решение Кирилла | A |

### 3.6. Факты и доказательства

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `fact_record` | id; case_id; kind (fact/assumption/unknown/recommendation); statement_ref; source; retrieved_at; snapshot_object_id; freshness; confidence (высокая/средняя/низкая/не оценена, `PLS-048`); superseded_by | Версионируется новыми строками | A |
| `evidence` | id; case_id; provenance; source; captured_at; object_id; content_hash; strength (сильное/умеренное/слабое/недостаточное) + rationale (`PLS-049`); attestation_ref (при отсутствии независимого следа, `PLS-052`, strength ≤ умеренное CHECK); links | Immutable; интерпретация — отдельными версионируемыми записями | A |
| `artifact` | id; object_key (UNIQUE, включает hash); sha256; size; mime; quarantine_status; retention_class; created_at | Перезапись object_key запрещена (и в storage §9.4, и UNIQUE здесь) | A |
| `late_evidence` | id; terminal_case_id; evidence_id; received_at | Никаких FK-побочных обновлений case (`PLS-038`); guard `G26` | A |
| `linked_case` | id; old_case_id; new_case_id; relation_type; old_question_ref; new_question_ref; baseline_difference_ref | Никакие grants/gates/counter не копируются: отсутствие механизма копирования + anti-inheritance тест | A |
| `evidence_retention_policy` | case_id; состав; форма; цель; trigger (срок/событие) | Обязательна до первого UA (`PLS-054`): наличие полной политики входит в предусловия первого User Acceptance и проверяется в составе `G08_FULL_USER_ACCEPTED` (`03` §5) в момент команды; отсутствие политики отклоняет первый UA, а не создаёт отдельный гейт | P до UA, затем I |

### 3.7. Время

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `timer` | id; case_id; kind (reminder_24h/pause_72h/external_control/day_14/prep_45/prep_60/deferred_decision/…); due_at (fixed); calendar_rule + timezone (для business-day); status (armed/claimed/fired/cancelled); last_claim_at; claim_lease; firing_idempotency_key (UNIQUE) | `due_at` не изменяется без разрешённого продуктового события (rule + событие-основание); scheduler выбирает по сохранённому due_at | P(status) |
| `preparation_interval` | id; case_id; started_at; ended_at (null=открыт); job_or_run_id; stage_bucket; lease_heartbeat_at | Бюджет = длина union пересекающихся интервалов (view `preparation_budget`); при crash закрытие по последнему heartbeat консервативно (не занижая); правая граница — первое предъявление UA | A (закрытие ended_at — единственный UPDATE) |
| `time_grant` | id; case_id; granted_minutes; consent_id | Аддитивен: не обнуляет consumed (`PLS-064`) | A |

### 3.8. Агентный контур

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `context_package` | id; role; case_id; manifest (selected refs, redactions); policy_version; package_hash; classification | Immutable; хранится в минимально допустимом объёме | I |
| `agent_run` | id; case_id; role; purpose (production/verification, immutable column); attempt; context_package_id; input_revision_id; allowed_tools; budget; deadline; parent_run_id; producer_run_ids; status; result_artifact_id; validation_result | CHECK: глубина ≤1 и ≤2 детей (application invariant + тест); reviewer run не имеет producer в ancestors (проверка Gate Engine до записи record) | A(lifecycle)+P(status) |
| `model_call` | id; agent_run_id; session_id/pass; provider_adapter; model_alias; returned_model_id; contract_version; context_package_hash; stateless (bool); provider_state_id_hash+reason+expiry (при разрешённом продолжении); data_policy_version+effective_date; tool_permissions/proposals/executions_ref; store_params; started/ended_at; stop_reason; usage; cost_record_id; response_hash; validation_result; applied (bool) | На attempt применяется максимум один applied=true (partial UNIQUE); production и verification несовместимы через run.purpose | A |
| `cost_record` | id; scope (model_call/process/db/storage/backup/monitoring/network/test); usage; provider_charge_estimate/actual; tariff_snapshot_date; billing_period | Пересчёт исторических записей новой ценой запрещён (immutable) | A |
| `price_catalog` / `data_policy_registry` / `cost_envelope` | по §12.6.5/§13.2–13.3 архитектуры: датированные записи с source и effective date | Только INSERT новых версий | A |

### 3.9. Закрытие

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `closure` | id; case_id; actions_ref; resources_ref; evidence_ref; obligations_ref; stop_justification_ref (`PLS-032` поля NOT NULL при stop); preliminary_countability | Immutable после completion; исправление — через новую revision | I |
| `decision_update` | id; case_id; before_after_ref; explicit_user_decision (основание, изменение уверенности 0–100 `PLS-047`, ответственный, следующий шаг); cycle_score_0_10, repeat_readiness, user_time (`PLS-056`); deferred (5 параметров NOT NULL при отсрочке, `PLS-028`) | Immutable accepted record | I |

### 3.10. Conditions, Review/Stop и Cycle Review (добавлено v0.1)

| Сущность | Поля | Constraints | Изм. |
|---|---|---|---|
| `condition_record` | id; case_id; kind (success/review/stop); statement_ref; interpretation_rules_ref; fixed_in_revision_id; superseded_by | Версионируется (`PLS-014`); для начатого эксперимента изменение kind/statement — материальное (`PLS-022`); зафиксированность до Execution проверяется guard-ом первого UA | A |
| `review_stop_record` | id; case_id; trigger (condition_id/timer_id/user_event_id); outcome (resume_resumption_only/revalidate/stop/…); justification_ref (для stop — поля `PLS-032` NOT NULL); waiting_ref | Привязан к событию и текущей revision; append-only | A |
| `cycle_review_record` | id; case_id; trigger_basis (повтор корневого дефекта/нет прогресса/угроза лимиту, `PLS-062`); history_ref; root_cause; new_vs_repeated_ref; resolution_owner; proposed_outcome (исправление/сужение/данные/ресурс/компромисс/Closure); user_decision_ref | Не гейт: запись не создаёт Gate Record, не сбрасывает counter, не меняет deadlines (инварианты раздела 5/приложения A) | A |

## 4. Реестр idempotency keys

| Вход | Ключ | Гарантия |
|---|---|---|
| Любая команда реестра `17` §1.2 | `command_receipt` (command_type, idempotency_key) UNIQUE | Один доменный эффект; повтор возвращает сохранённый outcome |
| Telegram update | (bot_id, update_id) | Один processing result транспортного входа (не заменяет доменный ключ команды) |
| Callback | decision_intent.token_hash + CAS pending→consumed | Один outcome, повтор возвращает прежний |
| Timer firing | timer.firing_idempotency_key | Однократное доменное срабатывание |
| Agent Run attempt | (case_id, role, gate_attempt_id?, attempt) | Один зарегистрированный run |
| Model apply | partial unique applied=true per attempt | Максимум один применённый результат |
| Outbox | logical_notification_id | Повтор — транспортный, не доменный |
| Expense/Action intent | intent id, action-owned key (не model-call-owned) | Повтор модели не создаёт действие |
| 45/60-события | (case_id, budget_epoch, kind) | Однократность на исходный бюджет/tranche |

## 5. Database-инварианты (enforced rules)

1. Set-once `experiment_anchor` (INSERT-only) — `PLS-065`.
2. UNIQUE active_experiment_slot — один активный эксперимент.
3. Terminal lock: rule на `case` при terminal_locked_at — `PLS-031/037/038`.
4. Один `gate_record` на `gate_attempt` (UNIQUE) — §5.4.6 архитектуры.
5. Append-only rules на все A-сущности (REVOKE UPDATE/DELETE + trigger-запрет).
6. `dossier_revision` immutable после публикации — `PLS-050`.
7. Expense: request-поля immutable; изменение = новая строка — `PLS-009/023`.
8. `decision_intent` единственный CAS-переход в consumed.
9. `absolute_deadline_at` CHECK ≤ старт + 14 дней; никакой UPDATE — `PLS-037`.
10. `purpose` agent_run immutable column.
11. Статусная модель case: current_status только из пяти значений `PLS-031`; `PRE_EXPERIMENT_DISMISSED` в enum статусов отсутствует — `PLS-063`.
12. `pre_experiment_dismissal`: FK на `case` и UNIQUE(case_id) — не более одного административного прекращения на кейс, и оно всегда адресно (`DMV-4`).
13. `state_transition`: genesis-CHECK раздела 3.3 — единственный переход с `from_state IS NULL` есть создание кейса (`case_version_before = 0`, `case_version_after = 1`, `to_state = 'INTAKE'`); для всех прочих `from_state` обязателен и версия растёт ровно на единицу (`DMV-5`).
14. `command_receipt`: UNIQUE(command_type, idempotency_key) — доменная идемпотентность команд не зависит от транспорта; таблица append-only, права ровно у исполнителя команд (`pls_worker`: SELECT + INSERT; UPDATE/DELETE отклоняются самой БД; `pls_web` прав не имеет — раздел 12). Проверяется T04 «злонамеренный worker»: разрешённые SELECT/INSERT проходят, UPDATE и DELETE отклоняются (`DMV-6`).

Инварианты, не выразимые constraint-ами (ancestry, coverage-полнота, materiality), закрепляются за engine-ами и обязательными property-тестами Verification Plan; их перечень — приложение A.

## 6. Слои хранения и projections

Соответствуют §9.2 архитектуры. Перестраиваемые представления: `preparation_budget` (union-длина), `tr_return_counter`, Telegram-summary payloads, cost aggregates, coverage progress. Ни одно производное представление не читается guard-ами полномочий напрямую — guards читают канонические строки; кэш в `case` сверяется recovery job.

## 7. Object storage metadata

`artifact.object_key` = `{env}/{case_id}/{sha256}/{semantic_name}`; metadata round-trip: content type, size, application hash, retention tag. Каждая запись объекта завершается `HeadObject` + повторной SHA-256 (§9.4). Backup-манифест: датированная таблица `object_export_manifest` (object_key, sha256, size, exported_at, target, verified).

## 8. Политика миграций

Backward-compatible, expand/contract; отдельный release-step до переключения приложения; CI dry-run на копии схемы; destructive-миграция — только с backup, restore-точкой и отдельным ADR; database rollback не выполняется — исправление forward. Версия схемы читается readiness-probe.

## 9. Retention и удаление

Retention управляется `evidence_retention_policy` и `artifact.retention_class`. Удаление содержимого — только авторизованной процедурой: объект удаляется/криптостирается, в БД остаётся tombstone (id, основание, время, hash) без содержимого. Terminal-записи не оправдывают бессрочное хранение лишних персональных данных (§12.5).

## 10. Recovery projections

### 10.1. Штатное восстановление процесса
Перезапуск без потери БД: web продолжает inbox; worker reclaim просроченных leases; scheduler сканирует overdue по `due_at`; notifier — pending outbox. Никаких пересчётов времени.

### 10.2. Rebuild и integrity
Recovery job сверяет: `case` против последнего `state_transition` (case_version, state); `current_revision_id` против max published revision; кэш counter против view; hashes revisions/artifacts. Расхождение → `diagnostic_hold` (событие с основанием), без продуктового статуса.

### 10.3. Post-restore реконсиляция (данные для §15.3 v1.1)
После восстановления БД до возобновления decision-потока выполняются запросы, определяемые здесь нормативно:
1. `UPDATE decision_intent SET status='superseded' WHERE status='pending'` + событие-основание restore_id; перевыпуск актуальных Intents новыми строками.
2. Outbox: строки `pending/delivering` анализируются по logical_notification_id; decision-kind не переотправляются до п.4, informational — допускают транспортный дубль.
3. **Divergence report** (материализуемая запись `restore_divergence_report`): restore_point; failure_point (последняя известная активность из внешних свидетельств); список кейсов в состояниях ожидания решений; открытые timers и deadlines с due_at в утраченном окне; последние consents/expenses/gate_records до restore_point; поле для известных Кириллу событий утраченного окна.
4. Событие `RESTORE_RESUME_CONFIRMED` c decision_intent Кирилла — единственный разблокирующий выпуск новых decision messages.
Ежемесячный test restore прогоняет пп. 1–3 и фиксирует результат в `restore_test_record`.

## 11. Traceability (ключевые привязки)

`PLS-065`→`experiment_anchor` set-once; `PLS-066`→`tr_return_counter` view; `PLS-031/063`→enum статусов + `pre_experiment_dismissal`; `PLS-050/051`→revision immutability + materiality default; `PLS-009/023`→expense immutable request + UNIQUE consent; `PLS-024/025/040`→timer kinds + calendar_rule; `PLS-064`→`preparation_interval` union + `time_grant` аддитивность; `PLS-037/038`→terminal rule + `late_evidence`; `PLS-053`→`linked_case` без копирования; `PLS-046`→canonical_record_ref; `PLS-047–049/052/054/056`→поля разделов 3.6/3.9. Полная матрица — приложение B к приёмке (строится проверяющим).

## 12. DB-привилегии процессов (часть закрытия `AAR-R1`)

| DB-роль | Процесс | Права |
|---|---|---|
| `pls_web` | web | INSERT `inbox`; SELECT projections/read models; EXECUTE только application commands постановки (enqueue): без прямых INSERT в gate_record/consent/authority_grant/experiment_anchor и **без каких-либо прав на `command_receipt`** — доменные команды, включая `SubmitOpportunity`/R01, исполняет worker (архитектура §1.1: web принимает webhook и ставит задание, не исполняет команду) |
| `pls_worker` | worker | Полный набор application commands через engine-модули: INSERT доменных A-таблиц, UPDATE projections; **SELECT и INSERT `command_receipt`** — чтение сохранённого outcome при повторе и запись нового; UPDATE и DELETE по `command_receipt` не выданы и дополнительно запрещены append-only rule (§5 п. 5, 14); без DDL; без DELETE (кроме retention-процедуры отдельной ролью) |
| `pls_scheduler` | scheduler | SELECT/UPDATE `timer` (claim), INSERT событий timer-firing и enqueue jobs; без записи в полномочия и гейты |
| `pls_retention` | ручная процедура | Единственная роль с ограниченным DELETE по retention-процедуре, с tombstone |
| `pls_migrator` | release-step | DDL; недоступна runtime-процессам |

**Явная intra-process trust assumption:** внутри worker-процесса разделение engine-модулей — кодовая дисциплина; `pls_worker` технически способен писать любые доменные строки. Компенсации: append-only/UNIQUE/set-once rules уровня БД (раздел 5), обязательные property-тесты, отсутствие у model-вызовов какого-либо пути кроме возврата данных. Полное закрытие `AAR-R1` (угрозы компрометации кода) — Security Threat Model Specification.

## 13. Открытые решения для приёмки

Единственное продуктово-значимое решение (закрывает `AAR-N3`): **определение «недели» для лимита `PLS-008` (5 часов внешних действий).** Предлагается: календарная ISO-неделя (понедельник–воскресенье) в configured timezone кейса — проще для самоконтроля и однозначна в отчётах. Альтернатива: скользящее окно 168 часов — строже, но труднее для ручной сверки. Требуется ваш выбор при приёмке; выбранное правило фиксируется в `workload_ledger.week_key`.

## 14. Приложение A. Инварианты вне constraints (обязательные тесты)

Ancestry/самоприёмка; coverage-полнота перед gate_record; глубина делегирования ≤1/≤2; materiality-презумпция; запрет копирования при linked_case; union-подсчёт бюджета при параллелизме и crash; недостижимость прямого `CLOSED_NOT_COUNTED` вне Decision Update; блок внешних действий после absolute deadline из любого нетерминального состояния.

Добавлено v0.3: **отклонение любой изменяющей команды по кейсу, для которого существует `pre_experiment_dismissal`.** Constraint-ом это не выражается (условие межтабличное), поэтому проверка принадлежит resolver-у (`17 v0.2` §3.4) и обязательному тесту класса T20: после disposition попытка `INTAKE_ACCEPTED`, `CLARIFICATION_COMPLETED`, `MAP_COMPLETED` и любой другой изменяющей команды по тому же кейсу должна отклоняться без частичных эффектов.

## 15. Changelog v0.1 (проверка по контуру `15`)

| Находка | Severity | Закрытие |
|---|---|---|
| DMV-1 — нет versioned-носителя success/review/stop conditions и записей их обработки (`PLS-014`, область 22) | MINOR | Раздел 3.10: `condition_record`, `review_stop_record` |
| DMV-2 — нет канонической записи Cycle Review (`PLS-062`) | MINOR | Раздел 3.10: `cycle_review_record` с инвариантом «не гейт» |
| DMV-3 — не оговорены security events вне кейса | MINOR | §3.3 `event`: nullable case_id с ограничением и минимальный состав |

Проверка выполнена той же ролью, что авторство черновика, — в соответствии с принятым отклонением `15-spec-stage-process-deviation-v0.md`; повторная независимая проверка входит в обязательный сводный аудит пакета перед task breakdown.

## 16. Changelog v0.2 (редакционные правки)

Обе правки редакционные: они приводят текст в соответствие уже принятым решениям и не изменяют продуктовую семантику. Новых решений `PLS-*` не вводят и ни одного не заменяют. Прочие разделы идентичны v0.1.

| # | Место | Было | Стало | Основание |
|---|---|---|---|---|
| 1 | §3.1, строка `case` | «current_status (null до терминала)»; один CHECK «current_status задан ⇔ current_state терминально» | «current_status (null вне состояний, имеющих продуктовый статус `PLS-031`)»; три раздельных CHECK: перечень из пяти допустимых значений; «задан ⇔ состояние имеет продуктовый статус, и тогда current_status = current_state»; «terminal_locked_at задан ⇔ статус терминален, pause-статусы terminal lock не создают» | **`PLS-031`**: продуктовыми статусами являются пять значений, включая `PAUSED_USER` и `PAUSED_EXTERNAL`; `03` §2 определяет продуктовый статус как «крупный пользовательский режим паузы или итог кейса». Прежняя формулировка исключала pause-статусы и противоречила §11 п. 11 настоящего документа («current_status только из пяти значений `PLS-031`»). `PRE_EXPERIMENT_DISMISSED` остаётся вне продуктовых статусов (`PLS-063`) |
| 2 | §3.6, строка `evidence_retention_policy` | «guard `G…` первого UA проверяет наличие» — незаполненный плейсхолдер идентификатора guard | «наличие полной политики входит в предусловия первого User Acceptance и проверяется в составе `G08_FULL_USER_ACCEPTED` (`03` §5) в момент команды; отсутствие политики отклоняет первый UA, а не создаёт отдельный гейт» | **`PAV-2`** (`24` §2, MINOR): плейсхолдер подлежал замене нормативной формулировкой в `14 v0.2` при первом содержательном изменении; принятое закрытие — требование входит в предусловия первого UA, состав guards `G08` по `03`. Отдельный guard `G01`–`G28` не вводится: реестр guards принадлежит `03` и настоящей спецификацией не расширяется |

Правка 1 описывает три constraint-а, уже реализованные в миграциях TB-04; изменений кода и миграций она не требует. Правка 2 семантику `PLS-054` не расширяет: состав, форма, цель и срок/событие политики остаются как приняты.

---


## 17. Changelog v0.3 (технические errata схемы)

Все три правки технические: они делают исполнимым то, что уже нормировано, и не изменяют продуктовую семантику. Новых решений `PLS-*` не вводят и ни одного не заменяют. Прочие разделы идентичны v0.2.

| ID | Место | Было | Стало | Основание |
|---|---|---|---|---|
| `DMV-4` | §3.1 `pre_experiment_dismissal`; §5 п. 12 | Строка не содержала `case_id`; признаком прекращения фактически служило отсутствие строки `active_experiment_slot` | `case_id` NOT NULL с FK на `case` и UNIQUE(case_id); строка объявлена канонической отметкой административного прекращения; снятие slot — следствие, а не доказательство | Без `case_id` loader не может доказать, что данный кейс прекращён: `case.current_state` остаётся, например, `INTAKE`, и правило R02 `INTAKE_ACCEPTED` остаётся формально применимым. Административный disposition переставал быть терминальным для обработки входа |
| `DMV-5` | §3.3 `state_transition`; §5 п. 13 | `from_state` без оговорки о создании кейса; фактическая миграция TB-04 объявляет `from_state text NOT NULL` | `from_state` допускает `NULL` только для genesis-перехода; добавлен CHECK, разделяющий genesis и обычный переход | Creation protocol `17 v0.2` §3.7 пишет переход при создании кейса, где исходного состояния не существует. Пустая строка `''` формально прошла бы `NOT NULL`, но стала бы значением вне перечня состояний `03` §3 и нарушила замкнутость state machine — обходом пользоваться нельзя |
| `DMV-6` | §3.3 `command_receipt`; §4; §5 п. 14; §12 | Реестр idempotency keys покрывал транспортные и доменные входы (Telegram update, callback, timer, run, apply, outbox, intent, 45/60), но общего носителя идемпотентности команды не было; у `event` такого поля нет | Введена append-only сущность `command_receipt` с UNIQUE(command_type, idempotency_key) и сохранённым outcome; в §4 она стоит выше транспортных ключей; права §12 — `pls_worker` SELECT + INSERT, UPDATE/DELETE отклоняются БД, у `pls_web` прав нет | Публичная точка `execute_trigger` (`17 v0.2` §3.1) принимает `idempotency_key` для любой команды, включая `SubmitOpportunity`, для которой строки `case` ещё нет. Привязка к `inbox (bot_id, update_id)` сделала бы доменную идемпотентность зависимой от Telegram и неприменимой к другим источникам входа |

**Что требуется от реализации.** Правки `DMV-4`–`DMV-6` изменяют схему и требуют миграции: `ALTER TABLE pre_experiment_dismissal ADD COLUMN case_id … NOT NULL` + FK + UNIQUE; `ALTER TABLE state_transition ALTER COLUMN from_state DROP NOT NULL` + genesis-CHECK; `CREATE TABLE command_receipt` + append-only trigger + привилегии (`GRANT SELECT, INSERT … TO pls_worker`, без GRANT для `pls_web`). Владелец миграции — задача **TB-04a** `25 v0.2`; порядок expand/contract раздела 8 сохраняется. До выполнения миграции TB-06 не начинается.


*Спецификация не изменяет продуктовый baseline и архитектуру v1.1. До пользовательской приёмки следующие документы стадии не создаются на её основе.*
