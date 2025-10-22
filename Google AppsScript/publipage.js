function doGet(e) {
  var allowedPages = ['Index', 'catalogo_Ideologico', 'pagina1'];
  var requestedPage = (e && e.parameter && e.parameter.page) || 'Index';
  var page = allowedPages.indexOf(requestedPage) !== -1 ? requestedPage : 'Index';

  return HtmlService.createHtmlOutputFromFile(page)
      .setTitle('resumen')
      .setSandboxMode(HtmlService.SandboxMode.IFRAME);
}

function getSheetData() {
  var data =  extraerArregloSheet(SPREADSHEET_ID,'resumen');
  var data =  indexAr2tableAr(data);
  if (data.length === 0) {
    Logger.log("No se encontraron datos en la hoja 'registros'.");
  } else {
    Logger.log("Datos obtenidos: " + JSON.stringify(data));
  }
  
  return data;
}


function onEdit(e) {
  // Este trigger actualizará la página web cada vez que se edite la hoja
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('resumen');
  if (e.source.getSheetName() === sheet.getName()) {
    var triggers = ScriptApp.getProjectTriggers();
    for (var i = 0; i < triggers.length; i++) {
      if (triggers[i].getHandlerFunction() == 'refreshPage') {
        ScriptApp.deleteTrigger(triggers[i]);
      }
    }
    ScriptApp.newTrigger('refreshPage')
      .timeBased()
      .after(1)
      .create();
  }
}

function refreshPage() {
  var template = HtmlService.createTemplateFromFile('Index');
  var html = template.evaluate();
  SpreadsheetApp.getUi().showSidebar(html);
}
