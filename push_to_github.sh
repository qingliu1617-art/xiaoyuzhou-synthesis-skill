#!/bin/bash
# ────────────────────────────────────────────────────────────
# 一键将 podcast-synthesis skill 推送到你的 GitHub
# 用法：在本脚本所在目录下运行  bash push_to_github.sh
# ────────────────────────────────────────────────────────────

set -e

# 在这里填入你的 GitHub Personal Access Token（需要 repo 权限）
# 申请地址：https://github.com/settings/tokens
GITHUB_TOKEN="${GITHUB_TOKEN:-YOUR_TOKEN_HERE}"
GITHUB_USER="qingliu1617-art"
REPO_NAME="xiaoyuzhou-synthesis-skill"
REPO_DESC="将小宇宙播客音频链接转录并综合分析，生成行业研究报告的 Claude skill"

# 1. 创建远程仓库（如果已存在会收到 422，可忽略）
echo "→ 创建 GitHub 仓库 $REPO_NAME ..."
curl -s -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"$REPO_NAME\",\"description\":\"$REPO_DESC\",\"private\":false,\"auto_init\":false}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('  仓库:', d.get('html_url', d.get('message','已存在或创建成功')))"

# 2. 初始化本地 git（若尚未初始化）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".git" ]; then
  git init
  git branch -M main
fi

# 3. 配置 remote
if git remote get-url origin &>/dev/null; then
  git remote set-url origin "https://$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"
else
  git remote add origin "https://$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"
fi

# 4. 提交所有文件
git config user.email "qingliu1617@gmail.com"
git config user.name "qing liu"

git add README.md skill/ evals.json podcast-synthesis.skill examples/
git commit -m "Initial commit: podcast-synthesis skill

- scripts/transcribe.py: 小宇宙音频链接 → 逐字稿 .txt
- skill/SKILL.md: 完整工作流（转录 + 综合分析 + 报告生成）
- evals.json: 5 个测试用例
- podcast-synthesis.skill: 可一键安装的 Claude skill 包
- examples/: 具身智能行业分析报告示例（含 4 张图表）"

# 5. 推送
echo "→ 推送到 GitHub ..."
git push -u origin main

echo ""
echo "✓ 完成！仓库地址：https://github.com/$GITHUB_USER/$REPO_NAME"
