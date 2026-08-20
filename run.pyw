"""사용자용 조용한 런처 — 더블클릭 실행 전용.

.pyw 확장자는 Windows에서 콘솔이 없는 pythonw.exe로 연결돼(py.exe 런처의 기본 연결) 터미널
창 없이 프로그램만 뜬다. 개발 중 `python run.py`(콘솔 필요 — 로그·에러 확인용)는 그대로 두고
이 파일만 신설했다(2026-08-20 실사용 피드백: "run 누르면 터미널도 같이 뜬다").
"""
from easycad.main import main

if __name__ == "__main__":
    main()
