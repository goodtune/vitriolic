from setuptools import find_packages, setup


setup(
    name='vitriolic',
    version='1.0.0',
    author='Gary Reynolds',
    author_email='gary@touch.asn.au',
    license='BSD',
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
    extras_require={
        'admin': [
            'django-bootstrap3>=7.0,<8',
            'django-gravatar2>=1.4,<2',
        ],
        'content': [
            'django-json-field==0.5.8',
        ],
        'news': [
            'django-imagekit',
        ],
        'competition': [
            'beautifulsoup4>=4.4,<5',
            'django-celery>=3.1.0',
            'django-formtools>=1.0',
            'django-mathfilters',
            'touchtechnology-oembed',
            'icalendar>=3.9.0,<4',
            'numpy',
            'pygraphviz>=1.2,<1.3',
            'pyparsing>=2.0.3,<3',
            'requests>=2.7,<3',
        ],
    },
    zip_safe=False,
)
