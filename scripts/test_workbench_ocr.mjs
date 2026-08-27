import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync("outputs/daily_application_workbench.html", "utf8");
const script = html.slice(html.indexOf("<script>") + 8, html.indexOf("</script>"));

function declaration(name) {
  const start = script.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} not found`);
  const body = script.indexOf("{", start);
  let depth = 0;
  for (let i = body; i < script.length; i += 1) {
    if (script[i] === "{") depth += 1;
    if (script[i] === "}") depth -= 1;
    if (depth === 0) return script.slice(start, i + 1);
  }
  throw new Error(`${name} is incomplete`);
}

const registryStart = script.indexOf("const OFFICIAL_RECRUITMENT_REGISTRY=");
const registryEnd = script.indexOf("function officialKey", registryStart);
const registry = script.slice(registryStart, registryEnd);
const roleGood = script.match(/const ROLE_GOOD=([^;]+);/)[0];
const source = [
  roleGood,
  registry,
  declaration("officialKey"),
  declaration("findOfficialRecruitment"),
  declaration("validCompany"),
  declaration("cleanOcrCell"),
  declaration("ocrDateToken"),
  declaration("ocrCompactOpeningDate"),
  declaration("ocrOpeningDate"),
  declaration("ocrDeadline"),
  declaration("campaignCompany"),
  declaration("parseOcrRows"),
  "return parseOcrRows;",
].join("\n");
const parseOcrRows = Function(source)();

const sample = `校招就应该投新兴行业（8月25日）
#具身智能
1. 曦诺未来2027届校园招聘全球启动｜8.22开启（具身智能）
2. 穹彻智能校园招聘｜8.20开启（具身智能）
3. 零次方机器人全球校园招聘正式启动｜8.20开启（具身智能）
4. 迈睿机器人2027届招新正式启动！｜8.20开启（具身智能）
5. 优必选2027届校园招聘正式启动！｜8.19开启（具身智能）
6. 启元机器人2027届校园招聘启动！｜8.19开启（具身智能）
7. 临界点 2027 校园招聘正式启动｜8.19开启（具身智能）
8. 西湖机器人2027校园招聘全面启动！｜8.18开启（具身智能）
#AI相关
1. 数 字 绿 土 2027届AI校园招聘正式启动｜8.20开启（AI相关）
2. 万兴科技2027届全球校招正式启动！｜8.18开启（AI相关）
3. 上海宜氪数据2027校园招聘简章｜8.17开启（AI相关）
4. 届 Manifold Al 校园招聘正式启动｜8.17开启（AI相关）
5. 科大讯飞招募｜8.12开启（AI相关）
6. MiniMax招聘｜728开启（AI相关）
7 移动九天 Al 招募｜7287/8（AI相关）
8. 智源研究院2027届校园招聘｜727开启（AI相关）
#自动驾驶
1. 轻舟智航2027校园招聘正式启动！｜8.17开启（自动驾驶）
2. 经纬恒润2027校园招聘正式启航｜8.17开启（自动驾驶）
3. Momenta 2027届秋招正式开启！｜731开启（自动驾驶）`;

const rows = parseOcrRows(sample);
assert.equal(rows.length, 19);
assert(rows.every(row => !/^\d/.test(row.company)), "company contains an ordinal");
assert(rows.every(row => row.role === ""), "campaign announcement fabricated a role");
assert(rows.every(row => row.openingDate && !row.deadline), "opening date was treated as deadline");
assert.equal(rows.find(row => row.company === "数字绿土")?.openingDate, "8.20");
assert.equal(rows.find(row => row.company === "Manifold AI")?.officialVerified, true);
assert.equal(rows.filter(row => row.officialVerified).length, 17);

console.log("workbench OCR parser regression OK: 19 companies, 17 official portals");
