# Contributing

Thanks for helping improve **solmate2mqtt**! It's a small project, so the
process is light.

## Reporting bugs

Open an issue and include:

- What you expected vs. what happened.
- Relevant logs — run with `LOG_LEVEL=DEBUG` in your `.env` and paste the
  output (**redact your serial number and password**).
- Your `solmate-sdk` / `paho-mqtt` versions if you changed them, and your
  Home Assistant version.

The most useful thing for SDK-related issues is the **raw `live_values`
payload** that `LOG_LEVEL=DEBUG` prints.

## Adding or fixing sensors

The SolMate live-values payload may expose more fields than the five mapped
here. To surface one, add a tuple to the `SENSORS` list in
[`bridge/bridge.py`](bridge/bridge.py):

```python
("sdk_key", "Friendly Name", "unit", "device_class", "mdi:icon"),
```

`device_class` and `unit` should be valid Home Assistant values so the entity
behaves correctly. Please mention which SolMate model/firmware you tested on.

## Pull requests

- Keep it focused — one logical change per PR.
- Match the existing style; no new dependencies unless necessary.
- Test against a real SolMate + broker if you can, and say so in the PR.
- Don't commit secrets. `.env`, `mosquitto/mosquitto.conf`, and broker data
  are gitignored — keep it that way.

## Security

Please don't file public issues for anything sensitive. If in doubt, note in
the issue that you'd prefer a private channel and we'll arrange one.
