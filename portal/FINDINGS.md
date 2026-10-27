# FINDINGS — Humax CXHD-5150C, локальный тулчейн для отладки прошивки и обновления

Дата: 2026-10-23. Всё выполнялось локально в LAN (Mac 192.168.1.18, приставка 192.168.1.21).

## 1. Приставка (STB)
- Модель: **Humax CXHD-5150C** OnLime (Ростелеком).
- `sys.systemId = 8050.8400`, `sys.softwareVersion = 1.00.22`.
- MAC `08:EB:74:8C:C8:C0`, serial `13110834507683|00000000000|0000`.
- Браузер: **ANT Galio 3.1.1.23.04.09**, HbbTV 1.1.1, UA `HbbTV/1.1.1 (+PVR;Humax;CXHD-5150C;1.00.22;1.0)CE-HTML/1.0 ANTGalio/3.1.1.23.04.09`, `Accept-Language: ru`, `TE: chunked, deflate, gzip`.
- Открытых TCP-портов на приставке нет (скан 1–65535 пустой).
- пароли `/etc/shadow`: root `$1$7ELGCsEd$indnv.03WmlVFw7DA1ysd0`, settop `$1$lwxLCXaO$epH6TjzpH9TJB15eViHNK1` (по словарю не подобрались).

## 2. Инфраструктура на Mac
- `humax-gpl/dns_poison.py` — DNS :53,   оверрайды `humax.onlime.ru`, `www.humax.onlime.ru`, `humaxtvportal.com`, `www.humaxtvportal.com` → 192.168.1.18;
  **WILDCARD** (включён по умолчанию): любые «странные» имена (содержат `:`, пустые, начинаются на `192.168.`, не-доменные символы) → 192.168.1.18.
  Остальное форвардится на роутер 192.168.1.1. Лог — `dns_log.txt`.
- `humax-gpl/portal_server.py` — HTTP :80/:5080, HTTPS :443/:5001 - всё в одном.
  - `/api/report` — маяки панели (`k`/`v`), в т.ч. `kind=data&off=<ключ>&d=<hex>` для блочных данных (URL-запросы);
  - `/api/upload` — приём бинарников: POST `name=...&off=N&hex=1`, тело = hex-строка `d=...` или сырые байты; пишется в `uploads/`;
  - `/api/events`, `/api/status`, `/api/dns`, `/api/config`;
  - **fw-шлюз**: любой путь, содержащий `fw.hdf` (на ВСЕХ портах) отвечает файлом `panel/fw.hdf` (22 908 907 B) ТОЛЬКО если существует маркер `logs/FW_GATE_OPEN`; иначе 503. Каждое обращение пишется в `logs/FW_HITS.log` и в events.
- Старт стоп двигается `humax-gpl/start_root.sh` (root; можно запустить без ручного
  терминала: `osascript -e 'do shell script ".../start_root.sh" with administrator privileges'` —
  покажется системный диалог пароля). Если старые процессы не умерли — `kill -9` по PID (`logs/dns.pid`, `logs/portal.pid`).
- Текущие PIDs: dns 6854, portal 6855 (root).

## 3. Что умеет браузер приставки (ANT Galio)

**ANT Galio = Opera (Presto) + libopera_hbbtv.so.** Rootfs 5150C идентичен FOXSAT-HDR (md5: `ad01e76f727057279f294840e7574c1b`) — Humax использовал один rootfs blob для обоих устройств, отличается только внешний HDF-контейнер (SysID).

- `XMLHttpRequest` на `file://` работает: читает файлы по пути (статусы 200/404),
  Выводы и ограничения:
  - читает ВСЁ содержимое, но максимум **1 МБ** и всегда с нулевого офсета; заголовок `Range` игнорируется;
  - `/proc/*` всегда `len=0` (загрузчик делает `stat()` → у procfs размер 0);
  - мусорные пути → 1703-байтовая HTML-страница «network error» со статусом 404;
  - `$PATH`/директории листинг не отдают; запись куда-либо (PUT/POST на file://) — 404;
  - блочные девайсы: `/dev/mtdblock0` len=0, `/dev/mtdblock1` — 404/HTML, `mtdblock2` — 1 байт «01», `mtdblock4/5` — len=0, `mtdblock6` — 1-й МБ весь `0xFF/0xFD`, далее «думает» (медленно, вероятно NAND);

### 3.1. Плагины — подтверждено на живом устройстве (до брика)
  - `valups/system`: modelName=CXHD-5150C, systemId, softwareVersion, macAddress, screenLanguage=rus, usedNetInterface и т.д.
  - `valups/upgrade`: константы `ERROR_NONE=0`, `ERROR_FAIL=255`, `ERROR_RECORDING_NONE=240`, `ERROR_RECORDING_NOW=241`, `ERROR_RECORDING_READY=242`; методы
    **`upgrade`** и **`forcedupgrade`**, оба `fn/2`, оба native (`function upgrade() { [native code] }`);
  - `application/oipfApplicationManager`: setApplicationType, isBroadcastRelated, selectService, gc, getOwnerApplication, getChildApplications (последняя кинула «convert null … ch to Object» при вызове с document);
  - `application/oipfConfiguration`: `configuration` (getText/setText, родительский контроль, pvrPolicy, preferredAudioLanguage, countryId, regionId), `localSystem` (setScreenSize, deviceID=null, networkInterfaces); `keyset`;
  - `application/oipfObjectFactory`: свойства form/archive/align/code/border читаются («null»/«»), создать приложение/медиа не вышло (методы createApplication/… не найдены);

### 3.2. Плагины — из libooif.so (rootfs, не тестировались на живом устройстве)
Все ниже зарегистрированы в `libooif.so` и должны быть доступны через `<object type="...">`:

| MIME тип | Ключевые методы | Интерес для атаки |
|---|---|---|
| `application/oipfConfiguration` | `getText(key)`, `setText(key,val)`, `setParentalControlPIN(pin)`, `unlockWithParentalControlPIN(pin)` | **ВЫСОКИЙ** — пишет в конфиг-стор, ключи неизвестны |
| `application/oipfDownloadTrigger` | `registerDownloadURL(url, contentType, start)` | **ВЫСОКИЙ** — инициирует скачивание с нашего сервера |
| `application/oipfRecordingScheduler` | `record(ch,time,dur,name)`, `recordAt(...)` | средний |
| `application/oipfParentalControlManager` | `setParentalControlPIN(pin)`, `verifyParentalControlPIN(pin)` | средний — сброс PIN |
| `application/oipfDownloadManager` | `getDownloads()`, pause/resume/remove | низкий |
| `application/oipfCapabilities` | `xmlCapabilities`, `hasCapability()` | info |
| `application/oipfDrmAgent` | DRM | — |
| `application/oipfGatewayInfo` | gateway info | info |
| `application/oipfSearchManager` | поиск | — |
| `video/broadcast` | `currentChannel`, `recordNow(dur)`, `getChannelConfig()` | средний |

### 3.3. Атакующий потенциал из браузера (до получения shell)
1. **`upgrade("A"*4096, 1)`** — buffer overflow в URL-парсере `libplugin_upgrade.so`; `strtok('/')` на буфере фиксированного размера. Самый прямой путь к RCE.
2. **`oipfConfiguration.setText(key, val)`** — ключи конфиг-стора неизвестны; нужно прощупать — возможна запись в config.db → выполнение при старте.
3. **`oipfDownloadTrigger.registerDownloadURL(url,...)`** — скачивает с нашего сервера, путь сохранения контролирует устройство (по стандарту нет `destinationPath`).
4. **`oipfParentalControlManager.setParentalControlPIN("0000")`** — сброс PIN, реальный ущерб.

### 3.4. Probe-страница
`portal/probe.html` — при загрузке через портал тестирует все объекты из 3.1/3.2, возвращает результат в `/api/report`. Запустить когда устройство поднято.

- Пачка Image()-маяков (>~100 за раз) ПОТЕРИ: движок отбрасывает их. Пишите маяки по одному с задержкой ≥250–300 мс.

## 4. ГЛАВНОЕ: как ведёт себя нативное обновление (valups/upgrade)
Протестировано лока конфигов (панель v8b/v9/v10):
1. `upgrade()`, `upgrade(1арг)` → возвращает `null` (одно-аргументные не работают).
2. **`upgrade(url, 1)` / `forcedupgrade(url, 1)` (2 аргумента) → возвращает число `240` (`ERROR_RECORDING_NONE` = «записей нет, обновлять можно»).** При этом:
   - URL парсится «влоб» (виден в dns_log): нативный код strtok'ом по `/` берёт ПЕРВЫЙ токен как хост — со схемой! Видели DNS-запросы на имена `http:`, `https:`, `file:`, пустое имя, и на `192.168.1.18:5080`.
   - Наш DNS wildcard отвечает 192.168.1.18 на такие «хосты» — нативный модуль резолв принял; и запустил цикл обновления.
3. **Вызов `upgrade(url,1)` поднимает ПОЛНОЭКРАННЫЙ нативный UI обновления** (экран карточки с прогрессом → ошибка **ER-05** → приставка возвращается в портал; LED-индикация «HUER»). Из-за этого JS-страница умирает: **после первого успешного вызова остальные вызовы в панели не выполняются** (маяков дальше 1 нет).
4. **TCP-соединение до Мака НЕ доходит** (в portal.out/panel_log нет подключений от STB на 80/443/5080/5001 в момент апдейта). Резолв был (DNS), а коннекта нет → нативный клиент либо коннектится на другой порт (не входящие в наши листенеры; вероятно FTP :21, TFTP :69, или на порт из своей конфы), либо шлёт не-HTTP протокол.
5. ER-05 трактуем как «не смог связаться с сервером обновления» (сервер дал :503 открытому шлюзу? нет, шлюз не добили; скорее порт).

**Рабочая строка вызова (из v10, проверено):**
```javascript
u.upgrade("192.168.1.18:5080/fw.hdf", 1);  // host-token = "192.168.1.18:5080"
```
и/или `forcedupgrade(url,1)`.

## 5. MTD/флэш
- Разделы `/dev/mtdblock0..7`: 0-й пусто (или stat-0), 1-й — 404/HTML-ошибка, 2-й — 1 байт «01», 4-й/5-й — len=0, 6-й — NAND, читается, но все первые МБ `0xFD` и медленно (стёртый/вредный state). rootfs пока не найден.
- Загрузчик 1 МБ на файл — лимит; Range не работает.
- `uploads/` содержит дамп-куски (mtdblock*), `/sys/class/mtd/mtd*/{name,size}` — 404-ошибки; `/proc/mtd` — len=0 (stat-0).

## 6. Формат HDF (прошивочный файл)
- Подгружается нативным плагином; используются/скопированы из `/Users/andrey/Desktop/humax/hd_7000i_upgrade.hdf` и `/Users/andrey/Desktop/humax/cxhd_5150c_upgrade.hdf` (создан сборкой systemId 8050.8400, header-CRC `0xa1b6`, размер 22 908 907; лежит в `humax-gpl/panel/fw.hdf`).
- Структура (как я её понял):
  - 12-байтовые блок-хедеры (`crc`, magic `0x00017ff6`, load-address);
  - magic файла `0x00010106` на `0x14` (header CRC `0x01104c17`);
  - после 0x100-байтного блока (вероятно сигнатура) + 2 байта — чексам-блок `0x00800014`;
  - 32-байтовый фан-хедер для большого файла: uncompressed `0x0012ff3f`, compressed `0x00040036`, `0`, `0xffffffff`, CRC `0x001a382c`, ключ `0x7fc8b181`, magic `0x89017ff6`, `0`;
  - payload сжат/шифрован — zlib/raw/bzip2/lzma не дали; формат не определён.
- Утилита `humidify` (копия в `tools/humidify-ubuntu-1.0.4`, ELF x86-64 статически слинкован) — list/extract:
  ```
  colima start --arch x86_64 --vm-type vz --cpu 2 --memory 2
  docker run --rm --platform linux/amd64 -v /Users/andrey/Desktop/humax:/humax \
    -w /humax/hdf_work/out ubuntu:22.04 \
    /humax/tools/humidify-ubuntu-1.0.4 -x /humax/firmwares/genuine/onlime_early_cxhd_5150c.hdf
  ```
  Колима останавливать `colima stop` после работы.

## 7. Диагностика/логи
- `humax-gpl/events.jsonl` — все запросы/hits/репорты (с `id`).
- `humax-gpl/panel_log.txt` — рабочее зеркало (читаемо grep'ом).
- `humax-gpl/dns_log.txt` — DNS-запросы (важно «Q <имя> -> (wild)» / «(local)»).
- `humax-gpl/logs/FW_HITS.log` — обращения к fw-шлюзу (если появились строки от 192.168.1.21 — нативный клиент добился HTTP!). `logs/FW_GATE_OPEN` — маркер открытия.
- `humax-gpl/panel/index.html` — текущая панель (v10, battery upgrade() calls), бекапы `index_prev*.html`.
- `humax-gpl/uploads/` — принятые файлы от приставки.

## 8. Что НЕ работает / подводные камни
- Yandex недоступен из этой сети — не пробовать.
- Пересылка файлов с максимальной скоростью: через `/api/report?...kind=upload&hex=1` (POST, тело `d=<hex>`) — работает стабильно; `/api/upload` тоже живёт.
- Пачки Image()-маяков — можно терять солнце; по одному.
- macOS AirPlay занимает :5000 (не использовать).
- Если рестарт стека: не бить старе процессы пока.listeners живы (см. раздел 2).

## 9. Статус проекта

### 23.10.2026 23:10 MSK (последнее рабочее состояние)
- Панель v10: `upgrade("192.168.1.18:5080/fw.hdf",1)` → 240 (ERROR_RECORDING_NONE), нативный UI поднялся, ER-05, вернулся в портал живым.
- TCP-соединение нативного апдейтера до мака не доходило — OTA daemon, вероятно, использует **TFTP (UDP:69)**. tcpdump_syn.pcap подтверждает: SYN только на :80 и :5080 от браузера, никаких SYN на другие порты от апдейтера.

### 25.10.2026 — БРИК
- Устройство брикнулось на 96% при попытке прошить Y4.11 HDF → bad NAND block → partial loader → не грузится.
- Путь восстановления: **JTAG** (ESP8266 serial bitbang → OpenOCD → `load_image vmlinux_v20.elf` → `resume 0x802AC000` → Linux в RAM → kexec).

### 27.10.2026 — Анализ прошивки (текущая сессия)
- rootfs 5150C = FOXSAT-HDR rootfs (идентичный blob, md5 `ad01e76f727057279f294840e7574c1b`).
- Полная карта OIPF-объектов из libooif.so — см. §3.2.
- P12-сертификаты в прошивке (`htvdev_portal_ccert_2k_20101106.p12`, `hdrfoxt2_*.p12`) — **пустой пароль**, шифрование RC2-40-CBC. Приватный ключ `htvdev.humaxtvportal.com` (клиентский cert) извлечён:
  `openssl pkcs12 -legacy -passin pass: -nocerts -nodes -in htvdev_portal_ccert_2k_20101106.p12`
  (root CA private key в прошивке отсутствует — только pub cert).
- Probe-страница: `portal/probe.html` — запустить сразу после восстановления через JTAG.

## 10. Правила игры
- Пользователь (Andrey) терпеливый, но не любит много «спящих» снов и длинных непонятных пауз — пиши кратко и по делу, пользователь сам перезагружает портал на приставке при запросе.
- Кратко о том, как делать вызовы upgrade: сначала закрываем шлюз (он уже закрыт по умолчанию), после — открытие шлюза вручную (`touch logs/FW_GATE_OPEN`) и НЕ закрывать его случайно (это железо!).
