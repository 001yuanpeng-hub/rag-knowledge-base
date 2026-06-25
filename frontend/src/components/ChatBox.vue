<template>
  <div class="chat-app">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="container">
        <div class="logo">
          <div class="logo-mark">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <path d="M6 4L14 16L10 28H13L16 20L19 28H22L18 16L26 4H23L16 14L9 4H6Z" fill="url(#gradient)"/>
              <defs>
                <linearGradient id="gradient" x1="6" y1="4" x2="26" y2="28">
                  <stop stop-color="#6366f1"/>
                  <stop offset="1" stop-color="#8b5cf6"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span class="logo-text">RAG 知识库</span>
        </div>
      </div>
    </header>

    <!-- 对话区域 -->
    <main class="messages" ref="messagesRef">
      <div class="container">
        <!-- 欢迎界面 -->
        <div v-if="messages.length === 0" class="welcome">
          <div class="welcome-mark">
            <svg width="48" height="48" viewBox="0 0 32 32" fill="none">
              <path d="M6 4L14 16L10 28H13L16 20L19 28H22L18 16L26 4H23L16 14L9 4H6Z" fill="url(#gradient2)"/>
              <defs>
                <linearGradient id="gradient2" x1="6" y1="4" x2="26" y2="28">
                  <stop stop-color="#6366f1"/>
                  <stop offset="1" stop-color="#8b5cf6"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1>有什么可以帮你的？</h1>
        </div>

        <!-- 消息列表 -->
        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['message', msg.role]"
        >
          <div class="bubble">
            <div class="bubble-text" v-html="formatMessage(msg.content)"></div>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="isLoading" class="message ai">
          <div class="bubble typing">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部输入区域 -->
    <footer class="footer">
      <div class="container">
        <!-- 已上传文件标签 -->
        <div v-if="uploadedFile" class="file-tag">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span>{{ uploadedFile }}</span>
          <button @click="uploadedFile = ''" class="remove-tag">×</button>
        </div>

        <div class="input-wrapper">
          <!-- 上传按钮 -->
          <div class="upload-btn-wrapper" ref="uploadWrapper">
            <button
              class="upload-trigger"
              @click="toggleUploadMenu"
              :class="{ active: showUploadMenu }"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>

            <!-- 上传菜单 -->
            <div v-if="showUploadMenu" class="upload-menu">
              <input
                type="file"
                ref="fileInput"
                @change="handleFileSelect"
                accept=".txt,.pdf,.md,.docx"
                hidden
              />
              <button class="menu-item" @click="triggerFileInput">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <span>上传文档</span>
                <span class="hint">TXT, PDF, MD, DOCX</span>
              </button>
            </div>
          </div>

          <!-- 模型选择器 -->
          <select v-model="selectedModel" class="model-select">
            <option value="mimo">MiMo</option>
            <option value="claude">Claude</option>
          </select>

          <!-- 输入框 -->
          <input
            v-model="question"
            @keyup.enter="send"
            placeholder="输入你的问题..."
            :disabled="isLoading"
            class="message-input"
          />

          <!-- 发送按钮 -->
          <button
            class="send-btn"
            @click="send"
            :disabled="isLoading || !question.trim()"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>

        <div class="footer-hint">按 Enter 发送</div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true
})

const question = ref('')
const messages = ref([])
const isLoading = ref(false)
const messagesRef = ref(null)
const fileInput = ref(null)
const uploadWrapper = ref(null)
const showUploadMenu = ref(false)
const uploadedFile = ref('')
const selectedModel = ref('mimo')  // 默认选择 MiMo

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

watch(messages, scrollToBottom, { deep: true })

function formatMessage(text) {
  if (!text) return ''
  // 使用 markdown-it 渲染 Markdown
  return md.render(text)
}

function toggleUploadMenu() {
  showUploadMenu.value = !showUploadMenu.value
}

function triggerFileInput() {
  fileInput.value.click()
}

async function handleFileSelect(e) {
  const file = e.target.files[0]
  if (!file) return

  showUploadMenu.value = false

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await axios.post('/api/upload/', formData)
    uploadedFile.value = file.name
    messages.value.push({
      role: 'ai',
      content: `文档 "${file.name}" 上传成功，已处理 ${res.data.chunks_count} 个片段。现在你可以基于文档提问了。`
    })
  } catch (err) {
    messages.value.push({
      role: 'ai',
      content: `上传失败：${err.message}`
    })
  } finally {
    fileInput.value.value = ''
  }
}

function handleClickOutside(e) {
  if (uploadWrapper.value && !uploadWrapper.value.contains(e.target)) {
    showUploadMenu.value = false
  }
}

async function loadHistory() {
  try {
    const res = await axios.get('/api/history/')
    const history = res.data
    for (const record of history) {
      messages.value.push(
        { role: 'user', content: record.question },
        { role: 'ai', content: record.answer }
      )
    }
  } catch (err) {
    console.error('加载历史记录失败:', err)
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  loadHistory()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

async function send() {
  if (!question.value.trim() || isLoading.value) return

  const userMessage = question.value.trim()
  messages.value.push({
    role: 'user',
    content: userMessage
  })
  question.value = ''
  isLoading.value = true

  // 添加一个空的 AI 消息，用于流式更新
  const aiMessageIndex = messages.value.length
  messages.value.push({
    role: 'ai',
    content: ''
  })

  try {
    const response = await fetch('/api/chat/stream/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question: userMessage,
        model: selectedModel.value
      })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.done) {
              // 流结束
              isLoading.value = false
            } else if (data.text) {
              // 追加文本
              messages.value[aiMessageIndex].content += data.text
              scrollToBottom()
            }
          } catch (e) {
            // 解析错误忽略
          }
        }
      }
    }
  } catch (err) {
    messages.value[aiMessageIndex].content = '请求失败：' + err.message
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.chat-app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #ffffff;
}

/* 通用容器 */
.container {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 0 20px;
}

/* 顶部导航 */
.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
}

.header .container {
  display: flex;
  align-items: center;
  height: 56px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-mark {
  display: flex;
  align-items: center;
}

.logo-text {
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
}

/* 对话区域 */
.messages {
  flex: 1;
  overflow-y: auto;
  padding-top: 56px;
  padding-bottom: 140px;
}

.messages .container {
  padding-top: 24px;
  padding-bottom: 24px;
}

/* 欢迎界面 */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  text-align: center;
}

.welcome-mark {
  margin-bottom: 20px;
  opacity: 0.9;
}

.welcome h1 {
  font-size: 1.75rem;
  font-weight: 600;
  color: #111827;
  margin-bottom: 28px;
  letter-spacing: -0.02em;
}

/* 消息 */
.message {
  margin-bottom: 20px;
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.message.ai {
  justify-content: flex-start;
}

.bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.7;
  font-size: 0.9375rem;
  word-break: break-word;
}

.bubble-text {
  white-space: normal;
}

.bubble-text p:last-child {
  margin-bottom: 0;
}

.bubble-text h1,
.bubble-text h2,
.bubble-text h3 {
  margin-top: 12px;
  margin-bottom: 8px;
  font-weight: 600;
}

.bubble-text h1 {
  font-size: 1.25rem;
}

.bubble-text h2 {
  font-size: 1.125rem;
}

.bubble-text h3 {
  font-size: 1rem;
}

.bubble-text p {
  margin-bottom: 8px;
}

.bubble-text ul,
.bubble-text ol {
  margin-left: 20px;
  margin-bottom: 8px;
}

.bubble-text li {
  margin-bottom: 4px;
}

.bubble-text code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 0.875em;
}

.bubble-text pre {
  background: rgba(0, 0, 0, 0.05);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin-bottom: 8px;
}

.bubble-text pre code {
  background: none;
  padding: 0;
}

.bubble-text strong {
  font-weight: 600;
}

.bubble-text blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 12px;
  margin-left: 0;
  margin-bottom: 8px;
  color: #6b7280;
}

.message.user .bubble {
  background: #f3f4f6;
  color: #111827;
  border-bottom-right-radius: 4px;
}

.message.ai .bubble {
  background: transparent;
  color: #374151;
}

.bubble.typing {
  display: flex;
  gap: 4px;
  padding: 16px 20px;
}

.dot {
  width: 6px;
  height: 6px;
  background: #9ca3af;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* 底部输入区域 */
.footer {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: linear-gradient(to top, #ffffff 80%, transparent);
  padding: 12px 0 16px;
}

.footer .container {
  display: flex;
  flex-direction: column;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 5px;
  padding: 4px 10px;
  background: #f9fafb;
  border-radius: 6px;
  font-size: 0.75rem;
  color: #6b7280;
  margin-bottom: 8px;
}

.remove-tag {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  font-size: 1rem;
  padding: 0 2px;
  line-height: 1;
}

.remove-tag:hover {
  color: #6b7280;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: #f9fafb;
  border: 1px solid transparent;
  border-radius: 14px;
  padding: 6px 6px 6px 4px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input-wrapper:focus-within {
  border-color: #e5e7eb;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.04);
}

.upload-btn-wrapper {
  position: relative;
  flex-shrink: 0;
}

.upload-trigger {
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: #9ca3af;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.upload-trigger:hover {
  background: #f3f4f6;
  color: #6b7280;
}

.upload-trigger.active {
  background: #f3f4f6;
  color: #6366f1;
}

.upload-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: #ffffff;
  border-radius: 10px;
  padding: 4px;
  min-width: 200px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: none;
  border: none;
  border-radius: 6px;
  color: #374151;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.15s;
  text-align: left;
}

.menu-item:hover {
  background: #f9fafb;
}

.menu-item .hint {
  margin-left: auto;
  font-size: 0.7rem;
  color: #9ca3af;
}

.model-select {
  flex-shrink: 0;
  padding: 6px 8px;
  background: transparent;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  color: #374151;
  font-size: 0.8rem;
  cursor: pointer;
  outline: none;
  transition: all 0.15s;
}

.model-select:hover {
  background: #f3f4f6;
}

.model-select:focus {
  border-color: #6366f1;
}

.message-input {
  flex: 1;
  min-width: 0;
  padding: 8px 4px;
  background: transparent;
  border: none;
  color: #111827;
  font-size: 0.9375rem;
  outline: none;
}

.message-input::placeholder {
  color: #9ca3af;
}

.message-input:disabled {
  cursor: not-allowed;
}

.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  background: #111827;
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.send-btn:hover:not(:disabled) {
  background: #374151;
}

.send-btn:disabled {
  background: #e5e7eb;
  cursor: not-allowed;
}

.footer-hint {
  text-align: center;
  font-size: 0.7rem;
  color: #d1d5db;
  margin-top: 8px;
}

/* 滚动条 */
.messages::-webkit-scrollbar {
  width: 4px;
}

.messages::-webkit-scrollbar-track {
  background: transparent;
}

.messages::-webkit-scrollbar-thumb {
  background: #e5e7eb;
  border-radius: 2px;
}

.messages::-webkit-scrollbar-thumb:hover {
  background: #d1d5db;
}

/* 响应式 */
@media (max-width: 840px) {
  .container {
    padding: 0 16px;
  }

  .welcome h1 {
    font-size: 1.375rem;
  }

  .bubble {
    max-width: 85%;
  }
}

@media (max-width: 480px) {
  .container {
    padding: 0 12px;
  }

  .welcome h1 {
    font-size: 1.25rem;
  }

  .bubble {
    max-width: 90%;
    font-size: 0.875rem;
  }

  .input-wrapper {
    gap: 6px;
    padding: 4px 4px 4px 2px;
  }

  .upload-trigger,
  .send-btn {
    width: 32px;
    height: 32px;
  }
}
</style>
