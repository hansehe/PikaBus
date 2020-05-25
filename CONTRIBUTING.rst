============
Contributing
============

Short intro on how to continue development.

Dependencies
------------

.. code-block:: shell

  pip install twine
  pip install wheel
  pip install -r requirements.txt

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
1. Configure setup.py with new version.
2. Package: python setup.py bdist_wheel
3. Publish: twine check dist/*
4. Publish: twine upload dist/*
5. Or with dbm:

.. code-block:: shell

  dbm -build -publish 

Sphinx Documentation
--------------------
Do following commands, and locate the document on http://localhost:8100

.. code-block:: shell

  cd ./docs/
  pip install -r requirements.txt
  sphinx-autobuild -b html --host 0.0.0.0 --port 8100 ./ ./_build
