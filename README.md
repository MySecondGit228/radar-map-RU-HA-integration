# RadarMap for Home Assistant

[![GitHub release](https://img.shields.io/github/v/release/MySecondGit228/radar-map-RU-HA-integration)](https://github.com/MySecondGit228/radar-map-RU-HA-integration/releases)

Неофициальная custom integration для [RadarMap](https://radar-map.ru/). Она
получает публичный агрегированный state RadarMap и предоставляет выбранные
регионы, районы и населённые пункты как нативные devices, binary sensors и
timestamp sensors Home Assistant.

## Installation

### HACS custom repository

1. Откройте HACS → Integrations.
2. В меню выберите **Custom repositories**.
3. Добавьте URL этого репозитория с категорией **Integration**.
4. Найдите и установите **RadarMap**.
5. Перезапустите Home Assistant.

HACS показывает установленную и доступную версии из `manifest.json` и GitHub
Releases. Если обновление не появилось сразу, обновите сведения о репозитории в
HACS.

Для ручной установки скопируйте `custom_components/radar_map` в каталог
`config/custom_components/` Home Assistant и перезапустите Home Assistant.

## Configuration

Откройте **Settings → Devices & services → Add Integration → RadarMap**.

Config Flow проверяет публичный API и предлагает множественный выбор регионов и
городов. Для районов сначала укажите регионы, каталоги которых нужно открыть, а
на следующем шаге выберите конкретные районы. Это поле не создаёт устройство
региона само по себе и предотвращает загрузку всех районных GeoJSON России.

Выбор можно изменить через **Configure** у config entry. Options Flow
автоматически перезагрузит интеграцию. YAML-конфигурация не используется.

Ползунок **Интервал опроса** доступен при установке и в Options Flow. Диапазон —
15–300 секунд, шаг — 5 секунд, значение по умолчанию — 30 секунд. Это
предпочтительный минимальный интервал: интеграция никогда не опрашивает API чаще,
чем разрешает текущий `poll_interval_sec` RadarMap. Например, при настройке 15
секунд и серверном значении 25 фактический интервал будет 25 секунд.

## Update transport

Интеграция опрашивает `GET https://radar-map.ru/api/state?nofeed=1`. Фактический
интервал равен большему из настроенного значения и серверного
`client_live.poll_interval_sec` / `poll_interval_sec` (fallback 30 секунд).
SSE и WebSocket сайта требуют платную Boosty-подписку, поэтому интеграция их не
использует и не пытается обходить авторизацию. Детали исследования находятся в
[`docs/api-research.md`](docs/api-research.md).

## Entities

Для каждого выбранного объекта создаётся отдельное устройство
`RadarMap — <имя>` и следующие binary sensors:

- `bpla` — фиксация/угроза БПЛА;
- `attention` — отдельный, более слабый warning;
- `danger` — опасность;
- `uab` — УАБ;
- `fpv` — FPV-дрон;
- `rocket` — ракета;
- `rocket_level` — ракетный уровень опасности;
- `aviation` — авиационная опасность;
- `pvo` — работа ПВО/перехват;
- `alert` — агрегат `bpla`, `danger`, `uab`, `fpv`, `rocket`,
  `rocket_level`, `aviation`. `attention` и `pvo` в него намеренно не входят.

Также создаётся `sensor.<object>_last_event` с timestamp последнего события и
компактными attributes:

```text
source_text
last_event_ts
object_type
region
latitude
longitude
active_alert_types
source
sources
```

`fill`, `bplaDim`, `uabDim`, `bplaLaunchAnim`, `rocketOnRegion` и прочие
presentation/animation fields не экспортируются как сущности.

Для всей config entry создаётся отдельное устройство `RadarMap — Summary` с
общими binary sensors:

- **Overall alert / Итоговая тревога** — включён, если `alert` активен хотя бы у
  одного выбранного региона, района или города;
- отдельные агрегаты `bpla`, `attention`, `danger`, `uab`, `fpv`, `rocket`,
  `rocket_level`, `aviation` и `pvo` — каждый включён, если соответствующий флаг
  активен хотя бы у одного выбранного объекта;
- **Connection / Подключение** (`device_class: connectivity`) — включён, если
  последний запрос RadarMap успешен, и выключен при ошибке API или сети.

Атрибуты итоговой тревоги:

```text
selected_object_count
active_object_count
active_objects
active_object_ids
active_alert_types
active_objects_truncated
```

Списки ограничены первыми 50 активными объектами, а полное число всегда доступно
в `active_object_count`. Если активных тревог нет, но одно из исходных полей
неизвестно из-за изменения API schema, итоговый sensor получает `unknown`, а не
ложный `off`.

Каждый отдельный агрегат угрозы содержит `alert_type`, `selected_object_count`,
`active_object_count`, `active_objects`, `active_object_ids` и
`active_objects_truncated`. Поэтому, например, общий sensor БПЛА одновременно
показывает факт угрозы и список выбранных объектов, где активен `bpla`.

Sensor подключения намеренно остаётся доступным при сбое, чтобы показать `off`,
пока остальные RadarMap entities становятся `unavailable`. Его атрибуты содержат
`last_successful_update`, `last_error`, `poll_interval_sec` и
`last_update_duration_sec`.

Unique ID стабилен в рамках идентификаторов RadarMap:

```text
region:<normalized_name>:<entity>
district:<gid_2>:<entity>
city:<key>:<entity>
```

## Home Assistant events

При реальном переходе semantic flag `false → true` или `true → false`
интеграция один раз отправляет событие `radar_map_alert`:

```json
{
  "object_type": "district",
  "object_id": "district:RUS.44.57_1",
  "name": "Рузский район",
  "region": "Московская область",
  "alert_type": "bpla",
  "state": "on",
  "last_event_ts": 1788245830,
  "source_text": "...",
  "sources": ["vrv_radar"]
}
```

Первичная загрузка и неизменившиеся polling cycles события не генерируют.
Перестановка JSON, `fill`, API `version` и animation fields также не считаются
изменением.

## Example automation

Фактический `entity_id` зависит от языка и entity registry вашей установки;
выберите его в UI либо подставьте свой ID:

```yaml
automation:
  - alias: "RadarMap — БПЛА в Рузском районе"
    triggers:
      - trigger: state
        entity_id: binary_sensor.radarmap_ruzskiy_rayon_bpla
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "БПЛА"
          message: >
            {{ state_attr('sensor.radarmap_ruzskiy_rayon_last_event',
                          'source_text') }}
```

Вариант с event bus:

```yaml
automation:
  - alias: "RadarMap — все начала тревог"
    triggers:
      - trigger: event
        event_type: radar_map_alert
        event_data:
          state: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "RadarMap: {{ trigger.event.data.name }}"
          message: "{{ trigger.event.data.alert_type }}"
```

Автоматизация по итоговому состоянию может использовать общий sensor без
перечисления отдельных объектов:

```yaml
automation:
  - alias: "RadarMap — итоговая тревога"
    triggers:
      - trigger: state
        entity_id: binary_sensor.radarmap_summary_overall_alert
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "RadarMap"
          message: >
            Активны: {{ state_attr('binary_sensor.radarmap_summary_overall_alert',
                                   'active_objects') | join(', ') }}
```

## Availability and diagnostics

Сетевая ошибка, HTTP error, malformed JSON либо transient
`startup_ready=false` / `state_ready=false` не сбрасывают угрозы в `off`.
Coordinator сохраняет последний успешный snapshot, а entities становятся
`unavailable`. После восстановления следующий успешный poll возвращает
доступность и обновляет состояния.

Diagnostics config entry содержат статус API, время последнего успешного
обновления, effective poll interval, API version, выбор объектов, последнюю
ошибку и сокращённое состояние. Cookies, credentials и полные API-деревья туда
не включаются.

Для debug logging:

```yaml
logger:
  logs:
    custom_components.radar_map: debug
```

## Limitations and safety notice

RadarMap — внешний, неофициальный и схематичный источник на основе публичных
лент. Эта интеграция не является официальной государственной системой
оповещения, не гарантирует полноту/точность/своевременность данных и не должна
использоваться как единственный источник информации об угрозах или как основание
для решений о безопасности. Следуйте официальным сигналам и рекомендациям
уполномоченных органов.

API не опубликован как формально версионированный контракт. Возможны изменения
schema, идентификаторов и доступности. `gid_2` стабилен в текущем наборе данных,
но может измениться при замене геоданных RadarMap.

## Branding

Стандартная и hDPI-иконки находятся в
`custom_components/radar_map/brand/icon.png` и `icon@2x.png`. Они включаются в
HACS-пакет и используются Home Assistant 2026.3+ в списке интеграций и Config
Flow. После обновления может потребоваться перезапуск Home Assistant и очистка
кэша браузера.

## Development

```bash
python -m pip install pytest pytest-asyncio pytest-homeassistant-custom-component ruff
pytest
ruff check .
ruff format --check .
```

## Versioning and releases

Проект использует [Semantic Versioning](https://semver.org/). Единственный
источник версии — поле `version` в
`custom_components/radar_map/manifest.json`.

Для релиза:

1. обновите версию в `manifest.json` и `CHANGELOG.md`;
2. закоммитьте изменения;
3. проверьте и опубликуйте релиз с префиксом `v`, например:

```bash
python scripts/check_version.py v1.2.0
gh release create v1.2.0 --target master --generate-notes
```

Скрипт проверяет строгий формат SemVer и совпадение тега с версией manifest.
Именно GitHub Release, а не просто тег, используется HACS как remote version.

License: MIT.
