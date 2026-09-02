# RadarMap API research

Исследование выполнено 1 сентября 2026 года. Использованы приложенные
`radar-map.ru_Archive [26-09-01 11-32-55].har`, `radar_parse.json`, текущий
frontend `app.js?v=1788249564`, публичная справка сайта и несколько одиночных
HTTP-запросов с соблюдением возвращаемого сервером интервала. Нагрузочное
тестирование не проводилось.

Метки выводов:

- **CONFIRMED** — подтверждено frontend-кодом и/или прямым запросом;
- **OBSERVED** — наблюдалось в HAR/снимках, но не является опубликованным контрактом;
- **INFERRED** — наиболее вероятная семантика по совокупности поведения;
- **UNKNOWN** — публичных гарантий не найдено.

## Endpoints

| Endpoint | Статус | Наблюдаемое назначение |
|---|---|---|
| `GET /api/state` | **CONFIRMED** | Полный актуальный state плюс полная лента `recent_messages` и `recent_by_source`. |
| `GET /api/state?nofeed=1` | **CONFIRMED** | Тот же полный state карты без большой ленты. Выбран интеграцией. |
| `GET /api/state?nofeed=1&feed_since=<ts>` | **CONFIRMED** | Полный state карты и, если есть новые сообщения, `recent_messages_patch`. Это delta только ленты, не карты. |
| `GET /events` | **CONFIRMED** | SSE для подписчиков. Без подписки: HTTP 403 и JSON `SSE доступен только подписчикам Boosty`. |
| `GET /ws` (Upgrade) | **CONFIRMED** | WebSocket для подписчиков. Без подписки handshake получает 101, затем close frame с кодом 4403 и причиной `subscriber required`. |
| `GET /api/presence?m=poll` | **CONFIRMED** | Presence/policy ping frontend; может обновить `client_live`. Интеграции не нужен. |
| `GET /api/user/me`, `/api/subscriber/me` | **CONFIRMED** | Состояние пользовательской/платной сессии frontend. Интеграция их не вызывает. |
| `POST /api/visit` | **CONFIRMED** | Статистика визита frontend. Интеграция не вызывает. |
| `GET /static/data/russia_regions.geojson` | **CONFIRMED** | Полный каталог регионов (89 объектов в HAR). |
| `GET /static/data/cities_ru.json`, `cities_user.json` | **CONFIRMED** | Каталоги населённых пунктов (979 и 758 строк в HAR). |
| `GET /static/data/districts_by_region/manifest.json` | **CONFIRMED** | Регион → GeoJSON-файл районов. Frontend загружает файлы лениво. |
| `/api/map_history*`, `/api/analytics/threats`, `/api/stats/public` | **OBSERVED** | История/аналитика/статистика frontend; для live-сущностей не нужны. |

Справка самого сайта подтверждает, что карта основана на публичных лентах,
является схематичной и неофициальной, а мгновенный WebSocket предоставляется
подписчикам: [RadarMap help](https://radar-map.ru/help).

## `/api/state`

**CONFIRMED:** endpoint доступен без регистрации. HAR-запрос не содержал cookie.
Прямой запрос с `Accept: application/json` и собственным User-Agent, без cookie,
Referer и браузерных `Sec-Fetch-*`, вернул HTTP 200. Поэтому cookies, Referer и
браузерные заголовки для публичного polling не нужны.

Пример сокращённого ответа 01.09.2026:

```json
{
  "type": "state",
  "version": 23,
  "poll_interval_sec": 25.0,
  "client_live": {
    "enforced": true,
    "tier": "free",
    "subscriber": false,
    "update_mode": "poll",
    "poll_interval_sec": 25.0
  },
  "regions": {},
  "cities": [],
  "districts": {},
  "sources": [],
  "states": {}
}
```

Ответ имеет `Cache-Control: public, max-age=10, stale-while-revalidate=60`.
**OBSERVED:** размер live-ответа с `nofeed=1` был около 247 КБ без HTTP-сжатия,
bare state — около 426 КБ. Размер зависит от текущей карты и ленты.

## Query parameters

### `_`

**CONFIRMED:** cache-buster в миллисекундах. В `app.js` функция
`fetchStateJson` добавляет `_=` + `Date.now()` только при `opts.noCache`
(строки 884–910 в сохранённой версии). Серверная бизнес-семантика от значения
не наблюдалась. Интеграция его не добавляет, чтобы использовать публичный cache.

### `nofeed`

**CONFIRMED:** `nofeed=1` убирает `recent_messages` и `recent_by_source`, но не
делает state карты частичным. В HAR bare `/api/state` содержал полную ленту,
последующий `nofeed=1` — те же основные коллекции без ленты. Frontend-комментарий:
«Полная лента — один раз при открытии; дальше карта + патч ленты»
(`app.js`, строки 891–905).

### `feed_since`

**CONFIRMED:** timestamp Unix в секундах для новых элементов ленты.

- `nofeed=1&feed_since=0`: patch отсутствовал;
- `nofeed=1&feed_since=1788257938`: вернулся
  `recent_messages_patch.prepend` с сообщением `ts=1788258058` и
  `prune_before_ts`;
- timestamp, равный последнему известному в HAR: patch отсутствовал, пока новых
  сообщений не было;
- `feed_since=<ts>` без `nofeed=1`: сервер вернул обычную полную ленту и не
  вернул patch.

Frontend вычисляет `feed_since` как максимальный `recent_messages[].ts`, а patch
сливает по ключу `<channel/source_id>:<msg_id>` и сортирует по `ts`
(`app.js`, строки 873–905 и 3996–4015).

**CONFIRMED:** это не delta состояния карты. Даже с `feed_since` сервер отдаёт
полные `regions`, `districts`, `cities` и другие state-коллекции. Поэтому схема
«initial state + HTTP delta + reconciliation» для карты недоступна.

## Polling, SSE and WebSocket

### Polling interval

**CONFIRMED:** бесплатная сессия получает `client_live.update_mode="poll"` и
`poll_interval_sec`. Frontend при `client_live.enforced` использует именно этот
интервал (`app.js`, строки 3774–3783). В HAR policy менялась с 50 до 25 секунд;
в live-проверке возвращалось 25 секунд. Значение является серверной политикой,
а не признаком срока жизни отдельной угрозы.

Интеграция использует серверное значение, ограничивая явно повреждённые значения
диапазоном 15–300 секунд; fallback при отсутствии — 30 секунд.

### SSE

**CONFIRMED:** frontend содержит `new EventSource("/events")`, но перед этим
проверяет premium-сессию. Комментарий в коде: «WS/SSE — только подписчики Boosty»
(`app.js`, строки 3715–3751 и 4256–4280). Неавторизованный live-запрос вернул
HTTP 403. SSE не используется интеграцией.

### WebSocket

**CONFIRMED:** frontend предпочитает `wss://<host>/ws` для подписчика и fallback
на polling при close 4403/1013 (`app.js`, строки 4161–4239). Код умеет принимать
`type="state_delta"` с `patch.regions/districts/cities`, но этот push-transport
закрыт подпиской. Неавторизованный live-handshake завершился кодом 4403.
Интеграция не эмулирует платную сессию и не использует WS.

### Выбранный transport

**CONFIRMED:** обычный polling `GET /api/state?nofeed=1`. Это единственный
публичный transport состояния карты, реально выбранный frontend для бесплатного
клиента. Feed patch не уменьшает state-ответ, а push-интерфейсы платные.

## State lifecycle and fields

**OBSERVED:** при начале/изменении угрозы соответствующий boolean становится
`true`, обновляются `last_event_ts` и `source_text`. Между двумя приложенными
снимками наблюдались, например:

- `Белгородская область`: `rocket false → true`, `rocket_level false → true`;
- `Горловка`: `uab false → true`;
- `Селечня`: `bpla true → false`, одновременно `danger false → true`.

**OBSERVED:** окончание также может выражаться удалением объекта из полного
snapshot. Между снимками несколько активных районов/городов исчезли из
коллекций. Frontend при каждом full state заменяет текущие коллекции
(`app.js`, строки 5420–5505), то есть отсутствие в успешно полученном полном
snapshot визуально означает отсутствие активной подсветки. Интеграция трактует
отсутствующий выбранный объект как safe/off. Это правило применяется только
после успешного валидного ответа; сетевой сбой делает сущности unavailable.

В HAR и `radar_parse.json` все перечисленные state-поля имели JSON boolean:
`bpla`, `bplaDim`, `attention`, `danger`, `uab`, `uabDim`, `fpv`, `rocket`,
`rocket_level`, `aviation`, `pvo`, `explosionOnRegion`, `bplaLaunchAnim`,
`rocketOnRegion`. **UNKNOWN:** публичного формального schema/enum-контракта нет.
Если экспортируемое поле присутствующего объекта исчезнет или перестанет быть
boolean, интеграция показывает `unknown`, а не ложный `off`.

Семантика по frontend и справке:

- `attention` — более слабое «внимание по БПЛА», отдельно от фактической тревоги;
- `danger` — опасность без отдельной фиксации БПЛА;
- `bpla`, `uab`, `fpv`, `rocket`, `aviation`, `pvo` — самостоятельные значки;
- `rocket_level` вместе с `rocket`/`aviation` определяет ракетную/авиационную
  опасность и красный уровень (`app.js`, строки 6616–6764);
- `bplaDim`, `uabDim` — визуальная яркость/затухание иконки;
- `bplaLaunchAnim` — запуск визуальной анимации;
- `rocketOnRegion` — компоновка ракетной иконки на регионе/районе;
- `explosionOnRegion` — региональный визуальный explosion/перехват marker; из-за
  его переходной UI-роли отдельная сущность не создаётся, при этом `pvo`
  экспортируется как семантическое состояние.

`fill` — presentation color. Он не используется интеграцией как источник истины.

### `last_event_ts` and `source_text`

**CONFIRMED:** `last_event_ts` — Unix timestamp последнего связанного события.
Frontend использует его для затухания иконки и сопоставления с лентой
(`app.js`, строки 2225–2249 и 5807+). Он не определяет активность угрозы.
`source_text` может сохранять старое сообщение после снятия flag; это контекст,
а не признак активной тревоги.

## Sources and aggregate state

**CONFIRMED:** `sources` — список `{id,label}`. В исследованных ответах:
`vrv_radar`, `lpr1_treugolnik`, `locatorru`. `states` содержит однотипные
снимки для каждого источника и `__all__`. `source_mode_default="__all__"`.
Frontend показывает top-level collections как актуальный агрегат `__all__`, а
источник можно вручную переключить (`app.js`, строки 4684–4715 и 5467–5484).

Интеграция использует top-level aggregate и добавляет компактные `source` /
`sources` attributes, определяя, в каких source-specific коллекциях присутствует
объект. Отдельные сущности на каждый источник не создаются.

## Object identifiers and catalogs

- **CONFIRMED:** регионы в state ключуются русским display name. GeoJSON также
  имеет `id` и `iso_3166_2`, но state на них не ссылается. Unique ID интеграции:
  `region:<normalized Russian name>`; исходное имя сохраняется.
- **CONFIRMED:** районы ключуются `gid_2`; frontend строит `districtByGid` и
  ищет state по нему (`app.js`, строки 8004–8021). Unique ID:
  `district:<gid_2>`.
- **OBSERVED:** `gid_2` стабилен в текущем GeoJSON и API, но похож на ID версии
  GADM (например `_1`) и публично не гарантирован навсегда. При замене набора
  геоданных миграция ID может потребоваться.
- **CONFIRMED:** города имеют `key`. Для всех строк проверенного live state он
  точно равнялся `<NFKC/casefold name>|<NFKC/casefold region>`. Unique ID:
  `city:<key>`.

Текущий state содержит только затронутые/недавние места, поэтому он не является
полным каталогом для Config Flow. Интеграция использует те же статические
каталоги, что frontend. Районные GeoJSON загружаются только для регионов,
явно выбранных пользователем как область поиска районов; это избегает десятков
ненужных запросов.

## Errors, caching and rate limits

**CONFIRMED:** frontend считает `type="wait"`, not-ready state, HTTP 429, 502,
503 и 504 временными ошибками и увеличивает backoff экспоненциально до 90 секунд
(`app.js`, строки 911–944). При потере данных он не применяет ложный safe state.
Интеграция делает то же концептуально через `DataUpdateCoordinator`: сохраняет
последние данные, помечает entities unavailable и автоматически восстанавливается.

**CONFIRMED:** HTTP 429 поддерживается клиентом; `Retry-After`, если он есть,
передаётся coordinator с ограничением. **UNKNOWN:** опубликованных численных
rate limits и SLA не найдено. Агрессивные проверки не выполнялись. Наблюдался
публичный nginx cache 10 секунд; штатный интервал 25 секунд существенно больше.

**UNKNOWN:** нет публичной гарантии обратной совместимости schema, стабильности
GeoJSON ID, времени хранения снятых объектов или доступности API для сторонних
интеграций. Клиент изолирует schema parsing от HA entities и осторожно обрабатывает
отсутствующие/неизвестные поля.

## Differences between supplied artifacts and live behavior

HAR и текущая страница ссылались на один и тот же `app.js?v=1788249564`, версия
state оставалась 23. Между снимками менялись данные, число объектов и policy
polling (50 → 25 секунд), но структура и transport logic не изменились.
