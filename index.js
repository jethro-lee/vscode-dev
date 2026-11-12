require('dotenv').config();
const { Telegraf } = require('telegraf');
const { message } = require('telegraf/filters');
const Anthropic = require('@anthropic-ai/sdk');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { OpenAI } = require('openai');
const fs = require('fs');
const axios = require('axios');
const path = require('path');
const { addDailySchedule } = require('./dailySchedule');
const { pgmTools, pgmHandlers, pgmSystemPrompt } = require('./pgmSource');

// 환경변수 누락 체크
if (!process.env.TELEGRAM_BOT_TOKEN) {
    console.error("❌ .env 파일에 환경변수가 누락되었습니다.");
    process.exit(1);
}

// 1. API 및 봇 초기화
const bot = new Telegraf(process.env.TELEGRAM_BOT_TOKEN);
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
const MY_CHAT_ID = process.env.MY_CHAT_ID;

// 2. MCP 클라이언트 설정
const vaultPath = "G:\\내 드라이브\\AI";
const transport = new StdioClientTransport({
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-filesystem", vaultPath]
});
const mcpClient = new Client({ name: "ai-assistant", version: "1.0.0" }, { capabilities: {} });

let mcpTools = [];

// 네이버 Access Token 재발급 함수
async function getNaverAccessToken() {
    const api_url = `https://nid.naver.com/oauth2.0/token?grant_type=refresh_token&client_id=${process.env.NAVER_CLIENT_ID}&client_secret=${process.env.NAVER_CLIENT_SECRET}&refresh_token=${process.env.NAVER_REFRESH_TOKEN}`;
    const response = await axios.get(api_url);
    return response.data.access_token;
}

// 네이버 캘린더에 일정 등록
async function addNaverSchedule({ title, description, location, start_time, end_time }) {
    const token = await getNaverAccessToken();
    const uid = Math.random().toString(36).substring(2, 11);
    const icalString = `BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:AI-Assistant\nBEGIN:VEVENT\nUID:${uid}\nDTSTART;TZID=Asia/Seoul:${start_time}\nDTEND;TZID=Asia/Seoul:${end_time}\nSUMMARY:${title}\nDESCRIPTION:${description || ''}\nLOCATION:${location || ''}\nEND:VEVENT\nEND:VCALENDAR`;

    const naverRes = await axios.post(
        'https://openapi.naver.com/calendar/createSchedule.json',
        `calendarId=defaultCalendarId&scheduleIcalString=${encodeURIComponent(icalString)}`,
        { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    if (naverRes.data.result !== 'success') {
        throw new Error(`네이버 응답: ${JSON.stringify(naverRes.data)}`);
    }
    return "네이버 캘린더에 등록했습니다.";
}

// 일정 하나를 네이버 캘린더와 일간 일정표 두 곳에 등록합니다.
// 한쪽이 실패해도 다른 쪽은 진행하고, 각각의 결과를 Claude에게 알려줍니다.
async function addSchedule(input) {
    const [naver, daily] = await Promise.allSettled([addNaverSchedule(input), addDailySchedule(input)]);
    const describe = (label, r) => r.status === 'fulfilled' ? `✅ ${r.value}` : `❌ ${label} 실패: ${r.reason.message}`;
    return [describe('네이버 캘린더', naver), describe('일간 일정표', daily)].join('\n');
}

// 일정 등록용 로컬 도구 정의
const localTools = [
    {
        name: "add_schedule",
        description: "일정을 등록합니다. 한 번 호출하면 네이버 캘린더와 업무노트의 일간 일정표(03.일간) 두 곳에 함께 기록됩니다. 일정 등록 요청에는 항상 이 도구를 사용하고, 일간 일정표 파일을 직접 수정하지 마세요.",
        input_schema: {
            type: "object",
            properties: {
                title: { type: "string", description: "일정 제목" },
                description: { type: "string", description: "일정 상세 내용 (없으면 빈 문자열)" },
                location: { type: "string", description: "장소 (없으면 빈 문자열)" },
                start_time: { type: "string", description: "시작 시간 (YYYYMMDDTHHMMSS 형식, 예: 20261110T150000)" },
                end_time: { type: "string", description: "종료 시간 (YYYYMMDDTHHMMSS 형식, 예: 20261110T160000). 종료 시간을 말하지 않았으면 시작 1시간 뒤" }
            },
            required: ["title", "start_time", "end_time"]
        }
    },
    // PGM 소스(HTML) 검색/열람 도구
    ...pgmTools
];

// 로컬 도구 이름 -> 실행 함수
const localHandlers = {
    add_schedule: addSchedule,   // 네이버 캘린더 + 일간 일정표 동시 등록
    ...pgmHandlers
};

// 소스 추적처럼 도구를 여러 번 부르는 작업이 끝없이 돌지 않도록 막는 상한
const MAX_TOOL_ROUNDS = 20;

// 서버 시작 함수
async function startServer() {
    await mcpClient.connect(transport);
    console.log("✅ MCP Filesystem 서버 연결 완료");

    const toolsResponse = await mcpClient.listTools();
    mcpTools = toolsResponse.tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        input_schema: tool.inputSchema
    }));
}

// Claude 호출 함수
async function askClaude(promptText) {
    let messages = [{ role: 'user', content: promptText }];
    const allTools = [...mcpTools, ...localTools];

    // 한 번의 질문/답변 사이클 동안 시간이 고정되도록 루프 밖에서 계산
    const now = new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const systemPrompt = `현재 한국 시간은 ${now}입니다. 이 시간을 기준으로 '오늘', '내일', '이번 주' 등의 상대적인 날짜를 정확히 계산해서 일정을 등록하세요.
일정 등록은 add_schedule 도구 하나로 네이버 캘린더와 일간 일정표에 모두 기록됩니다. 도구 결과에 실패가 있으면 어느 쪽이 실패했는지 사용자에게 알려 주세요.
${pgmSystemPrompt}`;

    for (let round = 0; ; round++) {
        if (round >= MAX_TOOL_ROUNDS) {
            return "⚠️ 확인할 내용이 너무 많아 중간에 멈췄습니다. 프로그램 이름이나 필드를 좀 더 구체적으로 물어봐 주세요.";
        }
        const response = await anthropic.messages.create({
            model: process.env.CLAUDE_MODEL || "claude-haiku-5-5",
            max_tokens: 4096,
            system: systemPrompt,
            tools: allTools,
            messages: messages
        });

        if (response.stop_reason === 'tool_use') {
            messages.push({ role: "assistant", content: response.content });

            let toolResults = [];
            for (const content of response.content) {
                if (content.type === 'tool_use') {
                    console.log(`🛠️ 도구 사용 중: ${content.name}`);
                    try {
                        let resultData;

                        if (localHandlers[content.name]) {
                            resultData = await localHandlers[content.name](content.input);
                        } else {
                            // 옵시디언 파일 탐색 도구 (MCP)
                            resultData = await mcpClient.callTool({
                                name: content.name,
                                arguments: content.input
                            });
                        }

                        toolResults.push({
                            type: "tool_result",
                            tool_use_id: content.id,
                            content: typeof resultData === 'string' ? resultData : JSON.stringify(resultData)
                        });
                    } catch (error) {
                        toolResults.push({
                            type: "tool_result",
                            tool_use_id: content.id,
                            content: `Error: ${error.message}`,
                            is_error: true
                        });
                    }
                }
            }
            messages.push({ role: "user", content: toolResults });

        } else {
            const text = response.content.filter(c => c.type === 'text').map(c => c.text).join('\n').trim();
            return text || "요청하신 작업을 완료했습니다.";
        }
    }
}

// 텔레그램 메시지는 4096자 제한이 있어서, 긴 답변(소스 분석 등)은 줄 단위로 나눠 보냅니다.
const TELEGRAM_LIMIT = 4000;
async function replyLong(ctx, text) {
    const chunks = [];
    let buf = '';
    for (const line of text.split('\n')) {
        let rest = line;
        while (rest.length > TELEGRAM_LIMIT) {           // 한 줄이 아주 긴 경우
            if (buf) { chunks.push(buf); buf = ''; }
            chunks.push(rest.slice(0, TELEGRAM_LIMIT));
            rest = rest.slice(TELEGRAM_LIMIT);
        }
        if (buf && buf.length + rest.length + 1 > TELEGRAM_LIMIT) { chunks.push(buf); buf = ''; }
        buf += (buf ? '\n' : '') + rest;
    }
    if (buf) chunks.push(buf);
    for (const chunk of chunks) await ctx.reply(chunk);
}

// 3. 텔레그램 텍스트 메시지 처리
bot.on(message('text'), async (ctx) => {
    const chatId = ctx.chat.id;
    if (chatId.toString() !== MY_CHAT_ID) return;

    await ctx.reply("🤔 확인 중입니다...");

    try {
        const reply = await askClaude(ctx.message.text);
        await replyLong(ctx, reply);
    } catch (error) {
        console.error(error);
        await ctx.reply("❌ 텍스트 처리 중 오류가 발생했습니다.");
    }
});

// 4. 텔레그램 음성 메시지 처리
bot.on(message('voice'), async (ctx) => {
    const chatId = ctx.chat.id;
    if (chatId.toString() !== MY_CHAT_ID) return;

    await ctx.reply("🎙️ 음성 분석 중...");

    try {
        const fileLink = await ctx.telegram.getFileLink(ctx.message.voice.file_id);
        const response = await axios({ url: fileLink.href, responseType: 'stream' });
        const tempFilePath = path.join(__dirname, `temp_${ctx.message.message_id}.ogg`);

        const writer = fs.createWriteStream(tempFilePath);
        response.data.pipe(writer);

        await new Promise((resolve, reject) => {
            writer.on('finish', resolve);
            writer.on('error', reject);
        });

        const transcription = await openai.audio.transcriptions.create({
            file: fs.createReadStream(tempFilePath),
            model: "whisper-1",
        });
        const rawText = transcription.text;
        fs.unlinkSync(tempFilePath);

        // 옵시디언 저장 및 일정 등록 통합 프롬프트
        const prompt = `방금 녹음된 음성 내용: "${rawText}"
        이 내용을 분석해서 회의록이나 메모라면 옵시디언 폴더에 마크다운으로 저장해 주고,
        만약 특정 날짜나 시간이 포함된 일정 관련 내용이라면 add_schedule 도구로 일정을 등록해 줘. (둘 다 해당하면 둘 다 처리해 줘)`;

        const reply = await askClaude(prompt);
        await replyLong(ctx, reply);

    } catch (error) {
        console.error(error);
        await ctx.reply("❌ 음성 처리 중 오류가 발생했습니다.");
    }
});

// MCP 도구 목록을 먼저 받아 온 뒤 봇을 시작합니다.
startServer()
    .catch(err => console.error("⚠️ MCP 서버 연결 실패 (일정 등록은 계속 동작):", err.message))
    .finally(() => {
        bot.launch();
        console.log("🤖 AI 비서 봇이 실행되었습니다.");
    });

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
