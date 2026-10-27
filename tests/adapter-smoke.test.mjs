import test from 'node:test';
import assert from 'node:assert/strict';
import adapter from '../scripts/txvideo-ad.egern.js';

test('Egern JSON response becomes a body patch without QX globals', async () => {
  const result = await adapter({
    request: { url: 'https://rdelivery.qq.com/v1/sdkconfig/get?a=1' },
    response: {
      headers: { 'Content-Type': 'application/json', 'Content-Length': '17' },
      text: async () => '{"tab_gray":true}'
    }
  });
  assert.equal(result.body, '{"tab_gray":false}');
  assert.equal(result.headers['Content-Type'], 'application/json');
  assert.ok(!Object.keys(result.headers).some(k => k.toLowerCase() === 'content-length'));
});

test('no matching URL passes through without consuming body', async () => {
  const result = await adapter({
    request: { url: 'https://example.com/', arrayBuffer() { throw new Error('must not read'); } }
  });
  assert.equal(result, undefined);
});
