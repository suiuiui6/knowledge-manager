const fs = require("fs");
const path = require("path");
const Module = require("module");

process.env.NODE_PATH = [
  process.env.NODE_PATH,
  "C:\\Users\\14156\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules",
  "C:\\Users\\14156\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\.pnpm\\node_modules",
].filter(Boolean).join(path.delimiter);
Module._initPaths();

const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  Packer,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} = require("docx");
const sharp = require("sharp");

const root = "D:\\tyh";
const sourcePath = path.join(root, "paper-assets", "writing", "knowledge-manager-paper-v3.md");
const outDir = path.join(root, "paper-assets", "deliverables");
const figDir = path.join(root, "paper-assets", "figures");
const outPath = path.join(outDir, "knowledge-manager-paper-v3-submission-draft.docx");

fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(figDir, { recursive: true });

const md = fs.readFileSync(sourcePath, "utf8").replace(/\r\n/g, "\n");

const pageWidth = 11906;
const pageHeight = 16838;
const margin = { top: 1440, right: 1260, bottom: 1440, left: 1260 };
const contentWidth = pageWidth - margin.left - margin.right;

const fontCn = "SimSun";
const fontHead = "Microsoft YaHei";
const fontCode = "Consolas";
const blue = "234D63";
const teal = "2F6F73";
const orange = "B66A2C";
const gray = "6B7280";

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function saveSvg(name, svg) {
  const file = path.join(figDir, name);
  fs.writeFileSync(file, svg, "utf8");
  return file;
}

function fig1Svg() {
  const boxes = [
    ["原始文档", 60, 96, "raw text"],
    ["抽取", 245, 96, "extract"],
    [".staging", 430, 96, "candidate modules"],
    ["人工审核", 615, 96, "review / approve"],
    ["正式知识库", 800, 96, "JSON modules + index"],
    ["CLI / MCP 服务", 985, 96, "serve"],
  ];
  const rows = [
    ["结构化模块字段", "overview / details / examples / references / caveats", 90, 300, teal],
    ["治理边界", "人工确认、Git diff、版本追踪、caveat 保留", 430, 300, blue],
    ["按需加载", "先读索引，再搜索模块，最后加载少量相关模块", 770, 300, orange],
  ];
  const boxSvg = boxes.map(([title, x, y, sub]) => `
    <rect x="${x}" y="${y}" width="145" height="92" rx="16" fill="#F8FAFC" stroke="#7AA6B2" stroke-width="2"/>
    <text x="${x + 72.5}" y="${y + 40}" text-anchor="middle" font-size="24" font-weight="700" fill="#173B45">${escapeXml(title)}</text>
    <text x="${x + 72.5}" y="${y + 68}" text-anchor="middle" font-size="15" fill="#5B6770">${escapeXml(sub)}</text>`).join("");
  const arrows = boxes.slice(0, -1).map(([, x, y]) => `
    <line x1="${x + 150}" y1="${y + 46}" x2="${x + 180}" y2="${y + 46}" stroke="#43616B" stroke-width="3" marker-end="url(#arrow)"/>`).join("");
  const rowSvg = rows.map(([title, sub, x, y, color]) => `
    <rect x="${x}" y="${y}" width="300" height="90" rx="14" fill="#FFFFFF" stroke="${color}" stroke-width="2"/>
    <text x="${x + 150}" y="${y + 34}" text-anchor="middle" font-size="23" font-weight="700" fill="${color}">${escapeXml(title)}</text>
    <text x="${x + 150}" y="${y + 65}" text-anchor="middle" font-size="16" fill="#4B5563">${escapeXml(sub)}</text>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#43616B"/>
    </marker>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#EEF7F8"/>
      <stop offset="1" stop-color="#FFF7ED"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="1200" height="470" rx="24" fill="url(#bg)"/>
  <text x="600" y="52" text-anchor="middle" font-size="30" font-weight="800" fill="#173B45">Knowledge Manager 知识流转与按需加载路径</text>
  ${boxSvg}
  ${arrows}
  <line x1="872" y1="190" x2="872" y2="288" stroke="#43616B" stroke-width="3" stroke-dasharray="7 7" marker-end="url(#arrow)"/>
  ${rowSvg}
  <text x="600" y="435" text-anchor="middle" font-size="15" fill="#64748B">知识先经过 staging 与人工审核，再以 JSON/index 服务给 CLI 和 MCP；运行时按任务加载模块，而非整库注入。</text>
</svg>`;
}

function fig2Svg() {
  const actors = [
    ["AI client", 190],
    ["MCP server", 600],
    ["Knowledge base", 1010],
  ];
  const steps = [
    ["1. read knowledge://index", 100, 190, 600, "right"],
    ["2. return index/categories", 600, 245, 190, "left"],
    ["3. search_modules(query)", 190, 300, 600, "right"],
    ["4. candidate modules", 600, 355, 190, "left"],
    ["5. load_module(module_id)", 190, 410, 600, "right"],
    ["6. selected structured module", 600, 465, 190, "left"],
  ];
  const actorSvg = actors.map(([name, x]) => `
    <rect x="${x - 100}" y="72" width="200" height="52" rx="14" fill="#F8FAFC" stroke="#2F6F73" stroke-width="2"/>
    <text x="${x}" y="106" text-anchor="middle" font-size="22" font-weight="700" fill="#173B45">${escapeXml(name)}</text>
    <line x1="${x}" y1="124" x2="${x}" y2="520" stroke="#94A3B8" stroke-width="2" stroke-dasharray="8 8"/>`).join("");
  const stepSvg = steps.map(([label, from, y, to, dir]) => {
    const start = dir === "right" ? from + 14 : from - 14;
    const end = dir === "right" ? to - 14 : to + 14;
    const textX = (start + end) / 2;
    const marker = dir === "right" ? "url(#arrowRight)" : "url(#arrowLeft)";
    return `
      <line x1="${start}" y1="${y}" x2="${end}" y2="${y}" stroke="#43616B" stroke-width="3" marker-end="${marker}"/>
      <rect x="${textX - 145}" y="${y - 29}" width="290" height="28" rx="8" fill="#FFFFFF" opacity="0.94"/>
      <text x="${textX}" y="${y - 9}" text-anchor="middle" font-size="16" fill="#334155">${escapeXml(label)}</text>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="580" viewBox="0 0 1200 580">
  <defs>
    <marker id="arrowRight" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#43616B"/>
    </marker>
    <marker id="arrowLeft" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M9,0 L9,6 L0,3 z" fill="#43616B"/>
    </marker>
    <linearGradient id="bg2" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#F0F9FF"/>
      <stop offset="1" stop-color="#FFF7ED"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="1200" height="580" rx="24" fill="url(#bg2)"/>
  <text x="600" y="45" text-anchor="middle" font-size="30" font-weight="800" fill="#173B45">MCP 按需加载序列示意</text>
  ${actorSvg}
  ${stepSvg}
  <rect x="805" y="170" width="290" height="325" rx="18" fill="#FFFFFF" stroke="#B66A2C" stroke-width="2" opacity="0.92"/>
  <text x="950" y="210" text-anchor="middle" font-size="22" font-weight="700" fill="#B66A2C">模块化知识对象</text>
  <text x="950" y="255" text-anchor="middle" font-size="17" fill="#4B5563">overview</text>
  <text x="950" y="295" text-anchor="middle" font-size="17" fill="#4B5563">details</text>
  <text x="950" y="335" text-anchor="middle" font-size="17" fill="#4B5563">examples</text>
  <text x="950" y="375" text-anchor="middle" font-size="17" fill="#4B5563">references</text>
  <text x="950" y="415" text-anchor="middle" font-size="17" fill="#4B5563">caveats</text>
  <text x="600" y="545" text-anchor="middle" font-size="15" fill="#64748B">客户端先看索引与候选模块，再加载具体模块；协议路径本身不替代知识审核和安全治理。</text>
</svg>`;
}

const figFiles = {
  "图 1": saveSvg("knowledge-manager-fig1-architecture.svg", fig1Svg()),
  "图 2": saveSvg("knowledge-manager-fig2-mcp-sequence.svg", fig2Svg()),
};

async function ensurePngFigures() {
  await Promise.all(Object.values(figFiles).map((svgPath) => {
    const pngPath = svgPath.replace(/\.svg$/i, ".png");
    return sharp(svgPath).png().toFile(pngPath);
  }));
}

function spacing(before = 80, after = 120) {
  return { before, after, line: 360 };
}

function textRun(text, options = {}) {
  return new TextRun({
    text,
    font: options.font || fontCn,
    size: options.size || 21,
    bold: options.bold,
    italics: options.italics,
    color: options.color || "111827",
  });
}

function inlineRuns(text, options = {}) {
  const runs = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  for (const match of text.matchAll(regex)) {
    if (match.index > last) {
      runs.push(textRun(text.slice(last, match.index), options));
    }
    const token = match[0];
    if (token.startsWith("`")) {
      runs.push(textRun(token.slice(1, -1), {
        ...options,
        font: fontCode,
        color: "374151",
        size: Math.max((options.size || 21) - 1, 18),
      }));
    } else {
      runs.push(textRun(token.slice(2, -2), { ...options, bold: true }));
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    runs.push(textRun(text.slice(last), options));
  }
  return runs.length ? runs : [textRun("", options)];
}

function paragraph(text, options = {}) {
  return new Paragraph({
    children: inlineRuns(text, options),
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: spacing(options.before ?? 60, options.after ?? 100),
    indent: options.noIndent ? undefined : { firstLine: 420 },
  });
}

function caption(text) {
  return new Paragraph({
    children: inlineRuns(text.replace(/^\*\*|\*\*$/g, ""), { size: 20, bold: true, color: blue }),
    alignment: AlignmentType.CENTER,
    spacing: spacing(180, 80),
  });
}

function codeParagraph(lines) {
  return new Paragraph({
    children: [textRun(lines.join("\n"), { font: fontCode, size: 18, color: "334155" })],
    spacing: spacing(80, 120),
    shading: { fill: "F8FAFC", type: ShadingType.CLEAR },
    border: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "CBD5E1" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "CBD5E1" },
      left: { style: BorderStyle.SINGLE, size: 2, color: "CBD5E1" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "CBD5E1" },
    },
  });
}

function splitTableLine(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function markdownTable(lines) {
  const rows = lines
    .filter((line) => !/^\|\s*:?-{3,}:?/.test(line.trim()))
    .map(splitTableLine);
  if (!rows.length) return null;
  const cols = Math.max(...rows.map((row) => row.length));
  const colWidth = Math.floor(contentWidth / cols);
  const widths = Array.from({ length: cols }, (_, i) => i === cols - 1 ? contentWidth - colWidth * (cols - 1) : colWidth);
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CBD5E1" };
  return new Table({
    width: { size: contentWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((row, rIdx) => new TableRow({
      children: widths.map((width, cIdx) => new TableCell({
        width: { size: width, type: WidthType.DXA },
        shading: rIdx === 0 ? { fill: "EAF4F6", type: ShadingType.CLEAR } : undefined,
        borders: { top: border, bottom: border, left: border, right: border },
        margins: { top: 90, bottom: 90, left: 100, right: 100 },
        children: [new Paragraph({
          children: inlineRuns(row[cIdx] || "", {
            size: rIdx === 0 ? 19 : 18,
            bold: rIdx === 0,
            color: rIdx === 0 ? blue : "111827",
          }),
          alignment: rIdx === 0 ? AlignmentType.CENTER : AlignmentType.LEFT,
          spacing: { before: 0, after: 0, line: 300 },
        })],
      })),
    })),
  });
}

function imageParagraph(file, title, width, height) {
  const pngFile = file.replace(/\.svg$/i, ".png");
  return new Paragraph({
    children: [new ImageRun({
      type: "png",
      data: fs.readFileSync(pngFile),
      transformation: { width, height },
      altText: { title, description: title, name: title },
    })],
    alignment: AlignmentType.CENTER,
    spacing: spacing(40, 120),
  });
}

function heading(text, level) {
  if (level === 0) {
    return new Paragraph({
      children: [textRun(text, { font: fontHead, size: 34, bold: true, color: blue })],
      alignment: AlignmentType.CENTER,
      spacing: spacing(0, 260),
    });
  }
  return new Paragraph({
    heading: level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    children: [textRun(text, {
      font: fontHead,
      size: level === 1 ? 28 : 24,
      bold: true,
      color: level === 1 ? blue : teal,
    })],
    spacing: spacing(level === 1 ? 240 : 160, 120),
  });
}

async function main() {
await ensurePngFigures();

const children = [];
const lines = md.split("\n");
let i = 0;
let inCode = false;
let codeLines = [];
let skipFigureFence = false;

while (i < lines.length) {
  const raw = lines[i];
  const line = raw.trimEnd();

  if (inCode) {
    if (line.trim().startsWith("```")) {
      inCode = false;
      if (!skipFigureFence) children.push(codeParagraph(codeLines));
      codeLines = [];
      skipFigureFence = false;
    } else {
      codeLines.push(raw);
    }
    i += 1;
    continue;
  }

  if (!line.trim()) {
    i += 1;
    continue;
  }

  if (line.trim().startsWith("```")) {
    inCode = true;
    codeLines = [];
    i += 1;
    continue;
  }

  if (line.startsWith("|")) {
    const tableLines = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      tableLines.push(lines[i]);
      i += 1;
    }
    const table = markdownTable(tableLines);
    if (table) {
      children.push(table);
      children.push(new Paragraph({ children: [textRun("")], spacing: spacing(80, 120) }));
    }
    continue;
  }

  if (line.startsWith("# ")) {
    children.push(heading(line.replace(/^#\s+/, ""), 0));
    i += 1;
    continue;
  }
  if (line.startsWith("## ")) {
    children.push(heading(line.replace(/^##\s+/, ""), 1));
    i += 1;
    continue;
  }
  if (line.startsWith("### ")) {
    children.push(heading(line.replace(/^###\s+/, ""), 2));
    i += 1;
    continue;
  }

  if (/^\*\*图\s+[12]/.test(line.trim())) {
    const text = line.trim().replace(/^\*\*/, "").replace(/\*\*$/, "");
    children.push(caption(line.trim()));
    const key = text.startsWith("图 1") ? "图 1" : "图 2";
    children.push(imageParagraph(figFiles[key], text, 560, key === "图 1" ? 220 : 270));
    skipFigureFence = true;
    i += 1;
    continue;
  }

  if (/^\*\*表\s+\d+/.test(line.trim())) {
    children.push(caption(line.trim()));
    i += 1;
    continue;
  }

  if (line.startsWith("**关键词**")) {
    children.push(paragraph(line, { noIndent: true, alignment: AlignmentType.LEFT }));
    i += 1;
    continue;
  }

  if (/^\[\d+\]/.test(line.trim())) {
    children.push(new Paragraph({
      children: inlineRuns(line.trim(), { size: 18, color: "1F2937" }),
      alignment: AlignmentType.LEFT,
      spacing: spacing(20, 80),
      indent: { hanging: 360, left: 360 },
    }));
    i += 1;
    continue;
  }

  children.push(paragraph(line.trim()));
  i += 1;
}

const doc = new Document({
  creator: "Codex",
  title: "面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统",
  description: "Knowledge Manager 中文投稿型 Word 初稿",
  styles: {
    default: {
      document: {
        run: { font: fontCn, size: 21 },
        paragraph: { spacing: { line: 360 } },
      },
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 28, bold: true, font: fontHead, color: blue },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 24, bold: true, font: fontHead, color: teal },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 },
      },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: pageWidth, height: pageHeight }, margin },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            textRun("第 ", { size: 18, color: gray }),
            new TextRun({ children: [PageNumber.CURRENT], font: fontCn, size: 18, color: gray }),
            textRun(" 页", { size: 18, color: gray }),
          ],
        })],
      }),
    },
    children,
  }],
});

const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buffer);
  console.log(outPath);
  console.log(figFiles["图 1"]);
  console.log(figFiles["图 2"]);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
