function monitorButtonControl() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TG_TOKEN');
  if (!token) throw new Error('Falta TG_TOKEN en Script Properties. Ejecuta setInitialProps_().');

  const targetChatId = String(TG_CHAT_COM);
  const offsetKey = TG_BUTTON_OFFSET_KEY;

  let offset = parseInt(props.getProperty(offsetKey) || '0', 10);
  if (isNaN(offset)) offset = 0;

  const telegramResult = telegramGetUpdates_(token, offset);
  if (!telegramResult.ok) return;

  const updates = telegramResult.updates;
  if (!updates.length) {
    props.setProperty(offsetKey, String(telegramResult.newOffset));
    return;
  }

  updates.forEach(function(upd) {
    try {
      processButtonControlUpdate_(token, upd, targetChatId, props);
    } catch (err) {
      Logger.log('monitorButtonControl error: ' + err.message);
    }
  });

  props.setProperty(offsetKey, String(telegramResult.newOffset));
}
