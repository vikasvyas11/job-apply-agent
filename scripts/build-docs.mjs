// Field Notes documentation builder (template from the field-notes-docs skill).
// Copy to <repo>/scripts/build-docs.mjs. Reads docs/docs.config.json, converts every
// tracked Markdown file to themed HTML (originals preserved), wraps authored HTML guides,
// and writes a searchable file index into docs/site/. Needs: git, node, `npm i -D marked`.
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';

const cfg = JSON.parse(readFileSync('docs/docs.config.json', 'utf8'));
const out = 'docs/site';
const guides = cfg.guides ?? [];
// Job Application Agent changes to the skill template:
// 1. Outside a git checkout (the private working copy) the file list comes from a
//    directory walk that skips private and generated paths, never the git index.
// 2. Personal content and its templates (content/, content.example/) are prompt data,
//    not documentation, so they are never turned into doc pages.
const PRIVATE = new Set(['node_modules', '.git', '.venv', 'output', 'content', 'archive', '__pycache__',
  '.pytest_cache', '.ruff_cache', 'tools']);
const SECRET_FILES = new Set(['credentials.json', 'token.json', 'local_settings.json']);
function walk(dir = '.') {
  const found = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = dir === '.' ? entry.name : `${dir}/${entry.name}`;
    if (entry.isDirectory()) { if (!PRIVATE.has(entry.name) && rel !== out) found.push(...walk(rel)); }
    else if (!SECRET_FILES.has(entry.name)) found.push(rel);
  }
  return found;
}
let listed;
try {
  listed = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).split('\0').filter(Boolean);
} catch { listed = walk(); }
const files = listed.filter(f => !f.startsWith(`${out}/`) && !f.split('/').some(part => PRIVATE.has(part))
  && !SECRET_FILES.has(path.posix.basename(f))).sort();
const docs = files.filter(f => f.toLowerCase().endsWith('.md') && !/^content(\.example)?\//.test(f));
files.push(`${out}/index.html`, `${out}/style.css`, ...guides.map(g => `${out}/${g.page}`), ...docs.map(f => `${out}/${f.replace(/\.md$/i, '.html')}`));
files.sort();

const escape = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const mdTitle = f => f.replace(/\.md$/i, '').replaceAll('-', ' ').replaceAll('/', ' / ');
const entries = [...guides.map(g => ({ name: g.title, href: g.page })), ...docs.map(f => ({ name: mdTitle(f), href: f.replace(/\.md$/i, '.html') }))];

function build(name, content, target) {
  const dir = path.posix.dirname(target);
  const relRoot = path.posix.relative(dir, '.') || '.';
  const relSite = path.posix.relative(dir, out) || '.';
  const nav = entries.map(e => `<a href="${relSite}/${e.href}"${e.name === name ? ' aria-current="page"' : ''}>${escape(e.name)}</a>`).join('');
  const mark = cfg.icon ? `<img src="${relRoot}/${cfg.icon}" alt="" style="width:37px;height:37px;border-radius:12px;vertical-align:middle;margin-right:8px">` : `<b>${escape((cfg.product ?? 'D')[0])}</b>`;
  const fileData = JSON.stringify(files).replaceAll('<', '\\u003c');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(name)} · ${escape(cfg.product)}</title><link rel="stylesheet" href="${relSite}/style.css"></head><body><header><a class="brand" href="${relSite}/index.html">${mark} ${escape(cfg.brand)}<span>.</span> <small>${escape(cfg.tagline ?? 'FIELD NOTES')}</small></a><div class="controls"><button id="left-toggle" aria-controls="left" aria-expanded="true">☰ <span>Documents</span></button><button id="right-toggle" aria-controls="right" aria-expanded="true">⌕ <span>Find files</span></button></div></header><div class="layout" id="layout"><aside id="left"><p class="eyebrow">THE LIBRARY</p><h2>On this project<span>.</span></h2><nav><a href="${relSite}/index.html"${name === 'Overview' ? ' aria-current="page"' : ''}>Overview</a>${nav}</nav><p class="small">Made for curious minds.<br>Available offline.</p></aside><main><div class="content"><p class="eyebrow">${escape(cfg.product.toUpperCase())} / DOCUMENTATION</p>${content}</div><footer>${escape(cfg.product)} <span>✳</span> ${escape(cfg.footer ?? 'Made to make sense.')}</footer></main><aside id="right"><p class="eyebrow">THE REPOSITORY</p><h2>Find a file<span>.</span></h2><label for="search">Search by filename or path</label><input id="search" type="search" placeholder="Try a filename or folder…" autocomplete="off"><p id="count" class="small"></p><div id="results"></div></aside></div><script>const files=${fileData};const root=${JSON.stringify(relRoot)};const site=${JSON.stringify(relSite)};const input=document.getElementById('search'),results=document.getElementById('results'),count=document.getElementById('count');function render(){const q=input.value.toLowerCase().trim();const matches=files.filter(f=>f.toLowerCase().includes(q));count.textContent=matches.length+' files';results.replaceChildren();for(const f of matches){const a=document.createElement('a');a.textContent=f;a.href=/\\.md$/i.test(f)?site+'/'+f.replace(/\\.md$/i,'.html'):root+'/'+f;results.append(a)}}input.addEventListener('input',render);render();for(const side of ['left','right']){const b=document.getElementById(side+'-toggle'),panel=document.getElementById(side);b.addEventListener('click',()=>{panel.hidden=!panel.hidden;b.setAttribute('aria-expanded',String(!panel.hidden));document.getElementById('layout').classList.toggle('hide-'+side,panel.hidden)})}</script></body></html>`;
}

mkdirSync(`${out}/fonts`, { recursive: true });
copyFileSync('docs/style-source.css', `${out}/style.css`);
if (existsSync('docs/fonts/manrope.ttf')) copyFileSync('docs/fonts/manrope.ttf', `${out}/fonts/manrope.ttf`);

const cards = guides.slice(0, 3).map(g => `<a href="${g.page}"><small>${escape(g.eyebrow ?? 'READ ↗')}</small><h2>${escape(g.title)}</h2><p>${escape(g.summary ?? '')}</p></a>`).join('');
const home = `<h1>${escape(cfg.homeTitle ?? 'Ideas, in order')}<span>.</span></h1><p class="lead">${escape(cfg.homeLead ?? 'Everything behind this project: guides, decisions and a way to find any file.')}</p><div class="cards">${cards}</div><h2>A map for the curious</h2><p>Choose a document on the left, or search the repository by name on the right. Panel buttons at the top give your reading more room.</p>`;
writeFileSync(`${out}/index.html`, build('Overview', home, `${out}/index.html`));
for (const g of guides) writeFileSync(`${out}/${g.page}`, build(g.title, readFileSync(g.source, 'utf8'), `${out}/${g.page}`));
for (const f of docs) {
  const target = `${out}/${f.replace(/\.md$/i, '.html')}`;
  mkdirSync(path.dirname(target), { recursive: true });
  let html = marked.parse(readFileSync(f, 'utf8'));
  html = html.replace(/href="([^"#?]+\.md)(#[^"]*)?"/gi, (_, url, hash = '') => {
    if (/^(https?:|mailto:)/i.test(url)) return `href="${url}${hash}"`;
    const abs = path.posix.normalize(path.posix.join(path.posix.dirname(f), url)).replace(/\.md$/i, '.html');
    return `href="${path.posix.relative(path.posix.dirname(target), `${out}/${abs}`)}${hash}"`;
  });
  writeFileSync(target, build(mdTitle(f), html, target));
}
console.log(`Built ${guides.length} guides and ${docs.length} Markdown documents; indexed ${files.length} files.`);
