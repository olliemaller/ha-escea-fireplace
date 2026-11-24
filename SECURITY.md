# Security policy

This integration controls a gas fireplace, so security problems matter more than usual. Thank you for reporting them carefully.

## Reporting a vulnerability

**Please don't open a public issue, discussion or pull request.**

Report it privately through GitHub: go to the [Security tab](https://github.com/olliemaller/ha-escea-fireplace/security) and select **Report a vulnerability**. Only the maintainer can see the report.

Include as much of this as you can:

- what someone could do (for example light the fire, stop it being turned off, change its timers, or read its web page login);
- how to reproduce it, and what access they'd need (local network, a Home Assistant user, a dashboard, an automation);
- the integration version, Home Assistant version, and whether the fire is Ethernet (Generation 2) or Wi-Fi (Generation 3);
- diagnostics or logs, with your own passwords, PINs, serial numbers and addresses removed.

## What happens next

- You'll get a reply within **7 days**.
- Once it's confirmed, a fix is aimed for within **30 days**, sooner for anything that can light the fire without being asked.
- A fixed release goes out with a GitHub security advisory. You'll be credited unless you'd rather not be.

Please give a reasonable time for a fix to be released before telling anyone else.

## Supported versions

Only the **latest release** gets security fixes. Update through the Marketplace or HACS.

## In scope

- Anything that lights the fire, or turns it on, without someone asking for it (including a timer save or a held command).
- Anything that stops the fire being turned off.
- The web page login, PIN or serial number being stored, logged or exposed (including in diagnostics).
- The integration making the fire's controller unstable (for example by flooding its web page).

## Out of scope

- Weaknesses in the fire's controller, its firmware, its web page or the Escea app. Report those to Escea.
- Home Assistant itself. See [Home Assistant's security policy](https://www.home-assistant.io/security/).
- Someone who already has administrator access to your Home Assistant.

## Keeping your own system safe

- Keep the fire's web page and ports off the internet. Use a VPN to reach Home Assistant remotely.
- Think before you automate lighting the fire, and follow Escea's safety instructions.
