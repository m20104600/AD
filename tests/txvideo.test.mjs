import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { gzipSync, gunzipSync, constants as zlibConstants } from 'node:zlib';

const adapterURL = new URL('../scripts/txvideo-ad.egern.js', import.meta.url);
const upstreamURL = new URL('../upstream/Txvideoad.js', import.meta.url);
let adapterPromise;
const adapter = () => adapterPromise ??= import(adapterURL.href).then(module => {
  assert.equal(typeof module.default, 'function', 'adapter exports a default handler');
  return module.default;
});
let upstreamPromise;
const upstream = () => upstreamPromise ??= readFile(upstreamURL, 'utf8');
const join = (...parts) => Buffer.concat(parts.map(part => Buffer.from(part)));
const utf8 = value => Buffer.from(value, 'utf8');
const ab = bytes => Uint8Array.from(bytes).buffer;
const bytes = value => Buffer.from(value);
function vint(value) {
  const result = [];
  while (value >= 128) { result.push((value % 128) | 128); value = Math.floor(value / 128); }
  result.push(value);
  return Buffer.from(result);
}
const scalar = (field, value) => join(vint(field * 8), vint(value));
const field = (number, value) => join(vint(number * 8 + 2), vint(value.length), value);
const string = (number, value) => field(number, utf8(value));
const any = (name, value = Buffer.alloc(0)) => join(string(1, `type.googleapis.com/test.${name}`), field(2, value));
function frame(body, header = string(7, '/test.Video/GetVideo')) {
  const fixed = Buffer.alloc(16);
  fixed[0] = 0x09; fixed[1] = 0x30;
  fixed.writeUInt32BE(16 + header.length + body.length, 4);
  fixed.writeUInt16BE(header.length, 8);
  return join(fixed, header, body);
}
const blockedFunction = '/trpc.business_splash.ad_ssp_splash.splashService/GetSplashPreload';
const requestFixture = () => frame(scalar(1, 19), string(7, blockedFunction));
const ordinaryBody = scalar(8, 23);
const adResponseFixture = () => frame(join(field(1, field(1, any('AdResponseInfo'))), ordinaryBody));
const abEntry = (key, config) => field(3, join(string(1, key), field(2, join(string(1, JSON.stringify(config)), scalar(2, 77), string(4, key)))));
const abFixture = (...entries) => join(scalar(1, 100), ...entries);
const abURL = 'https://config.ab.qq.com/tab/GetTabRemoteConfig?platform=ios';
const trpcURL = 'https://i.video.qq.com/?platform=ios';
const rdeliveryURL = 'https://rdelivery.qq.com/v1/sdkconfig/get?platform=ios';

// The oracle executes the unmodified callback script in a fresh realm per call.
// No application requests or third-party dependencies are used.
async function qx({ url, phase = 'response', body }) {
  const source = await upstream();
  const output = [];
  const context = {
    $request: { url, ...(phase === 'request' ? { bodyBytes: ab(body) } : {}) },
    $done(result) { output.push(result); },
    console: { log() {} },
  };
  if (phase === 'response') context.$response = typeof body === 'string' ? { body } : { bodyBytes: ab(body) };
  vm.runInNewContext(source, context, { filename: fileURLToPath(upstreamURL), timeout: 2000 });
  assert.equal(output.length, 1, 'QX source calls $done exactly once');
  const result = output[0];
  if (Object.hasOwn(result, 'bodyBytes')) return { body: bytes(result.bodyBytes) };
  if (Object.hasOwn(result, 'body')) return { body: result.body };
  return undefined;
}

function context({ url, phase = 'response', body, headers = { 'Content-Type': typeof body === 'string' ? 'application/json' : 'application/octet-stream', 'Content-Length': '999', 'content-length': '999', ...(typeof body !== 'string' && body[0] === 0x1f && body[1] === 0x8b ? { 'Content-Encoding': 'gzip' } : {}), 'X-Fixture': 'keep' } }) {
  const reads = { requestArrayBuffer: 0, requestText: 0, responseArrayBuffer: 0, responseText: 0 };
  const makeStream = name => ({
    headers,
    async arrayBuffer() {
      reads[`${name}ArrayBuffer`]++;
      assert.equal(name, phase, `${phase} handler must not consume ${name} stream`);
      assert.notEqual(typeof body, 'string', 'text fixture must use text()');
      return ab(body);
    },
    async text() {
      reads[`${name}Text`]++;
      assert.equal(name, phase, `${phase} handler must not consume ${name} stream`);
      assert.equal(typeof body, 'string', 'binary fixture must use arrayBuffer()');
      return body;
    },
  });
  const request = { ...makeStream('request'), url, method: 'POST' };
  const ctx = { phase, request };
  if (phase === 'response') ctx.response = { ...makeStream('response'), status: 200 };
  return { ctx, reads, originalHeaders: headers };
}
function headerPairs(headers) {
  return headers instanceof Headers ? [...headers.entries()] : Object.entries(headers);
}
function checkHeaders(result, original) {
  assert.ok(result.headers, 'modified result includes copied headers');
  assert.notEqual(result.headers, original, 'never mutate upstream header container');
  const expected = headerPairs(original).filter(([key]) => key.toLowerCase() !== 'content-length').map(([key, value]) => [key.toLowerCase(), value]).sort();
  const actual = headerPairs(result.headers).map(([key, value]) => [key.toLowerCase(), value]).sort();
  assert.deepEqual(actual, expected, 'remove only content-length, preserving content-encoding and unrelated headers');
}
async function parity(input, { modified = true, headers } = {}) {
  const oracle = await qx(input);
  assert.equal(oracle !== undefined, modified, 'fixture must exercise the intended upstream branch');
  const state = context({ ...input, ...(headers ? { headers } : {}) });
  const before = headerPairs(state.originalHeaders);
  const handler = await adapter();
  const result = await handler(state.ctx);
  assert.deepEqual(headerPairs(state.originalHeaders), before, 'original headers are unchanged');
  if (!modified) {
    assert.equal(result, undefined, 'no edit must return undefined, not an empty response');
  } else {
    assert.ok(result && typeof result === 'object');
    assert.equal(Object.hasOwn(result, 'bodyBytes'), false, 'do not leak QX bodyBytes to Egern');
    if (typeof oracle.body === 'string') {
      assert.equal(typeof result.body, 'string');
      assert.equal(result.body, oracle.body);
    } else {
      assert.ok(result.body instanceof Uint8Array, 'binary edits return Egern-supported Uint8Array, not ArrayBuffer');
      assert.deepEqual(bytes(result.body), oracle.body, 'binary output matches the exact original QX algorithm');
    }
    checkHeaders(result, state.originalHeaders);
    const prefix = input.phase === 'request' ? 'request' : 'response';
    assert.equal(state.reads[`${prefix}${typeof input.body === 'string' ? 'Text' : 'ArrayBuffer'}`], 1, 'read active stream exactly once');
  }
  if (input.phase !== 'request') {
    assert.equal(state.reads.requestArrayBuffer, 0);
    assert.equal(state.reads.requestText, 0);
  }
  return { result, oracle, ...state };
}

// Minimal JCE writers for genuine nested gzip envelopes accepted by onJce.
const jHead = (tag, type) => Buffer.from(tag < 15 ? [(tag << 4) | type] : [0xf0 | type, tag]);
function jInt(tag, value) {
  if (value === 0) return jHead(tag, 12);
  if (value <= 127) return join(jHead(tag, 0), [value]);
  if (value <= 32767) { const data = Buffer.alloc(2); data.writeInt16BE(value); return join(jHead(tag, 1), data); }
  const data = Buffer.alloc(4); data.writeInt32BE(value); return join(jHead(tag, 2), data);
}
const jString = (tag, value) => join(jHead(tag, 6), [utf8(value).length], utf8(value));
const jSimple = (tag, value) => join(jHead(tag, 13), [0], jInt(0, value.length), value);
function jceEnvelope(command, body) {
  const inner = join(Buffer.alloc(16), jSimple(1, body), [0x28]);
  inner[0] = 0x26; inner.writeUInt32BE(inner.length, 1);
  const header = Buffer.alloc(64);
  header[0] = 0x13;
  header.writeUIntBE(command, 8, 3);
  header.writeUInt32BE(inner.length, 60);
  // Stored DEFLATE blocks keep this synthetic packet above the source's 100-byte gate.
  const output = join(header, gzipSync(inner, { level: 0 }), [0x03]);
  output.writeUInt32BE(output.length, 1);
  return output;
}

// Oracle-only tests validate the fixture design even before the adapter exists.
test('upstream fixtures exercise request, response, AB, and JCE modifications', async () => {
  for (const input of [
    { url: trpcURL, phase: 'request', body: requestFixture() },
    { url: trpcURL, body: adResponseFixture() },
    { url: abURL, body: abFixture(abEntry('simple_mode_config', { enable: 0 })) },
    { url: 'https://iacc.qq.com/', body: jceEnvelope(89738, join(jInt(4, 1), jString(9, 'ABCDEF0123456789ABCDEF0123456789AB'))) },
  ]) assert.ok(await qx(input), `fixture should modify ${input.url}`);
});

test('request rewrites blocked TRPC function with exact QX bytes', async () => {
  const { result } = await parity({ url: trpcURL, phase: 'request', body: requestFixture() });
  assert.ok(bytes(result.body).includes(utf8('/XetSplashPreload')));
  assert.equal(bytes(result.body).length, requestFixture().length);
});

test('response removes protobuf ad element and updates TRPC total length', async () => {
  const { result } = await parity({ url: trpcURL, body: adResponseFixture() });
  const output = bytes(result.body);
  assert.deepEqual(output, frame(ordinaryBody));
  assert.equal(output.readUInt32BE(4), output.length);
});

for (const [name, options] of [['stored', { level: 0 }], ['fixed', { strategy: zlibConstants.Z_FIXED }], ['default', {}]]) {
  for (const phase of ['request', 'response']) {
    test(`${phase} ${name} gzip round trip keeps gzip and matches QX`, async () => {
      const plain = phase === 'request' ? requestFixture() : adResponseFixture();
      const { result } = await parity({ url: trpcURL, phase, body: gzipSync(plain, options) });
      const inflated = gunzipSync(bytes(result.body));
      const expected = await qx({ url: trpcURL, phase, body: plain });
      assert.deepEqual(inflated, expected.body);
      assert.equal(inflated.readUInt32BE(4), inflated.length);
    });
  }
}

test('Headers input is copied without content-length and retains content-encoding', async () => {
  await parity({ url: trpcURL, body: gzipSync(adResponseFixture()) }, { headers: new Headers({ 'content-length': '10', 'content-encoding': 'gzip', 'x-test': 'untouched' }) });
});

test('tab protobuf removes only targeted tabs and reindexes survivors', async () => {
  const tab = (title, key, index) => field(1, join(scalar(2, index), string(3, title), field(22, string(1, key))));
  const original = join(tab('首页', 'home', 4), tab('短剧', 'drama', 5), tab('精选', 'selected', 6), tab('商城', 'goods_entrance', 7));
  const input = frame(field(9, any('GetTabListRsp', original)));
  const { result } = await parity({ url: trpcURL, body: input });
  const expected = join(field(1, join(string(3, '首页'), field(22, string(1, 'home')))), tab('精选', 'selected', 1));
  assert.deepEqual(bytes(result.body), frame(field(9, any('GetTabListRsp', expected))));
});

test('teenager popup protobuf strips field 1 without disturbing its control marker', async () => {
  const marker = field(7, string(2, 'teenager_popup_ctrl'));
  const { result } = await parity({ url: trpcURL, body: frame(join(string(1, 'popup'), marker, ordinaryBody)) });
  assert.deepEqual(bytes(result.body), frame(join(marker, ordinaryBody)));
});

for (const [key, config, expected] of [
  ['simple_mode_config', { enable: 0, untouched: 9 }, { enable: 1, untouched: 9, feature_config: { enable: 1, tab_bar_cut_enable: 1, tab_bar_cut_whitelist: '0;2;4' } }],
  ['ios_nx_netframework_compatible', { quic: { enabled: true, allPbReqEnabled: true, allJceReqEnabled: true }, keep: 4 }, { quic: { enabled: false, allPbReqEnabled: false, allJceReqEnabled: false }, keep: 4 }],
  ['ios_nx_netframework_compatible_bbtf', { quic: { enabled: true } }, { quic: { enabled: false, allPbReqEnabled: false, allJceReqEnabled: false } }],
  ['network_resolve_config', { enablePreResolve: true, keep: 'yes' }, { enablePreResolve: false, keep: 'yes', enableNac: false, enableHdns: false }],
]) {
  test(`AB ${key} rewrites JSON while retaining protobuf metadata`, async () => {
    const { result } = await parity({ url: abURL, body: abFixture(abEntry(key, config)) });
    assert.deepEqual(bytes(result.body), abFixture(abEntry(key, expected)));
  });
}

test('AB gzip preserves compression and upstream simple-mode insertion behavior', async () => {
  const body = abFixture(abEntry('unrelated_config', { keep: true }));
  const plainOracle = await qx({ url: abURL, body });
  const { result } = await parity({ url: abURL, body: gzipSync(body) });
  assert.deepEqual(gunzipSync(bytes(result.body)), plainOracle.body);
  assert.ok(plainOracle.body.includes(utf8('simple_mode_config')));
});

test('AB already-patched config is pass-through', async () => {
  const config = { enable: 1, feature_config: { enable: 1, tab_bar_cut_enable: 1, tab_bar_cut_whitelist: '0;2;4' } };
  await parity({ url: abURL, body: abFixture(abEntry('simple_mode_config', config)) }, { modified: false });
});

for (const [name, command, body] of [
  ['teen config', 89738, join(jInt(4, 1), join(jHead(6, 10), [0x0b]), jString(9, 'ABCDEF0123456789ABCDEF0123456789AB'), join(jHead(10, 10), [0x0b]))],
  ['play tips', 126577, join(jHead(1, 8), jInt(0, 2), jString(0, '4_operator_info'), jString(1, 'remove'), jString(0, 'other'), jString(1, 'preserve'))],
  ['roll ads 129278', 129278, join(jHead(2, 9), jInt(0, 1), jString(0, 'livemsg'))],
  ['roll ads 130273', 130273, join(jHead(2, 9), jInt(0, 1), jString(0, 'livemsg'))],
]) {
  test(`JCE ${name} nested gzip envelope matches original QX`, async () => {
    const input = jceEnvelope(command, body);
    const { result } = await parity({ url: 'https://iacc.qq.com/?platform=ios', body: input });
    const output = bytes(result.body);
    assert.equal(output.readUInt32BE(1), output.length);
    const inner = gunzipSync(output.subarray(64, -1));
    assert.equal(inner.readUInt32BE(1), inner.length);
    assert.equal(output.readUInt32BE(60), inner.length);
    assert.equal(output.at(-1), 0x03);
  });
}

for (const headers of [undefined, new Headers({ 'content-length': '100', 'x-test': 'yes' })]) {
  test(`rdelivery text changes only first tab_gray true (${headers ? 'Headers' : 'object'})`, async () => {
    const body = '{"tab_gray" : true,"nested":{"tab_gray":true},"keep":9}';
    const { result, reads } = await parity({ url: rdeliveryURL, body }, { headers });
    assert.equal(result.body, '{"tab_gray" : false,"nested":{"tab_gray":true},"keep":9}');
    assert.equal(reads.responseText, 1);
    assert.equal(reads.responseArrayBuffer, 0);
  });
}

for (const body of ['{"tab_gray":false}', '{"other":true}', '', '{"tab_gray":"true"}']) {
  test(`rdelivery unchanged text ${JSON.stringify(body)} passes through`, async () => {
    await parity({ url: rdeliveryURL, body }, { modified: false });
  });
}

for (const [name, body] of [
  ['empty', Buffer.alloc(0)],
  ['unknown', Buffer.from([0x01, 0x02, 0x03, 0x04])],
  ['truncated protobuf frame', frame(Buffer.from([0x0a, 0xff, 0xff, 0x7f]))],
  ['corrupt gzip', Buffer.from([0x1f, 0x8b, 0x08, 0, 0, 0, 0, 0, 0, 255, 7])],
  ['incorrect TRPC length', (() => { const data = adResponseFixture(); data.writeUInt32BE(data.length + 1, 4); return data; })()],
]) {
  for (const phase of ['request', 'response']) {
    test(`${phase} ${name} bytes pass through without throwing`, async () => {
      await parity({ url: trpcURL, phase, body }, { modified: false });
    });
  }
}

test('unblocked TRPC request is pass-through', async () => {
  await parity({ url: trpcURL, phase: 'request', body: frame(ordinaryBody) }, { modified: false });
});

test('ordinary TRPC response without markers is pass-through', async () => {
  await parity({ url: trpcURL, body: frame(ordinaryBody) }, { modified: false });
});

for (const input of [
  { url: 'https://example.invalid/', body: adResponseFixture() },
  { url: 'https://example.invalid/', phase: 'request', body: requestFixture() },
  { url: 'https://config.ab.qq.com/other', body: abFixture(abEntry('simple_mode_config', { enable: 0 })) },
  { url: rdeliveryURL, phase: 'request', body: requestFixture() },
]) {
  test(`unrelated route/phase passes through: ${input.phase ?? 'response'} ${input.url}`, async () => {
    await parity(input, { modified: false });
  });
}

test('request-phase bytes must not be interpreted as response ad protobuf', async () => {
  await parity({ url: trpcURL, phase: 'request', body: adResponseFixture() }, { modified: false });
});

test('response-phase bytes must not trigger blocked request function rewrite', async () => {
  await parity({ url: trpcURL, body: requestFixture() }, { modified: false });
});
