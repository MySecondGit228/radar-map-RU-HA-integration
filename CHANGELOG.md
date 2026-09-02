# Changelog

Все заметные изменения проекта документируются в этом файле. Формат основан на
[Keep a Changelog](https://keepachangelog.com/), версии следуют
[Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-09-02

### Added

- структурированный sensor последнего semantic-события для каждого объекта;
- общий sensor последнего события среди всех выбранных объектов;
- локализованные состояния начала и окончания каждого типа угрозы;
- восстановление последнего события после перезапуска Home Assistant.

## [1.2.0] - 2026-09-02

### Added

- локальные brand icons для Home Assistant и HACS в размерах 256×256 и 512×512;
- настраиваемый через UI интервал polling от 15 до 300 секунд;
- diagnostics для настроенного, серверного и фактического интервала.

## [1.1.0] - 2026-09-02

### Added

- итоговая тревога по всем выбранным объектам;
- отдельные сводные sensors для каждого типа угрозы;
- sensor состояния подключения к RadarMap;
- SemVer-проверка согласованности manifest и GitHub Release для HACS.

## [1.0.0] - 2026-09-01

### Added

- первый выпуск интеграции RadarMap для Home Assistant;
- Config Flow, Options Flow, native entities, events и diagnostics;
- polling публичного RadarMap API с безопасной обработкой ошибок.

[1.3.0]: https://github.com/MySecondGit228/radar-map-RU-HA-integration/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/MySecondGit228/radar-map-RU-HA-integration/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/MySecondGit228/radar-map-RU-HA-integration/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/MySecondGit228/radar-map-RU-HA-integration/releases/tag/v1.0.0
