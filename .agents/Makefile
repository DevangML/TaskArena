run:
	bash .agents/tools/menu.sh

workers:
	seq 1 $${N:-4} | xargs -I{} -n1 -P$${N:-4} python3 .agents/tools/worker.py

router:
	python3 .agents/tools/router.py

judge:
	python3 .agents/tools/judge.py
