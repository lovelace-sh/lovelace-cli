from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

exec(open('lovelace/__init__.py').read())

setup(
    name="lovelace",
    version=__version__,
    author="Lovelace Development Team",
    author_email="support@lovelace.sh",
    description="CLI tool for one-way sync from Cloudflare R2 to local desktop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lovelace/lovelace-cli",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Version Control",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "boto3>=1.26.0",
        "requests>=2.28.0",
        "websocket-client>=1.5.0",
        "click>=8.1.0",
        "python-dotenv>=1.0.0",
        "cryptography>=41.0.0",
        "packaging>=21.0",
    ],
    entry_points={
        "console_scripts": [
            "lovelace=lovelace.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)