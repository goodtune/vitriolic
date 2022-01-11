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
        "django-classy-tags<0.9",
        "django-froala-editor",
        "django-guardian",
        "django-modelforms",
        "django-mptt",
        "django>=2.2,<4.1,!=3.0.*,!=3.1.*",
        "first",
        "namedentities",
        "pillow",
        "psycopg2-binary",
        "python-dateutil",
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
        "redis": ["django-redis-cache", "redis"],
        "admin": ["django-bootstrap3", "django-gravatar2"],
        "content": [],
        "news": ["django-imagekit", "python-magic"],
        "competition": [
            "celery",
            "cloudinary",
            "django-embed-video",
            "django-formtools",
            "django-mathfilters",
            "djangorestframework>=3.11",
            "drf-nested-routers",
            "icalendar",
            "pyparsing",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
