from setuptools import find_packages, setup

try:
    with open('README.rst') as fp:
        long_description = fp.read()
except IOError:
    long_description = None

setup(
    name='vitriolic',
    version='1.2.0',
    author='Gary Reynolds',
    author_email='gary@touch.asn.au',
    license='BSD',
    description=(
        'A suite of packages for the Django framework to provide integrated '
        'Content Management and Sports Administration functionality for '
        'sporting associations.'
    ),
    long_description=long_description,
    packages=find_packages(),
    install_requires=[
        'django-classy-tags~=0.7.2',
        'django-froala-editor~=2.0',
        'django-guardian~=1.4.5,!=1.4.6',
        'django-modelforms',
        'django-mptt~=0.8.6',
        'first~=2.0.1',
        'Pillow~=3.0',
        'python-dateutil~=2.5.3',
        'pytz',
        'sqlparse',
    ],
    extras_require={
        'redis': [
            'django-redis-cache>=1.5.0,<2',
        ],
        'admin': [
            'django-bootstrap3>=8.2,<9',
            'django-gravatar2>=1.4,<2',
        ],
        'content': [
            'django-json-field==0.5.8',
        ],
        'news': [
            'django-imagekit',
            'python-magic',
        ],
        'competition': [
            'django-celery>=3.1.0',
            'django-formtools>=1.0',
            'django-mathfilters',
            'touchtechnology-oembed',
            'icalendar>=3.9.0,<4',
            'numpy',
            'pygraphviz>=1.3',
            'pyparsing>=2.0.3,<3',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
