"""Standing user authorization for unattended, isolated development.

The container is the filesystem boundary. This policy prevents known host,
deployment and billing operations; it is not a shell security sandbox.
"""
import re
from . import core

def enabled(cwd):
    if core.autonomy_policy().get('unattended_development') is not True:return False
    if core.autonomy_policy().get('unrestricted_tools') is True:return True
    try:core.dev_path(cwd)
    except (ValueError,TypeError):return False
    return True

def shell_decision(command,cwd):
    if core.autonomy_policy().get('unrestricted_tools') is True:
        return 'allow' if isinstance(command,str) and command.strip() and '\x00' not in command else 'deny'
    if not enabled(cwd):return 'ask'
    if not isinstance(command,str) or not command.strip():return 'deny'
    # These effects are outside the standing development authorization. Deny
    # instead of leaving a human permission dialog pending overnight.
    forbidden=[
        r'(?<![\w./-])(?:sudo|su|docker|podman|systemctl|service|kubectl|helm|terraform|ssh|scp|rsync)(?=\s|$)',
        r'\bgit\s+(?:push|reset|clean)\b',
        r'\bgit\s+(?:merge|checkout|switch)\s+(?:[^;&|\n]*\s)?(?:main|master|production|prod)(?=\s|$)',
        r'\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:publish|deploy)\b',
        r'(?<![\w./-])(?:vercel|wrangler|flyctl|mkfs|shred|dd)(?=\s|$)',
        r'(?<![\w./-])(?:rm|rmdir|unlink)(?=\s|$)',
        r'\b(?:drop\s+(?:database|table)|truncate\s+(?:table\s+)?\w+)\b',
        r'\b(?:curl|wget)\b',
        r'/home/enok/Documentos/projetos/(?!paseo-orchestrator(?:/|\b))',
        r'/home/enok/(?:\.ssh|\.codex|\.claude)(?:/|\b)',
        r'/home/enok/srv_projetos/(?:config|orchestration|local-credential)(?:/|\b)',
    ]
    if any(re.search(pattern,command,re.I) for pattern in forbidden):return 'deny'
    return 'allow'
