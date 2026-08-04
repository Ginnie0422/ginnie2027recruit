import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const projectDir = path.resolve(path.dirname(__filename), "..");
const outputDir = path.join(projectDir, "outputs");
const trackerPath = path.join(outputDir, "job_tracker.html");
const outPath = path.join(outputDir, "matched_jobs_summary.xlsx");

const priorityLabels = {
  high: "高匹配",
  sprint: "高匹配/冲刺",
  normal: "可投备选",
  low: "低意向备查",
};

function extractSeedJobs(html) {
  const start = html.indexOf("const SEED_JOBS = [");
  const end = html.indexOf("];", start);
  if (start < 0 || end < 0) {
    throw new Error("SEED_JOBS not found");
  }
  Function(html.slice(start, end + 2).replace("const SEED_JOBS", "globalThis.SEED_JOBS"))();
  return globalThis.SEED_JOBS;
}

function normalizeDate(value) {
  return String(value || "").trim();
}

function rowForJob(job) {
  return [
    priorityLabels[job.priority] || "可投备选",
    job.company || "",
    job.role || "",
    job.location || "待确认",
    normalizeDate(job.sourceDate),
    normalizeDate(job.deadline) || "未标注",
    job.reason || "",
    job.url || "",
  ];
}

function countsByPriority(jobs) {
  const counts = { high: 0, sprint: 0, normal: 0, low: 0 };
  for (const job of jobs) {
    counts[job.priority] = (counts[job.priority] || 0) + 1;
  }
  return counts;
}

function writeSheet(sheet, rows) {
  const range = sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length);
  range.values = rows;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  sheet.getRangeByIndexes(0, 0, 1, rows[0].length).format.fill.color = "#EAF5F0";
  sheet.getRangeByIndexes(0, 0, 1, rows[0].length).format.font.bold = true;
  sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length).format.borders = {
    preset: "inside",
    style: "thin",
    color: "#E2E8F0",
  };
  sheet.getRange("A:A").format.columnWidth = 14;
  sheet.getRange("B:B").format.columnWidth = 24;
  sheet.getRange("C:C").format.columnWidth = 44;
  sheet.getRange("D:D").format.columnWidth = 28;
  sheet.getRange("E:F").format.columnWidth = 14;
  sheet.getRange("G:G").format.columnWidth = 48;
  sheet.getRange("H:H").format.columnWidth = 54;
  sheet.getRangeByIndexes(1, 2, Math.max(rows.length - 1, 1), 6).format.wrapText = true;
}

const html = await fs.readFile(trackerPath, "utf8");
const jobs = extractSeedJobs(html);
const headers = ["层级", "公司", "岗位", "地点", "更新时间", "截止时间", "匹配理由", "投递链接"];
const allRows = [headers, ...jobs.map(rowForJob)];
const topRows = [
  headers,
  ...jobs.filter((job) => ["high", "sprint"].includes(job.priority)).map(rowForJob),
];
const counts = countsByPriority(jobs);

const workbook = Workbook.create();
const summary = workbook.worksheets.add("汇总");
const all = workbook.worksheets.add("匹配岗位");
const top = workbook.worksheets.add("高匹配");

summary.showGridLines = false;
summary.getRange("A1:H1").merge();
summary.getRange("A1").values = [["金锦钰校招匹配岗位汇总"]];
summary.getRange("A1").format.font.bold = true;
summary.getRange("A1").format.font.size = 16;
summary.getRange("A1").format.fill.color = "#EAF5F0";
summary.getRange("A3:B10").values = [
  ["数据来源", "腾讯文档 2027届校招信息汇总表"],
  ["网站数据库岗位数", jobs.length],
  ["高匹配", counts.high + counts.sprint],
  ["可投备选", counts.normal],
  ["低意向备查", counts.low],
  ["表格行数", (html.match(/id=\"sourceRows\">(\d+)/) || [])[1] || ""],
  ["生成时间", new Date().toISOString().slice(0, 10)],
  ["说明", "新增岗位默认不进入看板，可在网页优选池中选择待动作或今日优先。"],
];
summary.getRange("A3:A10").format.font.bold = true;
summary.getRange("A3:B10").format.borders = { preset: "inside", style: "thin", color: "#E2E8F0" };
summary.getRange("A:A").format.columnWidth = 18;
summary.getRange("B:B").format.columnWidth = 72;
summary.getRange("B10").format.wrapText = true;

writeSheet(all, allRows);
writeSheet(top, topRows);

await fs.mkdir(outputDir, { recursive: true });
const rendered = await workbook.render({ sheetName: "汇总", range: "A1:B10", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "matched_jobs_summary_preview.png"), new Uint8Array(await rendered.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outPath);

const overview = await workbook.inspect({
  kind: "sheet,table",
  tableMaxRows: 8,
  tableMaxCols: 8,
  maxChars: 4000,
});
console.log(overview.ndjson);
console.log(JSON.stringify({ output: outPath, rows: jobs.length, high: counts.high + counts.sprint }));
