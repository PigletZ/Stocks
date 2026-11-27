"""只管理游资动向 cron 区块，先备份并保留其他任务。"""
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.runtime_state import BACKEND_DIR, RuntimeStore, utc_now

BEGIN = '# BEGIN stocks hot money monitor'
END = '# END stocks hot money monitor'


def updated_crontab(current, backend, python):
    if current.count(BEGIN) != current.count(END) or current.count(BEGIN) > 1:
        raise ValueError('游资任务区块不完整')
    if any(char in str(backend)+str(python) for char in ('\n', '\r', '%')):
        raise ValueError('不支持的任务路径')
    clean = re.sub(r'(?ms)^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'(?:\n|$)', '', current)
    command = f'cd {shlex.quote(str(backend))} && {shlex.quote(str(python))} scripts/sync_hot_money.py >> logs/hot_money.log 2>&1'
    return clean.rstrip()+'\n\n'+BEGIN+'\n45 16,18,20,21,22,23 * * 1-5 '+command+'\n'+END+'\n'


def main():
    if datetime.now().astimezone().utcoffset() != timedelta(hours=8):
        raise RuntimeError('服务器时区需为 UTC+08:00')
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=True)
    zones = re.findall(r'(?m)^CRON_TZ\s*=\s*(.+)$', result.stdout)
    if zones and zones[-1].strip().strip('\"\'') not in ('Asia/Shanghai', 'PRC'):
        raise RuntimeError('cron 时区需核对')
    revised = updated_crontab(result.stdout, BACKEND_DIR, sys.executable)
    if revised != result.stdout:
        RuntimeStore().write('cron-before-hot-money', {'content': result.stdout, 'saved_at': utc_now().isoformat()})
        subprocess.run(['crontab', '-'], input=revised, text=True, check=True)
    print('Hot-money monitor schedule installed; existing jobs preserved')


if __name__ == '__main__':
    main()
