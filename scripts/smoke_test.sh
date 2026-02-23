#!/usr/bin/env bash
set -e

echo "======================================"
echo "    Smoke Testing Environment..."
echo "======================================"

# 1. Health check
echo -n "Checking /debug/ping... "
RES=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/debug/ping)
if [ "$RES" -eq 200 ]; then
    echo "✅ OK"
else
    echo "❌ FAILED (Status: $RES)"
fi

# 2. UI load check
echo -n "Checking /admin loads... "
RES=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin)
if [ "$RES" -eq 200 ] || [ "$RES" -eq 307 ] || [ "$RES" -eq 302 ]; then
    echo "✅ OK"
else
    echo "❌ FAILED (Status: $RES)"
fi

echo ""
echo "Smoke tests completed!"
