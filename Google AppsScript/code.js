/**
 * Configuración global para facilitar el mantenimiento.
 */
const CONFIG = {
  PAGINA_INICIAL: 'Index',
  // --- AÑADIR ESTO ---
  // Reemplace con el ID de su Hoja de Cálculo
  ID_SHEET_DATOS: 'ID_DE_SU_HOJA_DE_CALCULO', 
  // Nombre de la hoja (pestaña) donde se guardarán los datos
  NOMBRE_HOJA_DATOS: 'Respuestas' 
};

/**
 * Sirve la aplicación web principal.
 * @param {object} e - Parámetros del evento (no usado aquí).
 * @returns {HtmlOutput} La página HTML principal (Index.html).
 */
function doGet(e) {
  return HtmlService.createHtmlOutputFromFile(CONFIG.PAGINA_INICIAL)
      .setTitle('Mi Aplicación Web Multi-página')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}

/**
 * Función expuesta a google.script.run para obtener el contenido de 
 * otros archivos HTML del proyecto.
 * @param {string} nombreArchivo - El nombre del archivo HTML (sin .html) a cargar.
 * @returns {string} El contenido HTML del archivo solicitado.
 */
function obtenerContenidoHtml(nombreArchivo) {
  // (Esta función no necesita cambios)
  if (!nombreArchivo || typeof nombreArchivo !== 'string' || nombreArchivo.includes('.')) {
    Logger.log(`Intento de carga inválido: ${nombreArchivo}`);
    throw new Error('Nombre de archivo no válido.');
  }
  try {
    return HtmlService.createHtmlOutputFromFile(nombreArchivo).getContent();
  } catch (err) {
    Logger.log(`Error al cargar el archivo HTML: ${nombreArchivo}. Detalles: ${err}`);
    return `<p style="color: red;">Error: No se pudo cargar la página '${nombreArchivo}'.</p>`;
  }
}

// --- FUNCIÓN NUEVA ---
/**
 * Recibe los datos del formulario de pagina1.html y los guarda en un Sheet.
 * @param {object} formData - El objeto de datos enviado desde el cliente.
 * @returns {string} Un mensaje de éxito.
 * @throws {Error} Si no se puede escribir en el Sheet.
 */
function submitForma1Entry(formData) {
  try {
    const sheet = SpreadsheetApp.openById(CONFIG.ID_SHEET_DATOS)
                      .getSheetByName(CONFIG.NOMBRE_HOJA_DATOS);
    
    if (!sheet) {
      throw new Error(`No se encontró la hoja: ${CONFIG.NOMBRE_HOJA_DATOS}`);
    }

    // Asegurarse que las cabeceras coincidan con el orden del formulario
    // (Ej: Fecha, Usuario, Numero)
    const fila = [
      formData.fecha,
      formData.usuario,
      formData.numero
    ];
    
    sheet.appendRow(fila);
    
    Logger.log(`Datos guardados: ${JSON.stringify(fila)}`);
    return 'Registro almacenado correctamente.';

  } catch (e) {
    Logger.log(`Error al guardar en Sheet: ${e.message}`);
    // Exponer un error amigable al cliente
    throw new Error(`Error del servidor al guardar: ${e.message}`);
  }
}