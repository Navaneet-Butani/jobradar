const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  mdash: "—",
  ndash: "–",
  rsquo: "’",
  lsquo: "‘",
  rdquo: "”",
  ldquo: "“",
  hellip: "…",
};

/** Job descriptions arrive from source ATS pages HTML-entity-encoded (sometimes twice). Decode until stable. */
function decodeHtmlEntities(input: string): string {
  const decodeOnce = (s: string) =>
    s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, code: string) => {
      if (code[0] === "#") {
        const isHex = code[1] === "x" || code[1] === "X";
        const num = parseInt(code.slice(isHex ? 2 : 1), isHex ? 16 : 10);
        return Number.isNaN(num) ? match : String.fromCodePoint(num);
      }
      return NAMED_ENTITIES[code] ?? match;
    });

  let out = input;
  for (let i = 0; i < 3; i++) {
    const next = decodeOnce(out);
    if (next === out) break;
    out = next;
  }
  return out;
}

/** Strip script/style/iframe tags and inline event handlers before rendering source-provided HTML. */
function stripUnsafeMarkup(html: string): string {
  return html
    .replace(/<(script|style|iframe|object|embed)[^>]*>[\s\S]*?<\/\1>/gi, "")
    .replace(/<(script|style|iframe|object|embed)[^>]*\/?>/gi, "")
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/(href|src)\s*=\s*("javascript:[^"]*"|'javascript:[^']*')/gi, "");
}

export function renderJobHtml(raw: string | null | undefined): string {
  if (!raw) return "";
  return stripUnsafeMarkup(decodeHtmlEntities(raw));
}
