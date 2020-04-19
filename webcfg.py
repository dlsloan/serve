import helpers
import json

from helpers import path_contains
from pathlib import Path
from typing import Sequence

class WebDir:
    def __init__(self, local_dir:Path, web_dir:Path=None):
        if web_dir is None: web_dir = Path('/')
        self.local_dir = local_dir.resolve(strict=True)
        self.web_dir = web_dir

    def web_contains(self, web_path:Path):
        return path_contains(self.web_dir, web_path, resolve=False)

    def get_local_path(self, web_path:Path):
        rel_path = web_path.relative_to(self.web_dir)
        return self.local_dir / rel_path

    def local_contains(self, local_path:Path):
        return path_contains(self.local_dir, local_path)

class WebCFG:
    def __init__(self, cfg_json:Path, web_dirs:Sequence[WebDir]):
        with open(cfg_json, 'r') as f:
            self.cfg = json.load(f)
        self.web_dirs = web_dirs

    def get_mime_type(self, web_path: Path, local_path: Path):
        if web_path.suffix == '':
            if local_path.suffix == '':
                ext = []
            else:
                ext = self.index_ext(web_path)
        else:
            ext = web_path.name.split('.')[1:]
        if len(ext) == 0:
            return self.cfg['file_types']['*']
        while len(ext) > 0:
            if '.' + ext[-1] in self.cfg['file_types']:
                return self.cfg['file_types']['.' + ext[-1]]
            ext = ext[:-1]
        return self.cfg['file_types']['*']

    def find_file(self, web_path:Path):
        web_dir = self.find_web_dir(web_path)
        if web_dir is None:
            return None
        local_path = web_dir.get_local_path(web_path)
        if local_path.is_dir():
            return self.find_index(web_dir, local_path)
        elif local_path.is_file():
            return local_path if web_dir.local_contains(local_path) else None
        else:
            return self.find_aliased_file(web_dir, local_path)

    def find_web_dir(self, web_file:Path):
        found_web_dir = None
        for web_dir in self.web_dirs:
            if web_dir.web_contains(web_file):
                if found_web_dir is None or found_web_dir.web_contains(web_dir.web_path):
                    found_web_dir = web_dir
        return found_web_dir

    def find_index(self, web_dir:WebDir, local_path:Path):
        for f in local_path.iterdir():
            if f.is_file() and self.is_index(f):
                return f if web_dir.local_contains(f) else None
        return None

    def find_aliased_file(self, web_dir:WebDir, local_path:Path):
        for f in local_path.parent.iterdir():
            if f.name.startswith(local_path.name + '.'):
                return f if web_dir.local_contains(f) else None
        return None

    def is_index(self, local_path:Path):
        if 'index' not in self.cfg:
            return False
        if local_path.name in self.cfg['index']:
            return True
        # Check for aliased index
        for index in self.cfg['index']:
            if local_path.name.startswith(index + '.'):
                return True
        return False

    def index_ext(self, local_path:Path):
        if 'index' not in self.cfg:
            return []
        if local_path.name in self.cfg['index']:
            return local_path.name.split('.')[1:]
        # Check for aliased index
        for index in self.cfg['index']:
            if local_path.name.startswith(index + '.'):
                return index.split('.')[1:]
        return []
