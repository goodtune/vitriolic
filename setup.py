from setuptools import find_packages, setup

try:
    with open("README.md") as fp:
        long_description = fp.read()
except IOError:
    long_description = None

setup(
    name="vitriolic",
    author="Gary Reynolds",
    author_email="gary@touch.asn.au",
    license="BSD",
    description=(
        "A suite of packages for the Django framework to provide integrated "
        "Content Management and Sports Administration functionality for "
        "sporting associations."
    ),
    long_description=long_description,
    packages=find_packages(),
    setup_requires=["setuptools_scm"],
    use_scm_version=True,
    install_requires=[
        "pillow",
        "django-classy-tags~=0.7.2",
        "django-froala-editor>=2.7.1",
        "django-guardian",
        "django-modelforms~=0.2,!=0.2.0",
        "django-mptt",
        "django>=2.2,<4",
        "first~=2.0.1",
        "namedentities",
        "psycopg2-binary",
        "python-dateutil~=2.5.3",
        "pytz",
    ],
    extras_require={
        "test": [
            "coverage",
            "coveralls[yaml]",
            "django-environ",
            "django-test-plus",
            "factory_boy",
            "freezegun",
            "mock",
        ],
        "redis": ["django-redis-cache>=1.8.0,<2",],
        "admin": ["django-bootstrap3>=8.2,<9", "django-gravatar2>=1.4,<2",],
        "content": [],
        "news": ["django-imagekit", "python-magic",],
        "competition": [
            "backports.statistics",
            "cloudinary",
            "django-celery>=3.1.0",
            "django-embed-video<1.3",
            "django-formtools>=2.1",
            "django-mathfilters",
            "djangorestframework",
            "drf-nested-routers",
            "icalendar>=3.9.0,<4",
            "pyparsing>=2.0.3,<3",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
