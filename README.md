# Kubu-HA
A home assistant component to add support for Kubu window and door devices.

# Notes
This repo is very much WIP and will be added to as new things are added. 

## Current State
This should be working with window and door sensors now, at least with the open/closed locked/unlocked states. The battery estimation is all over the place so this needs looking at. Tamper detection also isn't hooked up yet.

HA component: <img width="1053" height="357" alt="image" src="https://github.com/user-attachments/assets/1e0338b0-4ea6-40ad-9f5f-040bfaa63368" />

# Based on
This integration was templated from the [Integration Blueprint](https://github.com/ludeeus/integration_blueprint) repository.

# AI Disclaimer
Github Copilot has been used to help create the initial Home Assistant component template. This was done as my Python skills are lacking so it helped create a good starting point.
The 'meat' of the coding has been done by myself, along with the reversing of the protocol (that was the fun part!).
