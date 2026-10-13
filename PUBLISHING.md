# Publishing to PyPI

The package name is `nirmitee-control`. Build and publish from a clean checkout.

```bash
python3 -m pip install --upgrade build twine
python3 -m build                      # builds sdist + wheel into dist/
python3 -m twine check dist/*         # validate metadata
python3 -m twine upload dist/*        # needs a PyPI API token
```

The upload step needs a PyPI account token (set `TWINE_USERNAME=__token__` and
`TWINE_PASSWORD=<pypi-token>`), so it is done by a maintainer, not in CI by
default. Test first on TestPyPI with `twine upload --repository testpypi dist/*`.

Install after publishing:

```bash
pip install nirmitee-control            # core + browser + API + MCP, all platforms
pip install nirmitee-control[windows]   # adds the Windows desktop adapter
```
