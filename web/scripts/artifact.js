// Turn the static build's index.html into a claude.ai artifact page: the host
// wraps it in its own <html>/<head>/<body>, so keep the title, styles, body
// markup and inline script; drop the document skeleton, metas and favicon.
import { readFileSync, writeFileSync } from 'node:fs';

const dir = process.argv[2] ?? 'build-artifact';
const html = readFileSync(`${dir}/index.html`, 'utf8');
// The inline bundle itself contains "<body>" / "</body>" (the error page
// template), so split on the first <body> tag and the last </body>.
const open = html.indexOf('<body');
const close = html.lastIndexOf('</body>');
if (open < 0 || close < open) throw new Error(`no <body> in ${dir}/index.html`);
const head = html.slice(0, open);
const body = html.slice(html.indexOf('>', open) + 1, close);

const styles = head.match(/<style[\s\S]*?<\/style>/g) ?? [];
const scripts = head.match(/<script[\s\S]*?<\/script>/g) ?? [];
const page = [
	'<title>SportsML NFL</title>',
	'<meta name="claude:viewport-fit-sides" content="cover">',
	...styles,
	...scripts,
	body.trim()
].join('\n');
writeFileSync(`${dir}/sportsml.html`, page + '\n');
console.log(`wrote ${dir}/sportsml.html (${(page.length / 1024).toFixed(0)} KB)`);
