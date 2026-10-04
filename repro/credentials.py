"""Read explicitly selected literal shell env assignments without executing shell code."""
import os
from pathlib import Path
import re
import shlex

ALLOWED={'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','LLM_API_KEY','ANTHROPIC_BASE_URL'}

def load_env_file(path, *, override=False):
    values={}
    for line in Path(path).read_text().splitlines():
        if not re.match(r'^\s*(?:export\s+)?(?:ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|LLM_API_KEY|ANTHROPIC_BASE_URL)=',line):
            continue
        try:parts=shlex.split(line,comments=True)
        except ValueError:continue
        if parts and parts[0]=='export':parts=parts[1:]
        # Only one literal assignment per line. Reject expansion and shell operators.
        if len(parts)!=1 or '=' not in parts[0]:continue
        name,value=parts[0].split('=',1)
        if name not in ALLOWED or any(c in value for c in '$`\n'):continue
        values[name]=value
    for name,value in values.items():
        if override or not os.environ.get(name):os.environ[name]=value
    return sorted(name for name in values if values[name])
