from setuptools import find_packages, setup

try:
    with open('README.md') as fp:
        long_description = fp.read()
except IOError:
    long_description = None

setup(
    name='vitriolic',
    version='1.14.0',
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
        'pillow',
        'django-classy-tags~=0.7.2',
        'django-froala-editor>=2.7.1',
        'django-guardian<2',
        'django-modelforms~=0.2,!=0.2.0',
        'django-mptt>=0.9,<0.10',
        'django>=1.11,<2.1',
        'first~=2.0.1',
        'namedentities',
        'psycopg2-binary',
        'python-dateutil~=2.5.3',
        'pytz',
    ],
    extras_require={
        'test': [
            'coverage',
            'coveralls[yaml]',
            'django-environ',
            'django-test-plus>=1.0.15,<1.0.22',
            'factory_boy',
            'freezegun',
            'mock',
        ],
        'redis': [
            'django-redis-cache>=1.8.0,<2',
        ],
        'admin': [
            'django-bootstrap3>=8.2,<9',
            'django-gravatar2>=1.4,<2',
        ],
        'content': [
        ],
        'news': [
            'django-imagekit',
            'python-magic',
        ],
        'competition': [
            'cloudinary',
            'django-celery>=3.1.0',
            'django-embed-video',
            'django-formtools>=2.1',
            'django-mathfilters',
            'icalendar>=3.9.0,<4',
            'numpy',
            'pyparsing>=2.0.3,<3',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
