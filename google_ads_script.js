// === Google Ads Script: esporta spesa giornaliera per campagna in un Google Sheet ===
// Incolla in Google Ads -> Strumenti -> Azioni in blocco -> Script.
// 1) Sostituisci SHEET_URL con l'URL del tuo foglio.  2) Autorizza ed esegui.  3) Pianifica giornaliero.

var SHEET_URL = 'INCOLLA_QUI_URL_DEL_FOGLIO';
var DAYS = 90;

function main() {
  var ss = SpreadsheetApp.openByUrl(SHEET_URL);
  var sh = ss.getSheetByName('spesa') || ss.insertSheet('spesa');
  sh.clear();
  sh.appendRow(['data', 'campagna', 'costo']);

  var tz = AdsApp.currentAccount().getTimeZone();
  var to = new Date();
  var from = new Date(); from.setDate(from.getDate() - DAYS);
  var f = function (d) { return Utilities.formatDate(d, tz, 'yyyy-MM-dd'); };

  var q = "SELECT campaign.name, segments.date, metrics.cost_micros " +
          "FROM campaign " +
          "WHERE segments.date BETWEEN '" + f(from) + "' AND '" + f(to) + "' " +
          "AND metrics.cost_micros > 0";
  var rows = AdsApp.report(q).rows();
  var out = [];
  while (rows.hasNext()) {
    var r = rows.next();
    out.push([r['segments.date'], r['campaign.name'], Number(r['metrics.cost_micros']) / 1e6]);
  }
  if (out.length) sh.getRange(2, 1, out.length, 3).setValues(out);
  Logger.log('Righe scritte: ' + out.length);
}
