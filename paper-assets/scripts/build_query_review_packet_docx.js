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

const root = "D:\\tyh";
const sourcePath = path.join(root, "paper-assets", "eval", "judged-queries.author-review.json");
const outDir = path.join(root, "paper-assets", "deliverables");
const outPath = path.join(outDir, "knowledge-manager-query-review-packet.docx");

fs.mkdirSync(outDir, { recursive: true });

const payload = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
const rows = payload.rows || [];

const pageWidth = 11906;
const pageHeight = 16838;
const margin = { top: 1440, right: 1260, bottom: 1440, left: 1260 };
const contentWidth = pageWidth - margin.left - margin.right;
const fontCn = "SimSun";
const fontHead = "Microsoft YaHei";
const blue = "234D63";
const teal = "2F6F73";
const gray = "6B7280";

function run(text, options = {}) {
  return new TextRun({
    text: String(text || ""),
    font: options.font || fontCn,
    size: options.size || 20,
    bold: options.bold,
    color: options.color || "111827",
  });
}

function para(text, options = {}) {
  return new Paragraph({
    children: [run(text, options)],
    alignment: options.alignment || AlignmentType.LEFT,
    spacing: { before: options.before ?? 40, after: options.after ?? 80, line: 320 },
  });
}

function heading(text, level) {
  return new Paragraph({
    heading: level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    children: [run(text, {
      font: fontHead,
      size: level === 1 ? 28 : 23,
      bold: true,
      color: level === 1 ? blue : teal,
    })],
    spacing: { before: level === 1 ? 220 : 150, after: 100, line: 320 },
  });
}

function cell(text, width, shaded = false) {
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CBD5E1" };
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shaded ? { fill: "EAF4F6", type: ShadingType.CLEAR } : undefined,
    borders: { top: border, bottom: border, left: border, right: border },
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({
      children: [run(text, { size: shaded ? 19 : 18, bold: shaded, color: shaded ? blue : "111827" })],
      spacing: { before: 0, after: 0, line: 280 },
    })],
  });
}

function twoColTable(pairs) {
  const keyWidth = 2500;
  const valueWidth = contentWidth - keyWidth;
  return new Table({
    width: { size: contentWidth, type: WidthType.DXA },
    columnWidths: [keyWidth, valueWidth],
    rows: pairs.map(([key, value]) => new TableRow({
      children: [
        cell(key, keyWidth, true),
        cell(value, valueWidth, false),
      ],
    })),
  });
}

const children = [
  new Paragraph({
    children: [run("Knowledge Manager judged queries 作者审阅包", {
      font: fontHead,
      size: 32,
      bold: true,
      color: blue,
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 220, line: 360 },
  }),
  para("用途：本文件用于逐条确认 candidate judged queries。它不是实验结果，也不能替代正式 baseline 结果表。", { size: 20 }),
  para("填写建议：author_decision 可填写 accept、revise、exclude 或 needs_discussion；如需修改模块标签，请在 author_corrected_required_modules 中写明。", { size: 20 }),
  heading("汇总", 1),
  twoColTable([
    ["待审阅 query", String(rows.length)],
    ["当前状态", "candidate_needs_author_review"],
    ["进入主实验条件", "全部 query 至少更新为 author_labeled；如有二次核对，可更新为 double_checked。"],
  ]),
];

rows.forEach((row, index) => {
  children.push(heading(`${index + 1}. ${row.query_id}`, 2));
  children.push(twoColTable([
    ["corpus_id", row.corpus_id],
    ["query", row.query],
    ["task/scope/difficulty", `${row.task_type} / ${row.scope_type} / ${row.difficulty}`],
    ["required_modules", row.required_modules],
    ["module titles", row.required_module_titles],
    ["nice_to_have", row.nice_to_have_modules],
    ["boundary expected", `${row.should_refuse_or_boundary_note}; ${row.expected_boundary}`],
    ["evidence span", row.gold_evidence_spans],
    ["judge_notes", row.judge_notes],
    ["author_decision", ""],
    ["author_corrected_required_modules", ""],
    ["author_boundary_revision", ""],
    ["author_notes", ""],
  ]));
});

const doc = new Document({
  creator: "Codex",
  title: "Knowledge Manager judged queries 作者审阅包",
  description: "Author review packet for candidate judged queries",
  styles: {
    default: { document: { run: { font: fontCn, size: 20 } } },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 28, bold: true, font: fontHead, color: blue },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 23, bold: true, font: fontHead, color: teal },
        paragraph: { spacing: { before: 150, after: 100 }, outlineLevel: 1 },
      },
    ],
  },
  sections: [{
    properties: { page: { size: { width: pageWidth, height: pageHeight }, margin } },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            run("第 ", { size: 18, color: gray }),
            new TextRun({ children: [PageNumber.CURRENT], font: fontCn, size: 18, color: gray }),
            run(" 页", { size: 18, color: gray }),
          ],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outPath, buffer);
  console.log(outPath);
});
