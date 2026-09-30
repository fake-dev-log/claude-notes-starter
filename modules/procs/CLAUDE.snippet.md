## 백그라운드 프로세스

- dev 서버·watcher 는 `run_in_background` 로 띄우고, 세션이 끝나기 전에 **띄운 것은 내가 끈다**. 끈 뒤 `ps -eo pid,ppid,etime,command | grep <이름>` 으로 부모(감시자)까지 남았는지 본다 — 포트가 비어도 감시자는 포트를 안 잡는다.
- 루프를 띄울 땐 종료 조건을 안에 넣는다(`d=$((SECONDS+180)); while [ $SECONDS -lt $d ]; …`).
- 세션 시작에 `[session_procs]` 보고가 오면: 지금 작업 것이면 그 PID 만 끄고, 아니면 건드리지 말고 알린다.
