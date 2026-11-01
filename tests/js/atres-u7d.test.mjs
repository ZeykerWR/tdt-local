// Atresplayer's «últimos 7 días»: the plugin that reads the page, the dates, the channels and what the app lets through.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

import {
  Reading, SLUGS, allowedAddress, cleanItems, listUrl, watchAddress,
} from '../../desktop/lib/atres.js';
import { readPlugin, scriptsFor } from '../../desktop/lib/plugins.js';
import { atresEmbed, atresVideoLink, atresWeb } from '../../tdtlocal/static/js/lib/embeds.js';
import {
  ATRES_CHANNELS, atresChannels, atresItems, atresProgramme, atresTs, parseU7d,
} from '../../tdtlocal/static/js/lib/u7d.js';

// the plugin is a plain script: it is loaded the way the bridge is (see capturar.test.mjs)
const readerBox = { module: { exports: {} } };
vm.runInNewContext(readFileSync(new URL('../../tools/atresplayer-u7d/lector.js', import.meta.url), 'utf8'), readerBox);
const { leerTarjeta, leerTarjetas } = readerBox.module.exports;
const plain = (value) => JSON.parse(JSON.stringify(value)); // objects made inside the vm have another prototype
const REPO = new URL('../../', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const ID = '6ade9a5c1eef7d0008852eb7';
const IMG = 'https://imagenes.atresplayer.com/atp/clipping/x/386x217.jpg?optimize=low';

test('a card of the page becomes a recording with its day and time', () => {
  const item = leerTarjeta({
    href: `/grabaciones/antena3/${ID}/`,
    title: 'El secreto',
    aria: 'El secreto. Antena 3',
    lines: ['EMITIDO EN TV', 'Domingo 25', '22:10', 'El secreto'],
    image: IMG,
  });
  assert.deepEqual(plain(item), { id: ID, channel: 'antena3', title: 'El secreto', day: 25, time: '22:10', image: IMG });
});

test('the title falls back to the label or the last line, and cards that are not recordings are ignored', () => {
  const base = { href: `/grabaciones/neox/${ID}/`, lines: ['EMITIDO EN TV', 'Lunes 26', '9:05', 'Los Simpson'] };
  assert.equal(leerTarjeta({ ...base, aria: 'Los Simpson. Neox' }).title, 'Los Simpson');
  assert.equal(leerTarjeta(base).title, 'Los Simpson');
  assert.equal(leerTarjeta(base).time, '09:05');
  assert.equal(leerTarjeta({ ...base, lines: [], title: '' }), null); // no title anywhere
  assert.equal(leerTarjeta({ ...base, href: '/antena3/programas/x_6ada472a8028890007a6f6a4/' }), null);
  assert.equal(leerTarjeta({ ...base, href: '/grabaciones/antena3/not-an-id/' }), null);
  assert.equal(leerTarjeta({ ...base, href: `/grabaciones/../x/${ID}/` }), null);
});

test('only images of Atresplayer are kept, and repeated cards are read once', () => {
  const card = (id, image) => ({ href: `/grabaciones/antena3/${id}/`, title: 'X', lines: [], image });
  assert.equal(leerTarjeta(card(ID, 'https://evil.example/x.jpg')).image, '');
  assert.equal(leerTarjeta(card(ID, 'http://imagenes.atresplayer.com/x.jpg')).image, '');
  const other = '6ae4a9d835a9e100077c3b89';
  assert.deepEqual(plain(leerTarjetas([card(ID, IMG), card(other, ''), card(ID, IMG)]).map((i) => i.id)), [ID, other]);
});

test('dates: the day of the month is placed in the last month', () => {
  const now = new Date(2026, 10, 1, 18, 0); // Sunday 1 November 2026
  const at = (ts) => new Date(ts * 1000);
  assert.equal(at(atresTs(1, '16:00', now)).getDate(), 1); // earlier today
  const sunday = at(atresTs(25, '22:10', now));
  assert.deepEqual([sunday.getMonth(), sunday.getDate(), sunday.getHours(), sunday.getMinutes()], [9, 25, 22, 10]); // 25 October
  const later = atresTs(1, '19:00', now); // «the 1st at 19:00» has not happened yet today: it was last month's
  assert.equal(at(later).getMonth(), 9);
  assert.equal(at(later).getDate(), 1);
  assert.equal(atresTs(0, '22:10', now), 0);
  assert.equal(atresTs(25, '', now), 0);
  assert.equal(atresTs(32, '22:10', now), 0);
  assert.equal(at(atresTs(30, '10:00', new Date(2026, 2, 1))).getMonth(), 0); // from 1 March, the 30th is in January
});

test('the items of Atresplayer play with its official embedded player', () => {
  const chan = atresChannels([{ id: 'antena3', logo: 'L3' }]).find((c) => c.slug === 'antena3');
  const [item] = atresItems([{ id: ID, title: 'El secreto', day: 25, time: '22:10', image: IMG }], new Date(2026, 10, 1));
  assert.deepEqual([item.id, item.title, item.image], [ID, 'El secreto', IMG]);
  assert.ok(item.ts > 0);
  const c = atresProgramme(chan, item);
  assert.equal(c.vod, true);
  assert.equal(c.recording, true); // its embedded player answers 404 to recordings: the tile opens the page instead
  assert.equal(c.web, `https://www.atresplayer.com/grabaciones/antena3/${ID}/`);
  assert.equal(c.sources[0].u, `https://www.atresplayer.com/embed/video/${ID}/`);
  assert.equal(atresEmbed(c.sources[0].u), c.sources[0].u); // the tile treats it as an Atresplayer player
  assert.equal(parseU7d(c.sources[0].u), null); // and not as a server-resolved programme
  assert.equal(c.thumb, true);
});

test('the Atresmedia channels join U7D as entries that only the desktop app can open', () => {
  const list = atresChannels([{ id: 'lasexta', logo: 'LS' }]);
  assert.deepEqual(list.map((c) => c.slug), ATRES_CHANNELS.map((a) => a.slug));
  const sexta = list.find((c) => c.slug === 'lasexta');
  assert.deepEqual([sexta.id, sexta.kind, sexta.provider, sexta.logo, sexta.sources], ['u7d-atres-lasexta', 'u7d', 'atres', 'LS', []]);
  assert.deepEqual(list.map((c) => c.slug), SLUGS); // the same channels the app is willing to open
});

test('embeds: live players and recordings are recognised, other pages are not', () => {
  assert.equal(atresEmbed('https://www.atresplayer.com/embed/live/lasexta/'), 'https://www.atresplayer.com/embed/live/lasexta/');
  assert.equal(atresEmbed(`https://www.atresplayer.com/embed/video/${ID.toUpperCase()}`), atresVideoLink(ID));
  assert.equal(atresEmbed('https://www.atresplayer.com/embed/video/short/'), null);
  assert.equal(atresEmbed(`https://evil.example/embed/video/${ID}/`), null);
  assert.equal(atresEmbed(`https://www.atresplayer.com/grabaciones/antena3/${ID}/`), null);
  assert.equal(atresWeb(atresVideoLink(ID)), '');
  assert.equal(atresWeb('https://www.atresplayer.com/embed/live/neox/'), 'https://www.atresplayer.com/directos/neox/');
});

test('the explorer window only goes to Atresplayer', () => {
  assert.equal(listUrl('antena3'), 'https://www.atresplayer.com/antena3/u7d/');
  assert.ok(allowedAddress('https://www.atresplayer.com/antena3/u7d/'));
  assert.ok(allowedAddress('https://atresplayer.com/'));
  for (const bad of ['http://www.atresplayer.com/', 'https://atresplayer.com.evil.example/', 'https://www.atresplayer.com:8443/',
    'https://user@www.atresplayer.com/', 'https://evil.example/www.atresplayer.com/', 'file:///etc/passwd', 'nonsense', '']) {
    assert.equal(allowedAddress(bad), false, bad);
  }
});

test('the app only opens, to watch, the page of a recording on atresplayer.com', () => {
  const page = `https://www.atresplayer.com/grabaciones/antena3/${ID}/`;
  assert.equal(watchAddress(page), page);
  assert.equal(watchAddress(`https://www.atresplayer.com/grabaciones/NEOX/${ID.toUpperCase()}`), `https://www.atresplayer.com/grabaciones/neox/${ID}/`);
  for (const bad of [`http://www.atresplayer.com/grabaciones/antena3/${ID}/`, `https://evil.example/grabaciones/antena3/${ID}/`,
    `https://www.atresplayer.com.evil.example/grabaciones/antena3/${ID}/`, 'https://www.atresplayer.com/grabaciones/antena3/short/',
    `https://www.atresplayer.com/grabaciones/antena3/${ID}/../../x`, `https://www.atresplayer.com/directos/antena3/${ID}/`,
    `https://www.atresplayer.com/grabaciones/antena3/${ID}/?next=https://evil.example`, 'javascript:alert(1)', '', null, 5]) {
    assert.equal(watchAddress(bad), null, String(bad));
  }
});

test('what the plugin reports is cleaned, because a page can send the same message', () => {
  const good = { id: ID, title: ' El secreto ', day: 25, time: '22:10', image: IMG };
  assert.deepEqual(cleanItems([good]), [{ ...good, title: 'El secreto' }]);
  assert.deepEqual(cleanItems('nope'), []);
  assert.deepEqual(cleanItems([null, 5, {}, { ...good, id: 'x' }, { ...good, id: ID.toUpperCase() }, { ...good, title: '  ' }]), []);
  const odd = cleanItems([{ ...good, day: 99, time: '25h', image: 'https://evil.example/x.jpg' }])[0];
  assert.deepEqual([odd.day, odd.time, odd.image], [0, '', '']);
  assert.equal(cleanItems([{ ...good, title: 'x'.repeat(500) }])[0].title.length, 160);
  assert.deepEqual(cleanItems([good, good]).length, 1);
  const many = Array.from({ length: 500 }, (_, i) => ({ ...good, id: i.toString(16).padStart(24, '0') }));
  assert.equal(cleanItems(many).length, 200);
});

test('a reading ends once, with what the plugin read or with the reason there is nothing', () => {
  const results = [];
  const first = new Reading('antena3', (r) => results.push(r));
  first.message({ type: 'items', slug: 'lasexta', items: [{ id: ID, title: 'X' }] }); // another channel's page: ignored
  first.message({ type: 'items', slug: 'antena3', items: [{ id: ID, title: 'X' }] });
  first.message({ type: 'done', slug: 'antena3' });
  first.message({ type: 'items', slug: 'antena3', items: [] });
  first.end();
  assert.equal(results.length, 1);
  assert.equal(results[0].items[0].id, ID);

  const empty = [];
  new Reading('nova', (r) => empty.push(r)).end('ventana cerrada');
  assert.deepEqual(empty, [{ error: 'ventana cerrada' }]);
});

test('the plugin of the list is valid, acts only on the U7D pages and asks for nothing', () => {
  const plugin = readPlugin(`${REPO}tools/atresplayer-u7d`);
  assert.deepEqual(plugin.problems, []);
  const on = new Set([plugin.id]);
  const run = (url, top = true) => scriptsFor([plugin], on, url, top).length;
  assert.equal(run('https://www.atresplayer.com/antena3/u7d/'), 1);
  assert.equal(run('https://www.atresplayer.com/lasexta/u7d/'), 1);
  assert.equal(run('https://www.atresplayer.com/antena3/programas/x/'), 0);
  assert.equal(run('https://www.atresplayer.com/embed/live/lasexta/'), 0);
  assert.equal(run('https://evil.example/antena3/u7d/'), 0);
  assert.equal(run('https://www.atresplayer.com/antena3/u7d/', false), 0); // only the page itself, not frames inside it
  assert.equal(JSON.parse(readFileSync(`${REPO}tools/atresplayer-u7d/manifest.json`, 'utf8')).permissions, undefined);
});
