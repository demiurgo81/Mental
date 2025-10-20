/** /INSERTA UN ARREGLO BIDIMENSIONAL EN UNA HOJA DE CALCULO /**/
function insertarTablaEnHoja(libroId,nombreHoja,tablaAr, fila = 0, columna = 0,rangoUbicacion="A1:J200"){
    var log = Logger.log;
	var formSpreadsheet = SpreadsheetApp.openById(libroId);
	// Crear o modificar una sheet en formSpreadsheetId titulada diligenciamiento
    var diligenciamientoSheet = formSpreadsheet.getSheetByName(nombreHoja);
    if (!diligenciamientoSheet) {
      diligenciamientoSheet = formSpreadsheet.insertSheet(nombreHoja);
    } else {
      diligenciamientoSheet.getRange(rangoUbicacion).clearContent();
    }

    // Cargar la tabla tablaAr en la hoja diligenciamiento a partir de fila y columna
    diligenciamientoSheet.getRange(fila + 1, columna + 1, tablaAr.length, tablaAr[0].length).setValues(tablaAr);
	

    log("Se genero la hoja "+nombreHoja+" con los datos de la tabla");
}

function actualizarOpciones(formId,desplegables,arrayInd,campoIdx = "tipo"){
  desplegables.forEach(function(desplegable) {
    // Obtener la clave y el valor del objeto
    var indice = Object.keys(desplegable)[0];
    var formTitulo = Object.values(desplegable)[0];
    var indexAr = arrayInd.filter(record => record[campoIdx] === indice);
    var opcionDesplegable = indexAr.map(record => record.desplegable);
    
    actualizarOpcionesFormulario(formId, formTitulo, opcionDesplegable);
    logDeArray("Se actualiza la pregunta: " + formTitulo + ", Con los datos del indice: " + indice+ " por ejemplo: "); logDeArray(opcionDesplegable.slice(0,2));
  });
}

/** / TRANSFORMA UNA ARREGO BIDIMENSIONAL EN UN ARREGO INDEXADO  /**/
function tableAr2indexAr(tableAr) {
  // Obtener los nombres de las columnas de la primera fila
  const headers = tableAr[0];

  // Crear un nuevo arreglo para almacenar los objetos
  const result = [];

  // Iterar sobre las filas a partir de la segunda
  for (let i = 1; i < tableAr.length; i++) {
    const row = tableAr[i];
    const obj = {};

    // Crear un objeto para cada fila, asignando propiedades y valores
    for (let j = 0; j < headers.length; j++) {
      obj[headers[j]] = row[j];
    }

    // Agregar el objeto al arreglo de resultados
    result.push(obj);
  }

  return result;
}

/** / ACTUALIZAR OPCIONES MULTIPLES EXISTENTES EN FORMULARIO DESDE TITULO PREGUNTA  /**/
function actualizarOpcionesFormulario(formId, formTitulo, opciones) {
  const form = FormApp.openById(formId);
  const items = form.getItems();
  let itemEncontrado = false;
  items.forEach(item => {
    const titulo = item.getTitle();
    if (titulo === formTitulo) {
      itemEncontrado = true;
      const tipo = item.getType();
      let itemOpciones;

      if (tipo === FormApp.ItemType.MULTIPLE_CHOICE) {
        itemOpciones = item.asMultipleChoiceItem();
      } else if (tipo === FormApp.ItemType.LIST) {
        itemOpciones = item.asListItem();
      } else {
        throw new Error('Tipo de ítem no compatible: ' + tipo);
      }

      itemOpciones.setChoiceValues(opciones);
    }
  });
  if (!itemEncontrado) {
    throw new Error('El ítem "' + formTitulo + '" no fue encontrado en el formulario');
  }
}

/** / QUITAR DUPLICADOS DE UNA ARREGLO /**/
function unicValuesAr(tablaAr, listaIndex) {
  // Obtener la primera fila con los encabezados
  const encabezados = tablaAr[0];
  
  // Crear un objeto para mapear los nombres de los campos a sus índices en la tabla
  const indices = {};
  for (let i = 0; i < encabezados.length; i++) {
    if (listaIndex.includes(encabezados[i])) {
      indices[encabezados[i]] = i;
    }
  }

  // Crear un conjunto para almacenar las combinaciones únicas
  const combinacionesUnicas = new Set();

  // Recorrer las filas de datos y agregar las combinaciones únicas al conjunto
  for (let i = 1; i < tablaAr.length; i++) {
    const fila = tablaAr[i];
    const combinacion = listaIndex.map(campo => fila[indices[campo]]).join('|');
    combinacionesUnicas.add(combinacion);
  }

  // Convertir el conjunto de combinaciones únicas en un arreglo y agregar los encabezados
  const resultado = [listaIndex];
  combinacionesUnicas.forEach(combinacion => {
    resultado.push(combinacion.split('|'));
  });

  return resultado;
}

/** / ORGANIZA ARREGLO DE UNA TABLA /**/
function organizarTablaCampo(tablaAr, camposAr, orden = "AS") {
  // Determina el índice de los campos a ordenar
  let indices = camposAr.map(campo => tablaAr[0].indexOf(campo));
  
  // Verifica si los campos existen en la tabla
  if (indices.includes(-1)) {
    throw new Error("Uno o más campos no existen en la tabla");
  }

  // Ordena la tabla según los campos y el orden especificado
  let sortedTablaAr = tablaAr.slice(1).sort((a, b) => {
    for (let i = 0; i < indices.length; i++) {
      let idx = indices[i];
      if (a[idx] < b[idx]) return orden === "AS" ? -1 : 1;
      if (a[idx] > b[idx]) return orden === "AS" ? 1 : -1;
    }
    return 0;
  });

  // Retorna la tabla ordenada, incluyendo la fila de encabezado
  return [tablaAr[0]].concat(sortedTablaAr);
}

/** / EXTRAE ARREGLO INDEXADO DE UNA HOJA DE CALCULO OLD:extraerRespuestaForm/**/
function extraerArregloSheet(formSpreadsheetId, respuestaSheet = 'Respuestas de formulario 1'){
  var formSpreadsheet = SpreadsheetApp.openById(formSpreadsheetId);
  var sheet = formSpreadsheet.getSheetByName(respuestaSheet);
  if (!sheet) {
    throw new Error('Sheet no encontrada: ' + respuestaSheet);
  }

  var data = sheet.getDataRange().getValues();
  var headers = data[0];
  var respAr = [];
  
  for (var i = 1; i < data.length; i++) {
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      row[headers[j]] = data[i][j];
    }
    respAr.push(row);
  }
  //logDeArray('EJEMPLO DE DATA:');
  //logDeArray(respAr.slice(0,2));
  return respAr;
}

/** / TRANSFORA UN ARREGLO INDEXADO EN UN ARREGLO BIDIMENSIONAL /**/
function indexAr2tableAr(respAr) {
  // Obtener los nombres de las columnas (índices del primer registro)
  const columnNames = Object.keys(respAr[0]);

  // Crear una matriz para almacenar los datos de la tabla
  const tableData = [columnNames];

  // Recorrer los registros y extraer los valores
  for (const registro of respAr) {
    const fila = columnNames.map(columna => registro[columna]);
    tableData.push(fila);
  }

  return tableData;
}

/** / IMPRIME EN EL LOG EN FORMATO ARREGLO /**/
function logDeArray(arreglo){
  Logger.log(JSON.stringify(arreglo)); 
}


/** / ENVIA MENSAJE A UN BOT DE TELEGRAM /**/
function mensajeTelegram(token, id, mensaje = 'Mensaje default ✅' ) {
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  /**/
  const body = {
    chat_id: id,
    text: mensaje,
    parse_mode: "HTML",
    disable_web_page_preview: false // si quieres miniatura del link
  };
  /** /
  const body = {
    chat_id: id,
    text: mensaje,
    parse_mode: "MarkdownV2"
  };
  /**/
  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(body)
  });
  Logger.log(res.getContentText());
}

//----------------
/**********************
 * TELEGRAM → SHEETS
 * Modo: Polling (sin webhook)
 * Autor: Tú 😉 + GAS
 **********************/

// === Configuración básica ===
// Recomendado: dejar Spreadsheet y Sheet en Propiedades también.
// Si no configuras props, tomará el spreadsheet actual y creará/usar la hoja "Telegram".
const DEFAULT_SHEET_NAME = 'Telegram';

// === Claves en Script Properties ===
// TG_TOKEN       -> token del bot (BotFather)
// TG_CHAT_ID     -> opcional, si quieres filtrar por un chat/grupo específico
// TG_OFFSET      -> interno: último update procesado (no tocar)
// SS_ID          -> opcional: SpreadsheetId de destino
// SH_NAME        -> opcional: nombre de la hoja de destino

/**
 * Paso 0 (una vez): guarda tu token y (opcional) el Spreadsheet y Sheet
 * Ejecuta manualmente setInitialProps_() y edita los valores antes.
 */
function setInitialProps_() {
  const props = PropertiesService.getScriptProperties();
  props.setProperties({
    TG_TOKEN: TG_TOKEN,
    TG_CHAT_ID: TG_CHAT_COM, // opcional: id de grupo/canal/supergrupo; para DMs suele ser un número positivo
    SS_ID: '1S3qYQGNMIOEnpHlBpku9x9CJgaLKqMH22fn_Rg08MKU', // opcional: Spreadsheet destino
    //SH_NAME: 'Telegram' // opcional: nombre de hoja destino
  }, true);
  Logger.log('Propiedades guardadas. Edita aquí con tu token y/o IDs si lo requieres.');
}

/**
 * Crea (si no existe) el trigger de tiempo para leer Telegram cada minuto.
 * Ejecuta una vez: createMinuteTrigger()
 */
function createMinuteTrigger() {
  ScriptApp.newTrigger('fetchTelegramUpdates')
    .timeBased()
    .everyMinutes(1)
    .create();
  Logger.log('Trigger creado: fetchTelegramUpdates() cada 1 min.');
}

/**
 * Tarea programada: trae updates, parsea mensajes y guarda en Sheets.
 * Vincúlala al trigger de tiempo.
 */
function fetchTelegramUpdates() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TG_TOKEN');
  if (!token) throw new Error('Falta TG_TOKEN en Script Properties. Ejecuta setInitialProps_().');

  const chatFilter = props.getProperty('TG_CHAT_ID'); // opcional
  let offset = parseInt(props.getProperty('TG_OFFSET') || '0', 10);

  const url = getTelegramUrl_(token, 'getUpdates');
  const payload = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({
      offset: offset ? offset + 1 : undefined,
      timeout: 0
    }),
    muteHttpExceptions: true
  };

  const resp = UrlFetchApp.fetch(url, payload);
  const data = JSON.parse(resp.getContentText());

  if (!data.ok) {
    Logger.log('Telegram getUpdates NO ok: ' + resp.getContentText());
    return;
  }

  const updates = data.result || [];
  if (!updates.length) return;

  updates.forEach(upd => {
    try {
      const updateId = upd.update_id;
      offset = Math.max(offset, updateId);

      // Mensajes estándar
      if (upd.message && upd.message.text) {
        const chatId = upd.message.chat && upd.message.chat.id ? String(upd.message.chat.id) : '';
        if (chatFilter && chatFilter !== chatId) return; // filtra por chat si se configuró

        const text = upd.message.text.trim();
        const parsed = parseStructuredMessage_(text);
        if (parsed) {
          // Enriquecer con metadatos
          parsed._received_ts = new Date();
          parsed._chat_id = chatId;
          parsed._user = buildUser_(upd.message.from);
          parsed._message_id = upd.message.message_id;
          appendToSheet_(parsed);
        }
      }

      // Callbacks de inline keyboard (si decides usarlos)
      if (upd.callback_query) {
        const cq = upd.callback_query;
        const chatId = cq.message && cq.message.chat && cq.message.chat.id ? String(cq.message.chat.id) : '';
        if (chatFilter && chatFilter !== chatId) return;
        // Aquí podrías parsear cq.data si decides armar “botones‑formulario”
      }

    } catch (e) {
      Logger.log('Error procesando update: ' + e.message);
    }
  });

  // guarda offset para no re-procesar
  props.setProperty('TG_OFFSET', String(offset));
}

/**
 * Intenta parsear un mensaje con formato estructurado "tipo formulario".
 * Acepta cualquiera de estos formatos (sin importar el orden de campos):
 *
 *   FECHA=2025-08-24|ITEM=Útiles escolares|COSTO=12345
 *   FECHA=24/08/2025 | ITEM=Transporte | VALOR=18.000
 *   ITEM=Comida\nCOSTO=12,500\nFECHA=2025-08-23
 *
 * Claves admitidas (insensibles a mayúsculas):
 *   FECHA / DATE
 *   ITEM / CONCEPTO / DESCRIPCION
 *   COSTO / VALOR / MONTO
 */
function parseStructuredMessage_(text) {
  // Separar por | o saltos de línea
  const parts = text.split(/\||\n/).map(s => s.trim()).filter(Boolean);
  if (!parts.length) return null;

  const kv = {};
  parts.forEach(p => {
    const idx = p.indexOf('=');
    if (idx > -1) {
      const k = p.slice(0, idx).trim().toUpperCase();
      const v = p.slice(idx + 1).trim();
      kv[k] = v;
    }
  });

  // Mapear posibles alias
  const fechaRaw = kv['FECHA'] || kv['DATE'];
  const itemRaw  = kv['ITEM'] || kv['CONCEPTO'] || kv['DESCRIPCION'];
  const costoRaw = kv['COSTO'] || kv['VALOR'] || kv['MONTO'];

  if (!fechaRaw && !itemRaw && !costoRaw) {
    // Si el mensaje NO tiene ninguna clave conocida, ignorar.
    return null;
  }

  const fecha = normalizeDate_(fechaRaw);     // Date o null
  const costo = normalizeNumber_(costoRaw);   // Number o null
  const item  = itemRaw ? String(itemRaw) : '';

  return {
    fecha,   // Objeto Date (si parseó) o null
    item,    // String
    costo,   // Number (si parseó) o null
    raw: text // Mensaje original
  };
}

/**
 * Inserta una fila en la hoja de destino.
 * Estructura de columnas (puedes ajustar a gusto):
 * [TS_Recepción, FECHA, ITEM, COSTO, Usuario, ChatId, MessageId, RAW]
 */
function appendToSheet_(obj) {
  const { ss, sh } = getSheet_();
  ensureHeader_(sh);

  const row = [
    obj._received_ts || new Date(),
    obj.fecha ? obj.fecha : '',
    obj.item || '',
    typeof obj.costo === 'number' ? obj.costo : '',
    obj._user || '',
    obj._chat_id || '',
    obj._message_id || '',
    obj.raw || ''
  ];

  sh.appendRow(row);
}

/**
 * Envía al chat una plantilla de mensaje “lista para copiar/editar”.
 * Ejecuta manualmente sendTemplateToTelegram_() para que el bot envíe la plantilla.
 */
function sendTemplateToTelegram_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TG_TOKEN');
  const chatId = props.getProperty('TG_CHAT_ID');
  if (!token || !chatId) throw new Error('Necesitas TG_TOKEN y TG_CHAT_ID en Script Properties.');

  const plantilla =
`Copia y edita (sin comillas):
FECHA=YYYY-MM-DD|ITEM=Descripción|COSTO=12345
Ejemplos:
FECHA=2025-08-24|ITEM=Útiles escolares|COSTO=35000
ITEM=Transporte|COSTO=18.000|FECHA=24/08/2025`;

  sendMessage_(token, chatId, plantilla, { disable_web_page_preview: true });
}

/**
 * Envía un “teclado” de respuestas rápidas para construir el mensaje.
 * (Gratis, nativo de Telegram; no son formularios reales, pero ayudan.)
 */
function sendQuickKeyboard_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TG_TOKEN');
  const chatId = props.getProperty('TG_CHAT_ID');
  if (!token || !chatId) throw new Error('Necesitas TG_TOKEN y TG_CHAT_ID en Script Properties.');

  const hoy = new Date();
  const y = hoy.getFullYear();
  const m = String(hoy.getMonth() + 1).padStart(2, '0');
  const d = String(hoy.getDate()).padStart(2, '0');

  // Botones que “pegan” fragmentos para que el usuario construya el texto
  const keyboard = {
    keyboard: [
      [{ text: `FECHA=${y}-${m}-${d}|` }, { text: `FECHA=${d}/${m}/${y}|` }],
      [{ text: 'ITEM=' }, { text: 'COSTO=' }],
      [{ text: 'VALOR=' }, { text: 'MONTO=' }],
      [{ text: 'Borrar teclado' }]
    ],
    resize_keyboard: true,
    one_time_keyboard: false
  };

  sendMessage_(token, chatId,
    'Usa los botones para armar el mensaje. Ejemplo final:\nFECHA=2025-08-24|ITEM=Comida|COSTO=12500',
    { reply_markup: keyboard }
  );
}

/** Helpers ————————————————————————————— */

function getTelegramUrl_(token, method) {
  return `https://api.telegram.org/bot${encodeURIComponent(token)}/${method}`;
}

function sendMessage_(token, chatId, text, extra) {
  const url = getTelegramUrl_(token, 'sendMessage');
  const payload = {
    chat_id: chatId,
    text: text,
    parse_mode: 'HTML',
    ...extra
  };

  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const json = JSON.parse(resp.getContentText() || '{}');
  if (!json.ok) Logger.log('sendMessage_ error: ' + resp.getContentText());
  return json;
}

function getSheet_() {
  const props = PropertiesService.getScriptProperties();
  const ssId = props.getProperty('SS_ID');
  const shName = props.getProperty('SH_NAME') || DEFAULT_SHEET_NAME;

  const ss = ssId ? SpreadsheetApp.openById(ssId) : SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(shName);
  if (!sh) sh = ss.insertSheet(shName);
  return { ss, sh };
}

function ensureHeader_(sh) {
  const header = ['TS_Recepción', 'FECHA', 'ITEM', 'COSTO', 'Usuario', 'ChatId', 'MessageId', 'RAW'];
  const first = sh.getRange(1, 1, 1, header.length).getValues()[0];
  const equal = first.join('||') === header.join('||');
  if (!equal) {
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.getRange(1, 1, 1, header.length).setFontWeight('bold');
  }
}

function buildUser_(from) {
  if (!from) return '';
  const name = [from.first_name, from.last_name].filter(Boolean).join(' ').trim();
  const at = from.username ? '@' + from.username : '';
  return (name || at || String(from.id)).trim();
}

function normalizeDate_(v) {
  if (!v) return null;
  const s = String(v).trim();

  // yyyy-mm-dd
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));

  // dd/mm/yyyy
  m = s.match(/^(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})$/);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));

  // dd-mm-yyyy
  m = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));

  return null; // si no se pudo parsear, lo dejamos vacío
}

function normalizeNumber_(v) {
  if (v === null || v === undefined || v === '') return null;
  // elimina separadores de miles y unifica decimal
  const s = String(v).replace(/\./g, '').replace(',', '.').trim();
  const n = Number(s);
  return isNaN(n) ? null : n;
}

/**
 * Utilidad opcional: obtener rápidamente el chat_id.
 * Paso: envía un mensaje al bot y corre esta función para ver el último chat_id.
 */
function debugLastChatId_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TG_TOKEN');
  const url = getTelegramUrl_(token, 'getUpdates');
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ timeout: 0 }),
    muteHttpExceptions: true
  });
  const data = JSON.parse(resp.getContentText());
  if (!data.ok) {
    Logger.log(resp.getContentText());
    return;
  }
  const last = (data.result || []).reverse().find(x => x.message && x.message.chat);
  if (last) Logger.log('Último chat_id: ' + last.message.chat.id);
}
