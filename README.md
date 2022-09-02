# Hacker Pride 2022 Badge

## Description

Board takes the form of a raised hand (purple) holding a brick (pink). The brick has a pride flag down the side of it and the text "QUEER HACKER PRIDE" in exposed copper. Two HPDL-1414 alphanumeric bubble displays show the user's pronouns on the wrist. 

Badge is powered by alkaline batteries. 

## Objectives
* Low-cost 
* No lithium batteries 
* NO RF (WIFI, BTLE, etc) - fun for cons, but these have the potential to be worn at protests 
* Micropython
* Excuse to buy a laser cutter ;)

## Ports
* USB type-c (native)
* 1x SAO v0.69bis 
* SWD
* UART

## Operation
* Up/Down - Cycle Pronouns
* Left/Right - Cycle Flags

## PSU 

#### Components
* Battery: 2xAA (Serial) _Note: There's room on the board to move up to 3xAA if necessary_
* Boost Converter Control Logic: SN74AHC1G04
* Boost Converter: LN2266PB2MR (5v @ 600mA)
* 3v3 Regulator: PJ9193M33E (3.3v @ 300mA) 

#### Operation
The SN74AHC1G04 is a NOT gate tied to the Enable pin of the boost converter. When voltage is detected on the USB port, it pulls Enable low, disabling the boost converter. This takes the batteries out of circuit and forces the badge to rely on VUSB as the sole 5v source. 

Operation of the PJ9193 is unaffected. 

This setup allows for rougly 300mA on each of the 5v and 3v3 rails, which should be more than sufficient for our needs. 

The HPDL-1414s are safe up to roughly 6v, and they're the only thing on the 5v rail, so a 5v regulator shouldn't be required for operation on usb. 

> The PSU /should/ be safe if you forget to turn off battery power before plugging in USB, but this behavior is not recommended

## MCU

* RP2040 (Cortex M0+)
* 32Mbit QSPI flash

## Pronoun Displays
Note: displays require 5v VCC @ ~200mA peak

* 74xC595 shift register
* 2x HPDL-1414 alphanumeric LED modules
* Data sourced from pronoun.is

## Lightshow (illuminated pride flag)

* 12x side-view LEDs (rgb, common anode)
* 2x IS31FL3238 18-channel LED drivers
* Cast resin light guide (with glitter!)

## Stackup

Note: All PCBs use ENIG finish
> ------[Brick Board (2L, art only)]--------- <- Pink SM, black SS
> ------[SMD threaded inserts (#4-40)]---------
> ------[Logic Board (4L)]------------------ <- Matte Black SM, white SS
> ------[Battery Box (2xAA, side-by-side)]--

## Configuration

Config files for pronouns and flag animations are stored as JSON within the /data directory of the badge's onboard filesystem. Hacking is encouraged. :)

### Pronouns
Pronouns are stored as a simple list. New options can be added without any issue. 

> NOTE: Pronoun strings are limited to 4 characters. The HPDL-1414 drivers do not (currently?) support scrolling

### Flags
#### Colors
TODO
