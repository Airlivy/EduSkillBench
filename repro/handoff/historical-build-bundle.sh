#!/usr/bin/env bash
# Build an offline opencode-ai js-agents prefix bundle on the HOST (reliable
# egress, glibc x64) so containers can skip npm entirely. Output tarball is
# served from the .nodecache HTTP root on 172.17.0.1:8123.
set -e
cd /home/airlivy/EduSkillBench/.nodecache
NH=node-host
JS=js-host
rm -rf "$NH" "$JS" opencode-js-agents-1.18.11.tar.gz
mkdir -p "$NH"
tar -xJf node-v22.20.0-linux-x64.tar.xz -C "$NH" --strip-components=1 --no-same-owner
export PATH="$PWD/$NH/bin:$PATH"
echo "host node: $(node --version) npm: $(npm --version)"
# Outbound to the overseas registry.npmjs.org is intermittent from this China
# network (affects host AND containers in the same bad windows). npmmirror is
# the domestic full mirror and is reliable; metadata won't drop, so the glibc
# platform binary is resolved deterministically.
npm install -g --prefix "$PWD/$JS" opencode-ai@1.18.11 --no-audit --no-fund \
  --registry https://registry.npmmirror.com \
  --fetch-retries=6 --fetch-retry-mintimeout=2000 --fetch-retry-maxtimeout=60000
echo "install rc=$?"
# opencode-ai ships its platform binary as bin/opencode.exe — a native ELF
# (glibc loader), NOT a node script. bench's opencode-proxy launcher execs it
# directly when it has no shebang, so smoke-test it the same way.
BIN="$PWD/$JS/bin/opencode"
if [ "$(head -c2 "$BIN" 2>/dev/null)" = "#!" ]; then
  echo "bin is a script; testing via node"
  timeout 30 "$PWD/$NH/bin/node" "$BIN" --version || echo "(version rc=$? — not fatal if no tty)"
else
  echo "bin is native ($(file -b "$BIN" | cut -d, -f1-2)); testing direct exec"
  timeout 30 "$BIN" --version || echo "(version rc=$? — not fatal if no tty)"
fi
ls -la "$PWD/$JS/bin/"
tar -czf opencode-js-agents-1.18.11.tar.gz -C "$JS" .
ls -la opencode-js-agents-1.18.11.tar.gz
tar -tzf opencode-js-agents-1.18.11.tar.gz | head -20
