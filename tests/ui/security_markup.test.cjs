const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../app/routes/ui_assets.py'), 'utf8');
test('creator and provider text cannot break out of HTML text or attributes', () => {
  const start = source.indexOf('function escapeMarkup(value)');
  const end = source.indexOf('(function()', start);
  const context = {};
  vm.runInNewContext(source.slice(start, end), context);
  const payload = '<img src=x onerror="alert(1)">\' & &#34;';
  const escaped = context.escapeMarkup(payload);
  assert.equal(escaped, '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&#39; &amp; &amp;#34;');
  assert.equal(context.escapeMarkup('قُلْ هُوَ اللَّهُ أَحَدٌ'), 'قُلْ هُوَ اللَّهُ أَحَدٌ');
});
