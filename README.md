# Scalper Bot — RF x Hull x STC MTF Confluence → Telegram

Bot que replica en Python la lógica de tu indicador de Pine Script
(`RF_Hull_STC_MTF_Confluence.pine`: Range Filter + Hull Suite + confluencia STC
en 15m/1H/4H), usando **Yahoo Finance** como fuente de datos, y que se ejecuta
automáticamente cada 15 minutos mediante **GitHub Actions**, enviando las
señales a un chat de **Telegram**.

## ⚠️ Antes de usarlo

- Yahoo Finance **no es** el mismo feed que TradingView o tu bróker: puede haber
  pequeñas diferencias de precio.
- Yahoo no tiene velas nativas de 4H; se derivan resampleando velas de 1H.
- Esto **no ejecuta órdenes** ni es asesoría financiera. Solo replica la lógica
  de señales del indicador y te avisa por Telegram. Las decisiones de trading
  son tuyas.
- Prueba primero en un símbolo y con `workflow_dispatch` (ejecución manual)
  antes de dejarlo en automático.

## 1. Crear el bot de Telegram

1. Habla con **[@BotFather](https://t.me/BotFather)** en Telegram.
2. Envía `/newbot`, sigue las instrucciones y copia el **token** que te da
   (algo como `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).
3. Obtén tu **chat_id**:
   - Escríbele cualquier mensaje a tu bot recién creado.
   - Abre en el navegador:
     `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
   - Busca el campo `"chat":{"id": ...}` — ese número es tu `chat_id`.
   - Si quieres que publique en un canal en vez de a ti, agrega el bot como
     administrador del canal y usa el id del canal (empieza con `-100...`).

## 2. Subir estos archivos a GitHub

Sube toda esta carpeta tal cual a un repositorio nuevo (puede ser privado):

```
scalper-bot/
├── .github/workflows/scalper_bot.yml
├── bot.py
├── requirements.txt
├── state.json
└── README.md
```

## 3. Configurar Secrets y Variables del repositorio

En GitHub: **Settings → Secrets and variables → Actions**

**Secrets** (pestaña "Secrets"):
| Nombre | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | El token que te dio BotFather |
| `TELEGRAM_CHAT_ID` | Tu chat_id (o el del canal) |

No hace falta configurar ninguna variable de par: el bot ya trae precargados
los 19 pares cripto (`PAIRS` en `bot.py`), cada uno con su ticker equivalente
de Yahoo Finance (`YF_SYMBOLS`):

BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT, XRP/USDT, DOGE/USDT,
AVAX/USDT, LINK/USDT, DOT/USDT, NEAR/USDT, OP/USDT, ATOM/USDT, RENDER/USDT,
INJ/USDT, WLD/USDT, TIA/USDT, ZEC/USDT, XMR/USDT.

En cada ejecución el bot recorre los 19 pares uno por uno (si uno falla —por
ejemplo por un símbolo que Yahoo no reconozca ese día— se salta y sigue con
los demás; el error queda en los logs del workflow). Si quieres agregar,
quitar o cambiar algún par, edita las listas `PAIRS` y `YF_SYMBOLS` al inicio
de `bot.py` (deben tener las mismas claves en `symbol`).

## 4. Dar permiso de escritura al workflow (para guardar el estado)

**Settings → Actions → General → Workflow permissions** → selecciona
**"Read and write permissions"** y guarda.

Esto es necesario porque el bot guarda en `state.json` la última vela ya
notificada, para no mandarte el mismo aviso varias veces si el workflow corre
más seguido que el cierre de una vela.

## 5. Probarlo manualmente

Ve a la pestaña **Actions** del repo → selecciona el workflow
**"Scalper Bot - RF x Hull x STC MTF"** → **Run workflow**. Revisa los logs;
si todo está bien configurado, deberías recibir un mensaje en Telegram si hay
señal en la última vela cerrada (o ver "Sin señal en la última vela cerrada"
en los logs si no la hay).

Una vez confirmado, el `cron` en `.github/workflows/scalper_bot.yml` lo
ejecutará automáticamente cada 15 minutos.

## 6. Ajustar parámetros del indicador

Todos los parámetros (Range Filter, Hull, STC, filtro de triple MA, etc.) están
al inicio de `bot.py`, en la sección `CONFIGURACIÓN`, con los mismos valores
por defecto que trae tu script de Pine. Cámbialos ahí si usas otra
configuración en TradingView.

## Estructura de las alertas

| Prioridad | Significado |
|---|---|
| 🔥 FULL | Señal base (RF+Hull) + STC 15m en gatillo + sesgo 1H y 4H alineados |
| ⚠️ PARCIAL | Señal base + STC 15m en gatillo + sesgo alineado en 1H **o** 4H (no ambos) |
| ℹ️ INFO | Señal base sin confluencia de STC |

Cada alerta incluye el emoji propio de la moneda (🟠 BTC, 🔷 ETH, 🟣 SOL, etc.,
todos editables en `PAIRS`), la dirección (📈 LONG / 📉 SHORT), el marco
temporal, el precio formateado según su magnitud y la vela exacta. Ejemplo:

```
🔥 SEÑAL FULL  🟠
━━━━━━━━━━━━━━━
🪙 Par: BTC/USDT
📈 LONG (compra)
⏱️ Marco: 15m
💰 Precio: 105,234.56
📊 ✅ 15m + ✅ 1H + ✅ 4H alineados
🕒 Vela: 2026-07-26T15:00:00+00:00
```

## Notas técnicas / limitaciones conocidas

- `ta.rma` de Pine se aproxima con un EMA de `alpha = 1/length` (razonablemente
  cercano, no idéntico bar a bar).
- El filtro de sesión ("New York", "London", etc.) del script original **no**
  está implementado en el bot (queda simplificado a "sin filtro"); si lo
  necesitas, dilo y se puede agregar.
- La vela en formación nunca se evalúa (equivalente a `barstate.isconfirmed`),
  así que las alertas siempre corresponden a una vela 15m ya cerrada.
