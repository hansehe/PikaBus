============
Contributing
============

Short intro on how to continue development.

Dependencies
------------
This project is managed with `uv <https://docs.astral.sh/uv/>`_. Install it once:

.. code-block:: shell

  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Windows
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Then create the environment. ``uv`` provisions a suitable Python itself, so no separate interpreter
install is needed:

.. code-block:: shell

  uv sync

That installs the project plus the ``test`` dependency group, exactly as pinned in ``uv.lock``.
Use ``uv sync --group dev`` for everything, including the docs and build tooling.

Run any command inside the environment with ``uv run``, which keeps it in sync automatically:

.. code-block:: shell

  uv run python -m unittest discover -p "*Test*.py"
  uv run python ./Examples/basic_example.py

Dependencies are declared in ``pyproject.toml``. Add one with ``uv add <package>`` - it updates both
``pyproject.toml`` and ``uv.lock``. There is no ``setup.py`` or ``requirements.txt``; both were
removed in 2.0. ``uv.lock`` is committed and pins the development environment. It does not constrain
anyone installing the published package.

The library itself is a normal wheel, so consumers do not need uv:

.. code-block:: shell

  pip install PikaBus   # or: uv add PikaBus

Build System
------------
The build system uses `DockerBuildManagement <https://github.com/DIPSAS/DockerBuildManagement>`_, 
which is installed with pip:

.. code-block:: shell

  pip install DockerBuildManagement 

Unit Tests
----------
DockerBuildManagement is available as a cli command with `dbm`.

Open build-management.yml to see possible build steps.

.. code-block:: shell

  dbm -swarm -start
  dbm -test
  dbm -swarm -stop

Publish Pypi Package
--------------------
Releases are normally published by CI: pushing a ``v*`` tag runs the publish job in
``.github/workflows/ci.yml``, which uses PyPi Trusted Publishing and needs no token.

To build by hand:

1. Bump ``version`` under ``[project]`` in ``pyproject.toml``.
2. Package: ``uv build``
3. Check: ``uv run --no-project --with twine twine check dist/*``
4. Publish: ``uv publish``
5. Or with dbm:

.. code-block:: shell

  dbm -build -publish

6. Or directly with docker, needing nothing installed on the host:

.. code-block:: shell

  docker run -it -v $PWD/:/data -w /data ghcr.io/astral-sh/uv:python3.13-bookworm-slim bash
  # From inside container, run:
  uv build
  uv publish

.. note::
    Use ``uv build`` (or ``python -m build``), never ``python setup.py bdist_wheel``. There is no
    ``setup.py`` any more, direct ``setup.py`` invocation is deprecated, and it required
    ``setuptools`` to already be installed - which ``python:3.12+`` images do not provide, since
    Python 3.12 stopped bundling it. ``uv build`` reads ``pyproject.toml`` and provisions the build
    backend in an isolated environment.

Sphinx Documentation
--------------------
Do following commands, and locate the document on http://localhost:8100

.. code-block:: shell

  uv run --group docs sphinx-autobuild -b html --host 0.0.0.0 --port 8100 ./docs ./docs/_build

To build once instead of serving:

.. code-block:: shell

  uv run --group docs sphinx-build -b html ./docs ./docs/_build

.. note::
    ``docs/requirements.txt`` is kept for `Read the Docs <https://pikabus.readthedocs.org/>`_, which
    builds with pip rather than uv. Keep it in step with the ``docs`` dependency group in
    ``pyproject.toml``.

Or with dbm:

.. code-block:: shell

  dbm -build -run docs

