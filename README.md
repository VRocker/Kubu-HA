# Kubu-HA
A home assistant component to add support for Kubu devices

# Notes
This repo is very much WIP and will be added to as new things are added. No code as of yet as it's still in progress!

## Current State
* Kubu API reverse engineered
* BLE protocol decrypted and partially reversed
* PoC C# project created and responding to both advertisements and events
* Initial Home Assistant component created and talking to the Kubu API (not yet comitted)
* Wiki page documenting stuff (https://github.com/VRocker/Kubu-HA/wiki/BLE-Protocol)

* Initial HA component: <img width="1053" height="357" alt="image" src="https://github.com/user-attachments/assets/1e0338b0-4ea6-40ad-9f5f-040bfaa63368" />

# Based on
This integration was templated from the [Integration Blueprint](https://github.com/ludeeus/integration_blueprint) repository.

# AI Disclaimer
Github Copilot has been used to help create the initial Home Assistant component template. This was done as my Python skills are lacking so it helped create a good starting point.
The 'meat' of the coding has been done by myself, along with the reversing of the protocol (that was the fun part!).
