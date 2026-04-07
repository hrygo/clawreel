.PHONY: install install-dev clean help

help:
	@echo "ClawReel Makefile"
	@echo "-----------------"
	@echo "make install      - Install clawreel normally"
	@echo "make install-dev  - Install clawreel in editable mode for dev"
	@echo "make clean        - Remove build artifacts and caches"

install:
	pip install .

install-dev:
	pip install -e .

clean:
	rm -rf build/ dist/ *.egg-info/ .eggs/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
