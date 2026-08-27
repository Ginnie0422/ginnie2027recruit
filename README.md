# 校招岗位追踪器

本项目保存本地网页追踪器、岗位清单和简历匹配画像。

## 每日投递工作台

打开 `outputs/daily_application_workbench.html`，可使用岗位雷达、候选池、每日 5 家投递包和进度看板。岗位雷达支持上传、拖拽或粘贴多张招聘图片，在浏览器内识别企业、具体岗位、地点、开启时间和截止时间；首次识别需要联网加载中英文 OCR 模型。校招启动公告没有具体岗位时会保留空白，不再拼接无关文字。已收录企业会自动匹配经过核验的官方招聘入口，其他社交媒体线索须人工确认官网后才会进入候选池和每日排程。

## 每日自动更新

本机脚本：

```bash
python3 scripts/daily_update.py
```

安装 macOS launchd 定时任务：

```bash
./scripts/install_launchd.sh
```

安装后每天 09:30 执行，脚本会读取腾讯文档、解析岗位、更新 `outputs/recommended_jobs.md` 和 `outputs/job_tracker.html`，校验网页脚本，然后执行：

```bash
git add outputs/job_tracker.html outputs/recommended_jobs.md CHANGELOG.md
git commit -m "Update daily job recommendations"
git push
```

日志位置：

```text
logs/daily_update.out.log
logs/daily_update.err.log
```

本地试跑但不写文件：

```bash
python3 scripts/daily_update.py --use-cache --dry-run --no-git
```

如果一次识别的新岗位超过安全阈值，脚本会把候选写到 `work/daily_candidates_review.json`，并跳过网页更新，避免批量误写。
