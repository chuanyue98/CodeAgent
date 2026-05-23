#!/usr/bin/env bash
input=$(cat)
echo "$input" | grep -q 'git push' || exit 0

branch=$(git branch --show-current)
if [ -z "$branch" ] || [ "$branch" = "main" ]; then
    exit 0
fi

echo "⏳ [CI] 等待 CI 启动 (branch: $branch) ..."

run_id=""
run_url=""
for _ in 1 2 3 4 5 6; do
    run_json=$(gh run list --branch "$branch" --limit 1 --json databaseId,url,name 2>/dev/null)
    run_id=$(echo "$run_json" | grep -o '"databaseId":[0-9]*' | grep -o '[0-9]*')
    run_url=$(echo "$run_json" | grep -o '"url":"[^"]*"' | head -1 | cut -d'"' -f4)
    [ -n "$run_id" ] && break
    sleep 5
done

if [ -z "$run_id" ]; then
    echo "⚠️  [CI] 未检测到 CI 运行，请手动检查"
    exit 0
fi

echo "🔗 [CI] → $run_url"

if gh run watch "$run_id" --interval 10; then
    echo "✅ [CI] 所有检查通过！"
else
    echo "❌ [CI] 检查未通过，请查看上方详情"
fi
