.PHONY: test

test:
	python -m unittest discover -s tests/unit -p "test_*.py"
