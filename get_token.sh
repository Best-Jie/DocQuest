#!/usr/bin/env bash
set -euo pipefail

KEY_FILE="$HOME/.config/openai/key"
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
	  if [[ -r "$KEY_FILE" ]]; then
		      # 读取文件（确保已 chmod 600）
		          OPENAI_API_KEY="$(< "$KEY_FILE")"
			    else
				        echo "ERROR: 请设置环境变量 OPENAI_API_KEY 或创建 $KEY_FILE（chmod 600）" >&2
					    exit 1
					      fi
fi

START="${1:-2025-08-01}"
END="${2:-2025-08-15}"
URL="https://api.openai.com/v1/dashboard/billing/usage?start_date=${START}&end_date=${END}"

# 调用
curl -sS \
	  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
	    "$URL" | jq .
