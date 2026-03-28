// minimal markdown-to-HTML renderer — no external deps
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
export function renderMarkdown(text) {
  if (!text) return '';
  let html = esc(text);
  // fenced code blocks — wrap with copy button
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang ? `<span class="code-lang">${lang}</span>` : '';
    const escaped = code.replace(/"/g, '&quot;');
    return `<div class="code-block-wrapper">${langLabel}<button class="code-copy-btn" onclick="this.parentElement.querySelector('code').textContent.trim().replace(/^\\s+/gm,'').length&&navigator.clipboard.writeText(this.parentElement.querySelector('code').textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})">Copy</button><pre><code class="lang-${lang}">${code}</code></pre></div>`;
  });
  // inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // headers
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // bold + italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // blockquotes
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  // unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  // confidence badge
  html = html.replace(/Confidence:\s*(Very High|High|Medium|Low|Very Low)\s*\((\d+)%\)/gi, (_, level, pct) => {
    const n = parseInt(pct, 10);
    const tier = n >= 80 ? 'high' : n >= 50 ? 'mid' : 'low';
    return `<span class="confidence-badge confidence-${tier}"><span class="confidence-dot"></span>${level} <span class="confidence-pct">${pct}%</span></span>`;
  });
  // line breaks (double newline = paragraph, single = br)
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  return `<p>${html}</p>`;
}
