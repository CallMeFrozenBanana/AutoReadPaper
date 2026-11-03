import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def main():
    parser=argparse.ArgumentParser(description='AutoReadPaper 本地论文阅读库')
    parser.add_argument('command',choices=['serve','worker','run-once','init'],nargs='?',default='serve')
    parser.add_argument('--data-dir',default=os.environ.get('ARP_DATA_DIR','data'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-worker',action='store_true')
    args=parser.parse_args()
    os.environ['ARP_DATA_DIR']=str(Path(args.data_dir).resolve())
    from .store import init
    init()
    if args.command in ('worker','run-once'):
        from .worker import run
        run(once=args.command=='run-once');return
    if args.command=='init':return
    import uvicorn
    stop=threading.Event()
    children=[]
    command=[sys.executable,'-m','autoreadpaper.cli','worker','--data-dir',os.environ['ARP_DATA_DIR']]
    def shutdown(*_):
        stop.set()
        for child in children:
            if child.poll() is None:child.terminate()
    # Uvicorn restores and re-raises signals. Explicit handlers ensure workers are
    # terminated before the parent exits (default SIGTERM would skip finally).
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    if not args.no_worker:
        child=subprocess.Popen(command);children.append(child)
        time.sleep(.4)
        if child.poll() is not None:raise SystemExit('Worker 启动失败；已有 Worker 时请使用 --no-worker')
        def supervise():
            while not stop.wait(3):
                if children[-1].poll() is not None:
                    print('Worker 已退出，正在重新启动…',flush=True)
                    children.append(subprocess.Popen(command))
        threading.Thread(target=supervise,daemon=True).start()
    print(f'AutoReadPaper: http://127.0.0.1:{args.port}',flush=True)
    try:uvicorn.run('autoreadpaper.api:app',host='127.0.0.1',port=args.port)
    finally:
        shutdown()
        for child in children:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
