import pkg_resources
from setuptools import setup

pkg_resources.require("setuptools>=40")

if __name__ == "__main__":
    setup(
        setup_requires=["setuptools_scm"], use_scm_version=True, package_dir={"": "src"}
    )
