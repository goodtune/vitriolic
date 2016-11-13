from setuptools import find_packages, setup


setup(
    name='vitriolic',
    version='1.0.0',
    author='Gary Reynolds',
    author_email='gary@touch.asn.au',
    packages=find_packages(),
    install_requires=[
        'django-classy-tags~=0.7.2',
        'django-froala-editor~=2.0',
        'django-guardian~=1.4.5,!=1.4.6',
        'django-mptt~=0.8.6',
        'first~=2.0.1',
        'Pillow~=3.0',
        'python-dateutil~=2.5.3',
        'pytz',
    ],
    zip_safe=False,
)
