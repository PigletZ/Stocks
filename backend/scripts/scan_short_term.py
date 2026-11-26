import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.services.short_term_monitor import run

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['auto','intraday','close'],default='auto')
    parser.add_argument('--history-days',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.history_days<=20:parser.error('history-days must be 1..20')
    run(args.mode,args.history_days)
