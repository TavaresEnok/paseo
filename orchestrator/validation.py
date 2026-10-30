"""Opt-in proportional validation.

Legacy plans omit validation_policy and never reach these decisions.
Runner fingerprints bind the local image id/digest selected for checks and
the content hash of the mounted Node binary, plus the fixed runner
parameters. They do not store environment variables, credentials, host
paths, image tags, or file mtimes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

MODE = 'proportional_v1'
RUNNER_IMAGE = 'nexoisp-paseo-runtime:20261027'
MOUNTED_NODE = '/usr/local/bin/node'
_DIGEST = re.compile(r'^sha256:[0-9a-f]{64}$')
_IMAGE_REF = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$')
_INSPECT_FORMAT = '{{printf "%s\\n%s" .Id (json .RepoDigests)}}'


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _require_commands(commands, label):
    if not isinstance(commands, list) or not commands:
        raise ValueError(f'{label} deve ser uma lista não vazia de comandos.')
    for command in commands:
        if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
            raise ValueError('Testes devem ser listas de argumentos, sem shell implícito.')
        if any('\x00' in item for item in command):
            raise ValueError('Argumento de teste inválido.')
    return commands


def policy_from_plan(plan):
    """Return the opt-in policy, or None when the plan keeps legacy validation."""
    if not isinstance(plan, dict):
        raise ValueError('Plano inválido.')
    if 'validation_policy' not in plan or plan.get('validation_policy') is None:
        return None
    policy = plan['validation_policy']
    if not isinstance(policy, dict):
        raise ValueError('validation_policy deve ser um objeto.')
    extra = sorted(set(policy) - {'mode', 'final_tests'})
    if extra:
        raise ValueError('validation_policy contém campos não reconhecidos.')
    if policy.get('mode') != MODE:
        raise ValueError('Modo de validação inválido.')
    final_tests = _require_commands(policy.get('final_tests'), 'final_tests')
    return {'mode': MODE, 'final_tests': final_tests}


def enforce_task(task):
    if 'validation_checkpoint' in task and not isinstance(task.get('validation_checkpoint'), bool):
        raise ValueError('validation_checkpoint deve ser booleano.')


def _regular_file(path):
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _file_sha256(path):
    """Content hash of a regular file. None when the bytes cannot be read."""
    if not _regular_file(path):
        return None
    digest = hashlib.sha256()
    try:
        with Path(path).open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _normalize_digests(value):
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    found = []
    for item in value:
        if not isinstance(item, str):
            return None
        digest = item.rsplit('@', 1)[1] if '@' in item else item
        if not _DIGEST.fullmatch(digest):
            return None
        found.append(digest)
    return sorted(set(found))


def _parse_image_inspect(stdout):
    if not isinstance(stdout, str):
        return None
    lines = stdout.splitlines()
    if len(lines) != 2:
        return None
    image_id = lines[0].strip()
    if not _DIGEST.fullmatch(image_id):
        return None
    try:
        raw_digests = json.loads(lines[1])
    except json.JSONDecodeError:
        return None
    digests = _normalize_digests(raw_digests)
    if digests is None:
        return None
    return {'id': image_id, 'digests': digests}


def inspect_local_image(image, *, run=None):
    """Read-only identity of a local image. None when it cannot be confirmed.

    The helper never pulls, never contacts a registry, and never reads an
    identity from the environment. `run` exists so tests can simulate inspect
    without a Docker socket; production callers leave it unset.
    """
    if not isinstance(image, str) or not _IMAGE_REF.fullmatch(image):
        return None
    execute = run or subprocess.run
    argv = ['docker', 'image', 'inspect', '--format', _INSPECT_FORMAT, image]
    try:
        proc = execute(argv, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if getattr(proc, 'returncode', 1) != 0:
        return None
    return _parse_image_inspect(getattr(proc, 'stdout', None))


def resolve_node(cwd, default_node, *, mounted_node=MOUNTED_NODE):
    """Same node choice as the check runner. None when that binary cannot be confirmed.

    The check container bind-mounts the selected runtime at /usr/local/bin/node.
    That path is the verifiable binary when the host runtime path is not visible.
    """
    node = default_node
    try:
        major = (Path(cwd) / '.nvmrc').read_text().strip().lstrip('v').split('.')[0]
        if major.isdigit():
            candidate = Path(f'/home/enok/.local/share/node{major}/bin/node')
            if candidate.is_file():
                node = str(candidate)
    except OSError:
        pass
    if node and _regular_file(node):
        return str(node)
    if mounted_node and _regular_file(mounted_node):
        return str(mounted_node)
    return None


def runner_stamp(cwd, default_node, *, image_inspector=None, mounted_node=MOUNTED_NODE):
    """Comparable runner identity. None means the environment cannot authorize a skip.

    Identity is the selected local image id/digest and the Node binary's
    bytes. The same bytes through the mounted fallback match. A changed image
    under the same tag, or changed bytes at the same path, do not.
    `image_inspector` lets tests simulate inspect; production does not pass it
    and does not accept an identity from the environment.
    """
    node = resolve_node(cwd, default_node, mounted_node=mounted_node)
    if not node:
        return None
    node_hash = _file_sha256(node)
    if not node_hash:
        return None
    inspector = image_inspector or inspect_local_image
    try:
        image = inspector(RUNNER_IMAGE)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return None
    if not isinstance(image, dict):
        return None
    image_id = image.get('id')
    if not isinstance(image_id, str) or not _DIGEST.fullmatch(image_id):
        return None
    if 'digests' in image:
        digests = _normalize_digests(image.get('digests'))
        if digests is None:
            return None
    else:
        digests = []
    material = {
        'image_id': image_id,
        'image_digests': digests,
        'node_sha256': node_hash,
        'network': 'none',
        'user': '1000:1000',
        'read_only': True,
        'cap_drop': 'ALL',
        'pull': 'never',
    }
    fingerprint = hashlib.sha256(_encoded(material).encode()).hexdigest()
    return {'id': fingerprint, 'image': RUNNER_IMAGE}


def compact_results(results):
    """Short command/status records. Failure keeps only a relevant excerpt."""
    compact = []
    for check in results or []:
        item = {
            'command': check.get('command'),
            'exit_code': check.get('exit_code'),
            'status': 'passed' if check.get('exit_code') == 0 else 'failed',
        }
        if check.get('kind'):
            item['kind'] = check.get('kind')
        if check.get('seconds') is not None:
            item['seconds'] = check.get('seconds')
        if check.get('exit_code'):
            excerpt = (check.get('stderr') or check.get('stdout') or '')[-1500:]
            if excerpt:
                item['excerpt'] = excerpt
        compact.append(item)
    return compact


def reuse_decision(evidence, *, digest, commands, runner):
    """Reuse controller evidence only when source, commands, and runner still match."""
    if not isinstance(runner, dict) or not runner.get('id'):
        return False, 'ambiente do runner não verificável'
    if not isinstance(evidence, dict):
        return False, 'evidência ausente'
    if evidence.get('passed') is not True:
        return False, 'evidência com falha' if evidence.get('passed') is False else 'evidência ausente'
    if evidence.get('digest') != digest:
        return False, 'digest da fonte divergente'
    if evidence.get('commands') != commands:
        return False, 'comandos divergentes'
    stored = evidence.get('runner')
    if not isinstance(stored, dict) or stored.get('id') != runner.get('id'):
        return False, 'runner divergente'
    checks = evidence.get('checks')
    if not isinstance(checks, list) or len(checks) != len(commands):
        return False, 'evidência de checks ausente ou com falha'
    for item in checks:
        if not isinstance(item, dict) or item.get('exit_code') != 0:
            return False, 'evidência de checks ausente ou com falha'
    return True, 'evidência do controlador válida: fonte, comandos e runner iguais'


def proof_valid(proof, *, head, digest, commands, runner):
    if not isinstance(runner, dict) or not runner.get('id'):
        return False
    if not isinstance(proof, dict) or proof.get('passed') is not True:
        return False
    if proof.get('head') != head or proof.get('digest') != digest:
        return False
    if proof.get('commands') != commands:
        return False
    stored = proof.get('runner')
    return isinstance(stored, dict) and stored.get('id') == runner.get('id')


def integration_commands(spec, policy):
    """Essential checks for this task. A checkpoint also runs the final suite once."""
    commands = []
    seen = set()

    def add(command):
        key = _encoded(command)
        if key in seen:
            return
        seen.add(key)
        commands.append(command)

    for command in spec.get('tests') or []:
        add(command)
    if spec.get('validation_checkpoint') is True:
        for command in policy['final_tests']:
            add(command)
    return commands


def commands_cover(commands, required):
    have = {_encoded(command) for command in commands}
    return all(_encoded(command) in have for command in required)
