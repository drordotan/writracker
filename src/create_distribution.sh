#!/bin/bash

rm -rf dist writracker.egg-info build

python setup.py bdist_wheel --universal

rm -rf writracker.egg-info build

# After the distribution was tested, upload it to PyPi by writing:
# twine upload <distribution_file_name>

