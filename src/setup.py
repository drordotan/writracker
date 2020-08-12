from setuptools import setup, find_packages

import writracker

setup(name='writracker',
      version=".".join([str(v) for v in writracker.version()]),
      description='Framework for pen-tracking experiments',
      url='http://www.mathinklab.com/writracker',
      author='Dror Dotan',
      author_email='dotandro@mail.tau.ac.il',
      license='GPL',
      packages=find_packages(),
      install_requires=['numpy', 'matplotlib', 'tk', 'PySimpleGUI', 'pandas', 'PyQt5', 'mutagen', 'pygame'],
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Science/Research',
          'Topic :: Scientific/Engineering',
          'Programming Language :: Python :: 3.7'
      ],
      zip_safe=False)
