.PHONY: test check

# Unit and end-to-end tests for the scanner (standard library only).
test:
	python3 -m unittest discover -s tests -v

# Run rightsize on this repository; fails on any warning.
check:
	python3 skills/rightsize/scripts/scan.py . --strict
