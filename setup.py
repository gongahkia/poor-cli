"""
Setup script for poor-cli
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="poor-cli",
    version="0.1.0",
    author="Your Name",
    description="AI-powered CLI tool using Gemini",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "google-generativeai>=0.3.0",
        "rich>=13.0.0",
        "PyYAML>=6.0",
        "aiofiles>=23.0.0",
        "aiohttp>=3.9.0",
    ],
    entry_points={
        "console_scripts": [
            "poor-cli=poor_cli.repl_async:main",
            "poor-cli-sync=poor_cli.repl:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
