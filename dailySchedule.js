// 업무노트의 '03.일간' 폴더에 있는 날짜별 Markdown 일정표에 일정을 한 줄 추가합니다.
const fs = require('fs/promises');
const path = require('path');

const DEFAULT_DAILY_DIR =
    'G:\\내 드라이브\\AI\\공유_동부하이텍_업무노트 v1.1-20260715 08-24\\공유_동부하이텍_업무노트\\01.일정표\\03.일간';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

// "20261112T100000" -> { y, m, d, hh, mm }
function parseIcalTime(value) {
    const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(value || '');
    if (!m) throw new Error(`시간 형식이 잘못되었습니다: ${value}`);
    return { y: m[1], m: m[2], d: m[3], hh: m[4], mm: m[5] };
}

// 같은 날짜를 가리키는 여러 파일명 표기 (기존 파일 이름 규칙에 맞추기 위함)
function dateVariants({ y, m, d }) {
    return [`${y}-${m}-${d}`, `${y}${m}${d}`, `${y}.${m}.${d}`, `${y}_${m}_${d}`, `${y.slice(2)}${m}${d}`];
}

// 해당 날짜의 일정표 파일을 찾고, 없으면 기본 이름(YYYY-MM-DD.md)을 돌려줍니다.
// 하위 폴더(예: 2026\11월)도 찾아봅니다.
async function findDailyFile(dir, date) {
    const variants = dateVariants(date);
    const stack = [dir];
    while (stack.length) {
        const current = stack.pop();
        let entries;
        try {
            entries = await fs.readdir(current, { withFileTypes: true });
        } catch (err) {
            if (current === dir) throw new Error(`일간 일정표 폴더를 열 수 없습니다: ${dir} (${err.code})`);
            continue;
        }
        for (const entry of entries) {
            const full = path.join(current, entry.name);
            if (entry.isDirectory()) stack.push(full);
            else if (entry.name.toLowerCase().endsWith('.md') && variants.some(v => entry.name.includes(v))) {
                return { filePath: full, exists: true };
            }
        }
    }
    const fileName = (process.env.DAILY_FILE_FORMAT || 'YYYY-MM-DD')
        .replace('YYYY', date.y).replace('MM', date.m).replace('DD', date.d) + '.md';
    return { filePath: path.join(dir, fileName), exists: false };
}

// '일정'이 들어간 제목 아래에 줄을 넣고, 그런 제목이 없으면 '## 일정' 섹션을 새로 만듭니다.
function insertLine(content, line) {
    const lines = content.split(/\r?\n/);
    const headingIdx = lines.findIndex(l => /^#{1,6}\s.*일정/.test(l));
    if (headingIdx === -1) {
        const body = content.replace(/\s*$/, '');
        return `${body}${body ? '\n\n' : ''}## 일정\n${line}\n`;
    }
    let end = lines.findIndex((l, i) => i > headingIdx && /^#{1,6}\s/.test(l));
    if (end === -1) end = lines.length;
    let insertAt = end;
    while (insertAt - 1 > headingIdx && lines[insertAt - 1].trim() === '') insertAt--;
    lines.splice(insertAt, 0, line);
    return lines.join('\n');
}

async function addDailySchedule({ title, location, start_time, end_time }) {
    const dir = process.env.DAILY_SCHEDULE_DIR || DEFAULT_DAILY_DIR;
    const start = parseIcalTime(start_time);
    const end = parseIcalTime(end_time);

    const where = location ? ` (${location})` : '';
    const line = `- [ ] ${start.hh}:${start.mm}~${end.hh}:${end.mm} ${title}${where}`;

    const { filePath, exists } = await findDailyFile(dir, start);
    let content = '';
    if (exists) {
        content = await fs.readFile(filePath, 'utf8');
        if (content.includes(line)) return `일간 일정표에 이미 같은 일정이 있습니다: ${filePath}`;
    } else {
        const weekday = WEEKDAYS[new Date(Number(start.y), Number(start.m) - 1, Number(start.d)).getDay()];
        content = `# ${start.y}-${start.m}-${start.d} (${weekday})\n`;
    }

    await fs.writeFile(filePath, insertLine(content, line), 'utf8');
    return `일간 일정표에 등록했습니다: ${filePath}${exists ? '' : ' (새 파일)'}`;
}

module.exports = { addDailySchedule, insertLine, parseIcalTime };
