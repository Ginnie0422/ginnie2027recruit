# 校招岗位追踪器

本项目保存本地网页追踪器、岗位清单和简历匹配画像。

## 每日投递工作台

打开 `outputs/daily_application_workbench.html`，可使用岗位雷达、候选池、每日 5 家投递包和进度看板。社交媒体线索必须补充并确认官方招聘网址后，才会进入候选池和每日排程。

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
