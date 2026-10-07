# Margarita Tank

Un acuario de escritorio para tus sesiones de Claude Code. Un cangrejo pixel-art llamado Clawd vive en una pantalla y reacciona a lo que hace Claude: se anima según la herramienta en uso, avisa notificaciones, y ahora muestra tu **consumo de tokens en vivo** (sesión de 5h y semanal) directo en el display.

Corre sobre un [Waveshare ESP32-C6-LCD-1.47](https://s.click.aliexpress.com/e/_c4PGS55v) (320x172, ST7789). ¿Sin hardware? El simulador corre en macOS y Windows sin placa física.

> **Nota de fork.** Este es un fork personal de [**Clawd Tank** de Marcio Granzotto Rodrigues](https://github.com/marciogranzotto/clawd-tank), bajo licencia MIT. Todo el crédito del firmware, simulador y arquitectura del daemon originales es del autor upstream. La portabilidad del simulador (macOS + Windows) también es del proyecto original.

## Descargas

| Plataforma | Instalador |
| ---------- | ---------- |
| **macOS** (Apple Silicon) | [Margarita-Tank.dmg](https://github.com/depper-IA/margarita-tank/releases/latest/download/Margarita-Tank.dmg) |
| **Windows** (x64) | [Margarita-Tank-Setup.exe](https://github.com/depper-IA/margarita-tank/releases/latest/download/Margarita-Tank-Setup.exe) |

Ambos instalan la app de la barra de menú / bandeja con el simulador incluido, y la app instala los hooks de Claude Code en el primer arranque. Después, reinicia tus sesiones de Claude Code.

- **macOS**: abre el DMG y arrastra **Margarita Tank** a Aplicaciones. La app no está firmada, así que la primera vez hay que hacer clic derecho → **Abrir**, o ejecutar `xattr -dr com.apple.quarantine "/Applications/Margarita Tank.app"`.
- **Windows**: instalación por usuario, sin permisos de administrador. El instalador no está firmado, así que SmartScreen puede avisar: clic en **Más información** → **Ejecutar de todas formas**. Al desinstalar se quitan de `~/.claude/settings.json` solo los hooks de Margarita Tank; tus propios hooks quedan intactos.
- **Hardware**: el firmware del ESP32 no va en los instaladores; se flashea aparte (ver [Firmware](#firmware-esp-idf-53x)). Sin hardware, usa el simulador incluido desde el menú de la app.

## Qué agrega este fork

| Categoría | Cambios |
| --------- | ------- |
| **Barra de uso** | Franja superior de dos filas con SESIÓN (5h) y SEMANA (7d) como barras de progreso con color condicional (verde → lima → amarillo → naranja → rojo), cuenta regresiva de reset y reloj |
| **Ciclo día/noche** | Amanecer cálido agregado a la transición de cielo |
| **Rebrand "Margarita"** | Nombre BLE del dispositivo, scanner del daemon y tarjetas de notificación |
| **Localización** | Textos de las tarjetas en español |
| **Fix de watchdog** | Aísla los widgets de la barra del contenedor animado para frenar una tormenta de invalidación que crasheaba el ESP32-C6 |
| **Limpieza de sesiones** | Timeout adaptativo: las sesiones sin PID (p. ej. en Windows) se purgan más rápido para que no queden sesiones fantasma |

## Cómo funciona

```
Claude Code hooks --> clawd-tank-notify --> daemon --> BLE --> ESP32-C6 (Margarita)
                                                  \-> TCP --> Simulador (SDL2)
```

1. Los **hooks de Claude Code** (`SessionStart`, `PreToolUse`, `PreCompact`, `Stop`, `Notification`, `SessionEnd`, `SubagentStart/Stop`, etc.) disparan en eventos de sesión.
2. **clawd-tank-notify** reenvía el evento al daemon por socket local.
3. El **daemon** (Python) sigue el estado por sesión, mapea herramientas a animaciones, lee tu consumo del caché de statusline y envía payloads JSON a los transportes.
4. El **firmware** (o el simulador) renderiza la animación de Clawd, las notificaciones y la barra de uso en la pantalla.

## Stack

- **Firmware**: C (ESP-IDF 5.3.x), LVGL 9.5, NimBLE
- **Simulador**: C + SDL2 (macOS y Windows)
- **Host**: Python ≥ 3.10 (asyncio, bleak para BLE)
- **Hardware**: ESP32-C6, display ST7789 320x172

## Instalación

### Firmware (ESP-IDF 5.3.x)

```bash
cd firmware
idf.py build
idf.py -p <PUERTO> flash monitor
```

En Windows el puerto es `COMx` (p. ej. `COM5`); en macOS/Linux `/dev/ttyACM0` o similar.

### Simulador (sin hardware)

```bash
cd simulator
cmake -B build -G Ninja -DSTATIC_SDL2=ON -DCMAKE_C_COMPILER=gcc
cmake --build build
./build/clawd-tank-sim            # ventana interactiva
./build/clawd-tank-sim --listen   # escucha al daemon por TCP
```

### Daemon (host)

```bash
cd host
pip install -r requirements.txt
python -m clawd_tank_daemon --sim        # con simulador
python -m clawd_tank_daemon              # con BLE (busca "Margarita")
```

## Configuración

El daemon instala un hook handler en `~/.clawd-tank/clawd-tank-notify.py`. Para conectarlo a Claude Code, agregá los hooks a `~/.claude/settings.json` (o usá el instalador de la app). Reiniciá las sesiones de Claude Code para que tomen efecto.

Para renombrar el dispositivo, cambiá el nombre en un solo lugar por capa:
- Firmware: `firmware/main/ble_service.c` (`fields.name` / `ble_svc_gap_device_name_set`)
- Daemon: `host/clawd_tank_daemon/ble_client.py` (`DEVICE_NAME`)
- Tarjetas: `host/clawd_tank_daemon/protocol.py` (`DISPLAY_NAME`)

## Tests

```bash
# Tests del host (daemon + protocolo)
cd host && .venv/bin/pytest -v

# Tests C del firmware (notification store)
cd firmware/test && make test
```

## Créditos

- Proyecto original: [Clawd Tank](https://github.com/marciogranzotto/clawd-tank) por Marcio Granzotto Rodrigues (MIT).
- Modificaciones de este fork: Sam Wilkie.

## Licencia

MIT. Ver [LICENSE](LICENSE) — conserva el copyright original de Marcio Granzotto Rodrigues más el de las modificaciones de este fork.
