"""Windows-safe child process logging: both subprocess streams become stdout.

PowerShell 5.1 ErrorActionPreference=Stop otherwise can terminate on the
very first Python stderr traceback line before the actual exception appears.
"""
from __future__ import annotations
import argparse,sys,subprocess,os,time,traceback
from pathlib import Path


def run(command,logfile,cwd=None,env=None,echo=True):
    if not command:raise ValueError('Missing child command')
    log=Path(logfile);log.parent.mkdir(parents=True,exist_ok=True)
    cmd=list(command)
    if cmd and cmd[0]=='--':cmd=cmd[1:]
    if not cmd:raise ValueError('Missing command after --')
    with log.open('w',encoding='utf8',errors='replace',buffering=1) as output:
        def note(s):
            output.write(s+'\n');output.flush()
            if echo:sys.stdout.write(s+'\n');sys.stdout.flush()
        note(f'[launcher] UTC={time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}; pid={os.getpid()}; child={cmd!r}')
        try:
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True,encoding='utf-8',errors='replace',bufsize=1,
                                   cwd=cwd,env=env)
            try:
                for line in child.stdout:
                    output.write(line)
                    if echo:sys.stdout.write(line);sys.stdout.flush()
            except KeyboardInterrupt:
                note('[launcher] INTERRUPT: terminating child; completed shards are untouched')
                child.terminate();child.wait(timeout=30)
                raise
            code=child.wait()
            note(f'[launcher] CHILD_EXIT_CODE={code}; complete log={log}')
            return code
        except Exception as e:
            note('[launcher] FAILED: '+repr(e))
            note(traceback.format_exc())
            return 130 if isinstance(e,KeyboardInterrupt) else 1


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--log',required=True)
    p.add_argument('--cwd',default=None)
    p.add_argument('command',nargs=argparse.REMAINDER)
    args=p.parse_args()
    sys.exit(run(args.command,args.log,args.cwd))

if __name__=='__main__':main()
