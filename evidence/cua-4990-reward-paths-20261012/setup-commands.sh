python3 --version
python3 -m venv ${VENV_ROOT}
${VENV_ROOT}/bin/python -m pip install --dry-run --only-binary=:all: --index-url https://pypi.org/simple --report evidence/cua-4990-reward-paths-20261012/resolver.json pytest pytest-asyncio datasets pillow
# Resolver plan validated: each URL files.pythonhosted.org, .whl; HEAD sizes summed to 101566829 bytes.
${VENV_ROOT}/bin/python -m pip install --only-binary=:all: --index-url https://pypi.org/simple pytest==9.1.1 pytest-asyncio==1.4.0 datasets==5.1.0 pillow==12.3.0
${VENV_ROOT}/bin/python -m pip install --no-cache-dir --dry-run --only-binary=:all: --index-url https://pypi.org/simple --report evidence/cua-4990-reward-paths-20261012/resolver-extra.json python-dotenv httpx
# Supplemental resolver wheel URLs validated before install.
${VENV_ROOT}/bin/python -m pip install --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple python-dotenv httpx
${VENV_ROOT}/bin/python -m pip freeze
