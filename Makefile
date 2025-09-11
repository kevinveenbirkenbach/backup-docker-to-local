.PHONY: test

test:
	python -m unittest discover -s tests/unit -p "test_*.py"

install:
	@echo ">> Installation instructions:"
	@echo "   This software can be installed with pkgmgr under the alias 'baudolo':"
	@echo "     pkgmgr install baudolo"
	@echo ""
	@echo "   📦 pkgmgr project page:"
	@echo "     https://github.com/kevinveenbirkenbach/package-manager"