# FG Link Smart Home Ecosystems — 1.6.8

FG Link uses one ecosystem layer instead of adding an unrelated control path for every vendor.

## Active routes

| Ecosystem | State | Route |
| --- | --- | --- |
| Home Assistant | Ready | Local authenticated FG Link API on TCP 18086 |
| Amazon Alexa | Ready through Home Assistant | Alexa → Home Assistant → FG Link API → MTTL-W01 |
| Google Home | Ready through Home Assistant | Google Home → Home Assistant → FG Link API → MTTL-W01 |
| Matter | Reserved | Not enabled until an actual bridge implementation passes interoperability validation |

## Security boundary

Alexa and Google Home do not receive a privileged direct path to the MTTL controller. Home Assistant talks to the same authenticated local API already used by FG Link integrations. The cloud voice endpoint remains unable to fabricate executable relay commands because device-bound command signing is still enforced.

## MTTL path remains unchanged

- Provisioning endpoint: TCP 30300
- Verified controller protocol: TCP 10086
- Local authenticated integration API: TCP 18086
- Four verified AC relay channels remain the only switchable channels on MTTL-W01.
- USB switching is not invented or exposed through voice ecosystems.

## Setup

1. In FG Link, open **Smart Home → Smart Home Ecosystems** and choose **Set up Home Assistant bridge**.
2. FG Link opens the existing **Settings → Users, Sharing & Home Assistant** section.
3. Create a Home Assistant token and note the local/private FG Link API endpoint.
4. Install the FG Machines RCK Home Assistant custom integration and enter that endpoint and token.
5. Confirm the four outlet entities work from Home Assistant before exposing them to Alexa or Google Home.
6. In Home Assistant, use the user's selected Alexa or Google Home integration to expose only the desired FG Link switch entities.

Matter is intentionally not presented as working until a real bridge is implemented and validated.
