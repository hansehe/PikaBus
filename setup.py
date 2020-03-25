from setuptools import setup, find_packages
from codecs import open
import os

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

with open('requirements.txt') as f:
    reqLines = f.readlines()
REQUIREMENTS = [reqLine.replace('\r', '').replace('\n', '') for reqLine in reqLines]
VERSION = '1.0.13'

PACKAGE_NAME = 'PikaBus'
setup(
    name=PACKAGE_NAME,  # Required
    version=VERSION,  # Required
    description='Pika bus wrapper with amqp',  # Required
    long_description=long_description,  # Optional
    long_description_content_type='text/markdown',  # Optional
    url='https://github.com/hansehe/PikaBus',  # Optional
    author='Hans Erik Heggem',  # Optional
    author_email='hans.erik.heggem@gmail.com',  # Optional
    include_package_data=True,
    classifiers=[  # Optional
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Topic :: Communications', 'Topic :: Internet',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Networking',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],

    keywords='pika bus',  # Optional
    packages=find_packages(exclude=['contrib', 'docs', '*tests']),  # Required
    install_requires=REQUIREMENTS,  # Optional

    extras_require={  # Optional
        'dev': ['check-manifest'],
        'test': ['coverage'],
    },
)
