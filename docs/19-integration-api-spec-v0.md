# Personal Leverage System
## Integration/API Specification v0

**Статус:** кандидат на пользовательскую приёмку (проверка по контуру `15` — раздел 10)  
**Дата:** 6 августа 2026  
**Основание:** архитектура `11-technical-architecture-v1.1.md` §§2, 8, 9.4, 11–12, 14.3; принятые `14 v0.1`, `17 v0`, `18 v0`  
**Область:** контракты внешних границ — Telegram, Model Gateway (внутренний контракт и обязанности adapters), Tool & Fact Verification Gateway, object-storage adapter, health/readiness, таксономия ошибок границ, зарезервированная граница External Action Gateway  
**За рамками:** endpoint-код, конкретные payload-схемы уровня реализации, выбор провайдеров, промпты, изменение baseline/архитектуры

---

## 0. Нормативный статус

Границы доверия — по §2.1 архитектуры и не пересматриваются: всё внешнее есть вход, а не команда. Любой контракт этого документа реализует принцип fail closed for authority / fail durable for history (§11). Внутренние команды — только реестр `17` §1.2.

## 1. Telegram

### 1.1. Webhook (входящая граница)

| Аспект | Контракт |
|---|---|
| Аутентификация | Constant-time сравнение `X-Telegram-Bot-Api-Secret-Token` с активным секретом до любого парсинга; отказ → HTTP 403 без записи доменной команды, минимальный security event без содержимого |
| Дедупликация | INSERT в `inbox` по `(bot_id, update_id)` до обработки; дубликат → HTTP 200 c прежним processing result |
| Недоступность БД | HTTP 5xx (retryable) без подтверждения обработки; Telegram повторит; никакой буферизации входа вне БД |
| Allowlist | `from.id` = единственный настроенный `telegram_user_id`, `chat.type=private`, единственный допустимый `chat.id`; нарушение → HTTP 200 (поглощение без доменного эффекта) + security event |
| Нормализация | Update → typed Inbound Command кандидат; free-text никогда не сопоставляется с активным Intent (§8.4) |
| Ответ | Webhook всегда отвечает быстро; долгая работа — только через jobs; никакие модельные вызовы в обработчике |

### 1.2. Исходящие сообщения

Единственный путь отправки — outbox (`14` §3.3). Контракт рендеринга: informational и decision messages по §8.2 архитектуры; decision message обязан содержать элементы §8.6 (что изменилось, риски, deadlines, расходы, gaps) и кнопки только с opaque-токенами. Повторная доставка использует тот же `logical_notification_id`; редактирование/удаление сообщения в Telegram не имеет доменного эффекта — актуальное сообщение пересоздаётся из projection с пометкой о замене. При выпуске нового Intent по тому же предмету прежнее сообщение по возможности редактируется до «неактивно» с навигационной кнопкой на актуальную версию; неуспех редактирования не блокирует выпуск.

### 1.3. Callback

Обработка — одна транзакция по §8.3: повторная проверка secret/allowlist → поиск Intent по `token_hash` → проверки expiry, revision hash, `case_version`, неизменности предмета → CAS `pending→consumed` → создание consent/record/grant → ответ пользователю. Повтор/чужой источник/устаревшая редакция — исходы таблицы §8.4 архитектуры, все без второго доменного эффекта. Ответ callback-query отправляется всегда (в т.ч. на no-op), чтобы кнопка не «зависала».

### 1.4. Ротация секретов

Интерфейс transport maintenance mode по §8.5: команды `EnterTransportMaintenance`/`ExitTransportMaintenance` (admin), инвариант — pending outbox сохраняется, logical ids не меняются, компрометация reference → массовый supersede Intents тем же механизмом, что `14` §10.3 п.1.

## 2. Model Gateway (внутренний контракт)

### 2.1. Запрос/ответ

Внутренний request: `role`, `purpose`, `agent_run_ref`, `pass_ref?`, `context_package_ref+hash`, `capability_requirements` (structured_output, max_output, statelessness), `result_type` ожидаемого конверта `18` §1, budget. Внутренний response: raw payload + normalized `finish_reason`, usage, `response_hash`, adapter/model identifiers — далее конвейер валидации `18` §6. Gateway не интерпретирует содержание.

### 2.2. Обязанности adapter (совпадают с §14.3, здесь — как проверяемый контракт)

1. Native-преобразование без provider-hosted tools; 2. structured-output средствами провайдера, но повторная валидация на стороне PLS; 3. нормализация stop/error/usage в общую таксономию (раздел 5); 4. conformance-фикстуры, единые для всех adapters; 5. §12.6: stateless-by-default, запрет reuse identifiers, `store:false` где поддерживается, dated policy preflight до каждого вызова, fail-closed при отсутствии/истечении policy-записи; 6. failover — только новый независимый вызов из canonical package.

### 2.3. Timeout и повтор

Не более одного автоматического retry (§13.2). Если статус первого вызова неопределён (network timeout после отправки), оба ответа сохраняются как отдельные Model Calls; применяется максимум один по правилу `applied` (`14` §3.8); второй помечается `ignored` с причиной.

## 3. Tool & Fact Verification Gateway

Внутренний API: `invoke_tool(run_ref, tool_id, args)` → результат только после allowlist-проверок аргументов, host, MIME, размера, времени и бюджета (`18` §4). `fetch_public_page` создаёт snapshot object + `fact_record` c retrieved_at и пометкой `UNTRUSTED_CONTENT`; повторный fetch того же URL в одном run дедуплицируется по (run, normalized_url). Ошибки сети — retryable с лимитом; запрещённый host/аргумент — не retryable, фиксируется как denial event.

## 4. Object-storage adapter

Интерфейс — ровно операции §9.4 с сигнатурами: `put(key, stream, meta)`, `get(key, range?)`, `head(key)`, `delete(key, retention_authorization)`, `presign(key, op, ttl)`; multipart — за feature-флагом, выключен. Каждая операция возвращает нормализованный результат или ошибку раздела 5; adapter readiness = пройденные conformance tests для конкретной конфигурации (provider, region/account, SDK, дата) — непройденная конфигурация делает readiness-probe false для функций записи evidence. ETag никогда не подменяет application SHA-256.

## 5. Таксономия ошибок границ

| Класс | Примеры | Поведение |
|---|---|---|
| `RETRYABLE_TRANSIENT` | Сеть, 5xx провайдера, DB-переподключение | Ограниченный retry с backoff; счётчик в budget |
| `RETRYABLE_AMBIGUOUS` | Timeout после отправки | Правило §2.3: два сохранённых результата, применён максимум один |
| `NON_RETRYABLE_POLICY` | `PROVIDER_DATA_POLICY_BLOCKED`, hosted-tool, host вне allowlist | Fail closed, без failover в обход причины |
| `NON_RETRYABLE_CONTRACT` | Невалидная схема после repair, несуществующая capability | `FAILED_VALIDATION` / adapter incompatibility |
| `SECURITY_NOOP` | Чужой account/chat, неверный secret | Поглощение, security event, ноль доменных эффектов |
| `CONFLICT` | `case_version`, CAS Intent | Возврат инициатору актуального состояния, без автоприменения |

## 6. Health/readiness

По §15.4: liveness без внешних зависимостей; readiness = DB + migrations + secrets + критические policy-версии читаемы + (для evidence-записи) storage adapter conformance. Model-провайдер не входит в readiness; его недоступность — деградация jobs, не отказ сервиса.

## 7. External Action Gateway (зарезервированная граница)

В v1 отсутствует физически: нет коннекторов, credentials и кода отправки. Резервируется только контракт будущего: `Action Intent → Authority recheck → Dispatch Record`, idempotency key принадлежит action; включение любой исполняющей интеграции требует отдельного ADR, техспецификации и явного решения Кирилла. Настоящий документ не создаёт для этого никаких работ.

## 8. Traceability

Telegram → `PLS-013/055`, `ARC-N3`, §8; callback → `PLS-009/023/035/060`; Gateway/adapters → `ARC-M3`, §12.6/§14.3, `PLS-010/012/017`; storage → `ARC-N1`, §9.4, `PLS-013/054`; ошибки/повторы → §11, §13.2; External boundary → `PLS-010`, §11.1.

## 9. Открытые пункты

Открытых решений Кирилла нет. Конкретные payload-схемы (JSON Schema конвертов и команд) создаются на реализации от контрактов `17`/`18` без новых решений.

## 10. Changelog v0 (проверка по контуру `15`)

| Находка | Severity | Закрытие |
|---|---|---|
| IAV-1 — черновик не задавал поведение webhook при недоступной БД, допуская трактовку «принять и обработать позже» вне inbox | MINOR | §1.1: retryable 5xx без подтверждения; буферизация вне БД запрещена |
| IAV-2 — выпуск нового Intent не оговаривал судьбу прежнего Telegram-сообщения с живой кнопкой | MINOR | §1.2: best-effort редактирование в «неактивно»; безопасность и без него гарантирована server-side guards |
| IAV-3 — таксономия ошибок не выделяла `RETRYABLE_AMBIGUOUS`, смешивая обычный retry с dual-response правилом | MINOR | §5 + §2.3: отдельный класс с правилом «применён максимум один» |

---

*Документ не изменяет границы доверия §2 и контракты §§8–9, 12, 14 архитектуры v1.1.*
