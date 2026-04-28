from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="fieldforce_dz",
    version="1.0.0",
    description="FieldForce Pro DZ — Application de Vente Terrain pour ERPNext (Marché Algérien)",
    author="FieldForce DZ",
    author_email="dev@fieldforce.dz",
    license="MIT",
    url="https://github.com/fieldforce-dz/fieldforce_dz",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.10",
    entry_points={},
)
