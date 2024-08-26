import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ipyvuetable",
    version="0.7.7",
    author="Gabriel Robin",
    description="Table widget for Jupyter Notebook and JupyterLab",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.airbus.corp/Airbus/ipyvuetable",
    packages=setuptools.find_packages(),
    install_requires=["ipyvuetify", "polars"],
    extras_require={
        "ipyevents": ["ipyevents"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    package_data={"": ["custom.css"]},
    python_requires=">=3.8",
)
