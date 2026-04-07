from setuptools import setup, find_packages

setup(
    name="clawreel",
    version="1.0.0",
    description="Agent-driven short video orchestration pipeline.",
    author="Sisyphus",
    packages=find_packages(),
    install_requires=[
        "aiohttp",
        "pyyaml",
        "python-dotenv",
        "tenacity",
        "edge-tts",
    ],
    entry_points={
        "console_scripts": [
            "clawreel = clawreel.cli:main",
        ]
    },
    python_requires=">=3.10",
)
