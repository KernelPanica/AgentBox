"""Bounded file exchange; never trust archives produced by an agent."""
import io
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

LIMIT=64*1024*1024


def safe_source(path):
    p=Path(path).absolute()
    if '..' in p.parts:raise ValueError('Родительские компоненты пути запрещены')
    if any(x.is_symlink() for x in [p,*p.parents]):raise ValueError('Симлинки в пути запрещены')
    if p in (Path('/'),Path.home()):raise ValueError('Импорт корня или домашнего каталога запрещён')
    if not p.exists():raise ValueError('Файл не найден')
    return p


def pack(path):
    p=safe_source(path);stream=io.BytesIO();total=0
    files=[p,*sorted(p.rglob('*'))] if p.is_dir() else [p]
    with tarfile.open(fileobj=stream,mode='w') as tar:
        for item in files:
            if item.is_symlink() or not (item.is_file() or item.is_dir()):raise ValueError('Разрешены только обычные файлы/каталоги')
            total+=item.stat().st_size if item.is_file() else 0
            if total>LIMIT:raise ValueError('Лимит обмена 64 MiB')
            info=tar.gettarinfo(str(item),str(item.relative_to(p.parent)))
            info.uid=info.gid=1000;info.uname=info.gname='agent';info.mode=0o700 if info.isdir() else 0o600
            if info.isfile():
                fd=os.open(item,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:tar.addfile(info,f)
            else:tar.addfile(info)
    data=stream.getvalue()
    if len(data)>LIMIT:raise ValueError('Лимит архива 64 MiB')
    return data


def unpack(data,destination):
    if len(data)>LIMIT:raise ValueError('Лимит архива 64 MiB')
    dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError(dest)
    if any(p.is_symlink() for p in dest.parents):raise ValueError('Симлинк в пути назначения')
    total=0;seen=set()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as tar:
        members=tar.getmembers()
        for m in members:
            path=PurePosixPath(m.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in m.name or not (m.isfile() or m.isdir()) or m.name in seen:
                raise ValueError('Небезопасный архив')
            seen.add(m.name);total+=m.size
            if total>LIMIT or len(seen)>10000:raise ValueError('Лимит содержимого архива')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.agentbox-export-',dir=dest.parent) as tmp:
            root=Path(tmp)/'files';root.mkdir(mode=0o700)
            for m in members:
                p=root/m.name
                if m.isdir():p.mkdir(parents=True,exist_ok=True,mode=0o700)
                else:
                    p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with p.open('xb') as out:out.write(tar.extractfile(m).read())
                    p.chmod(0o600)
            os.rename(root,dest)
