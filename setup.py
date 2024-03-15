from setuptools import setup, find_packages

setup(
    name='azathoth',
    version='0.1.0',
    description='An advanced AI framework',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Oren Montano',
    packages=find_packages(),
    install_requires=[
        # List your project's dependencies here.
        # They will be installed by pip when your project is installed.
        'requests',
        'openai',
        'boto3'
    ],
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Information Technology',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Operating System :: OS Independent'
    ],
)
