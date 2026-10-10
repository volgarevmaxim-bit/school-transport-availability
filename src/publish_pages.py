"""Публикация вьюера на GitHub Pages (ветка gh-pages). Идемпотентно.

1. Пересобирает data/out/zones_viewer.html через build_viewer.py.
2. Кладёт в gh-pages: index.html (= вьюер), pt_zones.geojson, lobes_pt.geojson, .nojekyll.
3. Коммитит и пушит gh-pages (remote: school-transport-availability).
Pages включаются один раз: gh api repos/<owner>/<repo>/pages -X POST ...
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "https://github.com/volgarevmaxim-bit/school-transport-availability.git"


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(" ".join(args), "->", r.returncode)
        print(r.stderr[-500:])
        sys.exit(1)
    return r


def main():
    print("1) пересборка вьюера...")
    run([sys.executable, str(ROOT / "src" / "build_viewer.py")], cwd=ROOT)

    print("2) сборка ветки gh-pages...")
    tmp = Path(tempfile.mkdtemp(prefix="pages_"))
    run(["git", "init", "-b", "gh-pages"], cwd=tmp)
    run(["git", "remote", "add", "origin", REMOTE], cwd=tmp)
    r = run(["git", "fetch", "--depth=1", "origin", "gh-pages"], cwd=tmp, check=False)
    if r.returncode == 0:
        run(["git", "reset", "--soft", "FETCH_HEAD"], cwd=tmp)

    (tmp / "index.html").write_bytes((ROOT / "data" / "out" / "zones_viewer.html").read_bytes())
    for f in ("pt_zones.geojson", "lobes_pt.geojson", "car_zones.geojson", "lobes_car.geojson",
              "addresses.geojson", "address_zones_pt.geojson", "address_zones_car.geojson",
              "metro_lines.geojson"):
        src = ROOT / "data" / "out" / f
        if src.exists():
            (tmp / f).write_bytes(src.read_bytes())
    (tmp / ".nojekyll").write_text("", encoding="utf-8")

    run(["git", "add", "-A"], cwd=tmp)
    run(["git", "-c", "user.name=Maxim Volgarev", "-c", "user.email=Volgarevmaxim@gmail.com",
         "commit", "-m", "viewer: zones + lobes update"], cwd=tmp)
    print("3) пуш gh-pages...")
    run(["git", "push", "-f", "origin", "gh-pages"], cwd=tmp)
    print("готово: gh-pages обновлена")


if __name__ == "__main__":
    main()
