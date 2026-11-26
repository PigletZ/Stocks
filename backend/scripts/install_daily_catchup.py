"""仅管理晚间补齐计划的标记区块，保留现有 cron；重复执行不会增加重复任务。"""
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.runtime_state import BACKEND_DIR, RuntimeStore, utc_now

BEGIN = "# BEGIN stocks daily catchup"
END = "# END stocks daily catchup"


def updated_crontab(current, backend, python):
    if current.count(BEGIN) != current.count(END) or current.count(BEGIN) > 1:
        raise RuntimeError("已有任务标记不完整，未修改 cron")
    if any(char in str(backend)+str(python) for char in ("\n", "\r", "%")):
        raise ValueError("任务路径包含不支持的 cron 字符")
    clean = re.sub(r"(?ms)^"+re.escape(BEGIN)+r"\n.*?^"+re.escape(END)+r"(?:\n|$)", "", current)
    command = (f"30 18,20,21,22,23 * * 1-5 cd {shlex.quote(str(backend))} && bash scripts/run_throttled.sh "
               f"{shlex.quote(str(python))} scripts/import_daily.py >> logs/import_daily.log 2>&1")
    return clean.rstrip()+"\n\n"+BEGIN+"\n"+command+"\n"+END+"\n"


def main():
    if datetime.now().astimezone().utcoffset() != timedelta(hours=8):
        raise RuntimeError("服务器时区不是 UTC+08:00，未修改 cron；请先核对调度时区")
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("无法读取已有 cron，未修改计划")
    zones = re.findall(r"(?m)^CRON_TZ\s*=\s*(.+)$", result.stdout)
    if zones and zones[-1].strip().strip('\"\'') not in {"Asia/Shanghai", "PRC"}:
        raise RuntimeError("当前 cron 时区需人工核对，未修改计划")
    revised = updated_crontab(result.stdout, BACKEND_DIR, sys.executable)
    if revised == result.stdout:
        print("晚间补齐计划已存在，无需修改")
        return
    RuntimeStore().write("cron-before-catchup", {"content": result.stdout, "saved_at": utc_now().isoformat()})
    subprocess.run(["crontab", "-"], input=revised, text=True, check=True)
    print("已设置北京时间工作日 18:30 / 20:30 / 21:30 / 22:30 / 23:30 补齐计划，原任务保留")


if __name__ == "__main__":
    main()
