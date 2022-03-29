from setuptools import setup

with open("README.MD", "r") as f:
    long_description = f.read()

setup(
    name="interactions-voice",
    version="1.0.0",
    description="A voice-capable client for interactions.py",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/interactions-py/voice",
    author="EdVraz",
    author_email="edvraz12@gmail.com",
    license="MIT",
    packages=["interactions.ext.voice"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "discord-py-interactions>=4.1.1",
        "pynacl>=1.5.0",
    ],
)
