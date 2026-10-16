const test = require('node:test');
const assert = require('node:assert/strict');
const { translate } = require('../localization/store/store-zh.user.js');

test('translates screenshot navigation without translating unknown products', () => {
  assert.equal(translate('  Buffs & Services\n'), '  增益与服务\n');
  assert.equal(translate('A New Unreviewed Product'), 'A New Unreviewed Product');
});
test('keeps prices, point balances, quantities and discount figures', () => {
  for (const price of ['7,995', '109', '28', '$49.99', '-30%', 'https://store.lotro.com/']) {
    assert.equal(translate(price), price);
  }
  assert.equal(translate('59 items'), '59 件商品');
  assert.equal(translate('1 day'), '1 天');
  assert.equal(translate('+20% Mount Speed (6 hours) x5'), '+20% 坐骑速度（6 小时） x5');
});
test('does not drift on observer revisits', () => {
  for (const value of ['Specials', '+10% Run Speed Boost x5 (6 hours)', 'Max. 10']) {
    const once = translate(value);
    assert.equal(translate(once), once);
  }
});
