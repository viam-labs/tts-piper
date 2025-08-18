install:
	uv sync

bundle:
	tar -czf module.tar.gz *.sh dist meta.json

upload:
	viam module upload --version $(version) --platform linux/any module.tar.gz

clean:
	rm module.tar.gz && rm -rf dist/

.PHONY: build
build:
	uv build

publish: build bundle upload clean
