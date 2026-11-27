"""安装宽基观察独立 cron 区块；保留其他任务并备份原计划。"""
import re,shlex,subprocess,sys
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.services.runtime_state import BACKEND_DIR,RuntimeStore,utc_now

BEGIN='# BEGIN stocks broad funds monitor'
END='# END stocks broad funds monitor'


def updated_crontab(current,backend,python):
    if current.count(BEGIN)!=current.count(END) or current.count(BEGIN)>1:raise ValueError('宽基任务区块不完整')
    if any(char in str(backend)+str(python) for char in ('\n','\r','%')):raise ValueError('不支持的任务路径')
    clean=re.sub(r'(?ms)^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'(?:\n|$)','',current)
    command=f'cd {shlex.quote(str(backend))} && {shlex.quote(str(python))} scripts/sync_broad_funds.py >> logs/broad_funds.log 2>&1'
    return clean.rstrip()+'\n\n'+BEGIN+'\n5 9,10 * * * '+command+'\n55 16,20,22 * * 1-5 '+command+'\n'+END+'\n'


def main():
    if datetime.now().astimezone().utcoffset()!=timedelta(hours=8):raise RuntimeError('服务器时区需为 UTC+08:00')
    result=subprocess.run(['crontab','-l'],capture_output=True,text=True,check=True)
    zones=re.findall(r'(?m)^CRON_TZ\s*=\s*(.+)$',result.stdout)
    if zones and zones[-1].strip().strip('\"\'') not in ('Asia/Shanghai','PRC'):raise RuntimeError('cron 时区需核对')
    revised=updated_crontab(result.stdout,BACKEND_DIR,sys.executable)
    if revised!=result.stdout:
        RuntimeStore().write('cron-before-broad-funds',{'content':result.stdout,'saved_at':utc_now().isoformat()})
        subprocess.run(['crontab','-'],input=revised,text=True,check=True)
    print('Broad-fund schedule installed; existing jobs preserved')


if __name__=='__main__':main()
