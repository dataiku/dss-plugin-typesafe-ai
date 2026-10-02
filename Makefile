plugin_id=`cat plugin.json | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])"`
plugin_version=`cat plugin.json | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])"`
archive_file_name="dss-plugin-${plugin_id}-${plugin_version}.zip"

.DEFAULT_GOAL := plugin

plugin: dist-clean
	@echo "[START] Archiving plugin to dist/ folder..."
	@cat plugin.json | json_pp > /dev/null
	@mkdir dist
	@git archive -v -9 --format zip -o dist/${archive_file_name} HEAD
	@echo "[SUCCESS] Archiving plugin to dist/ folder: Done!"

dist-clean:
	rm -rf dist
