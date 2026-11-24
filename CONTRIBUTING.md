# Contributing

Thanks for helping. Bug reports, reports of how it went on your fire, documentation fixes and code are all welcome.

## Reporting

- **Bugs:** use the [bug report form](https://github.com/olliemaller/ha-escea-fireplace/issues/new/choose). Attach diagnostics from the integration's ⋮ menu; the login, PIN and serial number are removed.
- **Worked (or didn't) on your fire:** open an issue with the model, whether it's Ethernet or Wi-Fi, and what worked. This is one of the most useful things you can do.
- **Security problems:** don't open an issue. See the [security policy](SECURITY.md).
- **Ideas:** open an issue describing what you're trying to do, before writing code, so we can agree on the approach.

## Code

### Set up

```bash
git clone https://github.com/olliemaller/ha-escea-fireplace
cd ha-escea-fireplace
python -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component pytest-cov ruff mypy
pip install aioescea==0.1.4  # the version pinned in manifest.json
pytest
ruff check custom_components tests
```

The tests run a fake fire over real UDP on 127.0.0.1, so they work on Linux and macOS.

Changes to how the integration talks to the fire usually belong in [aioescea](https://github.com/olliemaller/aioescea).

### Ground rules

This controls people's real gas fires, so a few rules are firm:

- **Never light the fire unless someone asked.** No re-sending old commands, no holding a power-on, and no write that could switch the power as a side effect.
- **Turning off is never refused.**
- **Be gentle with the fire's web page.** It handles one request at a time and stops answering if pushed. No new polling without a good reason.
- **Never log or store secrets.** The web page login and PIN stay out of logs and diagnostics.
- **No new Python requirements** unless there's no other way.
- **Test it.** Add tests against `tests/fake_fire.py` for every change in behaviour. If you can, try it on a real fire and say which model in the pull request.

### Style

- `ruff check custom_components tests` and `ruff format --check custom_components tests` pass (the rules are in `pyproject.toml`, the same as the checks).
- Support every Home Assistant version from the minimum in `hacs.json` to the current release.
- User-facing text goes in `strings.json` and `translations/en.json`, in plain, short sentences.
- Documentation is written in Australian English (*colour*, *licence*, *organise*).

### Pull requests

1. Branch from `main`.
2. Keep it to one change, and explain what and why.
3. Update the README and add a line to `CHANGELOG.md` under an `Unreleased` heading.
4. The checks (hassfest, HACS and the tests) must pass.

The maintainer handles version numbers and releases.

## Licence

Contributions are licensed under the [MIT licence](LICENSE), the same as the project.
