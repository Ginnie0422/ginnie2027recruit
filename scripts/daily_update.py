#!/usr/bin/env python3
"""
Daily local updater for the campus recruitment tracker.

This script is designed to run from the user's Mac via launchd, not from the
Codex sandbox. It uses only Python standard-library modules so launchd can run
it without a virtualenv.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zlib
from pathlib import Path


MAX_AUTO_ADD = 80
PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "outputs"
WORK_DIR = PROJECT_DIR / "work"
LOG_DIR = PROJECT_DIR / "logs"
JOB_TRACKER = OUTPUT_DIR / "job_tracker.html"
RECOMMENDED = OUTPUT_DIR / "recommended_jobs.md"
CHANGELOG = PROJECT_DIR / "CHANGELOG.md"

DOC_ID = "DQUNxdHRXcndkeHFK"
TAB_ID = "986nx3"
DOC_URL = f"https://docs.qq.com/sheet/{DOC_ID}?tab={TAB_ID}"
OPENDOC_URL = "https://docs.qq.com/dop-api/opendoc"

HEADERS = [
    "公司名称",
    "行业大类",
    "企业性质",
    "批次",
    "招聘岗位",
    "工作地点",
    "招聘对象",
    "更新时间",
    "截止时间",
    "网申状态",
    "官方公告",
    "投递方式",
    "内推码/备注",
]

POSITIVE_HIGH = [
    "市场营销", "数字营销", "品牌", "活动营销", "渠道", "内容", "新媒体", "增长",
    "商业化", "产品运营", "用户运营", "海外", "出海", "AI产品", "AI 产品",
    "产品经理", "用户研究", "客户成功", "商务拓展", "BD", "管培", "战略",
    "咨询", "商业分析", "新零售", "SaaS", "Agent", "AIGC", "RAG",
    "开发者生态", "解决方案", "生态合作", "TikTok", "电商营销",
]
POSITIVE_NORMAL = [
    "运营", "产品", "市场", "营销", "销售", "商务", "项目管理", "策划", "管培生",
    "数据分析", "行业研究", "投资研究", "客户", "交付", "企划",
]
TECH_HEAVY = [
    "算法", "研发", "硬件", "芯片", "嵌入式", "机械", "电气", "工艺",
    "后端", "前端", "测试工程师", "材料", "结构", "量化开发",
]
EXCLUDE_ONLY = ["开放日", "宣讲会", "空中宣讲", "暑期实习", "寒暑假实习", "暑期助理顾问实习生", "Summer Intern", "Summer Internship"]
CITY_WORDS = [
    "北京", "上海", "深圳", "广州", "杭州", "南京", "苏州", "成都", "武汉", "西安",
    "重庆", "天津", "厦门", "青岛", "佛山", "合肥", "昆山", "固安", "香港", "海外",
    "全国", "长沙", "宁波", "无锡", "福州", "珠海", "东莞", "郑州", "济南",
]
COMPANY_NOISE_SUFFIXES = [
    "免费", "班车", "住宿", "食宿", "三餐", "公寓", "薪资", "薪酬", "福利", "代租",
    "实习", "岗位", "计划", "项目", "通道", "专场", "中心", "分校", "部门", "营销服",
    "校招", "秋招", "春招", "早鸟", "管培", "培训生", "Intern", "intern",
]
BAD_COMPANY_MARKERS = [
    "投递", "报名", "查看", "点击", "官方公告", "内推", "公众号", "链接", "网址", "扫码",
    "选择Internship", "实习生计划", "寒暑假实习", "暑期实习", "暑期助理", "Summer Intern",
    "Summer Internship",
]


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    log("$ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def fetch_text(url: str, opener: urllib.request.OpenerDirector, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Referer": DOC_URL,
            "Accept": "*/*",
        },
    )
    with opener.open(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def parse_jsonp(text: str) -> dict:
    text = text.strip()
    start = text.find("(")
    end = text.rfind(")")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("opendoc response is not JSONP")
    return json.loads(text[start + 1:end])


def unpack_blob(value: str) -> bytes:
    raw = base64.b64decode(value)
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return zlib.decompress(raw, -zlib.MAX_WBITS)


def get_initial_text(doc: dict) -> dict:
    return doc["clientVars"]["collab_client_vars"]["initialAttributedText"]["text"][0]


def opendoc_url(start_row: int, end_row: int, max_col: int) -> str:
    params = {
        "tab": TAB_ID,
        "u": "",
        "noEscape": "1",
        "enableSmartsheetSplit": "1",
        "needSheetState": "1",
        "sliceStates": "1",
        "block_end_col": str(max_col),
        "block_end_row": str(end_row),
        "block_start_col": "0",
        "block_start_row": str(start_row),
        "id": DOC_ID,
        "normal": "1",
        "outformat": "1",
        "wb": "1",
        "nowb": "0",
        "callback": "clientVarsCallback",
        "xsrf": "",
        "t": str(int(time.time() * 1000)),
    }
    return OPENDOC_URL + "?" + urllib.parse.urlencode(params)


def fetch_opendocs(use_cache: bool) -> tuple[list[dict], dict]:
    WORK_DIR.mkdir(exist_ok=True)
    if use_cache:
        dated: dict[str, list[Path]] = {}
        for path in WORK_DIR.glob("opendoc_*.js"):
            match = re.match(r"opendoc_(\d{4}-\d{2}-\d{2})_(\d+)_(\d+)\.js$", path.name)
            if match:
                dated.setdefault(match.group(1), []).append(path)
        files = []
        if dated:
            latest_day = max(dated)
            files = sorted(dated[latest_day], key=lambda path: int(path.name.rsplit("_", 2)[1]))
        if not files:
            files = sorted(WORK_DIR.glob("current_opendoc_*.js"))
        if not files:
            files = sorted(WORK_DIR.glob("daily2_opendoc_*.js"))
        docs = [parse_jsonp(path.read_text(encoding="utf-8")) for path in files]
        if not docs:
            raise RuntimeError("no cached opendoc files found")
        meta = get_initial_text(docs[0])
        return docs, {
            "title": docs[0].get("bodyData", {}).get("initialTitle", ""),
            "max_row": int(meta.get("maxRow") or meta.get("max_row") or 0),
            "max_col": int(meta.get("maxCol") or meta.get("max_col") or 31),
            "last_save": docs[0].get("bodyData", {}).get("lastSaveTimestamp", ""),
        }

    cookie_jar = http.cookiejar.MozillaCookieJar(str(WORK_DIR / "daily_update.cookies"))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    sheet_html = fetch_text(DOC_URL, opener)
    (WORK_DIR / f"sheet_{today()}.html").write_text(sheet_html, encoding="utf-8")
    cookie_jar.save(ignore_discard=True, ignore_expires=True)

    first_text = fetch_text(opendoc_url(0, 255, 31), opener)
    first_path = WORK_DIR / f"opendoc_{today()}_0_255.js"
    first_path.write_text(first_text, encoding="utf-8")
    first_doc = parse_jsonp(first_text)
    first_meta = get_initial_text(first_doc)
    max_row = int(first_meta.get("maxRow") or first_meta.get("max_row") or 0)
    max_col = int(first_meta.get("maxCol") or first_meta.get("max_col") or 31)
    docs = [first_doc]

    for start in range(256, max_row + 1, 256):
        end = min(start + 255, max_row)
        text = fetch_text(opendoc_url(start, end, max_col), opener)
        (WORK_DIR / f"opendoc_{today()}_{start}_{end}.js").write_text(text, encoding="utf-8")
        docs.append(parse_jsonp(text))

    return docs, {
        "title": first_doc.get("bodyData", {}).get("initialTitle", ""),
        "max_row": max_row,
        "max_col": max_col,
        "last_save": first_doc.get("bodyData", {}).get("lastSaveTimestamp", ""),
    }


def clean_piece(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = text.strip(" \t\r\n\"'“”")
    text = re.sub(r"\s+", " ", text)
    if len(text) >= 2 and re.match(r"^[A-Za-z0-9$#%&*+,.?/<>@:_-][\u4e00-\u9fff]", text):
        text = text[1:].strip()
    return text


def is_noise(text: str) -> bool:
    if not text or len(text) <= 1:
        return True
    if text in {"986nx3", "27秋招", "Microsoft YaHei", "宋体", "黑体", "Calibri"}:
        return True
    if re.fullmatch(r"[A-F0-9]{6,8}", text):
        return True
    if re.fullmatch(r"[0-9A-Za-z:;@*+\\/\- ]{1,12}", text) and not re.search(r"20\d{2}", text):
        return True
    if any(font in text for font in ["Times New Roman", "Microsoft YaHei", "Calibri", "宋体", "黑体"]):
        return True
    return False


def extract_tokens_and_urls(docs: list[dict]) -> tuple[list[str], list[str]]:
    tokens: list[str] = []
    urls: list[str] = []
    for doc in docs:
        text = get_initial_text(doc)
        blocks = text.get("block_datas", [])
        if not blocks and text.get("related_sheet"):
            blocks = [text]
        for block in blocks:
            value = block.get("related_sheet")
            if not value:
                continue
            raw = unpack_blob(value)
            for match in re.finditer(rb"https?://[^\x00-\x20\"<>\\]+", raw):
                url = match.group(0).decode("utf-8", "ignore").rstrip("),.;")
                if url not in urls:
                    urls.append(url)
            for match in re.finditer(rb"[\x09\x0a\x0d\x20-\x7e\x80-\xff]{1,}", raw):
                try:
                    item = match.group(0).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                for piece in re.split(r"[\n\r]+", item):
                    piece = clean_piece(piece)
                    if piece and not is_noise(piece) and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", piece):
                        tokens.append(piece)
    return tokens, urls


def load_previous_tokens(current_day: str) -> list[str]:
    dated: dict[str, list[Path]] = {}
    for path in WORK_DIR.glob("opendoc_*.js"):
        match = re.match(r"opendoc_(\d{4}-\d{2}-\d{2})_(\d+)_(\d+)\.js$", path.name)
        if match and match.group(1) < current_day:
            dated.setdefault(match.group(1), []).append(path)
    if not dated:
        return []
    previous_day = max(dated)
    files = sorted(dated[previous_day], key=lambda path: int(path.name.rsplit("_", 2)[1]))
    docs = [parse_jsonp(path.read_text(encoding="utf-8")) for path in files]
    tokens, _ = extract_tokens_and_urls(docs)
    return tokens


def table_data_start(tokens: list[str]) -> int | None:
    try:
        header = tokens.index("公司名称")
        return tokens.index("内推码/备注", header) + 1
    except ValueError:
        return None


def new_table_tokens(tokens: list[str], previous_tokens: list[str]) -> list[str] | None:
    current_start = table_data_start(tokens)
    previous_start = table_data_start(previous_tokens)
    if current_start is None or previous_start is None or previous_start >= len(previous_tokens):
        return None
    previous_first_company = previous_tokens[previous_start]
    try:
        previous_anchor = tokens.index(previous_first_company, current_start)
    except ValueError:
        return None
    return tokens[current_start:previous_anchor]


def latest_source_date(tokens: list[str]) -> str:
    dates = []
    for item in tokens:
        match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", item)
        if not match:
            continue
        try:
            value = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if value <= dt.date.today():
            dates.append(value)
    return max(dates).isoformat() if dates else today()


def looks_like_date(text: str) -> bool:
    return bool(re.search(r"20\d{2}[./年-]\d{1,2}([./月-]\d{1,2})?", text))


def parse_deadline(text: str) -> dt.date | None:
    match = re.search(r"(20\d{2})[./年-](\d{1,2})(?:[./月-](\d{1,2}))?", text or "")
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3) or 1)
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def is_expired(deadline: str) -> bool:
    parsed = parse_deadline(deadline)
    return bool(parsed and parsed < dt.date.today())


def has_any(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def is_location(text: str) -> bool:
    return any(city in text for city in CITY_WORDS) and len(text) <= 120


def is_non_company(text: str) -> bool:
    if looks_like_date(text) or is_location(text):
        return True
    bad = [
        "本科", "硕士", "博士", "招聘中", "招满即止", "民营企业", "央国企", "外企", "事业单位",
        "提前批", "秋招", "校招", "实习", "根据意向", "投递网页", "官方公告", "点击查看",
    ]
    if any(item in text for item in bad):
        return True
    role_markers = [
        "工程师", "经理", "助理", "岗位", "方向", "专业", "计划", "序列", "教师",
        "研发", "算法", "软件", "硬件", "产品类", "市场类", "运营类", "职能类",
        "技术类", "管理类", "销售类", "测试", "设计", "管培生",
    ]
    if any(item in text for item in role_markers):
        return True
    if "/" in text and len(text) > 12:
        return True
    return False


def looks_company_like(text: str) -> bool:
    text = clean_piece(text)
    if not text or len(text) < 2 or len(text) > 80:
        return False
    if looks_like_date(text) or is_location(text):
        return False
    if any(marker.lower() in text.lower() for marker in BAD_COMPANY_MARKERS):
        return False
    return not is_non_company(text)


def clean_company_name(text: str) -> str:
    text = clean_piece(text)
    text = text.lstrip("+-•·").strip()
    if not text:
        return ""

    for sep in ["，", ",", "｜", "|", "、", "；", ";"]:
        if sep in text:
            left, right = text.split(sep, 1)
            right_text = right.strip()
            if left and looks_company_like(left) and (
                any(marker.lower() in right_text.lower() for marker in COMPANY_NOISE_SUFFIXES)
                or looks_like_date(right_text)
                or is_location(right_text)
            ):
                text = left.strip()
                break

    if " " in text:
        first, rest = text.split(" ", 1)
        rest_text = rest.strip()
        if first and looks_company_like(first) and (
            any(marker.lower() in rest_text.lower() for marker in COMPANY_NOISE_SUFFIXES)
            or looks_like_date(rest_text)
            or is_location(rest_text)
        ):
            text = first.strip()

    if "-" in text:
        left, right = text.split("-", 1)
        right_text = right.strip()
        if left and looks_company_like(left) and (
            any(marker.lower() in right_text.lower() for marker in COMPANY_NOISE_SUFFIXES)
            or looks_like_date(right_text)
            or is_location(right_text)
        ):
            text = left.strip()

    return clean_piece(text)


def is_industry_like(text: str) -> bool:
    industry_markers = ["互联网", "金融", "电子", "芯片", "汽车", "制造", "教育", "咨询", "能源", "医药", "游戏", "电商"]
    return "/" in text or any(item in text for item in industry_markers) and len(text) <= 120


def is_role_like(text: str) -> bool:
    if len(text) < 4 or len(text) > 360:
        return False
    if looks_like_date(text) or is_location(text):
        return False
    role_words = POSITIVE_HIGH + POSITIVE_NORMAL + TECH_HEAVY + ["工程师", "岗位", "方向", "类"]
    return has_any(text, role_words)


def is_company_candidate(tokens: list[str], index: int) -> bool:
    text = tokens[index]
    if not (2 <= len(text) <= 60):
        return False
    if is_non_company(text):
        return False
    lookahead = tokens[index + 1:index + 5]
    return any(is_industry_like(item) or is_role_like(item) for item in lookahead)


def classify(company: str, role: str, context: str) -> tuple[str, str] | None:
    text = f"{company} {role}"
    if any(word in f"{text} {context}" for word in EXCLUDE_ONLY):
        return None
    if "实习" in text and "秋招" not in context and "校招" not in context and "2027届" not in context:
        return None
    if has_any(text, ["教师", "教学岗", "教研"]):
        return None
    if role.count("/") >= 5 and not has_any(role, ["岗位", "经理", "管培", "运营", "营销", "产品"]):
        return None

    high_hits = [word for word in POSITIVE_HIGH if word.lower() in text.lower()]
    normal_hits = [word for word in POSITIVE_NORMAL if word.lower() in text.lower()]
    tech_hits = [word for word in TECH_HEAVY if word.lower() in text.lower()]

    if len(tech_hits) >= 2 and not high_hits and not normal_hits:
        return None
    if len(high_hits) >= 2 or ("AI" in text and any(word in text for word in ["产品", "运营", "市场", "客户成功"])):
        return "high", "匹配 " + "、".join(high_hits[:4]) + "，适合优先检查"
    if high_hits or len(normal_hits) >= 2:
        return "normal", "包含匹配方向：" + "、".join((high_hits + normal_hits)[:4])
    if normal_hits and len(tech_hits) < 2:
        return "normal", "包含可迁移方向：" + "、".join(normal_hits[:3])
    if high_hits or normal_hits or ("AI" in text and tech_hits):
        return "low", "关键词相关但技术/职能/信息错位风险较高，放低意向备查"
    return None


def make_id(company: str, role: str, url: str) -> str:
    digest = hashlib.sha1(f"{company}|{role}".encode("utf-8")).hexdigest()[:10]
    return f"auto-{digest}"


def dedupe_key(company: str, role: str) -> str:
    normalized_company = unicodedata.normalize("NFKC", company).lower()
    normalized_role = unicodedata.normalize("NFKC", role).lower()
    normalized_company = re.sub(r"[\W_]+", "", normalized_company)
    category_terms = [
        "产品", "研发", "设计", "营销", "市场", "运营", "销售", "商务", "客户服务",
        "供应链", "生产", "制造", "物流", "职能", "质量", "管理", "管培", "策划",
    ]
    category_hits = sorted({term for term in category_terms if term in normalized_role})
    if len(category_hits) >= 3:
        normalized_role = "分类:" + ",".join(category_hits)
    normalized_role = re.sub(r"[\W_]+", "", normalized_role)
    return f"{normalized_company}|{normalized_role}"


def candidate_needs_review(company: str, role: str) -> bool:
    tech_hits = [word for word in TECH_HEAVY if word.lower() in role.lower()]
    positive_hits = [word for word in POSITIVE_HIGH + POSITIVE_NORMAL if word.lower() in role.lower()]
    if len(role) > 70 and len(tech_hits) >= 2:
        return True
    if tech_hits and set(positive_hits).issubset({"销售"}):
        return True
    if "consult" in company.lower() and not has_any(role, ["咨询", "顾问", "猎头", "运营", "市场", "营销", "商务", "产品"]):
        return True
    if "具体见" in role or "投递方式链接" in role:
        return True
    return False


def nearest_url(urls: list[str], index: int) -> str:
    return urls[index % len(urls)] if urls else DOC_URL


def build_candidates(tokens: list[str], urls: list[str], source_date: str | None = None) -> list[dict]:
    if "公司名称" in tokens:
        tokens = tokens[tokens.index("公司名称") + 1:]

    candidates: list[dict] = []
    seen: set[str] = set()
    company_indices = [index for index in range(len(tokens)) if is_company_candidate(tokens, index)]
    for pos, start in enumerate(company_indices):
        end = company_indices[pos + 1] if pos + 1 < len(company_indices) else min(len(tokens), start + 16)
        segment = tokens[start:end]
        if len(segment) < 2:
            continue
        company = clean_company_name(segment[0])
        if not looks_company_like(company):
            continue
        role = ""
        location = ""
        deadline = ""
        for item in segment[1:]:
            if not role and is_role_like(item) and not is_industry_like(item):
                role = item
            if not location and is_location(item):
                location = item
            if not deadline and (looks_like_date(item) or "招满即止" in item):
                deadline = item
        if not role:
            for item in segment[1:]:
                if is_role_like(item):
                    role = item
                    break
        if not role:
            continue
        if candidate_needs_review(company, role):
            continue
        if is_expired(deadline):
            continue
        classified = classify(company, role, " ".join(segment))
        if not classified:
            continue
        priority, reason = classified
        url = DOC_URL
        reason += "；需回原表核对链接"
        key = dedupe_key(company, role)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "id": make_id(company, role, url),
            "company": company[:80],
            "role": role[:220],
            "location": location[:120],
            "priority": priority,
            "reason": reason[:120],
            "url": url,
            "sourceDate": source_date or today(),
            "deadline": deadline[:40],
            "selected": False,
            "todayPriority": False,
            "discarded": False,
        })
    return candidates


def extract_seed_jobs(html: str) -> list[dict]:
    start = html.index("const SEED_JOBS = [") + len("const SEED_JOBS = ")
    end = html.index("];", start) + 1
    array_src = html[start:end]
    objects: list[str] = []
    depth = 0
    obj_start = None
    in_string = False
    escape = False
    for idx, char in enumerate(array_src):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                obj_start = idx
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                objects.append(array_src[obj_start:idx + 1])

    jobs = []
    fields = ["id", "company", "role", "location", "priority", "reason", "url", "sourceDate", "deadline"]
    for source in objects:
        job: dict = {}
        for field in fields:
            match = re.search(rf'(?:{field}|"({field})")\s*:\s*"((?:\\.|[^"\\])*)"', source)
            if match:
                job[field] = json.loads('"' + match.group(2) + '"')
        for field in ["selected", "todayPriority", "discarded"]:
            match = re.search(rf'(?:{field}|"({field})")\s*:\s*(true|false)', source)
            job[field] = match.group(2) == "true" if match else False
        if "id" in job and "company" in job and "role" in job:
            jobs.append(job)
    return jobs


def merge_jobs(existing: list[dict], candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    by_id = {job["id"]: job for job in existing}
    dedupe = {dedupe_key(job.get("company", ""), job.get("role", "")) for job in existing}
    added = []
    for candidate in candidates:
        key = dedupe_key(candidate["company"], candidate["role"])
        if candidate["id"] in by_id or key in dedupe:
            continue
        by_id[candidate["id"]] = candidate
        existing.append(candidate)
        dedupe.add(key)
        added.append(candidate)
    return existing, added


def js_string(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_seed_jobs(jobs: list[dict]) -> str:
    lines = ["["]
    for index, job in enumerate(jobs):
        comma = "," if index < len(jobs) - 1 else ""
        lines.append("      {")
        keys = ["id", "company", "role", "location", "priority", "reason", "url", "sourceDate", "deadline", "selected", "todayPriority", "discarded"]
        for key_index, key in enumerate(keys):
            suffix = "," if key_index < len(keys) - 1 else ""
            lines.append(f"        {json.dumps(key)}: {js_string(job.get(key, False if key in {'selected','todayPriority','discarded'} else ''))}{suffix}")
        lines.append(f"      }}{comma}")
    lines.append("    ]")
    return "\n".join(lines)


def update_tracker(jobs: list[dict], dry_run: bool) -> None:
    html = JOB_TRACKER.read_text(encoding="utf-8")
    start = html.index("const SEED_JOBS = [") + len("const SEED_JOBS = ")
    end = html.index("];", start) + 1
    next_html = html[:start] + render_seed_jobs(jobs) + html[end:]
    if not dry_run:
        JOB_TRACKER.write_text(next_html, encoding="utf-8")


def markdown_key(line: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\[[^\]]+\]\([^)]+\)", "", line)).lower()


def update_recommended(added: list[dict], meta: dict, all_jobs: list[dict], dry_run: bool) -> None:
    text = RECOMMENDED.read_text(encoding="utf-8")
    existing_keys = {markdown_key(line) for line in text.splitlines() if line.startswith("- [")}
    visible_added = [job for job in added if job["priority"] in {"high", "sprint", "normal"}]
    lines = []
    if visible_added:
        lines.append("")
        lines.append(f"## {today()} 新增优选")
        lines.append("")
        for job in visible_added:
            line = f"- [ ] {job['company']}｜{job['role']}｜{job.get('location') or '待确认'}｜{job['reason']}｜[投递链接]({job['url']})"
            if markdown_key(line) not in existing_keys:
                lines.append(line)

    unchecked = len(re.findall(r"^- \[ \]", text, flags=re.MULTILINE))
    high = sum(1 for job in all_jobs if job.get("priority") in {"high", "sprint"})
    normal = sum(1 for job in all_jobs if job.get("priority") == "normal")
    low = sum(1 for job in all_jobs if job.get("priority") == "low")
    run_line = (
        f"- {today()}：抓取 {meta.get('title') or '腾讯文档'} {meta.get('max_row', 0)} 行；"
        f"新增优选池 {len(added)} 个；当前种子岗位 {len(all_jobs)} 个："
        f"高匹配 {high}、可投备选 {normal}、低意向备查 {low}；Markdown 清单未勾选 {unchecked + len(visible_added)} 个。"
    )
    marker = "## 自动化运行记录"
    if marker in text:
        text = text.rstrip() + "\n" + run_line + "\n"
    else:
        text = text.rstrip() + "\n\n" + marker + "\n\n" + run_line + "\n"
    if lines:
        insert_at = text.index(marker)
        text = text[:insert_at].rstrip() + "\n" + "\n".join(lines) + "\n\n" + text[insert_at:]
    if not dry_run:
        RECOMMENDED.write_text(text, encoding="utf-8")


def update_changelog(added_count: int, dry_run: bool) -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    line = f"- 新增本机 daily_update.py 与 launchd 定时任务配置；每日抓取岗位并自动更新/推送。"
    if line not in text:
        text = text.rstrip() + "\n" + line + "\n"
    if added_count:
        update_line = f"- {today()} 自动抓取新增 {added_count} 个岗位种子。"
        if update_line not in text:
            text = text.rstrip() + "\n" + update_line + "\n"
    if not dry_run:
        CHANGELOG.write_text(text, encoding="utf-8")


def validate_tracker() -> None:
    code = (
        "const fs=require('fs');"
        "const html=fs.readFileSync('outputs/job_tracker.html','utf8');"
        "const start=html.indexOf('<script>')+8;"
        "const js=html.slice(start, html.indexOf('</script>', start));"
        "new Function(js);"
        "console.log('job_tracker.html script parse OK');"
    )
    result = run(["node", "-e", code], check=True)
    print(result.stdout, end="")


def git_commit_and_push(no_git: bool) -> None:
    if no_git:
        log("skip git because --no-git was set")
        return
    run(["git", "add", "outputs/job_tracker.html", "outputs/recommended_jobs.md", "CHANGELOG.md"], check=True)
    status = run(["git", "status", "--short"], check=True).stdout.strip()
    if not status:
        log("no changes to commit")
        return
    commit = run(["git", "commit", "-m", "Update daily job recommendations"], check=False)
    print(commit.stdout, end="")
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
        raise RuntimeError("git commit failed")
    push = run(["git", "push"], check=False)
    print(push.stdout, end="")
    if push.returncode != 0:
        raise RuntimeError("git push failed; check GitHub authentication")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-cache", action="store_true", help="parse cached work/current_opendoc_*.js files")
    parser.add_argument("--dry-run", action="store_true", help="do not write output files")
    parser.add_argument("--no-git", action="store_true", help="skip git add/commit/push")
    parser.add_argument("--max-auto-add", type=int, default=MAX_AUTO_ADD, help="fail safe if more than this many new jobs would be added")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    log("daily update started")
    docs, meta = fetch_opendocs(use_cache=args.use_cache)
    log(f"fetched {len(docs)} opendoc blocks; max_row={meta.get('max_row')} max_col={meta.get('max_col')}")
    tokens, urls = extract_tokens_and_urls(docs)
    log(f"extracted {len(tokens)} text tokens and {len(urls)} urls")
    previous_tokens = load_previous_tokens(today())
    incremental_tokens = new_table_tokens(tokens, previous_tokens) if previous_tokens else None
    if incremental_tokens is None:
        candidates = build_candidates(tokens, urls)
        log("no reliable previous-row anchor; parsed full table under safety threshold")
    else:
        source_date = latest_source_date(incremental_tokens)
        candidates = build_candidates(incremental_tokens, urls, source_date=source_date)
        log(f"isolated {len(incremental_tokens)} newly prepended table tokens; source_date={source_date}")
    log(f"built {len(candidates)} candidate jobs")

    html = JOB_TRACKER.read_text(encoding="utf-8")
    existing = extract_seed_jobs(html)
    original_jobs = list(existing)
    merged, added = merge_jobs(existing, candidates)
    log(f"existing={len(existing) - len(added)} added={len(added)} merged={len(merged)}")
    skip_tracker_update = False
    if len(added) > args.max_auto_add:
        review_path = WORK_DIR / "daily_candidates_review.json"
        if not args.dry_run:
            review_path.write_text(json.dumps(added, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"too many new jobs ({len(added)}); wrote {review_path} and skipped tracker update")
        else:
            log(f"too many new jobs ({len(added)}); would write {review_path} and skip tracker update")
        merged = original_jobs
        added = []
        skip_tracker_update = True

    if added and not skip_tracker_update:
        update_tracker(merged, dry_run=args.dry_run)
    else:
        log("skip tracker rewrite because there are no safe auto-additions")
    update_recommended(added, meta, merged, dry_run=args.dry_run)
    update_changelog(len(added), dry_run=args.dry_run)
    if not args.dry_run:
        validate_tracker()
        git_commit_and_push(no_git=args.no_git)
    log("daily update finished")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"ERROR: {exc}")
        raise
