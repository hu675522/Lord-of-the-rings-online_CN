// ==UserScript==
// @name         LOTRO Store 中文界面（本机测试稿）
// @namespace    local.lotro-zh
// @version      0.2.0
// @description  仅替换商城已知文字；不保存账号信息，不发起网络请求。
// @match        https://store.lotro.com/*
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';
  const dictionary = new Map(Object.entries({
    'Become a VIP': '成为 VIP', 'Buy LOTRO Points': '购买 LOTRO 点数',
    'Search': '搜索', 'Specials': '精选优惠', 'Sales': '促销',
    'Account': '账号', 'Character': '角色', 'Buffs & Services': '增益与服务',
    'Collections': '收藏', 'Cosmetics': '外观', 'Crafting': '制作',
    'Featured Items': '推荐商品', 'Legendary Items': '传奇物品',
    'Monster Play': '怪物扮演', 'Redeem Code': '兑换代码',
    'Most Popular': '最受欢迎', 'Special Releases in the LOTRO Store': 'LOTRO 商城特别上架',
    'Find Your Shadowfax': '寻找你的捷影', '30% Off Select Mounts, Warsteeds, & More!': '指定坐骑、战马等商品七折！',
    "Patron's Luxuriant Coffer of Promised Allies": '赞助者的应许盟友豪华宝箱',
    "Patron's Enhanced Coffer of Promised Allies": '赞助者的应许盟友强化宝箱',
    "Patron's Simple Coffer of Promised Allies": '赞助者的应许盟友基础宝箱',
    'Sale!': '促销！', 'Buy Now': '立即购买', 'Buy': '购买',
    'Add to Cart': '加入购物车', 'Cart': '购物车', 'Shopping Cart': '购物车',
    'Wishlist': '心愿单', 'Wish List': '心愿单', 'Remove': '移除',
    'Continue Shopping': '继续购物', 'Back': '返回', 'Next': '下一页',
    'Previous': '上一页', 'Close': '关闭', 'Cancel': '取消', 'Confirm': '确认',
    'Details': '详情', 'Description': '说明', 'Quantity': '数量',
    'Price': '价格', 'Total': '合计', 'Subtotal': '小计',
    'New': '新品', 'Featured': '推荐', 'All': '全部', 'No results': '无搜索结果',
    'Apprentice Riding Trait (Account)': '初级骑术特性（账号）',
    'Apprentice Riding Trait': '初级骑术特性', 'Journeyman Riding Trait': '熟练骑术特性',
    '(Account)': '（账号）',
    'Journeyman Riding Trait (Account)': '熟练骑术特性（账号）',
    'Stand Out From The Crowd!': '让你与众不同！',
    'Stand Out From the Crowd!': '让你与众不同！',
    'Shared Wardrobe': '共享衣橱', 'Privacy Policy': '隐私政策',
    'Terms of Service': '服务条款', 'Refund Policy': '退款政策',
    'Legal Agreements': '法律协议', 'Subscriptions': '订阅',
    'Transaction History': '交易记录', 'Active Coupons': '有效优惠券',
    'General': '常规', 'Favorites': '收藏夹', 'Recent Items': '最近浏览',
    'Sort By': '排序方式', 'Price: Low to High': '价格：从低到高',
    'Price: High to Low': '价格：从高到低', 'Newest': '最新',
    'Loading...': '正在加载……', 'No Results Found': '未找到结果'
  }));

  function translate(text) {
    const core = text.trim();
    let target = dictionary.get(core);
    let match;
    if (!target && (match = /^(\d+) items?$/.exec(core))) target = `${match[1]} 件商品`;
    if (!target && (match = /^(\d+) days?$/.exec(core))) target = `${match[1]} 天`;
    if (!target && (match = /^(\d+)% [Oo]ff Shared Wardrobe & More!$/.exec(core))) target = `共享衣橱等商品优惠 ${match[1]}%！`;
    if (!target && (match = /^(\d+)% [Oo]ff Select Mounts, Warsteeds, & More!$/.exec(core))) target = `指定坐骑、战马等商品优惠 ${match[1]}%！`;
    if (!target && (match = /^Max\. (\d+)$/.exec(core))) target = `最多 ${match[1]}`;
    if (!target && (match = /^(\+\d+%) Mount Speed \((\d+) hours\)( x\d+)?$/.exec(core))) {
      target = `${match[1]} 坐骑速度（${match[2]} 小时）${match[3] || ''}`;
    }
    if (!target && (match = /^(\+\d+%) Run Speed Boost (x\d+) \((\d+) hours\)$/.exec(core))) {
      target = `${match[1]} 奔跑速度提升 ${match[2]}（${match[3]} 小时）`;
    }
    if (!target) return text;
    return text.slice(0, text.length - text.trimStart().length) + target + text.slice(text.trimEnd().length);
  }

  // Expose only the pure wording function for local Node tests.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { translate, dictionary };
    return;
  }
  if (location.protocol !== 'https:' || location.hostname !== 'store.lotro.com') return;
  if (window.__LOTRO_ZH_STORE__?.active) return;

  function eligible(element) {
    return element && !element.closest('script,style,noscript,textarea,input,select,option,[contenteditable],code,pre');
  }
  function visit(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (eligible(node.parentElement)) {
        const translated = translate(node.nodeValue);
        if (translated !== node.nodeValue) node.nodeValue = translated;
      }
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE || (!eligible(node) && node.tagName !== 'INPUT')) return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let text;
    while ((text = walker.nextNode())) visit(text);
    // Placeholders and accessible names are display strings; input values and
    // all href/src/data attributes remain exactly as supplied by the store.
    for (const element of [node, ...node.querySelectorAll('[placeholder],[aria-label],[title]')]) {
      if (!eligible(element) && element.tagName !== 'INPUT') continue;
      for (const attr of ['placeholder', 'aria-label', 'title']) {
        const original = element.getAttribute(attr);
        if (original) {
          const translated = translate(original);
          if (translated !== original) element.setAttribute(attr, translated);
        }
      }
    }
  }
  function start() {
  if (window.__LOTRO_ZH_STORE__?.active || !document.body) return;
  visit(document.body);
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'characterData') visit(record.target);
      else if (record.type === 'attributes') visit(record.target);
      else for (const node of record.addedNodes) visit(node);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ['placeholder', 'aria-label', 'title'] });
  window.__LOTRO_ZH_STORE__ = { active: true, version: '0.2.0',
    stop() { observer.disconnect(); this.active = false; } };
  }
  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();
