"""KAIROS(API 게이트웨이) 문서를 다시 받아 `docs/reference/kairos/`와 비교한다 — 문서가 자주 바뀌어서(2026-10-20 사용자).

실행: python tools/kairos_docs_fetch.py          바뀐 쪽 목록 + 줄 차이를 보여 주고 파일을 새것으로 바꾼다
      python tools/kairos_docs_fetch.py --dry    받아서 비교만(파일은 그대로)

목차는 사이트의 `llms.txt`에서 api-gateway 쪽을 모으고, 각 쪽은 `.md`로 받는다(KBS 쪽 주소 `/docs/kbs/api-gateway/...`).
"""
import difflib
import re
import sys
from pathlib import Path

import httpx

SITE = "https://docs.factchat.kr"
OUT = Path(__file__).resolve().parent.parent / "docs" / "reference" / "kairos"


def pages(client) -> list:
    idx = client.get(f"{SITE}/llms.txt").text
    found = sorted(set(re.findall(r"/docs/general/api-gateway/((?:getting-started|reference)/[a-z0-9-]+)", idx)))
    return found


def main(dry: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    changed = 0
    with httpx.Client(timeout=30, headers={"User-Agent": "easycad-docs/1.0"}) as client:
        for p in pages(client):
            r = client.get(f"{SITE}/docs/kbs/api-gateway/{p}.md")
            if r.status_code != 200:
                print(f"! {p}: HTTP {r.status_code}")
                continue
            path = OUT / (p.replace("/", "_") + ".md")
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if old == r.text:
                continue
            changed += 1
            print(f"\n=== {'새 쪽' if not old else '바뀜'}: {p}")
            if old:
                for line in difflib.unified_diff(old.splitlines(), r.text.splitlines(), lineterm="", n=0):
                    if not line.startswith(("---", "+++")):
                        print(line)
            if not dry:
                path.write_text(r.text, encoding="utf-8")
    print(f"\n바뀐 쪽 {changed}개" + (" (--dry: 파일은 그대로)" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main("--dry" in sys.argv))
