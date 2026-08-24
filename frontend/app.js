const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const messages = document.querySelector('#messages');
const newChat = document.querySelector('#new-chat');
const sendButton = document.querySelector('.send-button');
const threadId = crypto.randomUUID ? crypto.randomUUID() : `thread-${Date.now()}`;
const conversation = [];

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
}

function formatInline(value) {
  return value.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>');
}

function renderMarkdown(value) {
  const lines = escapeHtml(value.trim()).split('\n');
  const output = [];
  let listType = '';
  let listItems = [];
  let orderedItemOpen = false;
  const closeList = () => {
    if (orderedItemOpen && listItems.length) listItems[listItems.length - 1] += '</li>';
    if (listItems.length) output.push(`<${listType}>${listItems.join('')}</${listType}>`);
    listItems = [];
    listType = '';
    orderedItemOpen = false;
  };
  lines.forEach((line) => {
    const unordered = line.match(/^\s*[-*] (.+)$/);
    const ordered = line.match(/^\s*\d+\. (.+)$/);
    if (unordered || ordered) {
      const nextType = unordered ? 'ul' : 'ol';
      if (listType && listType !== nextType) closeList();
      listType = nextType;
      if (nextType === 'ol') {
        if (orderedItemOpen) listItems[listItems.length - 1] += '</li>';
        listItems.push(`<li>${formatInline(ordered[1])}`);
        orderedItemOpen = true;
      } else {
        listItems.push(`<li>${formatInline(unordered[1])}</li>`);
      }
    } else if (!line.trim() && listType) {
      return;
    } else {
      closeList();
      if (/^#{1,3} /.test(line)) output.push(`<h4>${formatInline(line.replace(/^#{1,3} /, ''))}</h4>`);
      else if (line.trim()) output.push(`<p>${formatInline(line.trim())}</p>`);
    }
  });
  closeList();
  return output.join('');
}

function addMessage(text, role, meta = '') {
  document.querySelector('.welcome-message')?.remove();
  const message = document.createElement('article');
  message.className = `message ${role}`;
  message.innerHTML = `<div class="avatar" aria-hidden="true">${role === 'user' ? 'Y' : 'A'}</div><div><div class="bubble"></div>${meta ? `<div class="meta">${meta}</div>` : ''}</div>`;
  const bubble = message.querySelector('.bubble');
  if (role === 'assistant') bubble.innerHTML = renderMarkdown(text);
  else bubble.textContent = text;
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function addTyping() {
  const message = addMessage('', 'assistant');
  const bubble = message.querySelector('.bubble');
  bubble.className = 'bubble typing';
  bubble.innerHTML = '<i></i><i></i><i></i>';
  return message;
}

async function sendMessage(messageText) {
  const text = messageText.trim();
  if (text.length < 2) return;
  const history = conversation.slice(-12);
  conversation.push({ role: 'user', content: text });
  addMessage(text, 'user');
  input.value = '';
  input.style.height = 'auto';
  sendButton.disabled = true;
  const typing = addTyping();

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, thread_id: threadId, history })
    });
    const data = await response.json();
    typing.remove();
    if (!response.ok) throw new Error(data.detail || 'The assistant could not respond.');
    const meta = [data.cached ? 'Cached response' : data.model_used, data.processing_time_ms ? `${data.processing_time_ms} ms` : ''].filter(Boolean).join(' · ');
    conversation.push({ role: 'assistant', content: data.response });
    addMessage(data.response, 'assistant', meta);
  } catch (error) {
    typing.remove();
    addMessage(error.message, 'assistant', 'Something went wrong');
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => { event.preventDefault(); sendMessage(input.value); });
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 140)}px`; });
input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => sendMessage(button.dataset.prompt)));
newChat.addEventListener('click', () => { messages.innerHTML = '<div class="welcome-message"><div class="welcome-icon" aria-hidden="true">✦</div><p class="eyebrow">Fresh start</p><h3>What would you like to explore?</h3><p class="welcome-copy">Bring a question, a rough idea, or a problem worth untangling.</p></div>'; conversation.length = 0; input.value = ''; input.focus(); });
