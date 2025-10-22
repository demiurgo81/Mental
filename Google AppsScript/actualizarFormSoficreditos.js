function probarFunciones() {
  monitorButtonControl();
  //setInitialProps_();
  //sendQuickKeyboard_();
  //debugLastChatId_();
  //fetchTelegramUpdates();
  //mensajeTelegram(TG_TOKEN, TG_CHAT_COM, mensaje = 'Mensaje default ✅' ) 
}

// Función para actualizar los desplegables del formulario
function actualizarFormulario() {
  logDeArray('PASO1: TRAER DATOS INDEXADOS DE LA HOJA');
  const catalogoInx = extraerArregloSheet(SPREADSHEET_ID,'listado');
  //logDeArray('CATALOGO INDEXADO');  logDeArray(catalogoInx.slice(0,3));

  logDeArray('PASO2: TRANSFORMA DATOS DE LA HOJA EN TABLA');
  var catalogoTab = indexAr2tableAr(catalogoInx);
  //logDeArray('CATALOGO TABULADO');  logDeArray(catalogoTab.slice(0,4));
  
  logDeArray('PASO3: ORDENA Y DEJA SOLO LOS CAMPOS TIPO Y DESPLEGABLE(VALOR)');
  campDesplegable = ["tipo","Escenario"];
  tabdesplegable = organizarTablaCampo(catalogoTab, campDesplegable);
  campDesplegable = ["tipo","desplegable"];
  tabdesplegable = unicValuesAr(tabdesplegable, campDesplegable); 
  insertarTablaEnHoja(SPREADSHEET_ID,'resumen',tabdesplegable,0,0,"A1:B200");
  //logDeArray('DESPLEGABLE TABULADO UNICO E INDEXADO');  logDeArray(tabdesplegable.slice(0,4));

  logDeArray('PASO4: GENERA ARREGO INDEXADO DE TIPO Y VALOR');
  arrayInd = tableAr2indexAr(tabdesplegable);
  //logDeArray('DESPLEGABLE INDEXADO');  logDeArray(arrayInd.slice(0,4));
  
  logDeArray('PASO5: INICIA MODIFICACION DE LOS DESPLEGABLES DESDE EL ARREGO INDEXADO TIPO Y VALOR');
  var desplegables = [
  { "Multa": "desiciones" },
  { "Incentivo": "incentivos" },
  { "Catalogo": "recompensas" },
  ];
  actualizarOpciones(FORM_ID,desplegables,arrayInd);
  mensajeTelegram(TG_TOKEN, TG_CHAT_COM,mensaje = 'Se actualizo el formulario SOFICREDITOS ✅' ) 
}

// Función para actualizar un desplegable específico del formulario
function actualizarDesplegable(form, titulo, opciones) {
  const items = form.getItems(FormApp.ItemType.LIST);
  
  items.forEach(item => {
    if (item.getTitle() === titulo) {
      const desplegable = item.asListItem();
      desplegable.setChoiceValues(opciones);
    }
  });
}

// Función para configurar el trigger
function crearTrigger() {
  try {
    const hoja = SpreadsheetApp.openById(SPREADSHEET_ID);
    ScriptApp.newTrigger('actualizarFormulario')
      .forSpreadsheet(hoja)
      .onEdit()
      .create();
  } catch (e) {
    Logger.log('Error: ' + e.message);
  }
}

// Función de inicialización para configurar el trigger y actualizar el formulario
function inicializar() {
  crearTrigger();
  actualizarFormulario();
}
