from pathlib import Path

def path_contains(path: Path, target: Path, resolve=True):
    if resolve:
        path = path.resolve()
        target = target.resolve()
    try:
        return not str(target.relative_to(path)).startswith('..')
    except ValueError:
        return False