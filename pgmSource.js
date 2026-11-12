// HTML 형태로 모아 둔 PGM 소스 폴더를 읽어서 Claude가 검색/열람할 수 있게 해 주는 도구들입니다.
// HTML 태그를 걷어 내고 줄 번호가 붙은 텍스트로 바꿔서 돌려주므로, 토큰을 아끼면서 소스를 추적할 수 있습니다.
const fs = require('fs/promises');
const path = require('path');

const DEFAULT_PGM_DIR = 'G:\\내 드라이브\\AI\\PGM소스';
const SOURCE_EXTS = ['.html', '.htm'];
const MAX_READ_LINES = 400;      // read_program_source 한 번에 돌려줄 최대 줄 수
const MAX_OUTPUT_CHARS = 20000;  // 도구 결과 하나의 최대 길이
const LIST_CACHE_MS = 60 * 1000; // 폴더 목록 캐시 유지 시간

function pgmDir() {
    return process.env.PGM_SOURCE_DIR || DEFAULT_PGM_DIR;
}

// ---------------------------------------------------------------------------
// HTML -> 텍스트 변환
// ---------------------------------------------------------------------------

const NAMED_ENTITIES = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'", nbsp: ' ', '#39': "'" };

function decodeEntities(s) {
    return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (all, code) => {
        if (code[0] === '#') {
            const n = code[1] === 'x' || code[1] === 'X' ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
            return Number.isFinite(n) ? String.fromCodePoint(n) : all;
        }
        const v = NAMED_ENTITIES[code.toLowerCase()];
        return v !== undefined ? v : all;
    });
}

// <meta charset> 를 보고 인코딩을 고릅니다. 표기가 없으면 UTF-8로 읽어 보고, 깨지면 EUC-KR로 다시 읽습니다.
function decodeBuffer(buf) {
    const head = buf.subarray(0, 4096).toString('latin1');
    const m = /charset\s*=\s*["']?([\w-]+)/i.exec(head);
    let charset = m ? m[1].toLowerCase() : null;
    if (charset === 'ks_c_5601-1987' || charset === 'cp949' || charset === 'ms949') charset = 'euc-kr';
    if (!charset) {
        const utf8 = new TextDecoder('utf-8').decode(buf);
        if (!utf8.includes('\uFFFD')) return utf8;
        charset = 'euc-kr';
    }
    try {
        return new TextDecoder(charset).decode(buf);
    } catch {
        return new TextDecoder('utf-8').decode(buf);
    }
}

function extractTitle(html) {
    const m = /<title[^>]*>([\s\S]*?)<\/title>/i.exec(html);
    return m ? decodeEntities(m[1].replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim() : '';
}

function htmlToText(html) {
    let s = html
        .replace(/\r\n?/g, '\n')
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/<(script|style|head)\b[\s\S]*?<\/\1\s*>/gi, '')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/(p|div|tr|li|h[1-6]|pre|table|blockquote)\s*>/gi, '\n')
        .replace(/<\/(td|th)\s*>/gi, '\t')
        .replace(/<[^>]+>/g, '');
    s = decodeEntities(s);
    const lines = s.split('\n').map(l => l.replace(/[ \t\u00a0]+$/, ''));
    // 3줄 이상 연속된 빈 줄은 1줄로 줄입니다.
    const out = [];
    for (const l of lines) {
        if (l === '' && out.length && out[out.length - 1] === '' && out[out.length - 2] === '') continue;
        out.push(l);
    }
    while (out.length && out[0] === '') out.shift();
    while (out.length && out[out.length - 1] === '') out.pop();
    return out;
}

// ---------------------------------------------------------------------------
// 파일 목록 / 캐시
// ---------------------------------------------------------------------------

let listCache = { dir: null, at: 0, files: [] };
const textCache = new Map(); // fullPath -> { mtimeMs, size, title, lines }

async function listSourceFiles() {
    const dir = pgmDir();
    if (listCache.dir === dir && Date.now() - listCache.at < LIST_CACHE_MS) return listCache.files;

    const files = [];
    const stack = [dir];
    while (stack.length) {
        const current = stack.pop();
        let entries;
        try {
            entries = await fs.readdir(current, { withFileTypes: true });
        } catch (err) {
            if (current === dir) throw new Error(`PGM 소스 폴더를 열 수 없습니다: ${dir} (${err.code})`);
            continue;
        }
        for (const entry of entries) {
            const full = path.join(current, entry.name);
            if (entry.isDirectory()) stack.push(full);
            else if (SOURCE_EXTS.includes(path.extname(entry.name).toLowerCase())) {
                files.push({ full, rel: path.relative(dir, full).split(path.sep).join('/') });
            }
        }
    }
    files.sort((a, b) => a.rel.localeCompare(b.rel));
    listCache = { dir, at: Date.now(), files };
    return files;
}

async function loadFile(file) {
    const stat = await fs.stat(file.full);
    const cached = textCache.get(file.full);
    if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) return cached;
    const html = decodeBuffer(await fs.readFile(file.full));
    const entry = { mtimeMs: stat.mtimeMs, size: stat.size, title: extractTitle(html), lines: htmlToText(html) };
    textCache.set(file.full, entry);
    return entry;
}

const norm = s => (s || '').toLowerCase().replace(/[\s_\-.]/g, '');
const baseName = rel => path.posix.basename(rel).replace(/\.[^.]+$/, '');

// "a", "A.html", "폴더/A.htm", 화면 제목 등으로 프로그램 파일 하나를 찾습니다.
async function resolveProgram(name) {
    const files = await listSourceFiles();
    const q = norm(name);
    const exact = files.filter(f => norm(f.rel) === q || norm(baseName(f.rel)) === q);
    if (exact.length === 1) return exact[0];

    let candidates = exact.length ? exact : files.filter(f => norm(f.rel).includes(q));
    if (!candidates.length) {
        // 파일명에 없으면 <title> 로도 찾아봅니다.
        const byTitle = [];
        for (const f of files) {
            const { title } = await loadFile(f);
            if (title && norm(title).includes(q)) byTitle.push(f);
        }
        candidates = byTitle;
    }
    if (candidates.length === 1) return candidates[0];
    if (!candidates.length) throw new Error(`'${name}' 에 해당하는 프로그램이 없습니다. list_programs 로 목록을 확인하세요.`);
    throw new Error(`'${name}' 에 해당하는 프로그램이 여러 개입니다. 하나를 골라 정확한 이름으로 다시 호출하세요:\n` +
        candidates.slice(0, 30).map(f => `- ${f.rel}`).join('\n'));
}

function clip(text) {
    return text.length <= MAX_OUTPUT_CHARS ? text
        : text.slice(0, MAX_OUTPUT_CHARS) + '\n... (결과가 너무 길어 잘렸습니다. 범위를 좁혀 다시 호출하세요)';
}

// 일반 검색어는 대소문자와 띄어쓰기를 무시합니다 ("입고 금액" == "입고금액").
function buildPattern(keyword, isRegex) {
    if (isRegex) return new RegExp(keyword, 'i');
    const parts = keyword.trim().split(/\s+/).map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    return new RegExp(parts.join('\\s*'), 'i');
}

// ---------------------------------------------------------------------------
// 도구 구현
// ---------------------------------------------------------------------------

async function listPrograms({ query } = {}) {
    const files = await listSourceFiles();
    const rows = [];
    for (const f of files) {
        const { title, lines } = await loadFile(f);
        if (query && !norm(f.rel).includes(norm(query)) && !norm(title).includes(norm(query))) continue;
        rows.push(`- ${f.rel}${title ? ` | ${title}` : ''} | ${lines.length}줄`);
    }
    if (!rows.length) return query ? `'${query}' 와 일치하는 프로그램이 없습니다. (전체 ${files.length}개)` : 'PGM 소스 폴더에 HTML 파일이 없습니다.';
    return clip(`프로그램 ${rows.length}개 (폴더: ${pgmDir()})\n${rows.join('\n')}`);
}

async function searchProgramSource({ keyword, program, regex = false, context_lines = 3, max_results = 30 }) {
    if (!keyword) throw new Error('keyword 가 필요합니다.');
    const pattern = buildPattern(keyword, regex);
    const ctx = Math.max(0, Math.min(Number(context_lines) || 0, 15));
    const limit = Math.max(1, Math.min(Number(max_results) || 30, 100));
    const files = program ? [await resolveProgram(program)] : await listSourceFiles();

    const blocks = [];
    let total = 0;
    for (const f of files) {
        const { lines } = await loadFile(f);
        let lastShown = -1;
        for (let i = 0; i < lines.length; i++) {
            if (!pattern.test(lines[i])) continue;
            total++;
            if (blocks.length >= limit) continue;
            const from = Math.max(i - ctx, lastShown + 1);
            const to = Math.min(i + ctx, lines.length - 1);
            const body = [];
            for (let j = from; j <= to; j++) body.push(`${j + 1}${j === i ? '>' : ':'} ${lines[j]}`);
            blocks.push(`[${f.rel}:${i + 1}]\n${body.join('\n')}`);
            lastShown = to;
        }
    }
    if (!total) return `'${keyword}' 검색 결과가 없습니다.${program ? '' : ' (전체 프로그램 검색)'}`;
    const more = total > blocks.length ? `\n\n... 외 ${total - blocks.length}건 더 있음. program 을 지정하거나 검색어를 좁히세요.` : '';
    return clip(`'${keyword}' 검색 결과 ${total}건 ('>' 표시가 일치한 줄)\n\n${blocks.join('\n\n')}${more}`);
}

async function readProgramSource({ program, start_line = 1, end_line }) {
    const f = await resolveProgram(program);
    const { title, lines } = await loadFile(f);
    const start = Math.max(1, Number(start_line) || 1);
    const end = Math.min(lines.length, Number(end_line) || start + MAX_READ_LINES - 1, start + MAX_READ_LINES - 1);
    if (start > lines.length) return `${f.rel} 은 ${lines.length}줄입니다. start_line 이 범위를 벗어났습니다.`;
    const body = [];
    for (let i = start; i <= end; i++) body.push(`${i}: ${lines[i - 1]}`);
    const tail = end < lines.length ? `\n... (${end}/${lines.length}줄까지 표시. 이어서 보려면 start_line=${end + 1})` : '';
    return clip(`${f.rel}${title ? ` (${title})` : ''} ${start}-${end}줄 / 전체 ${lines.length}줄\n${body.join('\n')}${tail}`);
}

// ---------------------------------------------------------------------------
// Claude 도구 정의
// ---------------------------------------------------------------------------

const pgmTools = [
    {
        name: 'list_programs',
        description: 'PGM 소스 폴더(HTML로 저장된 프로그램 소스)에 있는 프로그램 목록을 돌려줍니다. 사용자가 말한 프로그램 이름이 어떤 파일인지 모를 때 query 로 이름 일부를 넣어 찾으세요.',
        input_schema: {
            type: 'object',
            properties: {
                query: { type: 'string', description: '파일명이나 화면 제목의 일부 (생략하면 전체 목록)' }
            }
        }
    },
    {
        name: 'search_program_source',
        description: 'PGM 소스에서 키워드를 찾아 줄 번호와 앞뒤 문맥을 돌려줍니다. 화면 라벨(예: "입고 금액"), 변수/컬럼명(예: IN_AMT), 함수명 등을 찾을 때 사용합니다. 일반 검색은 대소문자와 띄어쓰기를 무시합니다.',
        input_schema: {
            type: 'object',
            properties: {
                keyword: { type: 'string', description: '찾을 문자열 (regex=true 면 정규식)' },
                program: { type: 'string', description: '검색할 프로그램 이름 (생략하면 전체 프로그램 검색)' },
                regex: { type: 'boolean', description: 'keyword 를 정규식으로 해석할지 여부 (기본 false)' },
                context_lines: { type: 'integer', description: '일치한 줄 앞뒤로 보여 줄 줄 수 (기본 3, 최대 15)' },
                max_results: { type: 'integer', description: '최대 결과 수 (기본 30, 최대 100)' }
            },
            required: ['keyword']
        }
    },
    {
        name: 'read_program_source',
        description: `PGM 소스 파일을 줄 번호와 함께 읽습니다. 한 번에 최대 ${MAX_READ_LINES}줄까지 돌려주므로, 검색 결과의 줄 번호 근처를 범위로 지정해 읽으세요.`,
        input_schema: {
            type: 'object',
            properties: {
                program: { type: 'string', description: '프로그램 이름 (파일명, 경로, 화면 제목 일부 가능)' },
                start_line: { type: 'integer', description: '시작 줄 (기본 1)' },
                end_line: { type: 'integer', description: `끝 줄 (기본 start_line+${MAX_READ_LINES - 1})` }
            },
            required: ['program']
        }
    }
];

const pgmHandlers = {
    list_programs: listPrograms,
    search_program_source: searchProgramSource,
    read_program_source: readProgramSource
};

const pgmSystemPrompt = `
[PGM 소스 질의]
사용자가 프로그램(PGM)의 필드, 계산식, 로직, 테이블 등에 대해 물으면 list_programs / search_program_source / read_program_source 도구로 실제 소스를 확인한 뒤 답하세요. PGM 소스 폴더의 HTML 파일은 filesystem 도구로 직접 읽지 말고 이 도구들을 쓰세요.
필드 계산 방식을 물으면 다음 순서로 추적하세요.
1. 프로그램 파일을 특정합니다 (이름이 애매하면 list_programs).
2. 화면 라벨(예: "입고 금액")로 검색해서 그 라벨에 연결된 변수/컬럼/컨트롤 이름(예: IN_AMT, edtInAmt)을 찾습니다.
3. 그 이름으로 다시 검색해서 값을 대입하거나 계산하는 곳(대입문, SQL SELECT 식, 함수 호출)을 찾고, 필요하면 앞뒤를 읽어 조건 분기까지 확인합니다.
4. 계산에 쓰이는 다른 변수도 같은 방법으로 출처를 따라가되, 소스에 없는 부분(다른 프로그램, DB 함수 등)은 추측하지 말고 "소스에서 확인되지 않음"이라고 밝힙니다.
답변에는 최종 계산식을 한 줄로 먼저 쓰고, 조건별 차이와 근거 위치(파일명:줄번호)를 덧붙이세요. 텔레그램에서 읽기 쉽게 간결하게 쓰세요.`;

module.exports = {
    pgmTools, pgmHandlers, pgmSystemPrompt,
    // 테스트용
    htmlToText, decodeBuffer, buildPattern, listPrograms, searchProgramSource, readProgramSource,
    _resetCache: () => { listCache = { dir: null, at: 0, files: [] }; textCache.clear(); }
};
