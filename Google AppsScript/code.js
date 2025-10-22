/**
 * Configuración global para facilitar el mantenimiento.
 */
const CONFIG = {
  PAGINA_INICIAL: 'Index'
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


