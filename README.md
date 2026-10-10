<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/banner-light.svg">
  <img alt="Clawdy: un acuario de escritorio para tus sesiones de Claude Code" src="assets/readme/banner-dark.svg" width="100%">
</picture>

<p align="center">
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest"><img src="https://img.shields.io/github/v/release/sam-wilkie/margarita-tank?style=flat-square&color=000000&label=release" alt="Última versión"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/licencia-MIT-000000?style=flat-square" alt="Licencia MIT"></a>
<a href="https://hits.sh/github.com/sam-wilkie/margarita-tank/"><img src="https://hits.sh/github.com/sam-wilkie/margarita-tank.svg?style=flat-square&color=ff0000&label=views" alt="views"></a>
</p>

# Mi Buddy Clawdy

Un acuario de escritorio para tus sesiones de Claude Code. **Clawdy** es un cangrejo pixel-art que vive en una pantalla y reacciona a lo que hace Claude: se anima según la herramienta en uso, avisa las notificaciones y muestra tu **consumo de tokens en vivo** (sesión de 5 h y semanal) directamente en el display. Detrás, un cielo animado con ciclo día/noche acompaña a Clawdy mientras trabajás.

Corre sobre un [Waveshare ESP32-C6-LCD-1.47](https://s.click.aliexpress.com/e/_c4PGS55v) (320x172, ST7789). ¿Sin hardware? El simulador corre en macOS y Windows sin placa física.

> [!NOTE]
> **Linaje.** Clawdy nació como un fork personal de [**Clawd Tank** de Marcio Granzotto Rodrigues](https://github.com/marciogranzotto/clawd-tank) (MIT) y creció hasta volverse un proyecto propio: fondo de escena animado, nuevas animaciones, mod para Claude Code e instalador de Windows. El firmware base, el simulador y la arquitectura del daemon originales son de Marcio, y su crédito se conserva en la [licencia](LICENSE). El repositorio todavía se publica bajo el nombre `margarita-tank` mientras se completa el cambio de marca.

## `$ ./descargar`

<p align="center">
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest/download/Margarita-Tank.dmg"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/download-macos-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/download-macos-light.svg">
  <img alt="Descargar para macOS (Apple Silicon, .dmg)" src="assets/readme/download-macos-dark.svg" width="332">
</picture></a>
<a href="https://github.com/sam-wilkie/margarita-tank/releases/latest/download/Margarita-Tank-Setup.exe"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/download-windows-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/readme/download-windows-light.svg">
  <img alt="Descargar para Windows (x64, instalador .exe)" src="assets/readme/download-windows-dark.svg" width="332">
</picture></a>
</p>

<p align="center"><sub>¿Buscas otra versión? <a href="https://github.com/sam-wilkie/margarita-tank/releases">Ver todas las releases</a></sub></p>

Ambos instaladores incluyen la app de la barra de menú / bandeja con el simulador integrado, y la app instala los hooks de Claude Code en el primer arranque. Después, reinicia tus sesiones de Claude Code.

<details>
<summary><b>Notas de instalación</b> (macOS, Windows y hardware)</summary>

<br>

- **macOS**: abre el DMG y arrastra la app a Aplicaciones. Está firmada ad-hoc pero no notarizada por Apple, así que la primera vez hay que hacer clic derecho → **Abrir** (o *Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente*). Si macOS dice que la app "está dañada", ejecuta `xattr -dr com.apple.quarantine "/Applications/Margarita Tank.app"`.
- **Windows**: instalación por usuario, sin permisos de administrador. El instalador no está firmado, así que SmartScreen puede mostrar un aviso: haz clic en **Más información** → **Ejecutar de todas formas**. Al desinstalar se quitan de `~/.claude/settings.json` solo los hooks de Clawdy y, si lo activaste, la carpeta del panel de Claude Code; tus propios hooks quedan intactos.
- **Hardware**: el firmware del ESP32 no va en los instaladores; se flashea aparte (ver [Firmware](#firmware-esp-idf-53x)). Flashéalo de nuevo para ver las animaciones y el fondo nuevos; con un firmware anterior la app sigue funcionando con lo que ese firmware conoce. Sin hardware, usa el simulador incluido desde el menú de la app.
- **Bluetooth en PC de escritorio**: si la conexión se corta o falla con `Unreachable`, revisa que la placa tenga puestas las antenas Wi-Fi/Bluetooth. Sin ellas la señal llega muy débil (cerca de -95 dBm) aunque el ESP32 esté al lado.

</details>

## `$ ./clawdy --preview`

<table>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/preview-sesiones.png" alt="Dos sesiones de Claude Code activas, con la barra de uso de sesión y semanal en la parte superior"><br>
<b>Varias sesiones + barra de uso</b><br>
Un Clawdy por sesión, cada uno con su animación, y el consumo de tokens siempre visible arriba.<br>
<code>5 HORAS · SEMANA · ⟳ reinicio · reloj</code>
</td>
<td width="50%" valign="top">
<img src="assets/readme/preview-notificacion.png" alt="Tarjeta de notificación en español junto a Clawdy"><br>
<b>Notificaciones</b><br>
Cuando la API de Claude falla, aparece una tarjeta y el LED RGB parpadea. Que Claude termine su turno o te esté esperando lo muestra Clawdy, sin tarjetas.<br>
<code>hasta 8 tarjetas · rotación automática</code>
</td>
</tr>
</table>

<sub>Capturas del simulador escaladas 3x. Los valores de uso son de demostración.</sub>

### Fondo de escena animado

Clawdy ya no se para sobre un suelo plano: vive en una pequeña escena con vida propia.

- **Cielo con ciclo día/noche** — el degradé cambia a lo largo del día: amanecer cálido, día azul, atardecer naranja/violeta y noche con estrellas que titilan.
- **Sol y luna por hora** — recorren un arco de este a oeste según la hora real: salen por un lado detrás de las montañas, llegan al cenit al mediodía (la luna, a medianoche) y se ponen por el otro lado.
- **Colinas y nubes** — montañas redondeadas con volumen y nubes de distintos tamaños que derivan lento por el cielo; una pasa por detrás de las montañas para dar profundidad.
- **Piso con textura** — pasto con borde iluminado y matitas sobre una banda de tierra, en vez de una franja plana.

### Animaciones

<table>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/anim-wake.png" alt="Clawdy despertándose"><br>
<b>Despertar</b> · <code>wake</code><br>
Clawdy se despierta cuando arranca una sesión mientras la pantalla dormía.
</td>
<td width="50%" valign="top">
<img src="assets/readme/anim-happy.png" alt="Clawdy saltando de alegría"><br>
<b>¡Listo!</b> · <code>happy</code><br>
Un salto de alegría cuando Claude termina su turno o cuando un subagente termina su trabajo.
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/anim-low-battery.png" alt="Clawdy adormilado con una batería baja"><br>
<b>Pila baja</b> · <code>low_battery</code><br>
Reemplaza al reposo cuando tu uso de Claude (5 h o semanal) llega al 90 %.
</td>
<td width="50%" valign="top">
<img src="assets/readme/anim-hat-mishap.png" alt="Clawdy con el sombrero de mago caído"><br>
<b>Sombrero caído</b> · <code>hat_mishap</code><br>
Cuando falla una búsqueda o descarga web (WebSearch / WebFetch).
</td>
</tr>
</table>

También hay una animación de **señal MCP** (`beacon`): Clawdy levanta una antena con ondas de señal cuando una herramienta MCP está en uso. Mientras haces otra cosa, Clawdy muestra lo que hace la sesión principal (pensar, escribir, construir…), y el contador del mini-cangrejo (<code>x1</code>, <code>x2</code>…) indica cuántos subagentes trabajan en segundo plano.

### Íconos

<p>
<img src="assets/readme/icon-app.png" width="96" alt="Ícono de la app: Clawdy sobre un cuadrado oscuro">
&nbsp;&nbsp;
<img src="assets/readme/icon-tray-disconnected.png" width="48" alt="Bandeja: desconectado (gris)">
<img src="assets/readme/icon-tray-connected.png" width="48" alt="Bandeja: conectado (naranja)">
<img src="assets/readme/icon-tray-notifications.png" width="48" alt="Bandeja: con notificaciones (punto rojo)">
</p>

Ícono de la app e instalador, y los tres estados de la bandeja de Windows: <b>gris</b> desconectado, <b>naranja</b> conectado y <b>punto rojo</b> con notificaciones. En macOS la barra de menú mantiene íconos monocromos que se adaptan al tema.

## `$ cat novedades.md`

Lo que agrega Clawdy sobre el Clawd Tank original:

<table>
<tr>
<td width="50%" valign="top">
<b>Fondo de escena animado</b><br>
Ciclo día/noche completo, sol y luna que recorren un arco según la hora (detrás de las montañas al salir y ponerse), colinas con volumen, nubes de varios tamaños que derivan a distinta velocidad, y un piso con textura de pasto y tierra.<br>
<code>C · LVGL · firmware/main/scene.c</code>
</td>
<td width="50%" valign="top">
<b>Animaciones nuevas</b><br>
Rediseño v2 de los sprites y animaciones nuevas: <code>wake</code>, <code>low_battery</code>, <code>hat_mishap</code>, <code>happy</code> al terminar cada turno y la señal MCP <code>beacon</code> portada al estilo v2.<br>
<code>C · LVGL · sprites RLE · pipeline SVG→v2</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>Mod para Claude Code</b><br>
Un panel lateral dentro de Claude Code con Clawdy animado siguiendo tu sesión, con el sprite escalado para ocupar menos espacio en la terminal.<br>
<code>TypeScript · claude-mod/margarita-band</code>
</td>
<td width="50%" valign="top">
<b>App e instalador de Windows</b><br>
App de bandeja y un instalador por usuario (sin admin), con el simulador integrado y la instalación de hooks en el primer arranque.<br>
<code>Python · PyInstaller · Inno Setup</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>Barra de uso de tokens</b><br>
Franja superior con SESSION (5 h) y WEEKLY (7 d) como barras de progreso con color condicional (verde → lima → amarillo → naranja → rojo), cuenta regresiva de reset y reloj.<br>
<code>C · LVGL · firmware/main/scene.c</code>
</td>
<td width="50%" valign="top">
<b>Localización en español</b><br>
Textos de las tarjetas de notificación y de la interfaz en español.<br>
<code>C · firmware/main/notification_ui.c</code>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>Robustez en Windows</b><br>
Conexión BLE con un solo bucle por transporte, sin caché GATT de Windows y con límites de tiempo en escaneo/conexión; limpieza adaptativa de sesiones fantasma; fix de watchdog del ESP32-C6.<br>
<code>Python · bleak · WinRT · FreeRTOS</code>
</td>
<td width="50%" valign="top">
<b>Compatibilidad de firmware</b><br>
El firmware anuncia el protocolo v3; con un firmware anterior el daemon traduce las animaciones nuevas a las que ya conoce, así que actualizar la app antes que el ESP32 no rompe nada.<br>
<code>NimBLE · GATT · daemon</code>
</td>
</tr>
</table>

## `$ cat arquitectura.md`

```
Claude Code hooks --> clawd-tank-notify --> daemon --> BLE --> ESP32-C6
                                                  \-> TCP --> Simulador (SDL2)
```

1. Los **hooks de Claude Code** (`SessionStart`, `PreToolUse`, `PreCompact`, `Stop`, `Notification`, `SessionEnd`, `SubagentStart/Stop`, etc.) se disparan con los eventos de sesión.
2. **clawd-tank-notify** reenvía el evento al daemon por un socket local.
3. El **daemon** (Python) sigue el estado de cada sesión, asigna animaciones según la herramienta, lee tu consumo del caché del statusline y envía payloads JSON a los transportes.
4. El **firmware** (o el simulador) renderiza a Clawdy, el fondo de escena, las notificaciones y la barra de uso en la pantalla.

## `$ cat stack.yaml`

```yaml
firmware:   C (ESP-IDF 5.3.x), LVGL 9.5, NimBLE
simulador:  C + SDL2 (macOS y Windows)
host:       Python >= 3.10 (asyncio, bleak para BLE)
mod:        TypeScript (panel de Claude Code)
hardware:   ESP32-C6, display ST7789 320x172
```

## `$ ./install --from-source`

### Firmware (ESP-IDF 5.3.x)

```bash
cd firmware
idf.py build
idf.py -p <PUERTO> flash monitor
```

En Windows el puerto es `COMx` (p. ej., `COM5`); en macOS/Linux, `/dev/ttyACM0` o similar.

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
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
.venv/bin/python -m clawd_tank_daemon.daemon --sim   # con simulador
.venv/bin/python -m clawd_tank_daemon.daemon         # con BLE
.venv/bin/python -m clawd_tank_menubar               # app de barra de menú / bandeja
```

## `$ ./configurar`

El daemon instala un hook handler en `~/.clawd-tank/clawd-tank-notify` (`clawd-tank-notify.py` en Windows). Para conectarlo a Claude Code, agrega los hooks a `~/.claude/settings.json` (o usa el instalador de la app). Reinicia las sesiones de Claude Code para que los cambios surtan efecto.

La app también conecta la barra de uso de tokens a través del `statusLine` de Claude Code: instala `~/.clawd-tank/statusline_bridge.sh` (un script `sh` que no necesita Python; `margarita-statusline.exe` en el instalador de Windows) y lo registra como `statusLine` en `~/.claude/settings.json`. El puente guarda los límites de uso en `~/.clawd-tank/statusline-cache.json` y encadena tu `statusLine` anterior, así que tu línea de estado sigue funcionando igual. Al desinstalar los hooks se restaura tu `statusLine` original.

### Panel de Clawdy dentro de Claude Code (opcional)

Clawdy también puede vivir **dentro de Claude Code**: un panel lateral con el cangrejo animado (el uso de 5 h y semanal solo aparece como aviso de batería baja al llegar al 90 %), que sigue lo que hace tu sesión (pensando, escribiendo, esperando tu respuesta…). Es un mod de Claude Code (`claude-mod/margarita-band/`) y viene **desactivado**.

- **Activarlo o desactivarlo**: menú de la app → **Claude Code Mod (panel)**, junto a *Install Claude Code Hooks* (macOS y Windows). La marca indica que está activo.
- **Qué hace**: al activarlo copia el mod a `~/.clawd-tank/claude-mod/margarita-band/` y agrega esa carpeta a `env.CLAUDE_CODE_PLUGIN_DIRS` en `~/.claude/settings.json`; Claude Code carga cada carpeta de esa lista igual que `--plugin-dir` (varias carpetas se separan con `:` en macOS y `;` en Windows). Tus otras carpetas y el resto de tu configuración quedan intactos. Al desactivarlo se quita solo la carpeta de Clawdy. Si `settings.json` no es un JSON válido, la app no lo toca y te avisa. Al desinstalar la app también se quita.
- **Reinicia tus sesiones de Claude Code** después de activarlo o desactivarlo: las sesiones abiertas no vuelven a leer esa lista.
- **Dónde aparece**: en pantalla completa el panel se acopla a la **derecha** desde unas **110 columnas** de ancho; en una terminal más angosta se muestra encima del prompt. `/margarita` lo abre de nuevo; `/margarita <animación>` previsualiza una animación y `/margarita auto` vuelve al modo automático.
- **Barras de uso**: las lee de `~/.clawd-tank/statusline-cache.json`, el mismo archivo que escribe el puente de `statusLine` de arriba.

## `$ ./test`

```bash
# Tests del host (daemon + protocolo)
cd host && .venv/bin/python -m pytest -v   # Windows: .venv\Scripts\python -m pytest -v

# Tests C del firmware (notification store)
cd firmware/test && make test
```

## `$ cat CREDITS`

- Proyecto original: [Clawd Tank](https://github.com/marciogranzotto/clawd-tank), de Marcio Granzotto Rodrigues (MIT).
- Clawdy (fondo de escena, animaciones v2, mod de Claude Code, app/instalador de Windows, localización y mejoras): Sam Wilkie.

## `$ cat LICENSE`

MIT. Consulta [LICENSE](LICENSE): conserva el copyright original de Marcio Granzotto Rodrigues, además del de las modificaciones de Clawdy.
