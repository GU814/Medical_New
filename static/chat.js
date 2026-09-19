/**
 * 医学问诊智能体 - 前端交互逻辑
 */

// ==================== 全局状态 ====================
let sessionId = null;
let isProcessing = false;

// ==================== DOM 元素 ====================
const chatArea = document.getElementById('chatArea');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const resetBtn = document.getElementById('resetBtn');
const stageIndicator = document.getElementById('stageIndicator');

// ==================== 初始化 ====================

/**
 * 自动调整输入框高度
 */
messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

/**
 * Enter 发送消息（Shift+Enter 换行）
 */
messageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

/**
 * 发送按钮点击
 */
sendBtn.addEventListener('click', sendMessage);

/**
 * 重置按钮点击
 */
resetBtn.addEventListener('click', resetSession);

// ==================== 核心函数 ====================

/**
 * 发送消息
 */
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isProcessing) return;

    // 禁用输入
    isProcessing = true;
    sendBtn.disabled = true;
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // 显示用户消息
    appendMessage('user', message);

    // 显示"正在输入"指示器
    showTypingIndicator();

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
            }),
        });

        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('text/event-stream')) {
            // 流式输出（SSE）
            await handleStreamingResponse(response);
        } else {
            // 非流式 JSON 回退（服务端 STREAMING_OUTPUT=false 时）
            await handleJsonResponse(response);
        }
    } catch (error) {
        hideTypingIndicator();
        appendMessage('bot', '❌ 网络连接失败，请检查网络后重试。');
        console.error('发送消息失败:', error);
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

/**
 * 处理非流式 JSON 回退
 */
async function handleJsonResponse(response) {
    const data = await response.json();
    hideTypingIndicator();

    if (data.session_id) sessionId = data.session_id;
    if (data.stage) updateStageIndicator(data.stage);

    if (data.reply) appendMessage('bot', data.reply);
    if (data.report) appendReport(data.report);
}

/**
 * 处理 SSE 流式响应：逐段渲染回复与报告
 */
async function handleStreamingResponse(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');

    const replyEl = createStreamingBubble('bot');
    let replyRaw = '';
    let gotFirstChunk = false;

    let reportBody = null;
    let reportLabel = null;
    let reportRaw = '';

    let buffer = '';

    const appendReply = (chunk) => {
        if (!gotFirstChunk) {
            gotFirstChunk = true;
            hideTypingIndicator();
        }
        replyRaw += chunk;
        // 实时隐藏尾部 JSON 块，避免结构化数据/思维链闪现
        replyEl.innerHTML = renderMarkdown(cleanTrailingJson(replyRaw));
        scrollToBottom();
    };
    const finalizeReply = (cleanText) => {
        replyRaw = (cleanText != null) ? cleanText : replyRaw;
        replyEl.innerHTML = renderMarkdown(replyRaw);
        scrollToBottom();
    };
    const appendReport = (chunk) => {
        if (!reportBody) {
            reportBody = createReportBubble();
            reportLabel = reportBody.previousElementSibling; // 标题元素
        }
        reportRaw += chunk;
        reportBody.innerHTML = renderMarkdown(reportRaw);
        scrollToBottom();
    };
    const finalizeReport = () => {
        if (reportLabel) reportLabel.textContent = '📋 问诊报告';
    };

    const ctx = { appendReply, finalizeReply, appendReport, finalizeReport };

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 按空行切分 SSE 事件
        let sep;
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const ev = parseSSE(rawEvent);
            if (ev) handleSSEEvent(ev, ctx);
        }
    }

    // 处理残余数据
    if (buffer.trim()) {
        const ev = parseSSE(buffer);
        if (ev) handleSSEEvent(ev, ctx);
    }
    hideTypingIndicator();
    finalizeReport();
}

/**
 * 解析单个 SSE 事件块：返回 {event, data}
 */
function parseSSE(block) {
    const lines = block.split('\n');
    let event = 'message';
    const dataLines = [];
    for (const line of lines) {
        if (line.startsWith('event:')) {
            event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).replace(/^ /, ''));
        }
    }
    if (dataLines.length === 0) return null;
    return { event, data: dataLines.join('\n') };
}

/**
 * 根据事件类型更新界面
 */
function handleSSEEvent(ev, ctx) {
    switch (ev.event) {
        case 'reply':
            ctx.appendReply(ev.data);
            break;
        case 'report':
            ctx.appendReport(ev.data);
            break;
        case 'end': {
            try {
                const meta = JSON.parse(ev.data);
                if (meta.session_id) sessionId = meta.session_id;
                if (meta.stage) updateStageIndicator(meta.stage);
                if (meta.reply_clean != null) ctx.finalizeReply(meta.reply_clean);
            } catch (e) {
                console.error('解析 end 事件失败:', e);
            }
            break;
        }
        case 'report_done': {
            try {
                const meta = JSON.parse(ev.data);
                if (meta.stage) updateStageIndicator(meta.stage);
            } catch (e) { /* ignore */ }
            ctx.finalizeReport();
            break;
        }
        case 'error':
            ctx.appendReply('\n\n❌ ' + ev.data);
            break;
        default:
            break;
    }
}

/**
 * 隐藏流式文本末尾的结构化 JSON 块（```json ... ```），避免闪现
 */
function cleanTrailingJson(text) {
    const cutFrom = (marker) => {
        const i = text.lastIndexOf(marker);
        if (i === -1) return -1;
        const tail = text.slice(i + marker.length).trim();
        // 仅当尾部是 JSON 结构时才裁剪
        if (tail.startsWith('{') || tail.includes('"patient_name"') || tail.includes('"stage_complete"')) {
            return i;
        }
        return -1;
    };
    let cut = cutFrom('```json');
    if (cut === -1) cut = cutFrom('```');
    if (cut !== -1) {
        return text.slice(0, cut).trimEnd();
    }
    return text;
}

/**
 * 创建空的流式消息气泡，返回内容元素
 */
function createStreamingBubble(role) {
    const welcome = chatArea.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    messageDiv.appendChild(contentDiv);
    chatArea.appendChild(messageDiv);
    return contentDiv;
}

/**
 * 创建报告流式气泡（含标题），返回正文内容元素
 */
function createReportBubble() {
    const reportDiv = document.createElement('div');
    reportDiv.className = 'message bot';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const label = document.createElement('div');
    label.style.cssText = 'font-weight: 600; color: #2563eb; margin-bottom: 8px; font-size: 16px;';
    label.textContent = '📋 问诊报告（生成中…）';
    contentDiv.appendChild(label);

    const body = document.createElement('div');
    body.className = 'report-container';
    contentDiv.appendChild(body);

    reportDiv.appendChild(contentDiv);
    chatArea.appendChild(reportDiv);
    return body;
}

/**
 * 重置会话
 */
async function resetSession() {
    try {
        const response = await fetch('/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });

        const data = await response.json();

        if (data.session_id) {
            sessionId = data.session_id;
        }

        // 清空聊天区域
        chatArea.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">👨‍⚕️</div>
                <h2>欢迎使用医学问诊助手</h2>
                <p>我是您的AI问诊助手，将通过对话了解您的健康状况。</p>
                <p class="disclaimer">⚠️ 本系统仅供参考，不能替代医生诊断</p>
            </div>
        `;

        updateStageIndicator(1);

    } catch (error) {
        console.error('重置会话失败:', error);
    }
}

// ==================== UI 辅助函数 ====================

/**
 * 添加消息气泡
 */
function appendMessage(role, content) {
    // 如果欢迎消息还在，先移除
    const welcome = chatArea.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // 对 Bot 消息做简单的 Markdown 渲染
    if (role === 'bot') {
        contentDiv.innerHTML = renderMarkdown(content);
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(contentDiv);
    chatArea.appendChild(messageDiv);

    // 滚动到底部
    scrollToBottom();
}

/**
 * 添加报告显示
 */
function appendReport(reportText) {
    const reportDiv = document.createElement('div');
    reportDiv.className = 'message bot';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const reportLabel = document.createElement('div');
    reportLabel.style.cssText = 'font-weight: 600; color: #2563eb; margin-bottom: 8px; font-size: 16px;';
    reportLabel.textContent = '📋 问诊报告';

    const reportContent = document.createElement('div');
    reportContent.className = 'report-container';
    reportContent.innerHTML = renderMarkdown(reportText);

    contentDiv.appendChild(reportLabel);
    contentDiv.appendChild(reportContent);
    reportDiv.appendChild(contentDiv);
    chatArea.appendChild(reportDiv);

    scrollToBottom();
}

/**
 * 显示"正在输入"指示器
 */
function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.id = 'typingIndicator';

    indicator.innerHTML = `
        <div class="typing-bubble">
            <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;

    chatArea.appendChild(indicator);
    scrollToBottom();
}

/**
 * 隐藏"正在输入"指示器
 */
function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

/**
 * 更新阶段指示器
 */
function updateStageIndicator(stage) {
    const stageNames = {
        1: '基本信息',
        2: '主诉现病史',
        3: '既往史',
        4: '系统回顾',
        5: '问诊完成',
    };
    const stageName = stageNames[stage] || `阶段 ${stage}`;
    stageIndicator.textContent = `${stageName} (${stage}/5)`;

    // 阶段5用绿色
    if (stage === 5) {
        stageIndicator.style.background = '#d1fae5';
        stageIndicator.style.color = '#065f46';
    }
}

/**
 * 简单的 Markdown 渲染
 * 支持：标题、加粗、列表、分隔线、代码块
 */
function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

    // 标题
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // 分隔线
    html = html.replace(/^---$/gm, '<hr>');

    // 加粗
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 无序列表
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // 段落（双换行）
    html = html.replace(/\n\n/g, '</p><p>');

    // 单换行
    html = html.replace(/\n/g, '<br>');

    // 包裹段落
    html = '<p>' + html + '</p>';

    // 清理空段落
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>(<h[1-3]>)/g, '$1');
    html = html.replace(/(<\/h[1-3]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<hr>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');
    html = html.replace(/<p>(<pre>)/g, '$1');
    html = html.replace(/(<\/pre>)<\/p>/g, '$1');

    return html;
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 滚动到底部
 */
function scrollToBottom() {
    requestAnimationFrame(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    });
}

// 页面加载后聚焦输入框
messageInput.focus();
