// 실행: node --test
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pgm-'));
process.env.PGM_SOURCE_DIR = dir;
const pgm = require('../pgmSource');
test.after(() => fs.rmSync(dir, { recursive: true, force: true }));

// 코드 뷰어 스타일(span 하이라이트 + <br>) HTML
const eucKrHtml = `<html><head><meta http-equiv="Content-Type" content="text/html; charset=euc-kr">
<title>입고등록 화면</title><style>.k{color:blue}</style></head><body>
<span class="c">// 입고 금액 = 수량 * 단가 - 할인</span><br>
<span class="k">var</span> IN_QTY = ds.getColumn(row, &quot;IN_QTY&quot;);<br>
<span class="k">if</span> (IN_QTY &gt; 0 &amp;&amp; DC_YN == &#39;Y&#39;) {<br>
&nbsp;&nbsp;IN_AMT = IN_QTY * UNIT_PRC - DC_AMT;<br>
}<br>
lblInAmt.text = &quot;입고금액&quot;;<br>
</body></html>`;
// Node 에는 EUC-KR 인코더가 없으므로 파일은 UTF-8 로 저장하고, EUC-KR 판별은 decodeBuffer 테스트에서 따로 확인합니다.
fs.writeFileSync(path.join(dir, 'MM1010.html'), eucKrHtml.replace('euc-kr', 'utf-8'), 'utf8');
fs.mkdirSync(path.join(dir, 'sub'));
fs.writeFileSync(path.join(dir, 'sub', 'MM2020.htm'),
    '<html><head><title>출고등록</title></head><body><pre>SELECT OUT_QTY * PRICE AS OUT_AMT\n  FROM TB_OUT</pre></body></html>', 'utf8');

test('htmlToText: 태그 제거, 엔티티 복원, 줄 유지', () => {
    const lines = pgm.htmlToText(eucKrHtml);
    assert.ok(lines.includes("if (IN_QTY > 0 && DC_YN == 'Y') {"));
    assert.ok(lines.some(l => l.includes('IN_AMT = IN_QTY * UNIT_PRC - DC_AMT;')));
    assert.ok(!lines.some(l => l.includes('color:blue')), 'style 내용은 제외');
});

test('decodeBuffer: meta 가 없어도 EUC-KR 바이트를 판별', () => {
    const bytes = Buffer.from([0xc0, 0xd4, 0xb0, 0xed]); // "입고" (EUC-KR)
    assert.strictEqual(pgm.decodeBuffer(bytes), '입고');
});

test('search: 띄어쓰기 무시하고 라벨을 찾음', async () => {
    const r = await pgm.searchProgramSource({ keyword: '입고 금액', program: 'mm1010' });
    assert.match(r, /2건/);
    assert.match(r, /\[MM1010\.html:\d+\]/);
});

test('search: 전체 프로그램, 하위 폴더 포함', async () => {
    const r = await pgm.searchProgramSource({ keyword: 'out_amt' });
    assert.match(r, /sub\/MM2020\.htm:1/);
});

test('resolve: 화면 제목으로 프로그램 찾기 + read 범위', async () => {
    const r = await pgm.readProgramSource({ program: '출고등록', start_line: 2 });
    assert.match(r, /2: {3}FROM TB_OUT/);
});

test('list: query 로 필터', async () => {
    const r = await pgm.listPrograms({ query: '입고' });
    assert.match(r, /MM1010\.html \| 입고등록 화면/);
    assert.doesNotMatch(r, /MM2020/);
});

test('없는 프로그램은 안내 메시지', async () => {
    await assert.rejects(pgm.readProgramSource({ program: 'ZZ9999' }), /list_programs/);
});
