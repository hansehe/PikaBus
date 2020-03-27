# PikaBus Development

Short intro on how to continue development.

## Dependencies:
  - `pip install twine`
  - `pip install wheel`
  - `pip install -r requirements.txt`

## Build System
The build system uses [DockerBuildManagement](https://github.com/DIPSAS/DockerBuildManagement), 
which is installed with pip:
- pip install DockerBuildManagement 

## Run Unit Tests
DockerBuildManagement is available as a cli command with `dbm`.

Open [build-management.yml](./build-management.yml) to see possible build steps.
- dbm -swarm -start
- dbm -test
- dbm -swarm -stop

## Publish New Version.
1. Configure [setup.py](./setup.py) with new version.
2. Package: `python setup.py bdist_wheel`
3. Publish: `twine upload dist/*`
4. Or with dbm:
   - pip install DockerBuildManagement 
   - dbm -build -publish 
