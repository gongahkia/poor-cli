.PHONY: test compile smoke

test:
	python3 -m unittest discover -s tests -v

compile:
	python3 -m compileall src tests

smoke:
	@tmpdir=$$(mktemp -d); \
	mkdir -p $$tmpdir/data/notes; \
	printf '%s\n' "I think architecture clarity matters. In practice we ship in small validated steps." > $$tmpdir/data/notes/sample.md; \
	PYTHONPATH=src python3 -m seuss init --config $$tmpdir/seuss.yaml; \
	PYTHONPATH=src python3 -m seuss ingest --config $$tmpdir/seuss.yaml; \
	PYTHONPATH=src python3 -m seuss generate --config $$tmpdir/seuss.yaml --prompt "I think" --level hybrid --max-tokens 50 --save; \
	PYTHONPATH=src python3 -m seuss inspect --config $$tmpdir/seuss.yaml runs --limit 5; \
	PYTHONPATH=src python3 -m seuss eval --config $$tmpdir/seuss.yaml --suite smoke; \
	echo "Smoke workspace: $$tmpdir"
