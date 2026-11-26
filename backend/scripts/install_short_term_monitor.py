"""管理独立的短线扫描 cron 区块；不改变既有任务或写入凭据。"""
import re
import shlex
import subprocess
import sys
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.services.runtime_state import BACKEND_DIR,RuntimeStore,utc_now

BEGIN='# BEGIN stocks short term monitor'
END='# END stocks short term monitor'


def updated_crontab(current,backend,python):
    if current.count(BEGIN)!=current.count(END) or current.count(BEGIN)>1:raise ValueError('短线任务区块不完整')
    if any(char in str(backend)+str(python) for char in ('\n','\r','%')):raise ValueError('不支持的任务路径')
    clean=re.sub(r'(?ms)^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'(?:\n|$)','',current)
    command=f'cd {shlex.quote(str(backend))} && {shlex.quote(str(python))} scripts/scan_short_term.py'
    plans=[('31-59 9 * * 1-5','intraday'),('* 10,13,14 * * 1-5','intraday'),('0-30 11 * * 1-5','intraday'),
           ('0 15 * * 1-5','intraday'),('35 16,18,20,21 * * 1-5','close')]
    lines=[f'{plan} {command} --mode {mode} >> logs/short_term.log 2>&1' for plan,mode in plans]
    return clean.rstrip()+'\n\n'+BEGIN+'\n'+'\n'.join(lines)+'\n'+END+'\n'


def main():
    if datetime.now().astimezone().utcoffset()!=timedelta(hours=8):raise RuntimeError('服务器时区需为 UTC+08:00')
    result=subprocess.run(['crontab','-l'],capture_output=True,text=True,check=True)
    zones=re.findall(r'(?m)^CRON_TZ\s*=\s*(.+)$',result.stdout)
    if zones and zones[-1].strip().strip('\"\'') not in ('Asia/Shanghai','PRC'):raise RuntimeError('cron 时区需核对')
    revised=updated_crontab(result.stdout,BACKEND_DIR,sys.executable)
    if revised!=result.stdout:
        RuntimeStore().write('cron-before-short-term',{'content':result.stdout,'saved_at':utc_now().isoformat()})
        subprocess.run(['crontab','-'],input=revised,text=True,check=True)
    print('Short-term monitor schedule installed; existing jobs preserved')


if __name__=='__main__':main()
